"""Lender keyword list, version 2: common Kenyan lenders and loan products (to be extended by credit)

A new version of ai.statements.lender_keywords (version 1 is kept), effective from the
day the migration runs in Nairobi. Banks' loan repayment narrations, mobile-loan products
(Fuliza, M-Shwari, KCB M-Pesa, Hustler Fund ...), digital lenders (Tala, Branch, Zenka ...)
and microfinance banks. Loan-specific phrases only: version 1's bare "M-SHWARI" also
matched M-Shwari savings deposits, so version 2 uses "M-SHWARI LOAN".

Also: ai_statement_metric_inputs.matched_keyword, the keyword each matched transaction hit.

Revision ID: e5f6a7b8c9db
Revises: d4e5f6a7b8ca
Create Date: 2026-10-18 11:00:00.000000

"""
import json

from alembic import op
import sqlalchemy as sa


revision = 'e5f6a7b8c9db'
down_revision = 'd4e5f6a7b8ca'
branch_labels = None
depends_on = None

# Frozen copy of app/Settings/registry.py KENYAN_LENDER_KEYWORDS.
KEYWORDS = sorted({
    "LOAN REPAYMENT", "LOAN REPAY", "LN REPAYMENT", "LOAN RPYMT", "LOAN INSTALMENT", "LOAN INSTALLMENT",
    "LOAN RECOVERY", "LOAN DEDUCTION", "OVERDRAFT REPAYMENT", "OD LOAN REPAYMENT", "KCB LOAN", "EQUITY LOAN",
    "CO-OP LOAN", "COOP LOAN", "NCBA LOAN", "ABSA LOAN", "STANBIC LOAN", "FAMILY BANK LOAN", "DTB LOAN",
    "I&M LOAN",
    "FULIZA", "M-SHWARI LOAN", "MSHWARI LOAN", "KCB M-PESA LOAN", "KCB MPESA LOAN", "EAZZY LOAN", "EQUITEL LOAN",
    "MCO-OP CASH", "TIMIZA", "PESAPAP LOAN", "HUSTLER FUND", "STAWI",
    "TALA", "BRANCH INTERNATIONAL", "BRANCH MICROFINANCE", "BRANCH LOAN", "ZENKA", "OKOLEA", "ZASH", "IPESA",
    "M-KOPA", "WATU CREDIT", "MOGO", "PLATINUM CREDIT",
    "KWFT", "FAULU", "MUSONI", "SMEP", "LETSHEGO",
})


def upgrade():
    op.add_column('ai_statement_metric_inputs', sa.Column('matched_keyword', sa.String(length=60), nullable=True))
    op.get_bind().execute(sa.text(
        "INSERT INTO setting_versions (key, value, effective_from, version_no, source, evidence, reason, created_by,"
        " approved_by, approved_at) VALUES ('ai.statements.lender_keywords', CAST(:v AS jsonb),"
        " CAST((now() AT TIME ZONE 'Africa/Nairobi') AS date), 2, 'working_assumption',"
        " 'Starting list of Kenyan lenders and loan products seen on bank and M-Pesa statements; TO BE EXTENDED BY "
        "CREDIT (phase 3 brief, 2026-10-18)', 'Seed common Kenyan lenders', 'migration',"
        " 'docs/architecture/08-working-assumptions.md', now())"), {'v': json.dumps(KEYWORDS)})


def downgrade():
    op.execute("ALTER TABLE setting_versions DISABLE TRIGGER trg_setting_versions_insert_only")
    op.execute("DELETE FROM setting_versions WHERE key = 'ai.statements.lender_keywords' AND version_no = 2")
    op.execute("ALTER TABLE setting_versions ENABLE TRIGGER trg_setting_versions_insert_only")
    op.drop_column('ai_statement_metric_inputs', 'matched_keyword')
