"""change requests (generic maker-checker)

Phase 2a item 3 (ADR-04-1). change_requests, change_request_events and
approval_policies, with maker ≠ checker enforced by the database:
  * a trigger refuses an approve / reject / return event by the request's maker;
  * a unique index stops one person approving twice in the same round;
  * events are insert-only;
  * withdrawals and interest_periods get CHECK constraints for the same rule.

Revision ID: d3c4e5f6a7b8
Revises: c2b3d4e5f6a7
Create Date: 2026-10-16 17:00:00.000000

"""
import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'd3c4e5f6a7b8'
down_revision = 'c2b3d4e5f6a7'
branch_labels = None
depends_on = None

POLICIES = [
    ('withdrawal.approve', [{'permission': 'withdrawal.approve', 'count': 1}],
     'Any admin approves or rejects a withdrawal (unchanged from phase 1).'),
    ('interest.approve', [{'permission': 'interest.approve', 'count': 1}],
     'A second admin approves a month of interest (unchanged from phase 1).'),
] + [
    (t, [{'permission': 'role.manage', 'count': 1}], 'A second system administrator approves access changes.')
    for t in ('rbac.grant_role', 'rbac.revoke_role', 'rbac.set_limit', 'rbac.set_branch_scope', 'rbac.set_role_active')
]

TRIGGER_SQL = """
CREATE FUNCTION change_request_maker_is_not_checker() RETURNS trigger AS $$
BEGIN
    IF NEW.action IN ('approve', 'reject', 'return') AND NEW.actor_user_id IS NOT DISTINCT FROM
       (SELECT maker_user_id FROM change_requests WHERE id = NEW.request_id) THEN
        RAISE EXCEPTION 'Maker-checker: the person who made change request % cannot decide it (%).', NEW.request_id, NEW.action
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_change_request_maker_is_not_checker
    BEFORE INSERT ON change_request_events
    FOR EACH ROW EXECUTE FUNCTION change_request_maker_is_not_checker();

CREATE FUNCTION refuse_update_delete() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION '% rows are insert-only (% refused).', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'insufficient_privilege';
END
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_change_request_events_insert_only
    BEFORE UPDATE OR DELETE ON change_request_events
    FOR EACH ROW EXECUTE FUNCTION refuse_update_delete();
"""


def _ts():
    return [
        sa.Column('date_created', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('date_updated', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    ]


def upgrade():
    conn = op.get_bind()
    # Existing data must already obey the rule the new constraints enforce.
    bad_w = [r[0] for r in conn.execute(sa.text(
        "SELECT id FROM withdrawals WHERE decided_by IS NOT NULL AND lower(decided_by) = lower(requested_by)"))]
    bad_i = [r[0] for r in conn.execute(sa.text(
        "SELECT id FROM interest_periods WHERE approved_by IS NOT NULL AND lower(approved_by) = lower(calculated_by)"))]
    if bad_w or bad_i:
        raise RuntimeError(f"Maker = checker in existing data: withdrawals {bad_w}, interest_periods {bad_i}. "
                           "Investigate before migrating; nothing was changed.")

    op.create_table(
        'approval_policies',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('request_type', sa.String(60), nullable=False),
        sa.Column('min_amount', sa.Numeric(20, 2), nullable=True),
        sa.Column('max_amount', sa.Numeric(20, 2), nullable=True),
        sa.Column('levels', postgresql.JSONB(), nullable=False),
        sa.Column('same_branch_required', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('expiry_hours', sa.Integer(), server_default='168', nullable=False),
        sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        *_ts(),
        sa.CheckConstraint('min_amount IS NULL OR max_amount IS NULL OR min_amount <= max_amount',
                           name='ck_approval_policies_amount_band'),
        sa.CheckConstraint("jsonb_typeof(levels) = 'array' AND jsonb_array_length(levels) >= 1",
                           name='ck_approval_policies_levels'),
        sa.CheckConstraint('expiry_hours > 0', name='ck_approval_policies_expiry'),
    )
    op.create_index('ix_approval_policies_request_type', 'approval_policies', ['request_type'])

    op.create_table(
        'change_requests',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('request_type', sa.String(60), nullable=False),
        sa.Column('entity_type', sa.String(50), nullable=True),
        sa.Column('entity_id', sa.String(64), nullable=True),
        sa.Column('payload', postgresql.JSONB(), nullable=False),
        sa.Column('base_version', sa.String(128), nullable=True),
        sa.Column('amount', sa.Numeric(20, 2), nullable=True),
        sa.Column('currency', sa.String(3), server_default='KES', nullable=False),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id', ondelete='RESTRICT'), nullable=True),
        sa.Column('status', sa.String(10), server_default='pending', nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('maker_user_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('maker_email', sa.String(120), nullable=False),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('applied_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('policy_id', sa.Integer(), sa.ForeignKey('approval_policies.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('levels_required', sa.Integer(), nullable=False),
        sa.Column('levels_done', sa.Integer(), server_default='0', nullable=False),
        sa.Column('round', sa.Integer(), server_default='1', nullable=False),
        sa.Column('result', postgresql.JSONB(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        *_ts(),
        sa.CheckConstraint(
            "status IN ('pending', 'returned', 'applied', 'rejected', 'cancelled', 'expired', 'failed')",
            name='ck_change_requests_status'),
        sa.CheckConstraint("currency = 'KES'", name='ck_change_requests_currency_kes'),
        sa.CheckConstraint('amount IS NULL OR amount >= 0', name='ck_change_requests_amount'),
        sa.CheckConstraint('levels_done >= 0 AND levels_done <= levels_required', name='ck_change_requests_levels'),
    )
    op.create_index('ix_change_requests_status_type', 'change_requests', ['status', 'request_type'])
    op.create_index('ix_change_requests_maker_user_id', 'change_requests', ['maker_user_id'])

    op.create_table(
        'change_request_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('request_id', sa.Integer(), sa.ForeignKey('change_requests.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('round', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(10), nullable=False),
        sa.Column('level', sa.Integer(), nullable=True),
        sa.Column('actor_user_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='RESTRICT'), nullable=True),
        sa.Column('actor_email', sa.String(120), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('at', sa.DateTime(timezone=True), nullable=False),
        *_ts(),
        sa.CheckConstraint(
            "action IN ('submit', 'approve', 'reject', 'return', 'resubmit', 'cancel', 'apply', 'expire', 'fail')",
            name='ck_change_request_events_action'),
    )
    op.create_index('ix_change_request_events_request_id', 'change_request_events', ['request_id'])
    op.create_index('uq_change_request_events_one_approval', 'change_request_events',
                    ['request_id', 'round', 'actor_user_id'], unique=True,
                    postgresql_where=sa.text("action = 'approve'"))
    op.execute(TRIGGER_SQL)

    op.create_check_constraint('ck_withdrawals_maker_not_checker', 'withdrawals',
                               'decided_by IS NULL OR lower(decided_by) <> lower(requested_by)')
    op.create_check_constraint('ck_interest_periods_maker_not_checker', 'interest_periods',
                               'approved_by IS NULL OR lower(approved_by) <> lower(calculated_by)')

    conn.execute(sa.text("INSERT INTO permissions (code, module, description) VALUES "
                         "('change_request.view', 'approvals', 'Use the approvals inbox: see, submit and decide "
                         "change requests (each decision still needs its own permission)')"))
    conn.execute(sa.text("INSERT INTO role_permissions (role_id, permission_code) "
                         "SELECT id, 'change_request.view' FROM roles WHERE built_in"))
    for request_type, levels, desc in POLICIES:
        conn.execute(sa.text("INSERT INTO approval_policies (request_type, levels, description) "
                             "VALUES (:t, CAST(:l AS jsonb), :d)"), {'t': request_type, 'l': json.dumps(levels), 'd': desc})


def downgrade():
    op.drop_constraint('ck_interest_periods_maker_not_checker', 'interest_periods', type_='check')
    op.drop_constraint('ck_withdrawals_maker_not_checker', 'withdrawals', type_='check')
    op.execute("DELETE FROM role_permissions WHERE permission_code = 'change_request.view'")
    op.execute("DELETE FROM permissions WHERE code = 'change_request.view'")
    op.drop_table('change_request_events')
    op.drop_table('change_requests')
    op.drop_table('approval_policies')
    op.execute("DROP FUNCTION IF EXISTS change_request_maker_is_not_checker()")
    op.execute("DROP FUNCTION IF EXISTS refuse_update_delete()")
