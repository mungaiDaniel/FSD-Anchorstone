"""gl chart of accounts

Phase 4 (FSD v0.1 FIN-01; 03-general-ledger.md §2). The chart of accounts,
seeded with the skeleton in 03 §2 as a working assumption (WA-13, our
questionnaire F1) until the accountant's list replaces it. It holds every
account named in the FSD §13.1 posting rules, plus deferred fee income (2810)
for the "or deferred fees" option.

Accounts are never deleted (trigger); journals will reference the id, so codes
can change. Changes are the gl.account.create / gl.account.change change
requests, one approver with gl.chart.approve.

Revision ID: f1a1b2c3d4e5
Revises: d6e7f8a9b0c1
Create Date: 2026-10-17 20:00:00.000000

"""
import json

from alembic import op
import sqlalchemy as sa


revision = 'f1a1b2c3d4e5'
down_revision = 'd6e7f8a9b0c1'
branch_labels = None
depends_on = None

WA = 'Skeleton chart (03-general-ledger.md §2, WA-13); replaced by the accountant\'s list (questionnaire F1).'

# code, name, type, normal side, parent code, postable, control, manual postings allowed, active
CHART = [
    ('1000', 'Assets', 'asset', 'debit', None, False, False, False, True),
    ('1100', 'Bank accounts', 'asset', 'debit', '1000', False, False, False, True),
    ('1101', 'Bank - main operating account', 'asset', 'debit', '1100', True, False, True, True),
    ('1110', 'M-Pesa paybill float (clearing)', 'asset', 'debit', '1000', True, False, True, True),
    ('1120', 'Cheques in clearing', 'asset', 'debit', '1000', True, False, True, True),
    ('1130', 'Cash on hand', 'asset', 'debit', '1000', True, False, True, True),
    ('1200', 'Loans receivable - control', 'asset', 'debit', '1000', True, True, False, True),
    ('1210', 'Interest receivable - control', 'asset', 'debit', '1000', True, True, False, True),
    ('1211', 'Interest in suspense', 'asset', 'credit', '1000', True, False, False, True),
    ('1220', 'Penalty receivable - control', 'asset', 'debit', '1000', True, True, False, True),
    ('1221', 'Penalty in suspense', 'asset', 'credit', '1000', True, False, False, True),
    ('1230', 'Fees and charges receivable - control', 'asset', 'debit', '1000', True, True, False, True),
    ('1290', 'Loan loss provision (allowance for impairment)', 'asset', 'credit', '1000', True, False, True, True),
    ('1300', 'Inter-branch - due from', 'asset', 'debit', '1000', True, False, False, True),
    ('1400', 'Prepayments', 'asset', 'debit', '1000', True, False, True, True),
    ('1500', 'Fixed assets at cost', 'asset', 'debit', '1000', True, False, True, True),
    ('1510', 'Accumulated depreciation', 'asset', 'credit', '1000', True, False, True, True),
    ('1600', 'Treasury bills and bonds', 'asset', 'debit', '1000', True, False, True, True),
    ('2000', 'Liabilities', 'liability', 'credit', None, False, False, False, True),
    ('2100', 'Investor deposits - control', 'liability', 'credit', '2000', True, True, False, True),
    ('2110', 'Interest payable to investors - control', 'liability', 'credit', '2000', True, True, False, True),
    ('2120', 'Withholding tax payable - investor interest', 'liability', 'credit', '2000', True, False, True, True),
    ('2200', 'Member collection accounts - control', 'liability', 'credit', '2000', True, True, False, True),
    ('2210', 'Unallocated receipts (suspense)', 'liability', 'credit', '2000', True, False, True, True),
    ('2300', 'Pass-through payables', 'liability', 'credit', '2000', True, False, True, True),
    ('2400', 'Borrowings', 'liability', 'credit', '2000', True, False, True, True),
    ('2410', 'Interest payable on borrowings', 'liability', 'credit', '2000', True, False, True, True),
    ('2420', 'Withholding tax payable - borrowing interest', 'liability', 'credit', '2000', True, False, True, True),
    ('2500', 'Trade-finance cash margins - control', 'liability', 'credit', '2000', True, True, False, True),
    ('2600', 'Inter-branch - due to', 'liability', 'credit', '2000', True, False, False, True),
    ('2700', 'Commissions payable', 'liability', 'credit', '2000', True, False, True, True),
    ('2710', 'Withholding tax payable - commissions', 'liability', 'credit', '2000', True, False, True, True),
    ('2800', 'Other payables and accruals', 'liability', 'credit', '2000', True, False, True, True),
    ('2810', 'Deferred fee income', 'liability', 'credit', '2000', True, False, True, True),
    ('3000', 'Equity', 'equity', 'credit', None, False, False, False, True),
    ('3100', 'Share capital', 'equity', 'credit', '3000', True, False, True, True),
    ('3200', 'Retained earnings', 'equity', 'credit', '3000', True, False, True, True),
    ('3300', 'Current year profit', 'equity', 'credit', '3000', True, False, False, True),
    ('4000', 'Income', 'income', 'credit', None, False, False, False, True),
    ('4100', 'Interest income', 'income', 'credit', '4000', True, False, False, True),
    ('4200', 'Penalty income', 'income', 'credit', '4000', True, False, False, True),
    ('4300', 'Fee income', 'income', 'credit', '4000', True, False, False, True),
    ('4400', 'Guarantee commission income', 'income', 'credit', '4000', True, False, False, True),
    ('4500', 'Recoveries of written-off loans', 'income', 'credit', '4000', True, False, False, True),
    ('4600', 'Treasury income', 'income', 'credit', '4000', True, False, False, True),
    ('4700', 'Foreign exchange gains', 'income', 'credit', '4000', True, False, False, False),
    ('5000', 'Expenses', 'expense', 'debit', None, False, False, False, True),
    ('5100', 'Interest expense - investors', 'expense', 'debit', '5000', True, False, True, True),
    ('5110', 'Interest expense - borrowings', 'expense', 'debit', '5000', True, False, True, True),
    ('5200', 'Impairment expense', 'expense', 'debit', '5000', True, False, True, True),
    ('5210', 'Loans written off', 'expense', 'debit', '5000', True, False, True, True),
    ('5300', 'Commission expense', 'expense', 'debit', '5000', True, False, True, True),
    ('5400', 'Depreciation', 'expense', 'debit', '5000', True, False, True, True),
    ('5500', 'Foreign exchange losses', 'expense', 'debit', '5000', True, False, True, False),
]

PERMISSIONS = [
    ('gl.view', 'View the chart of accounts, journals, periods and GL reports', ('admin', 'super_admin')),
    ('gl.chart.edit', 'Request chart-of-accounts changes', ('admin', 'super_admin')),
    ('gl.chart.approve', 'Approve chart-of-accounts changes (checker)', ('admin', 'super_admin')),
]
POLICIES = [
    ('gl.account.create', [{'permission': 'gl.chart.approve', 'count': 1}],
     'A second person approves a new GL account (FSD FIN-01).'),
    ('gl.account.change', [{'permission': 'gl.chart.approve', 'count': 1}],
     'A second person approves a change to a GL account (FSD FIN-01).'),
]

TRIGGERS = """
CREATE FUNCTION gl_accounts_no_delete() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'GL accounts are never deleted; deactivate account % instead.', OLD.code
        USING ERRCODE = 'insufficient_privilege';
END
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_gl_accounts_no_delete BEFORE DELETE ON gl_accounts
    FOR EACH ROW EXECUTE FUNCTION gl_accounts_no_delete();
"""


def upgrade():
    op.create_table(
        'gl_accounts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('code', sa.String(20), nullable=False, unique=True),
        sa.Column('name', sa.String(150), nullable=False),
        sa.Column('account_type', sa.String(10), nullable=False),
        sa.Column('normal_side', sa.String(6), nullable=False),
        sa.Column('parent_id', sa.Integer(), sa.ForeignKey('gl_accounts.id', ondelete='RESTRICT'), nullable=True),
        sa.Column('is_postable', sa.Boolean(), nullable=False),
        sa.Column('is_control', sa.Boolean(), nullable=False),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id', ondelete='RESTRICT'), nullable=True),
        sa.Column('currency', sa.String(3), server_default='KES', nullable=False),
        sa.Column('allow_manual_posting', sa.Boolean(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('source', sa.String(20), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_by', sa.String(120), nullable=False),
        sa.Column('updated_by', sa.String(120), nullable=True),
        sa.Column('date_created', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('date_updated', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("account_type IN ('asset', 'liability', 'equity', 'income', 'expense')",
                           name='ck_gl_accounts_type'),
        sa.CheckConstraint("normal_side IN ('debit', 'credit')", name='ck_gl_accounts_normal_side'),
        sa.CheckConstraint("source IN ('working_assumption', 'client_confirmed', 'internal_decision')",
                           name='ck_gl_accounts_source'),
        sa.CheckConstraint("currency = 'KES'", name='ck_gl_accounts_currency_kes'),
        sa.CheckConstraint("code ~ '^[0-9A-Za-z][0-9A-Za-z.\\-]{0,19}$'", name='ck_gl_accounts_code_format'),
        sa.CheckConstraint('parent_id IS NULL OR parent_id <> id', name='ck_gl_accounts_not_own_parent'),
        sa.CheckConstraint('is_postable OR NOT is_control', name='ck_gl_accounts_header_not_control'),
    )
    op.create_index('ix_gl_accounts_parent_id', 'gl_accounts', ['parent_id'])
    op.execute(TRIGGERS)

    conn = op.get_bind()
    for code, name, typ, side, parent, postable, control, manual, active in CHART:
        conn.execute(sa.text(
            "INSERT INTO gl_accounts (code, name, account_type, normal_side, parent_id, is_postable, is_control,"
            " allow_manual_posting, is_active, source, description, version, created_by)"
            " VALUES (:c, :n, :t, :s, (SELECT id FROM gl_accounts WHERE code = :p), :post, :ctl, :man, :act,"
            " 'working_assumption', :d, 1, 'migration')"),
            {'c': code, 'n': name, 't': typ, 's': side, 'p': parent, 'post': postable, 'ctl': control,
             'man': manual, 'act': active, 'd': WA})
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
    op.drop_table('gl_accounts')
    op.execute('DROP FUNCTION gl_accounts_no_delete()')
