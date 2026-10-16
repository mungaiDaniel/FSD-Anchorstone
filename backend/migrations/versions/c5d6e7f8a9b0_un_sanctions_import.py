"""un sanctions import

FSD v0.1 KYC-06, 07 Q-CO6. The UN Security Council consolidated sanctions list
is imported into watchlist_entries (list 'sanctions_un') by the daily job
screening.un_sanctions_import. Each applied file is a sanctions_list_imports
row (the list's dateGenerated is its version). Entries gain the list's
reference number, aliases and details; a delisted entry is marked removed.

The import stays off (screening.un_sanctions.import_enabled = false) and
screening.lists_enabled is unchanged until compliance confirms them.

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-10-16 20:00:00.000000

"""
import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'c5d6e7f8a9b0'
down_revision = 'b4c5d6e7f8a9'
branch_labels = None
depends_on = None

SEED_DATE = '2026-01-01'
SEEDS = [
    ('screening.un_sanctions.import_enabled', False, '07 Q-CO6 / FSD KYC-06: off until compliance confirms'),
    ('screening.un_sanctions.source_url', 'https://scsanctions.un.org/resources/xml/en/consolidated.xml',
     '07 Q-CO6 / FSD KYC-06: the list as published by the UN Security Council'),
]


def upgrade():
    op.create_table('sanctions_list_imports',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('list', sa.String(length=20), nullable=False),
    sa.Column('source', sa.String(length=500), nullable=False),
    sa.Column('list_generated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('content_sha256', sa.String(length=64), nullable=False),
    sa.Column('entries_in_list', sa.Integer(), nullable=False),
    sa.Column('added', sa.Integer(), nullable=False),
    sa.Column('updated', sa.Integer(), nullable=False),
    sa.Column('removed', sa.Integer(), nullable=False),
    sa.Column('imported_by', sa.String(length=120), nullable=False),
    sa.Column('imported_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('date_created', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('date_updated', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("list IN ('sanctions_un')", name='ck_sanctions_list_imports_list'),
    sa.UniqueConstraint('list', 'content_sha256', name='uq_sanctions_list_imports_content'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('watchlist_entries', schema=None) as batch_op:
        batch_op.add_column(sa.Column('external_ref', sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column('aliases', postgresql.JSONB(astext_type=sa.Text()),
                                      server_default=sa.text("'[]'::jsonb"), nullable=False))
        batch_op.add_column(sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
        batch_op.add_column(sa.Column('import_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('watchlist_entries_import_id_fkey', 'sanctions_list_imports', ['import_id'],
                                    ['id'], ondelete='RESTRICT')
        batch_op.create_index('uq_watchlist_entries_external_ref', ['list', 'external_ref'], unique=True,
                              postgresql_where=sa.text("status = 'active' AND external_ref IS NOT NULL"))

    conn = op.get_bind()
    for key, value, evidence in SEEDS:
        conn.execute(sa.text(
            "INSERT INTO setting_versions (key, value, effective_from, version_no, source, evidence, created_by,"
            " approved_by, approved_at) VALUES (:k, CAST(:v AS jsonb), :d, 1, 'working_assumption', :e,"
            " 'migration', 'docs/architecture/08-working-assumptions.md', now())"),
            {'k': key, 'v': json.dumps(value), 'd': SEED_DATE, 'e': evidence})
    conn.execute(sa.text("INSERT INTO periodic_tasks (name, last_slot) VALUES ('screening.un_sanctions_import', now())"))


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM periodic_tasks WHERE name = 'screening.un_sanctions_import'"))
    op.execute("ALTER TABLE setting_versions DISABLE TRIGGER trg_setting_versions_insert_only")
    conn.execute(sa.text("DELETE FROM setting_versions WHERE key = ANY(:k)"), {'k': [k for k, _, _ in SEEDS]})
    op.execute("ALTER TABLE setting_versions ENABLE TRIGGER trg_setting_versions_insert_only")
    with op.batch_alter_table('watchlist_entries', schema=None) as batch_op:
        batch_op.drop_index('uq_watchlist_entries_external_ref',
                            postgresql_where=sa.text("status = 'active' AND external_ref IS NOT NULL"))
        batch_op.drop_constraint('watchlist_entries_import_id_fkey', type_='foreignkey')
        batch_op.drop_column('import_id')
        batch_op.drop_column('details')
        batch_op.drop_column('aliases')
        batch_op.drop_column('external_ref')
    op.drop_table('sanctions_list_imports')
