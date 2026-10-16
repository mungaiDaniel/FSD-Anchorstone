"""login attempts and account lockouts

Sign-in protection counters, kept in PostgreSQL so every gunicorn worker
shares them (see app/Admin/service.py).

Revision ID: 597aa1c2e2ae
Revises: 55a591f8bac8
Create Date: 2026-10-16 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '597aa1c2e2ae'
down_revision = '55a591f8bac8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'login_attempts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=150), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=False),
        sa.Column('outcome', sa.String(length=10), nullable=False),
        sa.Column('attempted_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('date_created', sa.DateTime(timezone=True), nullable=False),
        sa.Column('date_updated', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("outcome IN ('success', 'failed', 'blocked')", name='ck_login_attempts_outcome'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_login_attempts_email_time', 'login_attempts', ['email', 'attempted_at'])
    op.create_index('ix_login_attempts_ip_time', 'login_attempts', ['ip_address', 'attempted_at'])

    op.create_table(
        'account_lockouts',
        sa.Column('email', sa.String(length=150), nullable=False),
        sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('counting_from', sa.DateTime(timezone=True), nullable=True),
        sa.Column('unlocked_by', sa.String(length=120), nullable=True),
        sa.Column('date_created', sa.DateTime(timezone=True), nullable=False),
        sa.Column('date_updated', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('email'),
    )


def downgrade():
    op.drop_table('account_lockouts')
    op.drop_index('ix_login_attempts_ip_time', table_name='login_attempts')
    op.drop_index('ix_login_attempts_email_time', table_name='login_attempts')
    op.drop_table('login_attempts')
