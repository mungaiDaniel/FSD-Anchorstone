"""deposit reversal notice: at most once per deposit

A DEPOSIT_REVERSAL email must name its deposit, and there can be only one per
deposit (partial unique index; the check stops a NULL deposit_id slipping past it).

Revision ID: e080731771c7
Revises: 597aa1c2e2ae
Create Date: 2026-10-16 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e080731771c7'
down_revision = '597aa1c2e2ae'
branch_labels = None
depends_on = None


def upgrade():
    op.create_check_constraint(
        'ck_email_outbox_reversal_has_deposit', 'email_outbox',
        "email_type <> 'DEPOSIT_REVERSAL' OR deposit_id IS NOT NULL",
    )
    op.create_index(
        'uq_email_outbox_deposit_reversal', 'email_outbox', ['deposit_id'], unique=True,
        postgresql_where=sa.text("email_type = 'DEPOSIT_REVERSAL'"),
    )


def downgrade():
    op.drop_index('uq_email_outbox_deposit_reversal', table_name='email_outbox')
    op.drop_constraint('ck_email_outbox_reversal_has_deposit', 'email_outbox', type_='check')
