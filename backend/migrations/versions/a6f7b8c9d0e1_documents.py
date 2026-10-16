"""encrypted document storage

Phase 2a item 6 (ADR-04-2). documents (metadata and the wrapped data key; the
bytes live encrypted in a DocumentStore), document_links and data_access_logs.
The database refuses deleting a document or changing a destroyed one, and
data_access_logs is insert-only. Destruction is a change request
(document.destroy) approved by someone other than the maker.

Revision ID: a6f7b8c9d0e1
Revises: f5e6a7b8c9d0
Create Date: 2026-10-16 20:00:00.000000

"""
import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'a6f7b8c9d0e1'
down_revision = 'f5e6a7b8c9d0'
branch_labels = None
depends_on = None

PERMISSIONS = [
    ('document.upload', 'Upload documents', False, ('user', 'admin', 'super_admin')),
    ('document.view', 'Open documents', True, ('user', 'admin', 'super_admin')),
    ('document.view.sensitive', 'Open sensitive documents (IDs, financial statements)', True, ('admin', 'super_admin')),
    ('document.destroy.request', 'Request that a document be destroyed (maker)', False, ('admin', 'super_admin')),
    ('document.destroy.approve', 'Approve destroying a document (checker)', False, ('super_admin',)),
]

TRIGGERS = """
CREATE FUNCTION documents_guard() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Documents are never deleted; destroy them through a change request.'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF OLD.status = 'destroyed' THEN
        RAISE EXCEPTION 'Document % was destroyed and can''t be changed.', OLD.id
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NEW.sha256 <> OLD.sha256 OR NEW.storage_key <> OLD.storage_key OR NEW.nonce <> OLD.nonce
       OR NEW.size_bytes <> OLD.size_bytes OR NEW.uploaded_by <> OLD.uploaded_by THEN
        RAISE EXCEPTION 'A document''s content and origin can''t be changed; upload a new version.'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_documents_guard BEFORE UPDATE OR DELETE ON documents
    FOR EACH ROW EXECUTE FUNCTION documents_guard();

CREATE TRIGGER trg_data_access_logs_insert_only BEFORE UPDATE OR DELETE ON data_access_logs
    FOR EACH ROW EXECUTE FUNCTION refuse_update_delete();
"""


def _ts():
    return [
        sa.Column('date_created', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('date_updated', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    ]


def upgrade():
    op.create_table(
        'documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('storage_backend', sa.String(20), nullable=False),
        sa.Column('storage_key', sa.String(200), nullable=False, unique=True),
        sa.Column('document_type', sa.String(50), nullable=False),
        sa.Column('original_filename', sa.String(255), nullable=False),
        sa.Column('content_type', sa.String(100), nullable=False),
        sa.Column('size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('sha256', sa.String(64), nullable=False),
        sa.Column('wrapped_data_key', sa.LargeBinary(), nullable=True),
        sa.Column('key_id', sa.String(50), nullable=False),
        sa.Column('nonce', sa.LargeBinary(), nullable=False),
        sa.Column('sensitive', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('status', sa.String(10), server_default='active', nullable=False),
        sa.Column('retention_until', sa.Date(), nullable=True),
        sa.Column('legal_hold', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('uploaded_by', sa.String(120), nullable=False),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('destroyed_by', sa.String(120), nullable=True),
        sa.Column('destroyed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('destroy_reason', sa.Text(), nullable=True),
        *_ts(),
        sa.CheckConstraint("status IN ('active', 'destroyed')", name='ck_documents_status'),
        sa.CheckConstraint("(status = 'destroyed') = (wrapped_data_key IS NULL)", name='ck_documents_key_iff_active'),
        sa.CheckConstraint('size_bytes >= 0', name='ck_documents_size'),
        sa.CheckConstraint('char_length(sha256) = 64', name='ck_documents_sha256'),
    )
    op.create_table(
        'document_links',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='RESTRICT'),
                  nullable=False),
        sa.Column('entity_type', sa.String(50), nullable=False),
        sa.Column('entity_id', sa.String(64), nullable=False),
        sa.Column('purpose', sa.String(50), server_default='kyc', nullable=False),
        sa.Column('linked_by', sa.String(120), nullable=False),
        *_ts(),
        sa.UniqueConstraint('document_id', 'entity_type', 'entity_id', 'purpose', name='uq_document_links'),
    )
    op.create_index('ix_document_links_entity', 'document_links', ['entity_type', 'entity_id'])
    op.create_table(
        'data_access_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='RESTRICT'), nullable=True),
        sa.Column('user_email', sa.String(120), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='RESTRICT'),
                  nullable=True),
        sa.Column('entity_type', sa.String(50), nullable=True),
        sa.Column('entity_id', sa.String(64), nullable=True),
        sa.Column('action', sa.String(10), nullable=False),
        sa.Column('out_of_portfolio', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('ip_address', sa.String(64), nullable=True),
        sa.Column('user_agent', sa.String(255), nullable=True),
        sa.Column('at', sa.DateTime(timezone=True), nullable=False),
        *_ts(),
        sa.CheckConstraint("action IN ('view', 'download', 'upload', 'destroy')", name='ck_data_access_logs_action'),
    )
    op.create_index('ix_data_access_logs_document', 'data_access_logs', ['document_id', 'at'])
    op.execute(TRIGGERS)

    conn = op.get_bind()
    for code, desc, sensitive, legacy in PERMISSIONS:
        conn.execute(sa.text("INSERT INTO permissions (code, module, description, sensitive) "
                             "VALUES (:c, 'documents', :d, :s)"), {'c': code, 'd': desc, 's': sensitive})
        conn.execute(sa.text("INSERT INTO role_permissions (role_id, permission_code) SELECT id, :c FROM roles "
                             "WHERE legacy_role = ANY(:l)"), {'c': code, 'l': list(legacy)})
    conn.execute(sa.text("INSERT INTO approval_policies (request_type, levels, description) VALUES "
                         "('document.destroy', CAST(:l AS jsonb), 'A second person approves destroying a document.')"),
                 {'l': json.dumps([{'permission': 'document.destroy.approve', 'count': 1}])})


def downgrade():
    op.execute("DELETE FROM approval_policies WHERE request_type = 'document.destroy'")
    op.execute("DELETE FROM role_permissions WHERE permission_code LIKE 'document.%'")
    op.execute("DELETE FROM permissions WHERE code LIKE 'document.%'")
    op.drop_table('data_access_logs')
    op.drop_table('document_links')
    op.drop_table('documents')
    op.execute("DROP FUNCTION IF EXISTS documents_guard()")
