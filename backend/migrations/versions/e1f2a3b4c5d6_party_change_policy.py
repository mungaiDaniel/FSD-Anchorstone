"""party change policy

Phase 2b item 4 (FSD v0.1 KYC-08, WA-01). Changes to a client's identity, bank
and payout details (the groups in kyc.maker_checker_fields) are party.change
requests, approved by someone holding party.change.approve other than the maker.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-10-16 17:00:00.000000

"""
import json

from alembic import op
import sqlalchemy as sa


revision = 'e1f2a3b4c5d6'
down_revision = 'd0e1f2a3b4c5'
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().execute(sa.text(
        "INSERT INTO approval_policies (request_type, levels, description) VALUES "
        "('party.change', CAST(:l AS jsonb), 'A second person approves changes to client identity, bank and payout "
        "details (FSD KYC-08, WA-01).')"), {'l': json.dumps([{'permission': 'party.change.approve', 'count': 1}])})


def downgrade():
    op.execute("DELETE FROM approval_policies WHERE request_type = 'party.change'")
