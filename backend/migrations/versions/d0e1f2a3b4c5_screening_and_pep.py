"""screening and pep

Phase 2b item 3 (FSD v0.1 KYC-05, 06, 07). Watchlists (internal blacklist and
PEP list; the UN sanctions list once its import is built), a screening result
per check with a review that the onboarding maker can't do (CHECK constraint),
and the extra PEP details approved by two senior approvers (party.pep_approve).
Removing a watchlist entry is a change request (watchlist.remove). The daily
re-screen of existing clients is the periodic task screening.rescreen.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-10-16 16:30:00.000000

"""
import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'd0e1f2a3b4c5'
down_revision = 'c9d0e1f2a3b4'
branch_labels = None
depends_on = None

SEED_DATE = '2026-01-01'
PERMISSIONS = [
    ('screening.review', 'Clear or confirm a possible watchlist match (checker)', ('admin', 'super_admin')),
    ('watchlist.manage', 'Add names to the watchlists and request removals', ('admin', 'super_admin')),
    ('kyc.pep.approve', "Approve a politically exposed person's details (senior approver)", ('admin', 'super_admin')),
]
POLICIES = [
    ('party.pep_approve', [{'permission': 'kyc.pep.approve', 'count': 2}],
     'Two senior approvers, neither of them the maker, approve PEP details (FSD KYC-07).'),
    ('screening.review', [{'permission': 'screening.review', 'count': 1}],
     'A manager other than the onboarding maker reviews a watchlist match (FSD KYC-06).'),
    ('watchlist.remove', [{'permission': 'watchlist.manage', 'count': 1}],
     'A second person approves taking a name off a watchlist.'),
]
SEEDS = [('screening.lists_enabled', ['internal_blacklist', 'pep'], '07 Q-CO6 / FSD KYC-06')]


def upgrade():
    op.create_table('watchlist_entries',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('list', sa.String(length=20), nullable=False),
    sa.Column('full_name', sa.String(length=200), nullable=False),
    sa.Column('name_normalised', sa.String(length=200), nullable=False),
    sa.Column('identifiers', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('source', sa.String(length=200), nullable=True),
    sa.Column('status', sa.String(length=10), server_default='active', nullable=False),
    sa.Column('added_by', sa.String(length=120), nullable=False),
    sa.Column('added_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('removed_by', sa.String(length=120), nullable=True),
    sa.Column('removed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('date_created', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('date_updated', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("list IN ('internal_blacklist', 'pep', 'sanctions_un')", name='ck_watchlist_entries_list'),
    sa.CheckConstraint("status IN ('active', 'removed')", name='ck_watchlist_entries_status'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('watchlist_entries', schema=None) as batch_op:
        batch_op.create_index('ix_watchlist_entries_name', ['name_normalised'], unique=False)

    op.create_table('party_pep_details',
    sa.Column('party_id', sa.Integer(), nullable=False),
    sa.Column('position_held', sa.String(length=200), nullable=False),
    sa.Column('country', sa.String(length=2), server_default='KE', nullable=False),
    sa.Column('since', sa.Date(), nullable=True),
    sa.Column('until', sa.Date(), nullable=True),
    sa.Column('pep_relationship', sa.String(length=16), nullable=False),
    sa.Column('related_pep_name', sa.String(length=200), nullable=True),
    sa.Column('source_of_funds', sa.Text(), nullable=False),
    sa.Column('source_of_wealth', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=10), server_default='pending', nullable=False),
    sa.Column('recorded_by', sa.String(length=120), nullable=False),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('approved_by', sa.String(length=250), nullable=True),
    sa.Column('date_created', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('date_updated', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(status = 'approved') = (approved_at IS NOT NULL)", name='ck_party_pep_details_approved'),
    sa.CheckConstraint("pep_relationship = 'self' OR related_pep_name IS NOT NULL", name='ck_party_pep_details_related'),
    sa.CheckConstraint("pep_relationship IN ('self', 'family_member', 'close_associate')", name='ck_party_pep_details_relationship'),
    sa.CheckConstraint("status IN ('pending', 'approved', 'cleared')", name='ck_party_pep_details_status'),
    sa.ForeignKeyConstraint(['party_id'], ['parties.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('party_id')
    )
    op.create_table('screening_results',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('party_id', sa.Integer(), nullable=False),
    sa.Column('trigger', sa.String(length=20), nullable=False),
    sa.Column('lists', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('matches', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('outcome', sa.String(length=16), nullable=False),
    sa.Column('review_status', sa.String(length=12), nullable=False),
    sa.Column('maker_email', sa.String(length=120), nullable=False),
    sa.Column('screened_by', sa.String(length=120), nullable=False),
    sa.Column('screened_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('reviewed_by', sa.String(length=120), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('review_note', sa.Text(), nullable=True),
    sa.Column('date_created', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('date_updated', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(outcome = 'clear') = (review_status = 'not_required')", name='ck_screening_results_review_needed'),
    sa.CheckConstraint("(review_status IN ('cleared', 'confirmed')) = (reviewed_by IS NOT NULL)", name='ck_screening_results_reviewed'),
    sa.CheckConstraint("outcome IN ('clear', 'potential_match')", name='ck_screening_results_outcome'),
    sa.CheckConstraint("review_status IN ('not_required', 'pending', 'cleared', 'confirmed')", name='ck_screening_results_review'),
    sa.CheckConstraint("trigger IN ('onboarding', 'identity_change', 'watchlist_change', 'rescreen')", name='ck_screening_results_trigger'),
    sa.CheckConstraint('reviewed_by IS NULL OR lower(reviewed_by) <> lower(maker_email)', name='ck_screening_results_maker_not_checker'),
    sa.ForeignKeyConstraint(['party_id'], ['parties.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('screening_results', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_screening_results_party_id'), ['party_id'], unique=False)
        batch_op.create_index('ix_screening_results_pending', ['review_status'], unique=False)

    conn = op.get_bind()
    for code, desc, legacy in PERMISSIONS:
        conn.execute(sa.text("INSERT INTO permissions (code, module, description, sensitive) "
                             "VALUES (:c, 'parties', :d, false)"), {'c': code, 'd': desc})
        conn.execute(sa.text("INSERT INTO role_permissions (role_id, permission_code) SELECT id, :c FROM roles "
                             "WHERE legacy_role = ANY(:l)"), {'c': code, 'l': list(legacy)})
    for request_type, levels, desc in POLICIES:
        conn.execute(sa.text("INSERT INTO approval_policies (request_type, levels, description) "
                             "VALUES (:t, CAST(:l AS jsonb), :d)"), {'t': request_type, 'l': json.dumps(levels), 'd': desc})
    for key, value, evidence in SEEDS:
        conn.execute(sa.text(
            "INSERT INTO setting_versions (key, value, effective_from, version_no, source, evidence, created_by,"
            " approved_by, approved_at) VALUES (:k, CAST(:v AS jsonb), :d, 1, 'working_assumption', :e,"
            " 'migration', 'docs/architecture/08-working-assumptions.md', now())"),
            {'k': key, 'v': json.dumps(value), 'd': SEED_DATE, 'e': evidence})
    conn.execute(sa.text("INSERT INTO periodic_tasks (name, last_slot) VALUES ('screening.rescreen', now())"))


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM periodic_tasks WHERE name = 'screening.rescreen'"))
    op.execute("ALTER TABLE setting_versions DISABLE TRIGGER trg_setting_versions_insert_only")
    conn.execute(sa.text("DELETE FROM setting_versions WHERE key = ANY(:k)"), {'k': [k for k, _, _ in SEEDS]})
    op.execute("ALTER TABLE setting_versions ENABLE TRIGGER trg_setting_versions_insert_only")
    conn.execute(sa.text("DELETE FROM approval_policies WHERE request_type = ANY(:t)"), {'t': [p[0] for p in POLICIES]})
    conn.execute(sa.text("DELETE FROM role_permissions WHERE permission_code = ANY(:c)"), {'c': [p[0] for p in PERMISSIONS]})
    conn.execute(sa.text("DELETE FROM permissions WHERE code = ANY(:c)"), {'c': [p[0] for p in PERMISSIONS]})
    with op.batch_alter_table('screening_results', schema=None) as batch_op:
        batch_op.drop_index('ix_screening_results_pending')
        batch_op.drop_index(batch_op.f('ix_screening_results_party_id'))

    op.drop_table('screening_results')
    op.drop_table('party_pep_details')
    with op.batch_alter_table('watchlist_entries', schema=None) as batch_op:
        batch_op.drop_index('ix_watchlist_entries_name')

    op.drop_table('watchlist_entries')
