"""party consents

Phase 2b item 5 (Kenya DPA; FSD v0.1 AI-01; 05 §9.1). A consent per client and
purpose (KYC processing, automatic document reading, credit bureau checks,
marketing) with the date, method, who captured it, the notice version shown and,
for a signed form, the scanned form. Withdrawal is recorded on the row; consents
are never deleted.

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-10-16 17:30:00.000000

"""
import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'f2a3b4c5d6e7'
down_revision = 'e1f2a3b4c5d6'
branch_labels = None
depends_on = None

SEED_DATE = '2026-01-01'
GUARD = """
CREATE FUNCTION party_consents_refuse_delete() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Consents are never deleted; record a withdrawal instead.'
        USING ERRCODE = 'insufficient_privilege';
END
$$ LANGUAGE plpgsql;
CREATE TRIGGER trg_party_consents_no_delete BEFORE DELETE ON party_consents
    FOR EACH ROW EXECUTE FUNCTION party_consents_refuse_delete();
"""


def upgrade():
    op.create_table('party_consents',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('party_id', sa.Integer(), nullable=False),
    sa.Column('purpose', sa.String(length=30), nullable=False),
    sa.Column('granted_on', sa.Date(), nullable=False),
    sa.Column('method', sa.String(length=12), nullable=False),
    sa.Column('notice_version', sa.String(length=30), nullable=False),
    sa.Column('evidence_document_id', sa.UUID(), nullable=True),
    sa.Column('captured_by', sa.String(length=120), nullable=False),
    sa.Column('captured_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.String(length=10), server_default='active', nullable=False),
    sa.Column('withdrawn_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('withdrawn_by', sa.String(length=120), nullable=True),
    sa.Column('withdrawal_note', sa.Text(), nullable=True),
    sa.Column('date_created', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('date_updated', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(status = 'withdrawn') = (withdrawn_at IS NOT NULL)", name='ck_party_consents_withdrawn'),
    sa.CheckConstraint("method <> 'signed_form' OR evidence_document_id IS NOT NULL", name='ck_party_consents_signed_form_evidence'),
    sa.CheckConstraint("method IN ('signed_form', 'in_branch', 'email')", name='ck_party_consents_method'),
    sa.CheckConstraint("purpose IN ('kyc_processing', 'ai_document_processing', 'credit_bureau_check', 'marketing')", name='ck_party_consents_purpose'),
    sa.CheckConstraint("status IN ('active', 'withdrawn')", name='ck_party_consents_status'),
    sa.ForeignKeyConstraint(['evidence_document_id'], ['documents.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['party_id'], ['parties.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('party_consents', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_party_consents_party_id'), ['party_id'], unique=False)
        batch_op.create_index('uq_party_consents_active', ['party_id', 'purpose'], unique=True, postgresql_where=sa.text("status = 'active'"))

    op.execute(GUARD)
    conn = op.get_bind()
    conn.execute(sa.text("INSERT INTO permissions (code, module, description, sensitive) "
                         "VALUES ('consent.capture', 'parties', 'Record and withdraw client consent', false)"))
    conn.execute(sa.text("INSERT INTO role_permissions (role_id, permission_code) SELECT id, 'consent.capture' "
                         "FROM roles WHERE legacy_role IN ('user', 'admin', 'super_admin')"))
    conn.execute(sa.text(
        "INSERT INTO setting_versions (key, value, effective_from, version_no, source, evidence, created_by,"
        " approved_by, approved_at) VALUES ('consent.notice_version', CAST(:v AS jsonb), :d, 1, 'working_assumption',"
        " '07 Q-CO1', 'migration', 'docs/architecture/08-working-assumptions.md', now())"),
        {'v': json.dumps('v1'), 'd': SEED_DATE})


def downgrade():
    conn = op.get_bind()
    op.execute("ALTER TABLE setting_versions DISABLE TRIGGER trg_setting_versions_insert_only")
    conn.execute(sa.text("DELETE FROM setting_versions WHERE key = 'consent.notice_version'"))
    op.execute("ALTER TABLE setting_versions ENABLE TRIGGER trg_setting_versions_insert_only")
    conn.execute(sa.text("DELETE FROM role_permissions WHERE permission_code = 'consent.capture'"))
    conn.execute(sa.text("DELETE FROM permissions WHERE code = 'consent.capture'"))
    op.execute("DROP TRIGGER IF EXISTS trg_party_consents_no_delete ON party_consents")
    with op.batch_alter_table('party_consents', schema=None) as batch_op:
        batch_op.drop_index('uq_party_consents_active', postgresql_where=sa.text("status = 'active'"))
        batch_op.drop_index(batch_op.f('ix_party_consents_party_id'))

    op.drop_table('party_consents')
    op.execute("DROP FUNCTION IF EXISTS party_consents_refuse_delete()")
