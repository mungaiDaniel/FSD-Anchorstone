"""parties from investors

Phase 2b item 2 (02-domain-model §6). Every investor gets a person party (its
identifiers, email and phone, payout account, investor role) and an investment
account numbered with its ACL- client code; investors.party_id and account_id
become NOT NULL and unique. Nothing an investor or staff member sees changes:
the investor columns stay and are kept in step by the service, the client-code
sequence and the one-email-per-investor index are untouched, and balances still
come from the ledger.

Refuses to run while two investors share an ID number or a KRA PIN; the error
lists them (the same check as `flask --app main kyc-preflight`).

The normalising rules below are a frozen copy of app/Parties/normalise.py and
app/Parties/preflight.py as of this migration.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-10-16 16:00:00.000000

"""
import re
from collections import defaultdict

from alembic import op
import sqlalchemy as sa


revision = 'c9d0e1f2a3b4'
down_revision = 'b8c9d0e1f2a3'
branch_labels = None
depends_on = None

_SEP = re.compile(r"[\s\-/.]+")
_NOT_ALNUM = re.compile(r"[^A-Z0-9]")
_NATIONAL_ID = re.compile(r"^\d{6,9}$")


def _norm_id(value):
    text = _SEP.sub("", (value or "").strip().upper())
    return text or None


def _norm_pin(value):
    text = _NOT_ALNUM.sub("", (value or "").strip().upper())
    return text or None


def _norm_phone(value):
    digits = re.sub(r"[\s\-().]", "", value or "")
    if not digits:
        return None
    if digits.startswith("+"):
        rest = digits[1:]
        return f"+{rest}" if rest.isdigit() and 8 <= len(rest) <= 15 else None
    if not digits.isdigit():
        return None
    if len(digits) == 10 and digits[0] == "0" and digits[1] != "0":  # mobile 07…/01…, landline 020…, 041…
        return f"+254{digits[1:]}"
    if len(digits) == 12 and digits.startswith("254") and digits[3] != "0":
        return f"+{digits}"
    if len(digits) == 9 and digits[0] in "71":
        return f"+254{digits}"
    return None


def _split_name(full_name):
    words = full_name.split()
    if len(words) == 1:
        return None, None, words[0]
    if len(words) == 2:
        return words[0], None, words[1]
    return words[0], " ".join(words[1:-1]), words[-1]


def _refuse_duplicates(rows):
    by_id, by_pin = defaultdict(list), defaultdict(list)
    for r in rows:
        if _norm_id(r.id_number):
            by_id[_norm_id(r.id_number)].append(r)
        if _norm_pin(r.kra_pin):
            by_pin[_norm_pin(r.kra_pin)].append(r)
    problems = []
    for label, groups in (("ID number", by_id), ("KRA PIN", by_pin)):
        for value, group in sorted(groups.items()):
            if len(group) > 1:
                problems.append(f"  {label} {value}: " + ", ".join(f"{r.client_code} {r.full_name}" for r in group))
    if problems:
        raise RuntimeError(
            "Can't move investors onto parties: an ID number or KRA PIN may belong to one client only. "
            "Fix these investors first (flask --app main kyc-preflight lists them):\n" + "\n".join(problems))


def upgrade():
    op.create_table(
        'accounts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('account_no', sa.String(20), nullable=False, unique=True),
        sa.Column('account_type', sa.String(12), nullable=False),
        sa.Column('party_id', sa.Integer(), sa.ForeignKey('parties.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('currency', sa.String(3), server_default='KES', nullable=False),
        sa.Column('status', sa.String(10), server_default='active', nullable=False),
        sa.Column('opened_on', sa.Date(), nullable=False),
        sa.Column('closed_on', sa.Date(), nullable=True),
        sa.Column('created_by', sa.String(120), nullable=False),
        sa.Column('date_created', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('date_updated', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("account_type IN ('investment')", name='ck_accounts_type'),
        sa.CheckConstraint("status IN ('active', 'closed')", name='ck_accounts_status'),
        sa.CheckConstraint("currency = 'KES'", name='ck_accounts_currency_kes'),
        sa.CheckConstraint("(status = 'closed') = (closed_on IS NOT NULL)", name='ck_accounts_closed_on'),
    )
    op.create_index('ix_accounts_party_id', 'accounts', ['party_id'])
    op.create_index('ix_accounts_branch_id', 'accounts', ['branch_id'])
    op.add_column('investors', sa.Column('party_id', sa.Integer(), nullable=True))
    op.add_column('investors', sa.Column('account_id', sa.Integer(), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id, client_code, full_name, email, phone, id_number, kra_pin, payout_method, bank_name, "
        "payout_account, status, branch_id, created_at, created_by, closed_at FROM investors ORDER BY id")).all()
    _refuse_duplicates(rows)

    for r in rows:
        first, middle, last = _split_name(r.full_name)
        party_id = conn.execute(sa.text(
            "INSERT INTO parties (party_no, party_type, display_name, home_branch_id, kyc_status, status, "
            "created_at, created_by) VALUES ('P-' || lpad(nextval('party_no_seq')::text, 7, '0'), 'person', :name, "
            ":branch, 'incomplete', 'active', :at, :by) RETURNING id"),
            {"name": r.full_name, "branch": r.branch_id, "at": r.created_at, "by": r.created_by}).scalar()
        conn.execute(sa.text(
            "INSERT INTO party_persons (party_id, first_name, middle_name, last_name, name_needs_review) "
            "VALUES (:p, :f, :m, :l, true)"), {"p": party_id, "f": first, "m": middle, "l": last})

        if _norm_id(r.id_number):
            kind = "national_id" if _NATIONAL_ID.match(_norm_id(r.id_number)) else "passport"
            conn.execute(sa.text(
                "INSERT INTO party_identifiers (party_id, id_type, issuing_country, value_display, value_normalised) "
                "VALUES (:p, :t, 'KE', :d, :n)"), {"p": party_id, "t": kind, "d": r.id_number, "n": _norm_id(r.id_number)})
        if _norm_pin(r.kra_pin):
            conn.execute(sa.text(
                "INSERT INTO party_identifiers (party_id, id_type, issuing_country, value_display, value_normalised) "
                "VALUES (:p, 'kra_pin', 'KE', :d, :n)"), {"p": party_id, "d": r.kra_pin, "n": _norm_pin(r.kra_pin)})

        conn.execute(sa.text(
            "INSERT INTO party_contacts (party_id, kind, value, value_normalised, is_primary) "
            "VALUES (:p, 'email', :v, :n, true)"), {"p": party_id, "v": r.email, "n": r.email.strip().lower()})
        if r.phone:
            conn.execute(sa.text(
                "INSERT INTO party_contacts (party_id, kind, value, value_normalised, is_primary) "
                "VALUES (:p, 'mobile', :v, :n, true)"), {"p": party_id, "v": r.phone, "n": _norm_phone(r.phone)})
        if r.payout_account:
            conn.execute(sa.text(
                "INSERT INTO party_bank_accounts (party_id, kind, bank_name, account_no, is_default_payout, status) "
                "VALUES (:p, :k, :b, :a, true, 'active')"),
                {"p": party_id, "k": r.payout_method or ("bank" if r.bank_name else "mpesa"), "b": r.bank_name,
                 "a": r.payout_account})

        conn.execute(sa.text(
            "INSERT INTO party_roles (party_id, role, status, started_on, branch_id) "
            "VALUES (:p, 'investor', 'active', ((:at AT TIME ZONE 'UTC') + interval '3 hours')::date, :b)"),
            {"p": party_id, "at": r.created_at, "b": r.branch_id})
        account_id = conn.execute(sa.text(
            "INSERT INTO accounts (account_no, account_type, party_id, branch_id, status, opened_on, closed_on, created_by) "
            "VALUES (:no, 'investment', :p, :b, :s, ((:at AT TIME ZONE 'UTC') + interval '3 hours')::date, "
            "CASE WHEN :s = 'closed' THEN ((COALESCE(:closed, :at) AT TIME ZONE 'UTC') + interval '3 hours')::date END, "
            ":by) RETURNING id"),
            {"no": r.client_code, "p": party_id, "b": r.branch_id, "s": r.status, "at": r.created_at,
             "closed": r.closed_at, "by": r.created_by}).scalar()
        conn.execute(sa.text("UPDATE investors SET party_id = :p, account_id = :a WHERE id = :i"),
                     {"p": party_id, "a": account_id, "i": r.id})

    op.alter_column('investors', 'party_id', nullable=False)
    op.alter_column('investors', 'account_id', nullable=False)
    op.create_unique_constraint('uq_investors_party_id', 'investors', ['party_id'])
    op.create_unique_constraint('uq_investors_account_id', 'investors', ['account_id'])
    op.create_foreign_key('fk_investors_party_id', 'investors', 'parties', ['party_id'], ['id'], ondelete='RESTRICT')
    op.create_foreign_key('fk_investors_account_id', 'investors', 'accounts', ['account_id'], ['id'], ondelete='RESTRICT')


def downgrade():
    conn = op.get_bind()
    party_ids = [r[0] for r in conn.execute(sa.text("SELECT party_id FROM investors"))]
    op.drop_constraint('fk_investors_account_id', 'investors', type_='foreignkey')
    op.drop_constraint('fk_investors_party_id', 'investors', type_='foreignkey')
    op.drop_constraint('uq_investors_account_id', 'investors', type_='unique')
    op.drop_constraint('uq_investors_party_id', 'investors', type_='unique')
    op.drop_column('investors', 'account_id')
    op.drop_column('investors', 'party_id')
    op.drop_table('accounts')
    if party_ids:
        # The investors' parties go too (parties are otherwise never deleted).
        for table in ('party_roles', 'party_bank_accounts', 'party_contacts', 'party_identifiers', 'party_persons'):
            conn.execute(sa.text(f"DELETE FROM {table} WHERE party_id = ANY(:p)"), {"p": party_ids})
        op.execute("ALTER TABLE parties DISABLE TRIGGER trg_parties_no_delete")
        conn.execute(sa.text("DELETE FROM parties WHERE id = ANY(:p)"), {"p": party_ids})
        op.execute("ALTER TABLE parties ENABLE TRIGGER trg_parties_no_delete")
