"""job queue

Phase 2a item 5 (ADR-04-3). jobs is a PostgreSQL-backed queue claimed with
FOR UPDATE SKIP LOCKED by the worker process; (name, dedupe_key) is unique so
a periodic slot is enqueued once whatever the number of processes.
periodic_tasks keeps the scheduler's position per periodic task; seeding
last_slot = now() means nothing back-fills on the first run.

Revision ID: f5e6a7b8c9d0
Revises: e4d5f6a7b8c9
Create Date: 2026-10-16 19:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'f5e6a7b8c9d0'
down_revision = 'e4d5f6a7b8c9'
branch_labels = None
depends_on = None

PERIODIC = ('email.drain', 'email.recover_stuck', 'reports.aum_monthly', 'backup.daily', 'change_requests.expire')


def _ts():
    return [
        sa.Column('date_created', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('date_updated', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    ]


def upgrade():
    op.create_table(
        'jobs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(60), nullable=False),
        sa.Column('queue', sa.String(20), nullable=False),
        sa.Column('args', postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('status', sa.String(10), server_default='queued', nullable=False),
        sa.Column('priority', sa.Integer(), server_default='0', nullable=False),
        sa.Column('run_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
        sa.Column('max_attempts', sa.Integer(), server_default='3', nullable=False),
        sa.Column('dedupe_key', sa.String(120), nullable=True),
        sa.Column('enqueued_by', sa.String(120), nullable=False),
        sa.Column('locked_by', sa.String(120), nullable=True),
        sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('heartbeat_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('result', postgresql.JSONB(), nullable=True),
        *_ts(),
        sa.CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')", name='ck_jobs_status'),
        sa.CheckConstraint('max_attempts >= 1', name='ck_jobs_max_attempts'),
    )
    op.create_index('uq_jobs_name_dedupe_key', 'jobs', ['name', 'dedupe_key'], unique=True,
                    postgresql_where=sa.text('dedupe_key IS NOT NULL'))
    op.create_index('ix_jobs_claim', 'jobs', ['status', 'queue', 'priority', 'run_at'])

    op.create_table(
        'periodic_tasks',
        sa.Column('name', sa.String(60), primary_key=True),
        sa.Column('last_slot', sa.DateTime(timezone=True), nullable=False),
        sa.Column('next_slot', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_ticked_at', sa.DateTime(timezone=True), nullable=True),
        *_ts(),
    )
    conn = op.get_bind()
    for name in PERIODIC:
        conn.execute(sa.text('INSERT INTO periodic_tasks (name, last_slot) VALUES (:n, now())'), {'n': name})


def downgrade():
    op.drop_table('periodic_tasks')
    op.drop_table('jobs')
