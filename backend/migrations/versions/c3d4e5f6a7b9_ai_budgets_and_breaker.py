"""AI budgets, circuit breaker and kill switch (AI-12)

- ai_service_state: one row, running | paused. The circuit breaker pauses AI calls;
  only an admin resumes (permission ai.breaker.resume, audited).
- ai_budget_refusals: every API call refused before it was made (kill switch, pause,
  missing price, per-reading / per-application / monthly budget). Insert-only.
- ai_extraction_calls.estimated_cost_usd: the pre-call estimate, kept beside the
  ACTUAL cost (cost_usd, from the returned token usage).
- settings: ai.budget.monthly_usd 20, ai.budget.per_application_usd 2,
  ai.budget.per_run_usd 3, ai.breaker.consecutive_failures 5,
  ai.breaker.window_failures 10, ai.breaker.window_minutes 10.

Revision ID: c3d4e5f6a7b9
Revises: b2c3d4e5f6a8
Create Date: 2026-10-18 09:00:00.000000

"""
import json

from alembic import op
import sqlalchemy as sa


revision = 'c3d4e5f6a7b9'
down_revision = 'b2c3d4e5f6a8'
branch_labels = None
depends_on = None

SETTINGS = (
    ('ai.budget.monthly_usd', '20.00', 'Phase 3 brief: monthly AI budget before any live run'),
    ('ai.budget.per_application_usd', '2.00', 'Phase 3 brief'),
    ('ai.budget.per_run_usd', '3.00', 'Phase 3 brief (caps one reading, including test runs)'),
    ('ai.breaker.consecutive_failures', 5, 'Phase 3 brief'),
    ('ai.breaker.window_failures', 10, 'Phase 3 brief'),
    ('ai.breaker.window_minutes', 10, 'Phase 3 brief'),
)


def upgrade():
    op.create_table('ai_service_state',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('paused_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('paused_reason', sa.Text(), nullable=True),
    sa.Column('resumed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('resumed_by', sa.String(length=120), nullable=True),
    sa.Column('resume_reason', sa.Text(), nullable=True),
    sa.CheckConstraint('id = 1', name='ck_ai_service_state_single_row'),
    sa.CheckConstraint("status IN ('running', 'paused')", name='ck_ai_service_state_status'),
    sa.CheckConstraint("status = 'running' OR paused_reason IS NOT NULL", name='ck_ai_service_state_reason'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('ai_budget_refusals',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('extraction_id', sa.Integer(), nullable=False),
    sa.Column('application_id', sa.Integer(), nullable=True),
    sa.Column('page_number', sa.Integer(), nullable=True),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('limit_usd', sa.Numeric(precision=12, scale=6), nullable=True),
    sa.Column('spent_usd', sa.Numeric(precision=12, scale=6), nullable=True),
    sa.Column('estimate_usd', sa.Numeric(precision=12, scale=6), nullable=True),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('refused_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('date_created', sa.DateTime(timezone=True), nullable=False),
    sa.Column('date_updated', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("kind IN ('disabled', 'paused', 'pricing', 'monthly', 'per_application', 'per_run')",
                       name='ck_ai_budget_refusals_kind'),
    sa.ForeignKeyConstraint(['extraction_id'], ['ai_extractions.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['application_id'], ['loan_applications.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_ai_budget_refusals_at', 'ai_budget_refusals', ['refused_at'])
    op.add_column('ai_extraction_calls', sa.Column('estimated_cost_usd', sa.Numeric(precision=12, scale=6),
                                                   nullable=True))
    op.execute("""CREATE TRIGGER trg_ai_budget_refusals_insert_only BEFORE UPDATE OR DELETE ON ai_budget_refusals
                  FOR EACH ROW EXECUTE FUNCTION docai_insert_only();""")
    conn = op.get_bind()
    conn.execute(sa.text("INSERT INTO ai_service_state (id, status) VALUES (1, 'running')"))
    conn.execute(sa.text("INSERT INTO permissions (code, module, description, sensitive) VALUES ('ai.breaker.resume', "
                         "'docai', 'Resume AI document reading after the circuit breaker paused it', true)"))
    conn.execute(sa.text("INSERT INTO role_permissions (role_id, permission_code) SELECT id, 'ai.breaker.resume' "
                         "FROM roles WHERE legacy_role IN ('admin', 'super_admin')"))
    for key, value, evidence in SETTINGS:
        conn.execute(sa.text(
            "INSERT INTO setting_versions (key, value, effective_from, version_no, source, evidence, created_by,"
            " approved_by, approved_at) VALUES (:k, CAST(:v AS jsonb), '2026-01-01', 1, 'working_assumption', :e,"
            " 'migration', 'docs/architecture/08-working-assumptions.md', now())"),
            {'k': key, 'v': json.dumps(value), 'e': evidence})


def downgrade():
    conn = op.get_bind()
    op.execute("ALTER TABLE setting_versions DISABLE TRIGGER trg_setting_versions_insert_only")
    conn.execute(sa.text("DELETE FROM setting_versions WHERE key = ANY(:k)"), {'k': [k for k, _, _ in SETTINGS]})
    op.execute("ALTER TABLE setting_versions ENABLE TRIGGER trg_setting_versions_insert_only")
    conn.execute(sa.text("DELETE FROM role_permissions WHERE permission_code = 'ai.breaker.resume'"))
    conn.execute(sa.text("DELETE FROM permissions WHERE code = 'ai.breaker.resume'"))
    op.drop_column('ai_extraction_calls', 'estimated_cost_usd')
    op.drop_index('ix_ai_budget_refusals_at', table_name='ai_budget_refusals')
    op.drop_table('ai_budget_refusals')
    op.drop_table('ai_service_state')
