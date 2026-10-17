"""Pre-selection rules and credit decisions (phase 3b, AI-08, AI-09, AI-11)

- setting screening.rule_set, version 1 = the nine starting rules of WA-10 as data.
  Changing it is a settings.change request: a new, immutable version, whose id each
  screening run records.
- permissions credit.decide (record proceed / decline / more info) and
  credit.override.approve (approve proceeding against a Not qualified recommendation),
  admin and up until the FSD credit roles are switched on
- approval policy credit.override: one level, credit.override.approve

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f7
Create Date: 2026-10-17 18:00:00.000000

"""
import json

from alembic import op
import sqlalchemy as sa


revision = 'b2c3d4e5f6a8'
down_revision = 'a1b2c3d4e5f7'
branch_labels = None
depends_on = None

# A frozen copy of app/Applications/ruleset.py DEFAULT_RULE_SET (WA-10, exactly as written).
RULE_SET_V1 = {"rules": [
    {"id": "R1", "description": "Time in business at least 12 months", "metric": "months_in_business",
     "comparison": ">=", "threshold": 12, "outcome_if_failed": "not_qualified"},
    {"id": "R2", "description": "Average monthly inflows (6 months) at least 3 × instalment",
     "metric": "avg_monthly_inflow_6m", "comparison": ">=", "threshold": {"times": 3, "of": "estimated_instalment"},
     "outcome_if_failed": "needs_review"},
    {"id": "R3", "description": "CRB: listed → Not qualified; cleared → Needs review", "metric": "crb_status",
     "comparison": "==", "threshold": "clear",
     "outcome_if_failed": {"listed": "not_qualified", "previously_listed_cleared": "needs_review"}},
    {"id": "R4", "description": "Forced-sale cover at least 125%", "metric": "forced_sale_cover_percent",
     "comparison": ">=", "threshold": 125, "outcome_if_failed": "needs_review",
     "applies_to": {"products": ["asset_finance", "business_loan"]}},
    {"id": "R5", "description": "Age 18 to 70 at maturity", "metric": "age_at_maturity", "comparison": "between",
     "threshold": [18, 70], "outcome_if_failed": "not_qualified", "applies_to": {"party_types": ["person"]}},
    {"id": "R6", "description": "Name and ID consistent across documents", "metric": "identity_consistent",
     "comparison": "==", "threshold": "pass", "outcome_if_failed": "needs_review"},
    {"id": "R7", "description": "CR12 directors match the directors captured", "metric": "cr12_directors_match",
     "comparison": "==", "threshold": "pass", "outcome_if_failed": "needs_review",
     "applies_to": {"party_types": ["organisation"]}},
    {"id": "R8", "description": "Bounced items at most 2 in 6 months", "metric": "returned_items_6m",
     "comparison": "<=", "threshold": 2, "outcome_if_failed": "needs_review"},
    {"id": "R9", "description": "Other lenders' repayments below 50% of inflows", "metric": "lender_repayment_share_6m",
     "comparison": "<", "threshold": "0.50", "outcome_if_failed": "needs_review"},
]}
PERMISSIONS = (
    ('credit.decide', 'Record the credit decision on a pre-screened application (with a reason)'),
    ('credit.override.approve', 'Approve proceeding with an application the rules recommended Not qualified'),
)


def upgrade():
    conn = op.get_bind()
    for code, description in PERMISSIONS:
        conn.execute(sa.text("INSERT INTO permissions (code, module, description, sensitive) "
                             "VALUES (:c, 'applications', :d, true)"), {'c': code, 'd': description})
        conn.execute(sa.text("INSERT INTO role_permissions (role_id, permission_code) SELECT id, :c "
                             "FROM roles WHERE legacy_role IN ('admin', 'super_admin')"), {'c': code})
    conn.execute(sa.text(
        "INSERT INTO approval_policies (request_type, levels, description) VALUES ('credit.override', "
        "CAST(:l AS jsonb), 'A second credit approver for proceeding against a Not qualified recommendation "
        "(05 §7.4).')"), {'l': json.dumps([{'permission': 'credit.override.approve', 'count': 1}])})
    conn.execute(sa.text(
        "INSERT INTO setting_versions (key, value, effective_from, version_no, source, evidence, created_by,"
        " approved_by, approved_at) VALUES ('screening.rule_set', CAST(:v AS jsonb), '2026-01-01', 1,"
        " 'working_assumption', 'WA-10 / FSD §5.3 starting pre-selection rules', 'migration',"
        " 'docs/architecture/08-working-assumptions.md', now())"), {'v': json.dumps(RULE_SET_V1)})


def downgrade():
    conn = op.get_bind()
    op.execute("ALTER TABLE setting_versions DISABLE TRIGGER trg_setting_versions_insert_only")
    conn.execute(sa.text("DELETE FROM setting_versions WHERE key = 'screening.rule_set'"))
    op.execute("ALTER TABLE setting_versions ENABLE TRIGGER trg_setting_versions_insert_only")
    conn.execute(sa.text("DELETE FROM approval_policies WHERE request_type = 'credit.override'"))
    codes = [c for c, _ in PERMISSIONS]
    conn.execute(sa.text("DELETE FROM role_permissions WHERE permission_code = ANY(:c)"), {'c': codes})
    conn.execute(sa.text("DELETE FROM permissions WHERE code = ANY(:c)"), {'c': codes})
