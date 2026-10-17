"""gl posting engine

Phase 4 (FSD v0.1 §13: "business code records events; a posting engine turns
each event into balanced journal lines using configurable posting rules").

  * gl_posting_rules / gl_posting_rule_lines: versioned, insert-only rules
    (event type -> account, debit or credit, amount field, client-account
    reference). New versions through the gl.posting_rule.change change
    request; lines can't be added to a version once a journal has used it.
  * gl_events: one row per posted business event, unique on its source key
    (event type, source type, source id, occurrence); insert-only.
  * journal_entries.posting_rule_id: the version each journal was built from.

Version 1 of the investor rules in 03 §4.1 / FSD §13.1 is seeded as a working
assumption (bank = 1101 until company bank accounts are mapped, Q-F4). The
investor services don't post yet: dual-write is the next phase 4 step.

Revision ID: f3a3b4c5d6e7
Revises: f2a2b3c4d5e6
Create Date: 2026-10-17 22:00:00.000000

"""
import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'f3a3b4c5d6e7'
down_revision = 'f2a2b3c4d5e6'
branch_labels = None
depends_on = None

SEED_DATE = '2026-01-01'
# event type, description, [(side, account code, amount field, account ref)]
RULES = [
    ('INV_DEPOSIT_POSTED', 'Investor deposit received',
     [('debit', '1101', 'amount', None), ('credit', '2100', 'amount', 'investment_account')]),
    ('INV_WITHDRAWAL_APPROVED', 'Investor withdrawal paid out',
     [('debit', '2100', 'amount', 'investment_account'), ('credit', '1101', 'amount', None)]),
    ('INV_INTEREST_APPROVED', 'Investor interest approved for the month',
     [('debit', '5100', 'gross', None), ('credit', '2110', 'gross', 'investment_account'),
      ('debit', '2110', 'tax', 'investment_account'), ('credit', '2120', 'tax', None)]),
    ('INV_INTEREST_PAID', 'Investor interest paid',
     [('debit', '2110', 'net', 'investment_account'), ('credit', '1101', 'net', None)]),
]
PERMISSIONS = [
    ('gl.posting_rule.edit', 'Request a new version of a posting rule', ('admin', 'super_admin')),
    ('gl.posting_rule.approve', 'Approve a new version of a posting rule (checker)', ('admin', 'super_admin')),
]
POLICIES = [
    ('gl.posting_rule.change', [{'permission': 'gl.posting_rule.approve', 'count': 1}],
     'A second person approves a new version of a posting rule (FSD §13).'),
]

TRIGGERS = r"""
CREATE FUNCTION gl_insert_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION '% rows are never changed or deleted; add a new version instead.', TG_TABLE_NAME
        USING ERRCODE = 'insufficient_privilege';
END
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_gl_posting_rules_insert_only BEFORE UPDATE OR DELETE ON gl_posting_rules
    FOR EACH ROW EXECUTE FUNCTION gl_insert_only();
CREATE TRIGGER trg_gl_posting_rule_lines_insert_only BEFORE UPDATE OR DELETE ON gl_posting_rule_lines
    FOR EACH ROW EXECUTE FUNCTION gl_insert_only();
CREATE TRIGGER trg_gl_events_insert_only BEFORE UPDATE OR DELETE ON gl_events
    FOR EACH ROW EXECUTE FUNCTION gl_insert_only();

CREATE FUNCTION gl_posting_rule_line_before_insert() RETURNS trigger AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM journal_entries WHERE posting_rule_id = NEW.rule_id) THEN
        RAISE EXCEPTION 'Posting rule % has been used; add a new version instead of changing its lines.',
            NEW.rule_id USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_gl_posting_rule_lines_before_insert BEFORE INSERT ON gl_posting_rule_lines
    FOR EACH ROW EXECUTE FUNCTION gl_posting_rule_line_before_insert();
"""


def _stamps():
    return [sa.Column('date_created', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('date_updated', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False)]


def upgrade():
    op.create_table(
        'gl_posting_rules',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('event_type', sa.String(60), nullable=False),
        sa.Column('version_no', sa.Integer(), nullable=False),
        sa.Column('effective_from', sa.Date(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('source', sa.String(20), nullable=False),
        sa.Column('change_request_id', sa.Integer(), sa.ForeignKey('change_requests.id', ondelete='RESTRICT'),
                  nullable=True),
        sa.Column('created_by', sa.String(120), nullable=False),
        sa.Column('approved_by', sa.String(120), nullable=False),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=False),
        *_stamps(),
        sa.UniqueConstraint('event_type', 'version_no', name='uq_gl_posting_rules_version'),
        sa.UniqueConstraint('event_type', 'effective_from', name='uq_gl_posting_rules_effective'),
        sa.CheckConstraint("event_type ~ '^[A-Z][A-Z0-9_]{2,59}$'", name='ck_gl_posting_rules_event_type'),
        sa.CheckConstraint("source IN ('working_assumption', 'client_confirmed', 'internal_decision')",
                           name='ck_gl_posting_rules_source'),
        sa.CheckConstraint('lower(approved_by) <> lower(created_by)', name='ck_gl_posting_rules_maker_not_checker'),
    )
    op.create_index('ix_gl_posting_rules_event_type', 'gl_posting_rules', ['event_type'])
    op.create_table(
        'gl_posting_rule_lines',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('rule_id', sa.Integer(), sa.ForeignKey('gl_posting_rules.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('line_no', sa.Integer(), nullable=False),
        sa.Column('side', sa.String(6), nullable=False),
        sa.Column('gl_account_id', sa.Integer(), sa.ForeignKey('gl_accounts.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('amount_field', sa.String(40), nullable=False),
        sa.Column('account_ref', sa.String(40), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        *_stamps(),
        sa.UniqueConstraint('rule_id', 'line_no', name='uq_gl_posting_rule_lines_line'),
        sa.CheckConstraint("side IN ('debit', 'credit')", name='ck_gl_posting_rule_lines_side'),
        sa.CheckConstraint("amount_field ~ '^[a-z][a-z0-9_]{0,39}$'", name='ck_gl_posting_rule_lines_amount_field'),
        sa.CheckConstraint("account_ref IS NULL OR account_ref ~ '^[a-z][a-z0-9_]{0,39}$'",
                           name='ck_gl_posting_rule_lines_account_ref'),
    )
    op.create_index('ix_gl_posting_rule_lines_rule_id', 'gl_posting_rule_lines', ['rule_id'])
    op.add_column('journal_entries', sa.Column(
        'posting_rule_id', sa.Integer(), sa.ForeignKey('gl_posting_rules.id', ondelete='RESTRICT'), nullable=True))
    op.create_table(
        'gl_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('event_type', sa.String(60), nullable=False),
        sa.Column('source_type', sa.String(40), nullable=False),
        sa.Column('source_id', sa.String(64), nullable=False),
        sa.Column('occurrence', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('value_date', sa.Date(), nullable=False),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('amounts', postgresql.JSONB(), nullable=False),
        sa.Column('refs', postgresql.JSONB(), nullable=False),
        sa.Column('posting_rule_id', sa.Integer(), sa.ForeignKey('gl_posting_rules.id', ondelete='RESTRICT'),
                  nullable=False),
        sa.Column('journal_entry_id', sa.Integer(), sa.ForeignKey('journal_entries.id', ondelete='RESTRICT'),
                  nullable=False, unique=True),
        sa.Column('created_by', sa.String(120), nullable=False),
        *_stamps(),
        sa.UniqueConstraint('event_type', 'source_type', 'source_id', 'occurrence', name='uq_gl_events_source_key'),
        sa.CheckConstraint('occurrence >= 1', name='ck_gl_events_occurrence'),
    )
    op.execute(TRIGGERS)

    conn = op.get_bind()
    for event_type, description, lines in RULES:
        rule_id = conn.execute(sa.text(
            "INSERT INTO gl_posting_rules (event_type, version_no, effective_from, description, source, created_by,"
            " approved_by, approved_at) VALUES (:t, 1, :d, :desc, 'working_assumption', 'migration',"
            " 'docs/architecture/03-general-ledger.md', now()) RETURNING id"),
            {'t': event_type, 'd': SEED_DATE, 'desc': description}).scalar()
        for n, (side, code, field, ref) in enumerate(lines, 1):
            conn.execute(sa.text(
                "INSERT INTO gl_posting_rule_lines (rule_id, line_no, side, gl_account_id, amount_field, account_ref)"
                " VALUES (:r, :n, :s, (SELECT id FROM gl_accounts WHERE code = :c), :f, :ref)"),
                {'r': rule_id, 'n': n, 's': side, 'c': code, 'f': field, 'ref': ref})
    for code, desc, legacy in PERMISSIONS:
        conn.execute(sa.text("INSERT INTO permissions (code, module, description, sensitive) "
                             "VALUES (:c, 'ledger', :d, false)"), {'c': code, 'd': desc})
        conn.execute(sa.text("INSERT INTO role_permissions (role_id, permission_code) SELECT id, :c FROM roles "
                             "WHERE legacy_role = ANY(:l) OR code = 'finance'"), {'c': code, 'l': list(legacy)})
    for request_type, levels, desc in POLICIES:
        conn.execute(sa.text("INSERT INTO approval_policies (request_type, levels, description) "
                             "VALUES (:t, CAST(:l AS jsonb), :d)"), {'t': request_type, 'l': json.dumps(levels), 'd': desc})


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM approval_policies WHERE request_type = ANY(:t)"), {'t': [p[0] for p in POLICIES]})
    conn.execute(sa.text("DELETE FROM role_permissions WHERE permission_code = ANY(:c)"), {'c': [p[0] for p in PERMISSIONS]})
    conn.execute(sa.text("DELETE FROM permissions WHERE code = ANY(:c)"), {'c': [p[0] for p in PERMISSIONS]})
    op.drop_table('gl_events')
    op.execute('ALTER TABLE journal_entries DISABLE TRIGGER trg_journal_entries_immutable')
    op.drop_column('journal_entries', 'posting_rule_id')
    op.execute('ALTER TABLE journal_entries ENABLE TRIGGER trg_journal_entries_immutable')
    op.drop_table('gl_posting_rule_lines')
    op.drop_table('gl_posting_rules')
    op.execute('DROP FUNCTION gl_posting_rule_line_before_insert()')
    op.execute('DROP FUNCTION gl_insert_only()')
