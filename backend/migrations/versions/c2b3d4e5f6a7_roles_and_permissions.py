"""roles and permissions

Phase 2a item 4 (ADR-04-4). Permission codes bundled into roles, extra roles per
user, branch scopes, per-role / per-user transaction limits and SoD conflicts.

The three built-in roles reproduce today's decorators exactly:
    ops_staff     (user)         what @staff_required allowed
    ops_admin     (admin)        + what @admin_required allowed
    system_admin  (super_admin)  + what @super_admin_required allowed
The FSD Section 15 departmental roles are created inactive and unassigned.

Revision ID: c2b3d4e5f6a7
Revises: b1a2c3d4e5f6
Create Date: 2026-10-16 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c2b3d4e5f6a7'
down_revision = 'b1a2c3d4e5f6'
branch_labels = None
depends_on = None

# code, module, description, sensitive, amount_limited
PERMISSIONS = [
    ('investor.view', 'investments', 'View investors, their ledger, deposits, withdrawals, payouts and emails', True, False),
    ('investor.create', 'investments', 'Add investors', False, False),
    ('investor.edit', 'investments', 'Edit investor details', False, False),
    ('investor.close', 'investments', 'Close or reopen an investor account', False, False),
    ('deposit.view', 'investments', 'View deposits', False, False),
    ('deposit.record', 'investments', 'Record deposits', False, False),
    ('deposit.reverse', 'investments', 'Reverse a posted deposit', False, False),
    ('withdrawal.view', 'investments', 'View withdrawals', False, False),
    ('withdrawal.request', 'investments', 'Record withdrawal requests', False, False),
    ('withdrawal.approve', 'investments', 'Approve or reject withdrawal requests (checker)', False, True),
    ('interest.view', 'investments', 'View interest rates and periods', False, False),
    ('interest.rate.set', 'investments', 'Set the interest rate', False, False),
    ('interest.calculate', 'investments', 'Calculate or recalculate a month of interest (maker)', False, False),
    ('interest.discard', 'investments', 'Discard a draft interest calculation', False, False),
    ('interest.approve', 'investments', 'Approve a month of interest (checker)', False, True),
    ('interest.mark_paid', 'investments', 'Mark interest payouts paid', False, False),
    ('statement.view', 'investments', 'Download interest statements', True, False),
    ('statement.generate', 'investments', 'Generate statement emails', False, False),
    ('email.view', 'emails', 'View the email outbox and attachments', True, False),
    ('email.manage', 'emails', 'Retry or cancel emails', False, False),
    ('email.send_now', 'emails', 'Send the email queue now', False, False),
    ('email.confirm', 'emails', 'Confirm or suppress emails awaiting review', False, False),
    ('stats.view', 'dashboard', 'View the dashboard', False, False),
    ('report.view', 'reports', 'List reports', False, False),
    ('report.export.investors', 'reports', 'Export the investors report', True, False),
    ('report.export.deposits', 'reports', 'Export the deposits report', False, False),
    ('report.export.withdrawals', 'reports', 'Export the withdrawals report', False, False),
    ('report.export.interest', 'reports', 'Export the interest payout report', False, False),
    ('report.export.aum', 'reports', 'Export the AUM summary', False, False),
    ('report.export.audit-log', 'reports', 'Export the audit log', True, False),
    ('report.export.email-log', 'reports', 'Export the email log', True, False),
    ('audit.view', 'audit', 'View the audit log', True, False),
    ('user.unlock', 'it', 'Unlock a locked-out account', False, False),
    ('user.manage', 'it', 'Create, edit, disable and reset staff accounts', False, False),
    ('role.manage', 'it', 'Propose and approve role, limit and branch-scope changes', False, False),
    ('settings.email', 'it', 'Email server and email queue settings', False, False),
    ('settings.reports', 'it', 'Scheduled report settings', False, False),
    ('backup.view', 'it', 'View database backups', False, False),
    ('backup.run', 'it', 'Start a database backup', False, False),
]

STAFF = [
    'investor.view', 'investor.create', 'investor.edit', 'deposit.view', 'deposit.record',
    'withdrawal.view', 'withdrawal.request', 'interest.view', 'statement.view', 'email.view', 'stats.view',
    'report.view', 'report.export.investors', 'report.export.deposits', 'report.export.withdrawals',
    'report.export.interest', 'report.export.aum',
]
ADMIN = STAFF + [
    'investor.close', 'deposit.reverse', 'withdrawal.approve', 'interest.rate.set', 'interest.calculate',
    'interest.discard', 'interest.approve', 'interest.mark_paid', 'statement.generate', 'email.manage',
    'email.send_now', 'email.confirm', 'audit.view', 'report.export.audit-log', 'report.export.email-log',
    'user.unlock',
]
SUPER = ADMIN + ['user.manage', 'role.manage', 'settings.email', 'settings.reports', 'backup.view', 'backup.run']

VIEW_ALL = [
    'investor.view', 'deposit.view', 'withdrawal.view', 'interest.view', 'statement.view', 'email.view',
    'stats.view', 'report.view', 'report.export.investors', 'report.export.deposits',
    'report.export.withdrawals', 'report.export.interest', 'report.export.aum',
]

DEPARTMENTS = [
    ('OPS', 'Operations'), ('CREDIT', 'Credit'), ('FIN', 'Finance'), ('RISK', 'Risk and compliance'),
    ('IR', 'Investor relations'), ('IT', 'IT'), ('MGMT', 'Management'),
]

# code, name, department, built_in, active, all_branches, legacy_role, description, permissions
ROLES = [
    ('ops_staff', 'Operations staff', 'OPS', True, True, True, 'user',
     'Built-in. Today\'s "user" role: view, add and edit investors, record deposits and withdrawal requests.', STAFF),
    ('ops_admin', 'Operations admin', 'OPS', True, True, True, 'admin',
     'Built-in. Today\'s "admin" role: approves withdrawals, reversals and interest; manages emails.', ADMIN),
    ('system_admin', 'System administrator', 'IT', True, True, True, 'super_admin',
     'Built-in. Today\'s "super_admin" role: users, settings, backups, plus every admin right '
     '(removing business approvals is pending Q-IT10).', SUPER),
    # FSD Section 15. Inactive and unassigned until the business confirms them;
    # their lending permissions are added by the phases that build lending.
    ('credit_officer', 'Credit officer', 'CREDIT', False, False, False, None,
     'FSD 15: capture applications, review AI extractions, prepare credit analysis.', ['investor.view', 'stats.view']),
    ('credit_manager', 'Credit manager', 'CREDIT', False, False, False, None,
     'FSD 15: approve loans within limit (WA-14: up to KES 500,000); approve extraction reviews.',
     ['investor.view', 'stats.view', 'report.view']),
    ('credit_committee', 'Credit committee member', 'CREDIT', False, False, True, None,
     'FSD 15 / WA-14: loans KES 500,001 to 2,000,000, any two members.', ['investor.view', 'report.view']),
    ('board_credit_committee', 'Board credit committee member', 'MGMT', False, False, True, None,
     'FSD 15 / WA-14: loans above KES 2,000,000.', ['investor.view', 'report.view']),
    ('finance', 'Finance', 'FIN', False, False, True, None,
     'FSD 15: manual journals (maker), reconciliations, month-end, financial reports.', VIEW_ALL),
    ('risk_audit', 'Risk and audit', 'RISK', False, False, True, None,
     'FSD 15: read-only access to everything, including audit and AI decision logs.',
     VIEW_ALL + ['audit.view', 'report.export.audit-log', 'report.export.email-log']),
]

# Built-in approvers keep today's behaviour: no amount cap.
UNLIMITED = [('ops_admin', 'withdrawal.approve'), ('ops_admin', 'interest.approve'),
             ('system_admin', 'withdrawal.approve'), ('system_admin', 'interest.approve')]

SOD = [
    ('user.manage', 'withdrawal.approve', 'warn', 'IT administrators should not approve business transactions (Q-IT10).'),
    ('deposit.record', 'deposit.reverse', 'warn', 'The person reversing a deposit should not be the one who recorded it.'),
]


def _ts():
    return [
        sa.Column('date_created', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('date_updated', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    ]


def upgrade():
    op.create_table(
        'departments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('code', sa.String(10), nullable=False, unique=True),
        sa.Column('name', sa.String(100), nullable=False),
        *_ts(),
    )
    op.create_table(
        'permissions',
        sa.Column('code', sa.String(80), primary_key=True),
        sa.Column('module', sa.String(40), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('sensitive', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('amount_limited', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        *_ts(),
    )
    op.create_table(
        'roles',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('code', sa.String(40), nullable=False, unique=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('department_id', sa.Integer(), sa.ForeignKey('departments.id', ondelete='RESTRICT'), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('built_in', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('all_branches', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('legacy_role', sa.String(20), nullable=True, unique=True),
        *_ts(),
        sa.CheckConstraint("legacy_role IS NULL OR legacy_role IN ('user', 'admin', 'super_admin')",
                           name='ck_roles_legacy_role'),
    )
    op.create_table(
        'role_permissions',
        sa.Column('role_id', sa.Integer(), sa.ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('permission_code', sa.String(80), sa.ForeignKey('permissions.code', ondelete='RESTRICT'),
                  primary_key=True),
        *_ts(),
    )
    op.create_table(
        'user_roles',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role_id', sa.Integer(), sa.ForeignKey('roles.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('granted_by', sa.String(120), nullable=False),
        sa.Column('granted_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('via_change_request_id', sa.Integer(), nullable=True),
        *_ts(),
        sa.UniqueConstraint('user_id', 'role_id', name='uq_user_roles_user_role'),
    )
    op.create_index('ix_user_roles_user_id', 'user_roles', ['user_id'])
    op.create_table(
        'user_branch_scopes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id', ondelete='RESTRICT'), nullable=True),
        sa.Column('all_branches', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('granted_by', sa.String(120), nullable=False),
        *_ts(),
        sa.CheckConstraint('all_branches = (branch_id IS NULL)', name='ck_user_branch_scopes_all_or_one'),
    )
    op.create_index('ix_user_branch_scopes_user_id', 'user_branch_scopes', ['user_id'])
    op.create_index('uq_user_branch_scopes_user_branch', 'user_branch_scopes',
                    ['user_id', sa.text('coalesce(branch_id, 0)')], unique=True)
    op.create_table(
        'transaction_limits',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('subject_type', sa.String(10), nullable=False),
        sa.Column('subject_id', sa.Integer(), nullable=False),
        sa.Column('permission_code', sa.String(80), sa.ForeignKey('permissions.code', ondelete='RESTRICT'),
                  nullable=False),
        sa.Column('currency', sa.String(3), server_default='KES', nullable=False),
        sa.Column('max_per_item', sa.Numeric(20, 2), nullable=True),
        sa.Column('max_per_day', sa.Numeric(20, 2), nullable=True),
        sa.Column('effective_from', sa.Date(), nullable=False),
        sa.Column('set_by', sa.String(120), nullable=False),
        *_ts(),
        sa.CheckConstraint("subject_type IN ('role', 'user')", name='ck_transaction_limits_subject'),
        sa.CheckConstraint("currency = 'KES'", name='ck_transaction_limits_currency_kes'),
        sa.CheckConstraint('max_per_item IS NULL OR max_per_item > 0', name='ck_transaction_limits_item_positive'),
        sa.CheckConstraint('max_per_day IS NULL OR max_per_day > 0', name='ck_transaction_limits_day_positive'),
        sa.UniqueConstraint('subject_type', 'subject_id', 'permission_code', 'effective_from',
                            name='uq_transaction_limits_subject_perm_date'),
    )
    op.create_table(
        'sod_conflicts',
        sa.Column('permission_a', sa.String(80), sa.ForeignKey('permissions.code', ondelete='RESTRICT'),
                  primary_key=True),
        sa.Column('permission_b', sa.String(80), sa.ForeignKey('permissions.code', ondelete='RESTRICT'),
                  primary_key=True),
        sa.Column('severity', sa.String(5), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        *_ts(),
        sa.CheckConstraint("severity IN ('block', 'warn')", name='ck_sod_conflicts_severity'),
    )
    op.add_column('user', sa.Column('branch_id', sa.Integer(), server_default='1', nullable=False))
    op.create_foreign_key('fk_user_branch_id', 'user', 'branches', ['branch_id'], ['id'], ondelete='RESTRICT')

    conn = op.get_bind()
    for code, name in DEPARTMENTS:
        conn.execute(sa.text('INSERT INTO departments (code, name) VALUES (:c, :n)'), {'c': code, 'n': name})
    for code, module, desc, sensitive, limited in PERMISSIONS:
        conn.execute(sa.text('INSERT INTO permissions (code, module, description, sensitive, amount_limited) '
                             'VALUES (:c, :m, :d, :s, :l)'),
                     {'c': code, 'm': module, 'd': desc, 's': sensitive, 'l': limited})
    for code, name, dept, built_in, active, all_branches, legacy, desc, perms in ROLES:
        role_id = conn.execute(sa.text(
            'INSERT INTO roles (code, name, department_id, description, built_in, active, all_branches, legacy_role) '
            'VALUES (:c, :n, (SELECT id FROM departments WHERE code = :d), :desc, :b, :a, :ab, :lr) RETURNING id'
        ), {'c': code, 'n': name, 'd': dept, 'desc': desc, 'b': built_in, 'a': active, 'ab': all_branches,
            'lr': legacy}).scalar()
        for perm in sorted(set(perms)):
            conn.execute(sa.text('INSERT INTO role_permissions (role_id, permission_code) VALUES (:r, :p)'),
                         {'r': role_id, 'p': perm})
    for role, perm in UNLIMITED:
        conn.execute(sa.text(
            "INSERT INTO transaction_limits (subject_type, subject_id, permission_code, max_per_item, effective_from, set_by) "
            "VALUES ('role', (SELECT id FROM roles WHERE code = :r), :p, NULL, DATE '2000-01-01', 'migration')"
        ), {'r': role, 'p': perm})
    for a, b, severity, reason in SOD:
        conn.execute(sa.text('INSERT INTO sod_conflicts (permission_a, permission_b, severity, reason) '
                             'VALUES (:a, :b, :s, :r)'), {'a': a, 'b': b, 's': severity, 'r': reason})


def downgrade():
    op.drop_constraint('fk_user_branch_id', 'user', type_='foreignkey')
    op.drop_column('user', 'branch_id')
    for table in ('sod_conflicts', 'transaction_limits', 'user_branch_scopes', 'user_roles',
                  'role_permissions', 'roles', 'permissions', 'departments'):
        op.drop_table(table)
