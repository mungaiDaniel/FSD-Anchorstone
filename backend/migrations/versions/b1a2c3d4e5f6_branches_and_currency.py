"""branches and currency

Phase 2a item 1. A `branches` table with one Head Office branch (id 1, code 000),
a `branch_id` on investors and on the money tables that belong to an investor,
and a `currency` column on every money table, locked to KES by a CHECK.
Existing rows are put on Head Office and KES by the column defaults.

Revision ID: b1a2c3d4e5f6
Revises: e080731771c7
Create Date: 2026-10-16 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b1a2c3d4e5f6'
down_revision = 'e080731771c7'
branch_labels = None
depends_on = None

MONEY_TABLES = ('deposits', 'withdrawals', 'interest_periods', 'interest_payouts')
BRANCH_TABLES = ('investors', 'deposits', 'withdrawals', 'interest_payouts')


def upgrade():
    op.create_table(
        'branches',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=3), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('status', sa.String(length=10), server_default='active', nullable=False),
        sa.Column('date_created', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('date_updated', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("status IN ('active', 'closed')", name='ck_branches_status'),
        sa.CheckConstraint("code ~ '^[0-9]{3}$'", name='ck_branches_code_format'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
    )
    op.execute("INSERT INTO branches (id, code, name, status) VALUES (1, '000', 'Head Office', 'active')")
    op.execute("SELECT setval(pg_get_serial_sequence('branches', 'id'), 1)")

    for table in MONEY_TABLES:
        op.add_column(table, sa.Column('currency', sa.String(length=3), server_default='KES', nullable=False))
        op.create_check_constraint(f'ck_{table}_currency_kes', table, "currency = 'KES'")

    for table in BRANCH_TABLES:
        op.add_column(table, sa.Column('branch_id', sa.Integer(), server_default='1', nullable=False))
        op.create_foreign_key(f'fk_{table}_branch_id', table, 'branches', ['branch_id'], ['id'], ondelete='RESTRICT')
        op.create_index(f'ix_{table}_branch_id', table, ['branch_id'])


def downgrade():
    for table in BRANCH_TABLES:
        op.drop_index(f'ix_{table}_branch_id', table_name=table)
        op.drop_constraint(f'fk_{table}_branch_id', table, type_='foreignkey')
        op.drop_column(table, 'branch_id')
    for table in MONEY_TABLES:
        op.drop_constraint(f'ck_{table}_currency_kes', table, type_='check')
        op.drop_column(table, 'currency')
    op.drop_table('branches')
