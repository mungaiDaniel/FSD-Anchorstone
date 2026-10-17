"""AI review maker-checker (phase 3b, AI-07)

Staff review an AI reading (accept / correct / not present); a different person
approves it (change request ai.review) before anything is written to the client.

- permissions ai.review (the reviewer) and ai.review.approve (the approver), admin
  and up, like the sensitive documents they read
- approval policy for ai.review: one level, ai.review.approve
- setting ai.review.confidence_threshold, version 1 = 0.85

Revision ID: a1b2c3d4e5f7
Revises: f157c466eb8c
Create Date: 2026-10-17 16:00:00.000000

"""
import json

from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5f7'
down_revision = 'f157c466eb8c'
branch_labels = None
depends_on = None

PERMISSIONS = (
    ('ai.review', 'Review what the AI read from a document (accept or correct each value)'),
    ('ai.review.approve', 'Approve a review done by someone else, saving confirmed values to the client'),
)


def upgrade():
    conn = op.get_bind()
    for code, description in PERMISSIONS:
        conn.execute(sa.text("INSERT INTO permissions (code, module, description, sensitive) "
                             "VALUES (:c, 'docai', :d, true)"), {'c': code, 'd': description})
        conn.execute(sa.text("INSERT INTO role_permissions (role_id, permission_code) SELECT id, :c "
                             "FROM roles WHERE legacy_role IN ('admin', 'super_admin')"), {'c': code})
    conn.execute(sa.text(
        "INSERT INTO approval_policies (request_type, levels, description) VALUES ('ai.review', CAST(:l AS jsonb), "
        "'A second person approves a review of AI-read values before they reach the client record (05 §8).')"),
        {'l': json.dumps([{'permission': 'ai.review.approve', 'count': 1}])})
    conn.execute(sa.text(
        "INSERT INTO setting_versions (key, value, effective_from, version_no, source, evidence, created_by,"
        " approved_by, approved_at) VALUES ('ai.review.confidence_threshold', CAST(:v AS jsonb), '2026-01-01', 1,"
        " 'working_assumption', '07 Q-C8; phase 3b brief (default 0.85)', 'migration',"
        " 'docs/architecture/08-working-assumptions.md', now())"), {'v': json.dumps('0.85')})


def downgrade():
    conn = op.get_bind()
    op.execute("ALTER TABLE setting_versions DISABLE TRIGGER trg_setting_versions_insert_only")
    conn.execute(sa.text("DELETE FROM setting_versions WHERE key = 'ai.review.confidence_threshold'"))
    op.execute("ALTER TABLE setting_versions ENABLE TRIGGER trg_setting_versions_insert_only")
    conn.execute(sa.text("DELETE FROM approval_policies WHERE request_type = 'ai.review'"))
    codes = [c for c, _ in PERMISSIONS]
    conn.execute(sa.text("DELETE FROM role_permissions WHERE permission_code = ANY(:c)"), {'c': codes})
    conn.execute(sa.text("DELETE FROM permissions WHERE code = ANY(:c)"), {'c': codes})
