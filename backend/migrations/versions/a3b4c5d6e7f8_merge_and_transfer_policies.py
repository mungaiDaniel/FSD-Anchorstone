"""merge and transfer policies

Phase 2b item 7 (FSD v0.1 KYC-10, KYC-12). Merging duplicate clients and
moving a client to another branch are change requests approved by someone
holding party.change.approve other than the maker.

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-10-16 18:00:00.000000

"""
import json

from alembic import op
import sqlalchemy as sa


revision = 'a3b4c5d6e7f8'
down_revision = 'f2a3b4c5d6e7'
branch_labels = None
depends_on = None

POLICIES = [
    ('party.merge', 'A second person approves merging duplicate clients (FSD KYC-10).'),
    ('party.branch_transfer', 'A second person approves moving a client to another branch (FSD KYC-12).'),
]


def upgrade():
    conn = op.get_bind()
    for request_type, desc in POLICIES:
        conn.execute(sa.text("INSERT INTO approval_policies (request_type, levels, description) "
                             "VALUES (:t, CAST(:l AS jsonb), :d)"),
                     {'t': request_type, 'd': desc,
                      'l': json.dumps([{'permission': 'party.change.approve', 'count': 1}])})


def downgrade():
    op.get_bind().execute(sa.text("DELETE FROM approval_policies WHERE request_type = ANY(:t)"),
                          {'t': [p[0] for p in POLICIES]})
