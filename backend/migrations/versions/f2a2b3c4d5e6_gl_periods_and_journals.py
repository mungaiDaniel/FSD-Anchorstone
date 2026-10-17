"""gl periods and journals

Phase 4 (FSD v0.1 FIN-02, FIN-03; 03-general-ledger.md ADR-03-2, ADR-03-3).
Monthly accounting periods (open/closed), journal entries and lines, and the
rules the database itself enforces whoever writes:

  * balanced: >= 2 lines, debits = credits > 0, checked at COMMIT (deferred
    constraint triggers on both tables);
  * immutable: no UPDATE or DELETE on entries or lines; corrections are
    reversal entries (reversal_of unique; a reversal can't be reversed);
  * periods: nothing posted into a closed period (the period row is share-
    locked so it can't close mid-posting); no new period at or before the
    latest closed one; lines only in the entry's own transaction;
  * currency: lines carry the entry's currency (composite FK), KES only;
  * lines: active postable accounts, branch-specific accounts in their branch,
    a client account exactly on control accounts;
  * numbering: JV-<financial year>-000001, allocated by the insert trigger
    from gl_journal_sequences (row-locked until commit, so gapless);
  * accounts with postings can't change type, side, postability, control
    flag or branch.

Plus the setting gl.financial_year_end_month (12 until questionnaire G4) and
the gl.period.close / gl.period.reopen change requests.

Revision ID: f2a2b3c4d5e6
Revises: f1a1b2c3d4e5
Create Date: 2026-10-17 21:00:00.000000

"""
import json

from alembic import op
import sqlalchemy as sa


revision = 'f2a2b3c4d5e6'
down_revision = 'f1a1b2c3d4e5'
branch_labels = None
depends_on = None

SEED_DATE = '2026-01-01'
SEEDS = [
    ('gl.financial_year_end_month', 12,
     'Financial year ends 31 December until the client answers questionnaire G4 (FSD FIN-05).'),
]
PERMISSIONS = [
    ('gl.period.close', 'Request closing a GL period', ('admin', 'super_admin')),
    ('gl.period.close.approve', 'Approve closing a GL period (checker)', ('admin', 'super_admin')),
    ('gl.period.reopen', 'Request reopening a closed GL period', ('admin', 'super_admin')),
    ('gl.period.reopen.approve', 'Approve reopening a closed GL period (one of two approvers)', ('super_admin',)),
]
POLICIES = [
    ('gl.period.close', [{'permission': 'gl.period.close.approve', 'count': 1}],
     'A second person approves closing a GL period (FSD FIN-03).'),
    ('gl.period.reopen', [{'permission': 'gl.period.reopen.approve', 'count': 2}],
     'Two approvers, neither of them the maker, approve reopening a closed GL period, with a reason.'),
]

TRIGGERS = r"""
-- Balanced at COMMIT ------------------------------------------------------------
CREATE FUNCTION gl_assert_entry_balanced() RETURNS trigger AS $$
DECLARE
    e_id integer := (to_jsonb(NEW) ->> TG_ARGV[0])::integer;  -- 'entry_id' on lines, 'id' on entries
    d numeric; c numeric; n integer;
BEGIN
    SELECT COALESCE(SUM(debit), 0), COALESCE(SUM(credit), 0), COUNT(*) INTO d, c, n
        FROM journal_lines WHERE entry_id = e_id;
    IF n < 2 THEN
        RAISE EXCEPTION 'Journal entry % needs at least two lines (it has %).', e_id, n
            USING ERRCODE = 'check_violation';
    END IF;
    IF d <> c OR d = 0 THEN
        RAISE EXCEPTION 'Journal entry % is unbalanced (debits %, credits %).', e_id, d, c
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NULL;
END
$$ LANGUAGE plpgsql;

CREATE CONSTRAINT TRIGGER trg_journal_lines_balanced AFTER INSERT ON journal_lines
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION gl_assert_entry_balanced('entry_id');
CREATE CONSTRAINT TRIGGER trg_journal_entries_balanced AFTER INSERT ON journal_entries
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION gl_assert_entry_balanced('id');

-- Immutable ---------------------------------------------------------------------
CREATE FUNCTION gl_journal_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Posted journals are never changed or deleted (%). Post a reversal instead.', TG_TABLE_NAME
        USING ERRCODE = 'insufficient_privilege';
END
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_journal_entries_immutable BEFORE UPDATE OR DELETE ON journal_entries
    FOR EACH ROW EXECUTE FUNCTION gl_journal_immutable();
CREATE TRIGGER trg_journal_lines_immutable BEFORE UPDATE OR DELETE ON journal_lines
    FOR EACH ROW EXECUTE FUNCTION gl_journal_immutable();

-- Entry: open period, reversal rules, journal number ---------------------------
CREATE FUNCTION gl_journal_entry_before_insert() RETURNS trigger AS $$
DECLARE
    p gl_periods%ROWTYPE;
    t journal_entries%ROWTYPE;
    n integer;
BEGIN
    SELECT * INTO p FROM gl_periods WHERE id = NEW.period_id FOR SHARE;
    IF NOT FOUND OR NEW.value_date < p.period_start OR NEW.value_date > p.period_end THEN
        RAISE EXCEPTION 'Journal entry dated % doesn''t belong to GL period %.', NEW.value_date, NEW.period_id
            USING ERRCODE = 'check_violation';
    END IF;
    IF p.status <> 'open' THEN
        RAISE EXCEPTION 'GL period % is closed; nothing can be posted into it.', to_char(p.period_start, 'YYYY-MM')
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.reversal_of IS NOT NULL THEN
        SELECT * INTO t FROM journal_entries WHERE id = NEW.reversal_of;
        IF FOUND AND t.reversal_of IS NOT NULL THEN
            RAISE EXCEPTION 'Journal entry % is itself a reversal and can''t be reversed.', t.journal_no
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    INSERT INTO gl_journal_sequences AS s (financial_year, last_value) VALUES (p.financial_year, 1)
        ON CONFLICT (financial_year) DO UPDATE SET last_value = s.last_value + 1
        RETURNING last_value INTO n;
    NEW.financial_year := p.financial_year;
    NEW.seq_no := n;
    NEW.journal_no := 'JV-' || p.financial_year || '-' || CASE WHEN n < 1000000 THEN lpad(n::text, 6, '0') ELSE n::text END;
    NEW.posted_txid := txid_current();
    NEW.status := 'posted';
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_journal_entries_before_insert BEFORE INSERT ON journal_entries
    FOR EACH ROW EXECUTE FUNCTION gl_journal_entry_before_insert();

-- Line: same transaction as its entry, usable account ---------------------------
CREATE FUNCTION gl_journal_line_before_insert() RETURNS trigger AS $$
DECLARE
    e journal_entries%ROWTYPE;
    a gl_accounts%ROWTYPE;
BEGIN
    SELECT * INTO e FROM journal_entries WHERE id = NEW.entry_id;
    IF e.posted_txid <> txid_current() THEN
        RAISE EXCEPTION 'Journal entry % is already posted; lines can''t be added to it.', e.journal_no
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    SELECT * INTO a FROM gl_accounts WHERE id = NEW.gl_account_id;
    IF NOT a.is_postable THEN
        RAISE EXCEPTION 'GL account % is a header and can''t take postings.', a.code USING ERRCODE = 'check_violation';
    END IF;
    IF NOT a.is_active THEN
        RAISE EXCEPTION 'GL account % is inactive.', a.code USING ERRCODE = 'check_violation';
    END IF;
    IF a.branch_id IS NOT NULL AND a.branch_id <> NEW.branch_id THEN
        RAISE EXCEPTION 'GL account % belongs to another branch.', a.code USING ERRCODE = 'check_violation';
    END IF;
    IF a.is_control AND NEW.account_id IS NULL THEN
        RAISE EXCEPTION 'GL account % is a control account; the line must name a client account.', a.code
            USING ERRCODE = 'check_violation';
    END IF;
    IF NOT a.is_control AND NEW.account_id IS NOT NULL THEN
        RAISE EXCEPTION 'GL account % isn''t a control account; the line can''t name a client account.', a.code
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.currency <> a.currency THEN
        RAISE EXCEPTION 'GL account % is in %, the line in %.', a.code, a.currency, NEW.currency
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_journal_lines_before_insert BEFORE INSERT ON journal_lines
    FOR EACH ROW EXECUTE FUNCTION gl_journal_line_before_insert();

-- Periods: never deleted, dates fixed, no new period behind a closed one -------
CREATE FUNCTION gl_periods_guard() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'GL periods are never deleted.' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF TG_OP = 'INSERT' THEN
        IF EXISTS (SELECT 1 FROM gl_periods WHERE status = 'closed' AND period_start > NEW.period_start) THEN
            RAISE EXCEPTION 'GL period % is before a closed period and can''t be opened.',
                to_char(NEW.period_start, 'YYYY-MM') USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END IF;
    IF NEW.period_start <> OLD.period_start OR NEW.period_end <> OLD.period_end
       OR NEW.financial_year <> OLD.financial_year OR NEW.created_by <> OLD.created_by THEN
        RAISE EXCEPTION 'A GL period''s dates and financial year never change.' USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_gl_periods_guard BEFORE INSERT OR UPDATE OR DELETE ON gl_periods
    FOR EACH ROW EXECUTE FUNCTION gl_periods_guard();

-- Accounts with postings keep their meaning ---------------------------------------
CREATE FUNCTION gl_accounts_fixed_once_used() RETURNS trigger AS $$
BEGIN
    IF (NEW.account_type, NEW.normal_side, NEW.is_postable, NEW.is_control, NEW.branch_id)
       IS DISTINCT FROM (OLD.account_type, OLD.normal_side, OLD.is_postable, OLD.is_control, OLD.branch_id)
       AND EXISTS (SELECT 1 FROM journal_lines WHERE gl_account_id = OLD.id) THEN
        RAISE EXCEPTION 'GL account % has postings; its type, side, postability, control flag and branch are fixed.',
            OLD.code USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_gl_accounts_fixed_once_used BEFORE UPDATE ON gl_accounts
    FOR EACH ROW EXECUTE FUNCTION gl_accounts_fixed_once_used();
"""


def _stamps():
    return [sa.Column('date_created', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('date_updated', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False)]


def upgrade():
    op.create_table(
        'gl_periods',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('period_start', sa.Date(), nullable=False, unique=True),
        sa.Column('period_end', sa.Date(), nullable=False),
        sa.Column('financial_year', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(6), nullable=False),
        sa.Column('closed_by', sa.String(120), nullable=True),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reopen_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_change_request_id', sa.Integer(),
                  sa.ForeignKey('change_requests.id', ondelete='RESTRICT'), nullable=True),
        sa.Column('created_by', sa.String(120), nullable=False),
        *_stamps(),
        sa.CheckConstraint("status IN ('open', 'closed')", name='ck_gl_periods_status'),
        sa.CheckConstraint("extract(day FROM period_start) = 1 AND period_end = "
                           "(period_start + interval '1 month' - interval '1 day')::date", name='ck_gl_periods_month'),
        sa.CheckConstraint("(status = 'closed') = (closed_by IS NOT NULL AND closed_at IS NOT NULL)",
                           name='ck_gl_periods_closed'),
    )
    op.create_table(
        'gl_journal_sequences',
        sa.Column('financial_year', sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column('last_value', sa.Integer(), nullable=False),
    )
    op.create_table(
        'journal_entries',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('journal_no', sa.String(24), nullable=False, unique=True),
        sa.Column('financial_year', sa.Integer(), nullable=False),
        sa.Column('seq_no', sa.Integer(), nullable=False),
        sa.Column('entry_date', sa.Date(), nullable=False),
        sa.Column('value_date', sa.Date(), nullable=False),
        sa.Column('period_id', sa.Integer(), sa.ForeignKey('gl_periods.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('currency', sa.String(3), server_default='KES', nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('event_type', sa.String(60), nullable=True),
        sa.Column('source_type', sa.String(40), nullable=True),
        sa.Column('source_id', sa.String(64), nullable=True),
        sa.Column('status', sa.String(6), server_default='posted', nullable=False),
        sa.Column('reversal_of', sa.Integer(), sa.ForeignKey('journal_entries.id', ondelete='RESTRICT'),
                  nullable=True, unique=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(120), nullable=False),
        sa.Column('approved_by', sa.String(120), nullable=True),
        sa.Column('posted_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('posted_txid', sa.BigInteger(), nullable=False),
        *_stamps(),
        sa.CheckConstraint("status = 'posted'", name='ck_journal_entries_status'),
        sa.CheckConstraint("currency = 'KES'", name='ck_journal_entries_currency_kes'),
        sa.CheckConstraint('reversal_of IS NULL OR reason IS NOT NULL', name='ck_journal_entries_reversal_reason'),
        sa.CheckConstraint('approved_by IS NULL OR lower(approved_by) <> lower(created_by)',
                           name='ck_journal_entries_maker_not_checker'),
        sa.CheckConstraint('(source_type IS NULL) = (source_id IS NULL)', name='ck_journal_entries_source'),
        sa.UniqueConstraint('id', 'currency', name='uq_journal_entries_id_currency'),
        sa.UniqueConstraint('financial_year', 'seq_no', name='uq_journal_entries_year_seq'),
    )
    op.create_index('ix_journal_entries_value_date', 'journal_entries', ['value_date'])
    op.create_index('ix_journal_entries_period_id', 'journal_entries', ['period_id'])
    op.create_index('ix_journal_entries_source', 'journal_entries', ['source_type', 'source_id'])
    op.create_table(
        'journal_lines',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('entry_id', sa.Integer(), sa.ForeignKey('journal_entries.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('line_no', sa.Integer(), nullable=False),
        sa.Column('gl_account_id', sa.Integer(), sa.ForeignKey('gl_accounts.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('debit', sa.Numeric(20, 2), nullable=False, server_default='0'),
        sa.Column('credit', sa.Numeric(20, 2), nullable=False, server_default='0'),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('accounts.id', ondelete='RESTRICT'), nullable=True),
        sa.Column('party_id', sa.Integer(), sa.ForeignKey('parties.id', ondelete='RESTRICT'), nullable=True),
        sa.Column('currency', sa.String(3), server_default='KES', nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        *_stamps(),
        sa.CheckConstraint('(debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0)', name='ck_journal_lines_one_side'),
        sa.CheckConstraint("currency = 'KES'", name='ck_journal_lines_currency_kes'),
        sa.ForeignKeyConstraint(['entry_id', 'currency'], ['journal_entries.id', 'journal_entries.currency'],
                                name='fk_journal_lines_entry_currency', ondelete='RESTRICT'),
        sa.UniqueConstraint('entry_id', 'line_no', name='uq_journal_lines_entry_line'),
    )
    op.create_index('ix_journal_lines_entry_id', 'journal_lines', ['entry_id'])
    op.create_index('ix_journal_lines_account_id', 'journal_lines', ['account_id'])
    op.create_index('ix_journal_lines_gl_account_branch', 'journal_lines', ['gl_account_id', 'branch_id'])
    op.execute(TRIGGERS)

    conn = op.get_bind()
    for code, desc, legacy in PERMISSIONS:
        conn.execute(sa.text("INSERT INTO permissions (code, module, description, sensitive) "
                             "VALUES (:c, 'ledger', :d, false)"), {'c': code, 'd': desc})
        conn.execute(sa.text("INSERT INTO role_permissions (role_id, permission_code) SELECT id, :c FROM roles "
                             "WHERE legacy_role = ANY(:l) OR code = 'finance'"), {'c': code, 'l': list(legacy)})
    for request_type, levels, desc in POLICIES:
        conn.execute(sa.text("INSERT INTO approval_policies (request_type, levels, description) "
                             "VALUES (:t, CAST(:l AS jsonb), :d)"), {'t': request_type, 'l': json.dumps(levels), 'd': desc})
    for key, value, evidence in SEEDS:
        conn.execute(sa.text(
            "INSERT INTO setting_versions (key, value, effective_from, version_no, source, evidence, created_by,"
            " approved_by, approved_at) VALUES (:k, CAST(:v AS jsonb), :d, 1, 'working_assumption', :e,"
            " 'migration', 'docs/architecture/08-working-assumptions.md', now())"),
            {'k': key, 'v': json.dumps(value), 'd': SEED_DATE, 'e': evidence})


def downgrade():
    conn = op.get_bind()
    op.execute("ALTER TABLE setting_versions DISABLE TRIGGER trg_setting_versions_insert_only")
    conn.execute(sa.text("DELETE FROM setting_versions WHERE key = ANY(:k)"), {'k': [k for k, _, _ in SEEDS]})
    op.execute("ALTER TABLE setting_versions ENABLE TRIGGER trg_setting_versions_insert_only")
    conn.execute(sa.text("DELETE FROM approval_policies WHERE request_type = ANY(:t)"), {'t': [p[0] for p in POLICIES]})
    conn.execute(sa.text("DELETE FROM role_permissions WHERE permission_code = ANY(:c)"), {'c': [p[0] for p in PERMISSIONS]})
    conn.execute(sa.text("DELETE FROM permissions WHERE code = ANY(:c)"), {'c': [p[0] for p in PERMISSIONS]})
    op.execute('DROP TRIGGER trg_gl_accounts_fixed_once_used ON gl_accounts')
    op.drop_table('journal_lines')
    op.drop_table('journal_entries')
    op.drop_table('gl_journal_sequences')
    op.drop_table('gl_periods')
    for fn in ('gl_assert_entry_balanced', 'gl_journal_immutable', 'gl_journal_entry_before_insert',
               'gl_journal_line_before_insert', 'gl_periods_guard', 'gl_accounts_fixed_once_used'):
        op.execute(f'DROP FUNCTION {fn}()')
