"""account holds

Phase 2b acceptance criterion 9 (02-domain-model §1.2). Money set aside on an
account reduces the available balance without moving money. A pending
withdrawal is the first kind of hold: requesting places it, approving or
rejecting releases it. Every withdrawal pending now gets its hold here, placed
by the person who requested it, so available balances are unchanged.

A hold is placed once and released once; a trigger refuses any other change,
and deleting one.

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-10-16 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b4c5d6e7f8a9'
down_revision = 'a3b4c5d6e7f8'
branch_labels = None
depends_on = None

TRIGGERS = """
CREATE FUNCTION account_holds_guard() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Account holds are never deleted; release them.'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF OLD.released_at IS NOT NULL THEN
        RAISE EXCEPTION 'Account hold % was already released and can''t be changed.', OLD.id
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NEW.account_id <> OLD.account_id OR NEW.amount <> OLD.amount OR NEW.reason <> OLD.reason
       OR NEW.reference_type IS DISTINCT FROM OLD.reference_type
       OR NEW.reference_id IS DISTINCT FROM OLD.reference_id
       OR NEW.placed_by <> OLD.placed_by OR NEW.placed_at <> OLD.placed_at THEN
        RAISE EXCEPTION 'An account hold can only be released; place a new hold instead.'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_account_holds_guard BEFORE UPDATE OR DELETE ON account_holds
    FOR EACH ROW EXECUTE FUNCTION account_holds_guard();
"""


def upgrade():
    op.create_table(
        'account_holds',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('accounts.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('amount', sa.Numeric(20, 2), nullable=False),
        sa.Column('reason', sa.String(24), nullable=False),
        sa.Column('reference_type', sa.String(30), nullable=True),
        sa.Column('reference_id', sa.Integer(), nullable=True),
        sa.Column('placed_by', sa.String(120), nullable=False),
        sa.Column('placed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('released_by', sa.String(120), nullable=True),
        sa.Column('released_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('date_created', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('date_updated', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('amount > 0', name='ck_account_holds_amount_positive'),
        sa.CheckConstraint("reason IN ('loan_lien', 'legal', 'written_off_recovery', 'pending_withdrawal')",
                           name='ck_account_holds_reason'),
        sa.CheckConstraint('(released_at IS NULL) = (released_by IS NULL)', name='ck_account_holds_released'),
        sa.CheckConstraint('(reference_type IS NULL) = (reference_id IS NULL)', name='ck_account_holds_reference'),
    )
    op.create_index('ix_account_holds_account_id', 'account_holds', ['account_id'])
    op.create_index('uq_account_holds_reference', 'account_holds', ['reason', 'reference_type', 'reference_id'],
                    unique=True, postgresql_where=sa.text('reference_id IS NOT NULL'))
    op.create_index('ix_account_holds_active', 'account_holds', ['account_id'],
                    postgresql_where=sa.text('released_at IS NULL'))
    op.execute(TRIGGERS)

    op.execute("""
        INSERT INTO account_holds (account_id, amount, reason, reference_type, reference_id, placed_by, placed_at)
        SELECT i.account_id, w.amount, 'pending_withdrawal', 'withdrawal', w.id, w.requested_by, w.created_at
        FROM withdrawals w JOIN investors i ON i.id = w.investor_id
        WHERE w.status = 'pending'
    """)


def downgrade():
    op.drop_table('account_holds')
    op.execute('DROP FUNCTION account_holds_guard()')
