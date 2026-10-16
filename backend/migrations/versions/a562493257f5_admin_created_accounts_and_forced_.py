"""admin-created accounts and forced password change

- No public sign-up any more: the 'pending' (awaiting approval) status becomes
  'disabled', and new accounts default to 'active'.
- must_change_password: set on accounts created or reset by a super admin.
  Existing accounts chose their own passwords, so they start as False.

Revision ID: a562493257f5
Revises: 69d9315c13f7
Create Date: 2026-10-01 14:58:40.469411

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a562493257f5'
down_revision = '69d9315c13f7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        # Existing rows get False; the default then flips to True for new accounts.
        batch_op.add_column(sa.Column('must_change_password', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('password_changed_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.alter_column('must_change_password', server_default=sa.true())

        batch_op.drop_constraint('ck_user_status', type_='check')
    op.execute("UPDATE \"user\" SET status = 'disabled' WHERE status = 'pending'")
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.create_check_constraint('ck_user_status', "status IN ('active', 'disabled')")
        batch_op.alter_column('status', server_default='active')


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_constraint('ck_user_status', type_='check')
    op.execute("UPDATE \"user\" SET status = 'pending' WHERE status = 'disabled'")
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.create_check_constraint('ck_user_status', "status IN ('pending', 'active')")
        batch_op.alter_column('status', server_default='pending')
        batch_op.drop_column('password_changed_at')
        batch_op.drop_column('must_change_password')
