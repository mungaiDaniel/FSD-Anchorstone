"""
Pre-screen loan applications (phase 3b; 05 §1, §7). TEMPORARY: a minimal shell
for AI pre-selection. Phase 5's product engine replaces the product list, the
term limits and the instalment ESTIMATE (06-phase-plan.md).

    loan_applications            applicant, product (WA-04), amount, term, indicative
                                 rate, estimated instalment
    application_parties          guarantors (for the collateral-owner check)
    application_crb_statuses     CRB status entered by staff or proposed from a CRB report;
                                 confirmed by a second person (application.crb_confirm)
    extraction_reviews           a reviewer's accept / correct of one AI extraction, approved
      field_reviews              by a different user (change request ai.review); corrections
      transaction_reviews        sit beside the AI values, never replacing them
    screening_runs               one evaluation of the rule set: version used, inputs and
      screening_rule_results     their hash, outcome, every rule's result and reason
    credit_decisions             the human decision (proceed / decline / more info)
"""
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Sequence,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.database.database import db
from app.utils.dates import iso
from app.utils.money import as_str
from base_model import Base

# AP-0000001 … the pre-screen application number.
application_no_seq = Sequence("application_no_seq", metadata=db.metadata)

# WA-04 (08-working-assumptions Q-C2): label, minimum and maximum term (months), repayment shape.
PRODUCTS = {
    "business_loan": ("Business loan", 3, 24, "amortising"),
    "bridge_loan": ("Short-term bridge loan", 1, 3, "interest_only"),
    "asset_finance": ("Asset finance", 6, 36, "amortising"),
}
APPLICATION_STATUSES = ("open", "decided")
CRB_STATUSES = ("clear", "listed", "previously_listed_cleared")
CRB_LABELS = {"clear": "Clear", "listed": "Listed", "previously_listed_cleared": "Previously listed, now cleared"}
REVIEW_ACTIONS = ("accept", "correct", "not_present")
OUTCOMES = ("shortlisted", "needs_review", "not_qualified")
OUTCOME_LABELS = {"shortlisted": "Shortlisted", "needs_review": "Needs review", "not_qualified": "Not qualified"}
RULE_RESULTS = ("pass", "fail", "missing", "not_applicable")
DECISIONS = ("proceed", "decline", "more_info")
DECISION_LABELS = {"proceed": "Proceed to credit analysis", "decline": "Decline", "more_info": "Request more information"}


def _in(column: str, values) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class LoanApplication(Base, db.Model):
    __tablename__ = "loan_applications"
    __table_args__ = (
        CheckConstraint(_in("product_code", PRODUCTS), name="ck_loan_applications_product"),
        CheckConstraint(_in("status", APPLICATION_STATUSES), name="ck_loan_applications_status"),
        CheckConstraint("amount_requested > 0", name="ck_loan_applications_amount"),
        CheckConstraint("term_months >= 1", name="ck_loan_applications_term"),
        CheckConstraint("indicative_rate_percent >= 0 AND indicative_rate_percent <= 100",
                        name="ck_loan_applications_rate"),
    )

    id = Column(Integer, primary_key=True)
    application_no = Column(String(12), nullable=False, unique=True)
    party_id = Column(Integer, ForeignKey("parties.id", ondelete="RESTRICT"), nullable=False, index=True)
    product_code = Column(String(20), nullable=False)
    amount_requested = Column(Numeric(20, 2), nullable=False)
    term_months = Column(Integer, nullable=False)
    indicative_rate_percent = Column(Numeric(7, 4), nullable=False)
    estimated_instalment = Column(Numeric(20, 2), nullable=False)       # ESTIMATE (phase 5 replaces it)
    estimated_final_payment = Column(Numeric(20, 2), nullable=False)    # last month's payment (bullet: principal)
    business_start_date = Column(Date, nullable=True)
    status = Column(String(10), nullable=False, default="open", server_default="open")
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False)
    created_by = Column(String(120), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)

    def to_dict(self) -> dict:
        label, lo, hi, shape = PRODUCTS[self.product_code]
        return {
            "id": self.id, "application_no": self.application_no, "party_id": self.party_id,
            "product_code": self.product_code, "product_label": label, "repayment": shape,
            "amount_requested": as_str(self.amount_requested), "term_months": self.term_months,
            "indicative_rate_percent": f"{self.indicative_rate_percent:.4f}",
            "estimated_instalment": as_str(self.estimated_instalment),
            "estimated_final_payment": as_str(self.estimated_final_payment),
            "estimate_note": "Estimate only: phase 5's product engine will calculate the actual schedule.",
            "business_start_date": iso(self.business_start_date), "status": self.status,
            "branch_id": self.branch_id, "created_by": self.created_by, "created_at": iso(self.created_at),
        }


class ApplicationParty(Base, db.Model):
    __tablename__ = "application_parties"
    __table_args__ = (
        CheckConstraint("role IN ('guarantor')", name="ck_application_parties_role"),
        UniqueConstraint("application_id", "party_id", "role", name="uq_application_parties"),
    )

    id = Column(Integer, primary_key=True)
    application_id = Column(Integer, ForeignKey("loan_applications.id", ondelete="RESTRICT"), nullable=False,
                            index=True)
    party_id = Column(Integer, ForeignKey("parties.id", ondelete="RESTRICT"), nullable=False)
    role = Column(String(12), nullable=False, default="guarantor")
    added_by = Column(String(120), nullable=False)


class ApplicationCrbStatus(Base, db.Model):
    __tablename__ = "application_crb_statuses"
    __table_args__ = (
        CheckConstraint(_in("status", CRB_STATUSES), name="ck_application_crb_statuses_status"),
        CheckConstraint("confirmed_by IS NULL OR lower(confirmed_by) <> lower(entered_by)",
                        name="ck_application_crb_statuses_maker_checker"),
        CheckConstraint("(confirmed_by IS NULL) = (confirmed_at IS NULL)", name="ck_application_crb_statuses_confirm"),
    )

    id = Column(Integer, primary_key=True)
    application_id = Column(Integer, ForeignKey("loan_applications.id", ondelete="RESTRICT"), nullable=False,
                            index=True)
    status = Column(String(30), nullable=False)
    status_date = Column(Date, nullable=False)
    bureau = Column(String(80), nullable=False)
    extraction_id = Column(Integer, ForeignKey("ai_extractions.id", ondelete="RESTRICT"), nullable=True)
    change_request_id = Column(Integer, ForeignKey("change_requests.id", ondelete="RESTRICT"), nullable=True)
    entered_by = Column(String(120), nullable=False)
    entered_at = Column(DateTime(timezone=True), nullable=False)
    confirmed_by = Column(String(120), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)

    def to_dict(self) -> dict:
        return {"id": self.id, "status": self.status, "status_label": CRB_LABELS[self.status],
                "status_date": iso(self.status_date), "bureau": self.bureau, "extraction_id": self.extraction_id,
                "source": "crb_report" if self.extraction_id else "entered", "change_request_id":
                self.change_request_id, "entered_by": self.entered_by, "entered_at": iso(self.entered_at),
                "confirmed_by": self.confirmed_by, "confirmed_at": iso(self.confirmed_at)}


class ExtractionReview(Base, db.Model):
    __tablename__ = "extraction_reviews"
    __table_args__ = (
        CheckConstraint("approved_by IS NULL OR lower(approved_by) <> lower(reviewed_by)",
                        name="ck_extraction_reviews_maker_checker"),
        CheckConstraint("(approved_by IS NULL) = (approved_at IS NULL)", name="ck_extraction_reviews_approved"),
        UniqueConstraint("extraction_id", name="uq_extraction_reviews_extraction"),
    )

    id = Column(Integer, primary_key=True)
    extraction_id = Column(Integer, ForeignKey("ai_extractions.id", ondelete="RESTRICT"), nullable=False)
    application_id = Column(Integer, ForeignKey("loan_applications.id", ondelete="RESTRICT"), nullable=True)
    reviewed_by = Column(String(120), nullable=False)
    statement_unreliable = Column(Boolean, nullable=False, default=False, server_default="false")
    unreliable_reason = Column(Text, nullable=True)
    change_request_id = Column(Integer, ForeignKey("change_requests.id", ondelete="RESTRICT"), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    approved_by = Column(String(120), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    confirmed_metrics = Column(JSONB, nullable=True)  # statements: metrics recomputed from reviewed rows
    party_updates = Column(JSONB, nullable=True)      # what approval wrote to the party, and what it didn't


class FieldReview(Base, db.Model):
    __tablename__ = "field_reviews"
    __table_args__ = (
        CheckConstraint(_in("action", REVIEW_ACTIONS), name="ck_field_reviews_action"),
        CheckConstraint("action <> 'correct' OR (corrected_value IS NOT NULL AND reason IS NOT NULL)",
                        name="ck_field_reviews_correction"),
        UniqueConstraint("review_id", "field_id", name="uq_field_reviews_field"),
    )

    id = Column(Integer, primary_key=True)
    review_id = Column(Integer, ForeignKey("extraction_reviews.id", ondelete="RESTRICT"), nullable=False)
    field_id = Column(Integer, ForeignKey("ai_extracted_fields.id", ondelete="RESTRICT"), nullable=False)
    action = Column(String(12), nullable=False)
    corrected_value = Column(Text, nullable=True)
    reason = Column(Text, nullable=True)
    reviewed_by = Column(String(120), nullable=False)
    reviewed_at = Column(DateTime(timezone=True), nullable=False)


class TransactionReview(Base, db.Model):
    __tablename__ = "transaction_reviews"
    __table_args__ = (UniqueConstraint("review_id", "transaction_id", name="uq_transaction_reviews_row"),
                      CheckConstraint("reason IS NOT NULL", name="ck_transaction_reviews_reason"))

    id = Column(Integer, primary_key=True)
    review_id = Column(Integer, ForeignKey("extraction_reviews.id", ondelete="RESTRICT"), nullable=False)
    transaction_id = Column(Integer, ForeignKey("ai_statement_transactions.id", ondelete="RESTRICT"), nullable=False)
    txn_date = Column(Date, nullable=True)
    debit = Column(Numeric(20, 2), nullable=True)
    credit = Column(Numeric(20, 2), nullable=True)
    balance = Column(Numeric(20, 2), nullable=True)
    reason = Column(Text, nullable=False)
    reviewed_by = Column(String(120), nullable=False)
    reviewed_at = Column(DateTime(timezone=True), nullable=False)


class ScreeningRun(Base, db.Model):
    __tablename__ = "screening_runs"
    __table_args__ = (CheckConstraint(_in("outcome", OUTCOMES), name="ck_screening_runs_outcome"),
                      Index("ix_screening_runs_application", "application_id", "evaluated_at"))

    id = Column(Integer, primary_key=True)
    application_id = Column(Integer, ForeignKey("loan_applications.id", ondelete="RESTRICT"), nullable=False)
    rule_set_version_id = Column(Integer, ForeignKey("setting_versions.id", ondelete="RESTRICT"), nullable=False)
    rule_set_version_no = Column(Integer, nullable=False)
    rule_set = Column(JSONB, nullable=False)       # the exact rules evaluated (copy of the version)
    inputs = Column(JSONB, nullable=False)         # every metric and check, with its sources
    inputs_sha256 = Column(String(64), nullable=False)
    outcome = Column(String(14), nullable=False)
    evaluated_by = Column(String(120), nullable=False)
    evaluated_at = Column(DateTime(timezone=True), nullable=False)


class ScreeningRuleResult(Base, db.Model):
    __tablename__ = "screening_rule_results"
    __table_args__ = (CheckConstraint(_in("result", RULE_RESULTS), name="ck_screening_rule_results_result"),
                      UniqueConstraint("run_id", "rule_id", name="uq_screening_rule_results_rule"))

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("screening_runs.id", ondelete="RESTRICT"), nullable=False)
    position = Column(Integer, nullable=False)
    rule_id = Column(String(40), nullable=False)
    description = Column(Text, nullable=False)
    metric = Column(String(60), nullable=False)
    value = Column(JSONB, nullable=True)
    comparison = Column(String(10), nullable=False)
    threshold = Column(JSONB, nullable=True)
    result = Column(String(16), nullable=False)
    outcome_if_failed = Column(String(14), nullable=True)  # what this rule's failure counts as (when it failed)
    reason = Column(Text, nullable=False)

    def to_dict(self) -> dict:
        return {"position": self.position, "rule_id": self.rule_id, "description": self.description,
                "metric": self.metric, "value": self.value, "comparison": self.comparison,
                "threshold": self.threshold, "result": self.result, "outcome_if_failed": self.outcome_if_failed,
                "reason": self.reason}


class CreditDecision(Base, db.Model):
    __tablename__ = "credit_decisions"
    __table_args__ = (
        CheckConstraint(_in("decision", DECISIONS), name="ck_credit_decisions_decision"),
        CheckConstraint("char_length(btrim(reason)) > 0", name="ck_credit_decisions_reason"),
        CheckConstraint("approved_by IS NULL OR lower(approved_by) <> lower(decided_by)",
                        name="ck_credit_decisions_maker_checker"),
        CheckConstraint("NOT override OR approved_by IS NOT NULL", name="ck_credit_decisions_override_approved"),
    )

    id = Column(Integer, primary_key=True)
    application_id = Column(Integer, ForeignKey("loan_applications.id", ondelete="RESTRICT"), nullable=False,
                            index=True)
    run_id = Column(Integer, ForeignKey("screening_runs.id", ondelete="RESTRICT"), nullable=False)
    decision = Column(String(10), nullable=False)
    reason = Column(Text, nullable=False)
    override = Column(Boolean, nullable=False, default=False, server_default="false")  # proceed despite Not qualified
    decided_by = Column(String(120), nullable=False)
    decided_at = Column(DateTime(timezone=True), nullable=False)
    approved_by = Column(String(120), nullable=True)
    change_request_id = Column(Integer, ForeignKey("change_requests.id", ondelete="RESTRICT"), nullable=True)

    def to_dict(self) -> dict:
        return {"id": self.id, "application_id": self.application_id, "run_id": self.run_id,
                "decision": self.decision, "decision_label": DECISION_LABELS[self.decision], "reason": self.reason,
                "override": self.override, "decided_by": self.decided_by, "decided_at": iso(self.decided_at),
                "approved_by": self.approved_by, "change_request_id": self.change_request_id}
