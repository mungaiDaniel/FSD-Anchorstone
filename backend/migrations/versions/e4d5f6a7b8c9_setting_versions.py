"""versioned business-rule settings

Phase 2a item 2 (08-working-assumptions.md §3). setting_versions holds
immutable, effective-dated values for the keys in app/Settings/registry.py,
changed only through change requests (settings.change, or
settings.change_security with two approvers). Version 1 of every key is seeded
with source 'working_assumption' and its WA / 07 reference.

The sign-in limits seed from the LOGIN_* environment values if set, so a
deployment that tuned them keeps its numbers; afterwards the setting rules.

Revision ID: e4d5f6a7b8c9
Revises: d3c4e5f6a7b8
Create Date: 2026-10-16 18:00:00.000000

"""
import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'e4d5f6a7b8c9'
down_revision = 'd3c4e5f6a7b8'
branch_labels = None
depends_on = None

SEED_DATE = '2026-01-01'
MIME = ['application/pdf', 'image/heic', 'image/jpeg', 'image/png', 'image/tiff']

# key, value, evidence (frozen copy of the registry defaults on 2026-10-16)
SEEDS = [
    ('security.password_min_length', 10, 'FSD SEC-02 (at least 8); 10 kept, 08 §2.1 #5'),
    ('security.login_max_failures', 5, 'FSD SEC-02'),
    ('security.login_window_minutes', 15, 'FSD SEC-02'),
    ('security.login_lock_minutes', 15, '07 Q-IT5'),
    ('security.login_ip_max_failures', 20, '07 Q-IT5'),
    ('security.password_max_age_days', 90, 'FSD SEC-02'),
    ('security.password_history', 0, 'FSD SEC-02 (no reuse)'),
    ('security.idle_timeout_minutes', 30, '07 Q-IT5'),
    ('investments.wht_rate_percent', '0.0000', 'WA-03'),
    ('email.max_attempts', 3, 'internal'),
    ('notifications.reminder_days_before', [3, 0], 'FSD NTF-01'),
    ('lending.max_open_loans_per_client', 3, 'WA-05'),
    ('lending.max_open_loans_per_group', 3, 'WA-05'),
    ('lending.in_duplum_enabled', True, '07 Q-CO4 / FSD INT-05'),
    ('lending.penalty_grace_days', 7, 'WA-06'),
    ('kyc.maker_checker_fields', ['bank', 'identity', 'payout'], 'WA-01 / FSD KYC-08'),
    ('retention.documents_years_after_end', 7, 'WA-12'),
    ('retention.ai_raw_output_months', 24, '07 Q-CO8'),
    ('retention.audit_years', 7, '07 Q-CO8'),
    ('access.out_of_portfolio_mode', 'flag', '07 Q-CO3'),
    ('documents.allowed_types', MIME, '07 Q-IT9'),
    ('documents.max_mb', 25, '07 Q-IT9'),
    ('ai.enabled', False, '07 Q-CO2 (off until data location is confirmed)'),
]
ENV_SEEDS = {
    'security.login_max_failures': 'LOGIN_MAX_FAILURES',
    'security.login_window_minutes': 'LOGIN_WINDOW_MINUTES',
    'security.login_lock_minutes': 'LOGIN_LOCK_MINUTES',
    'security.login_ip_max_failures': 'LOGIN_IP_MAX_FAILURES',
}

PERMISSIONS = [
    ('settings.business.view', 'View business-rule settings and their history'),
    ('settings.business.edit', 'Propose a change to a business-rule setting (maker)'),
    ('settings.business.approve', 'Approve a change to a business-rule setting (checker)'),
]
POLICIES = [
    ('settings.change', [{'permission': 'settings.business.approve', 'count': 1}],
     'A second person approves a business-rule change.'),
    ('settings.change_security', [{'permission': 'settings.business.approve', 'count': 2}],
     'Two people other than the maker approve a security setting change.'),
]


def _env_value(key, default):
    try:
        from flask import current_app
        return int(current_app.config.get(ENV_SEEDS[key], default))
    except Exception:
        return default


def upgrade():
    op.create_table(
        'setting_versions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('key', sa.String(80), nullable=False),
        sa.Column('scope_type', sa.String(10), server_default='global', nullable=False),
        sa.Column('scope_id', sa.Integer(), nullable=True),
        sa.Column('value', postgresql.JSONB(), nullable=False),
        sa.Column('effective_from', sa.Date(), nullable=False),
        sa.Column('version_no', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(20), nullable=False),
        sa.Column('evidence', sa.Text(), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('change_request_id', sa.Integer(), sa.ForeignKey('change_requests.id', ondelete='RESTRICT'),
                  nullable=True),
        sa.Column('created_by', sa.String(120), nullable=False),
        sa.Column('approved_by', sa.String(120), nullable=False),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('date_created', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('date_updated', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("scope_type IN ('global', 'branch', 'product')", name='ck_setting_versions_scope_type'),
        sa.CheckConstraint("(scope_type = 'global') = (scope_id IS NULL)", name='ck_setting_versions_scope_id'),
        sa.CheckConstraint("source IN ('working_assumption', 'client_confirmed', 'internal_decision')",
                           name='ck_setting_versions_source'),
        sa.CheckConstraint('lower(approved_by) <> lower(created_by)', name='ck_setting_versions_maker_not_checker'),
    )
    op.create_index('uq_setting_versions_key_scope_date', 'setting_versions',
                    ['key', 'scope_type', sa.text('coalesce(scope_id, 0)'), 'effective_from'], unique=True)
    op.create_index('ix_setting_versions_lookup', 'setting_versions',
                    ['key', 'scope_type', 'scope_id', 'effective_from'])
    # refuse_update_delete() comes from the change-requests migration.
    op.execute("CREATE TRIGGER trg_setting_versions_insert_only BEFORE UPDATE OR DELETE ON setting_versions "
               "FOR EACH ROW EXECUTE FUNCTION refuse_update_delete()")

    conn = op.get_bind()
    for key, value, evidence in SEEDS:
        if key in ENV_SEEDS:
            value = _env_value(key, value)
        conn.execute(sa.text(
            "INSERT INTO setting_versions (key, value, effective_from, version_no, source, evidence, created_by,"
            " approved_by, approved_at) VALUES (:k, CAST(:v AS jsonb), :d, 1, 'working_assumption', :e,"
            " 'migration', 'docs/architecture/08-working-assumptions.md', now())"),
            {'k': key, 'v': json.dumps(value), 'd': SEED_DATE, 'e': evidence})

    for code, desc in PERMISSIONS:
        conn.execute(sa.text("INSERT INTO permissions (code, module, description) VALUES (:c, 'settings', :d)"),
                     {'c': code, 'd': desc})
        conn.execute(sa.text("INSERT INTO role_permissions (role_id, permission_code) SELECT id, :c FROM roles "
                             "WHERE legacy_role IN ('admin', 'super_admin')"), {'c': code})
    for request_type, levels, desc in POLICIES:
        conn.execute(sa.text("INSERT INTO approval_policies (request_type, levels, description) "
                             "VALUES (:t, CAST(:l AS jsonb), :d)"), {'t': request_type, 'l': json.dumps(levels), 'd': desc})


def downgrade():
    op.execute("DELETE FROM approval_policies WHERE request_type IN ('settings.change', 'settings.change_security')")
    op.execute("DELETE FROM role_permissions WHERE permission_code LIKE 'settings.business.%'")
    op.execute("DELETE FROM permissions WHERE code LIKE 'settings.business.%'")
    op.drop_table('setting_versions')
