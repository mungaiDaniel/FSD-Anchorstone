"""Pre-selection rule set version 2: rule 10, collateral owner (WA-10 now has 10 rules)

A NEW version of the setting screening.rule_set (version 1 is kept, and the runs that
used it keep their copy). Rule 10: "Collateral owner is the applicant or a guarantor",
failed outcome Needs review, for the secured products (business loan, asset finance; the
bridge loan has no collateral in WA-04, so the rule is not applicable to it).

Seeded the way every setting is seeded (maker 'migration', approval reference
08-working-assumptions.md, with its evidence), effective from the day the migration
runs in Nairobi: never backdated.

Revision ID: d4e5f6a7b8ca
Revises: c3d4e5f6a7b9
Create Date: 2026-10-18 10:00:00.000000

"""
import json

from alembic import op
import sqlalchemy as sa


revision = 'd4e5f6a7b8ca'
down_revision = 'c3d4e5f6a7b9'
branch_labels = None
depends_on = None

RULE_10 = {"id": "R10", "description": "Collateral owner is the applicant or a guarantor",
           "metric": "collateral_owner_match", "comparison": "==", "threshold": "pass",
           "outcome_if_failed": "needs_review", "applies_to": {"products": ["asset_finance", "business_loan"]}}


def upgrade():
    conn = op.get_bind()
    v1 = conn.execute(sa.text("SELECT value FROM setting_versions WHERE key = 'screening.rule_set' AND version_no = 1 "
                              "AND scope_type = 'global'")).scalar()
    rules = (v1 if isinstance(v1, dict) else json.loads(v1))["rules"] + [RULE_10]
    conn.execute(sa.text(
        "INSERT INTO setting_versions (key, value, effective_from, version_no, source, evidence, reason, created_by,"
        " approved_by, approved_at) VALUES ('screening.rule_set', CAST(:v AS jsonb),"
        " CAST((now() AT TIME ZONE 'Africa/Nairobi') AS date), 2, 'internal_decision',"
        " 'WA-10 updated 2026-10-18 (phase 3 brief): rule 10, collateral owner is the applicant or a guarantor',"
        " 'Collateral-owner cross-check becomes a pre-selection rule (failed: Needs review)', 'migration',"
        " 'docs/architecture/08-working-assumptions.md', now())"), {'v': json.dumps({"rules": rules})})


def downgrade():
    op.execute("ALTER TABLE setting_versions DISABLE TRIGGER trg_setting_versions_insert_only")
    op.execute("DELETE FROM setting_versions WHERE key = 'screening.rule_set' AND version_no = 2")
    op.execute("ALTER TABLE setting_versions ENABLE TRIGGER trg_setting_versions_insert_only")
