"""
Parties (02-domain-model ADR-02-1): one record per real person or organisation,
whatever its roles. Identity, contacts, bank details, roles and links between
parties hang off it; role-specific business data (investments, later loans)
stays in role tables keyed by party_id.

Duplicates are refused by the unique index on party_identifiers
(id_type, issuing_country, value_normalised), across all branches (KYC-04).
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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.Branches.model import HEAD_OFFICE_ID
from app.database.database import db
from app.utils.dates import iso
from app.utils.money import as_str
from base_model import Base

# P-0000001, P-0000002 … branch-independent, so a client keeps one number when moving branch.
party_no_seq = Sequence("party_no_seq", metadata=db.metadata)

PARTY_TYPES = ("person", "organisation")
KYC_STATUSES = ("incomplete", "pending_review", "verified")
PARTY_STATUSES = ("active", "blacklisted", "merged")
RISK_RATINGS = ("low", "medium", "high")
GENDERS = ("male", "female", "other")
MARITAL_STATUSES = ("single", "married", "divorced", "widowed", "other")
RESIDENCIES = ("local", "foreign")
# KYC-11 and the Anchorstone FSD organisation types.
ORG_TYPES = ("sme", "corporate", "cooperative", "ngo", "investment_group", "public_institution", "sacco",
             "church", "fund_manager", "insurer")
CONTACT_KINDS = ("email", "mobile", "phone")
ADDRESS_KINDS = ("home", "business", "postal", "registered")
BANK_KINDS = ("bank", "mpesa")
ROLES = ("investor", "borrower", "guarantor", "director", "shareholder", "signatory", "agent", "next_of_kin")
# from_party is the related person (director, kin, guarantor…); to_party the client it relates to.
RELATIONSHIPS = ("director", "shareholder", "signatory", "next_of_kin", "guarantor_of", "related_party", "referred_by")
RELATIONSHIP_ROLE = {"director": "director", "shareholder": "shareholder", "signatory": "signatory",
                     "next_of_kin": "next_of_kin", "guarantor_of": "guarantor", "referred_by": "agent"}
MANDATE_RULES = ("any_one", "all", "a_and_b", "custom")
ROW_STATUSES = ("active", "ended")


def _in(column: str, values) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Party(Base, db.Model):
    __tablename__ = "parties"
    __table_args__ = (
        CheckConstraint(_in("party_type", PARTY_TYPES), name="ck_parties_type"),
        CheckConstraint(_in("kyc_status", KYC_STATUSES), name="ck_parties_kyc_status"),
        CheckConstraint(_in("status", PARTY_STATUSES), name="ck_parties_status"),
        CheckConstraint("risk_rating IS NULL OR " + _in("risk_rating", RISK_RATINGS), name="ck_parties_risk"),
        CheckConstraint("(status = 'merged') = (merged_into_party_id IS NOT NULL)", name="ck_parties_merged"),
        CheckConstraint("(kyc_status = 'verified') = (verified_at IS NOT NULL)", name="ck_parties_verified"),
    )

    id = Column(Integer, primary_key=True)
    party_no = Column(String(12), nullable=False, unique=True)
    party_type = Column(String(12), nullable=False)
    display_name = Column(String(200), nullable=False)
    home_branch_id = Column(Integer, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True,
                            default=HEAD_OFFICE_ID, server_default=str(HEAD_OFFICE_ID))
    classification = Column(String(40), nullable=True)   # e.g. retail, HNI, SME — free text until Q-C8/C9
    risk_rating = Column(String(10), nullable=True)
    is_pep = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    kyc_status = Column(String(15), nullable=False, default="incomplete", server_default="incomplete")
    status = Column(String(12), nullable=False, default="active", server_default="active")
    merged_into_party_id = Column(Integer, ForeignKey("parties.id", ondelete="RESTRICT"), nullable=True)
    relationship_officer_user_id = Column(Integer, ForeignKey("user.id", ondelete="RESTRICT"), nullable=True)
    notes = Column(Text, nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    verified_by = Column(String(120), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    created_by = Column(String(120), nullable=False)

    person = db.relationship("PartyPerson", uselist=False, back_populates="party", foreign_keys="PartyPerson.party_id")
    organisation = db.relationship("PartyOrganisation", uselist=False, back_populates="party")

    def summary(self) -> dict:
        return {"id": self.id, "party_no": self.party_no, "party_type": self.party_type,
                "display_name": self.display_name, "kyc_status": self.kyc_status, "status": self.status,
                "is_pep": self.is_pep}

    def to_dict(self) -> dict:
        return {
            **self.summary(),
            "home_branch_id": self.home_branch_id, "classification": self.classification,
            "risk_rating": self.risk_rating, "merged_into_party_id": self.merged_into_party_id,
            "relationship_officer_user_id": self.relationship_officer_user_id, "notes": self.notes,
            "verified_at": iso(self.verified_at), "verified_by": self.verified_by,
            "created_at": iso(self.created_at), "created_by": self.created_by,
            "person": self.person.to_dict() if self.person else None,
            "organisation": self.organisation.to_dict() if self.organisation else None,
        }


class PartyPerson(Base, db.Model):
    __tablename__ = "party_persons"
    __table_args__ = (
        CheckConstraint("gender IS NULL OR " + _in("gender", GENDERS), name="ck_party_persons_gender"),
        CheckConstraint("marital_status IS NULL OR " + _in("marital_status", MARITAL_STATUSES),
                        name="ck_party_persons_marital"),
        CheckConstraint(_in("residency", RESIDENCIES), name="ck_party_persons_residency"),
    )

    party_id = Column(Integer, ForeignKey("parties.id", ondelete="RESTRICT"), primary_key=True)
    salutation = Column(String(20), nullable=True)
    first_name = Column(String(80), nullable=True)
    middle_name = Column(String(80), nullable=True)
    last_name = Column(String(80), nullable=True)
    gender = Column(String(10), nullable=True)
    date_of_birth = Column(Date, nullable=True)
    marital_status = Column(String(10), nullable=True)
    nationality = Column(String(2), nullable=False, default="KE", server_default="KE")
    residency = Column(String(10), nullable=False, default="local", server_default="local")
    sector = Column(String(100), nullable=True)
    nature_of_business = Column(String(200), nullable=True)
    employer_name = Column(String(150), nullable=True)
    employer_party_id = Column(Integer, ForeignKey("parties.id", ondelete="RESTRICT"), nullable=True)
    # Set by the investor migration when a full name was split by guesswork.
    name_needs_review = Column(Boolean, nullable=False, default=False, server_default=text("false"))

    party = db.relationship("Party", back_populates="person", foreign_keys=[party_id])

    def to_dict(self) -> dict:
        return {k: (iso(v) if k == "date_of_birth" else v) for k, v in (
            ("salutation", self.salutation), ("first_name", self.first_name), ("middle_name", self.middle_name),
            ("last_name", self.last_name), ("gender", self.gender), ("date_of_birth", self.date_of_birth),
            ("marital_status", self.marital_status), ("nationality", self.nationality),
            ("residency", self.residency), ("sector", self.sector), ("nature_of_business", self.nature_of_business),
            ("employer_name", self.employer_name), ("employer_party_id", self.employer_party_id),
            ("name_needs_review", self.name_needs_review))}


class PartyOrganisation(Base, db.Model):
    __tablename__ = "party_organisations"
    __table_args__ = (CheckConstraint(_in("org_type", ORG_TYPES), name="ck_party_organisations_type"),)

    party_id = Column(Integer, ForeignKey("parties.id", ondelete="RESTRICT"), primary_key=True)
    legal_name = Column(String(200), nullable=False)
    trading_name = Column(String(200), nullable=True)
    registration_date = Column(Date, nullable=True)
    org_type = Column(String(20), nullable=False)
    sector = Column(String(100), nullable=True)
    nature_of_business = Column(String(200), nullable=True)

    party = db.relationship("Party", back_populates="organisation")

    def to_dict(self) -> dict:
        return {"legal_name": self.legal_name, "trading_name": self.trading_name,
                "registration_date": iso(self.registration_date), "org_type": self.org_type,
                "sector": self.sector, "nature_of_business": self.nature_of_business}


class PartyIdentifier(Base, db.Model):
    __tablename__ = "party_identifiers"
    __table_args__ = (
        CheckConstraint("id_type IN ('national_id', 'passport', 'alien_id', 'kra_pin', 'company_reg_no')",
                        name="ck_party_identifiers_type"),
        # KYC-04: one party per identifier, across every branch.
        UniqueConstraint("id_type", "issuing_country", "value_normalised", name="uq_party_identifiers_value"),
        UniqueConstraint("party_id", "id_type", name="uq_party_identifiers_one_per_type"),
    )

    id = Column(Integer, primary_key=True)
    party_id = Column(Integer, ForeignKey("parties.id", ondelete="RESTRICT"), nullable=False, index=True)
    id_type = Column(String(20), nullable=False)
    issuing_country = Column(String(2), nullable=False, default="KE", server_default="KE")
    value_display = Column(String(50), nullable=False)
    value_normalised = Column(String(50), nullable=False)
    issued_on = Column(Date, nullable=True)
    expires_on = Column(Date, nullable=True)

    def to_dict(self) -> dict:
        return {"id": self.id, "id_type": self.id_type, "issuing_country": self.issuing_country,
                "value": self.value_display, "issued_on": iso(self.issued_on), "expires_on": iso(self.expires_on)}


class PartyContact(Base, db.Model):
    __tablename__ = "party_contacts"
    __table_args__ = (
        CheckConstraint(_in("kind", CONTACT_KINDS), name="ck_party_contacts_kind"),
        Index("ix_party_contacts_lookup", "kind", "value_normalised"),
    )

    id = Column(Integer, primary_key=True)
    party_id = Column(Integer, ForeignKey("parties.id", ondelete="RESTRICT"), nullable=False, index=True)
    kind = Column(String(10), nullable=False)
    value = Column(String(150), nullable=False)
    value_normalised = Column(String(150), nullable=True)  # NULL = couldn't be read (flagged)
    is_primary = Column(Boolean, nullable=False, default=False, server_default=text("false"))

    def to_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "value": self.value, "is_primary": self.is_primary,
                "needs_review": self.value_normalised is None}


class PartyAddress(Base, db.Model):
    __tablename__ = "party_addresses"
    __table_args__ = (CheckConstraint(_in("kind", ADDRESS_KINDS), name="ck_party_addresses_kind"),)

    id = Column(Integer, primary_key=True)
    party_id = Column(Integer, ForeignKey("parties.id", ondelete="RESTRICT"), nullable=False, index=True)
    kind = Column(String(12), nullable=False)
    line1 = Column(String(200), nullable=False)
    line2 = Column(String(200), nullable=True)
    town = Column(String(100), nullable=True)
    county = Column(String(100), nullable=True)
    country = Column(String(2), nullable=False, default="KE", server_default="KE")

    def to_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "line1": self.line1, "line2": self.line2, "town": self.town,
                "county": self.county, "country": self.country}


class PartyBankAccount(Base, db.Model):
    __tablename__ = "party_bank_accounts"
    __table_args__ = (
        CheckConstraint(_in("kind", BANK_KINDS), name="ck_party_bank_accounts_kind"),
        CheckConstraint(_in("status", ROW_STATUSES), name="ck_party_bank_accounts_status"),
        Index("uq_party_bank_accounts_one_default", "party_id", unique=True,
              postgresql_where=text("is_default_payout AND status = 'active'")),
    )

    id = Column(Integer, primary_key=True)
    party_id = Column(Integer, ForeignKey("parties.id", ondelete="RESTRICT"), nullable=False, index=True)
    kind = Column(String(10), nullable=False)
    bank_name = Column(String(100), nullable=True)
    branch_name = Column(String(100), nullable=True)
    account_no = Column(String(100), nullable=False)
    account_name = Column(String(150), nullable=True)
    is_default_payout = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    status = Column(String(10), nullable=False, default="active", server_default="active")

    def to_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "bank_name": self.bank_name, "branch_name": self.branch_name,
                "account_no": self.account_no, "account_name": self.account_name,
                "is_default_payout": self.is_default_payout, "status": self.status}


class PartyRole(Base, db.Model):
    __tablename__ = "party_roles"
    __table_args__ = (
        CheckConstraint(_in("role", ROLES), name="ck_party_roles_role"),
        CheckConstraint(_in("status", ROW_STATUSES), name="ck_party_roles_status"),
        Index("uq_party_roles_active", "party_id", "role", unique=True, postgresql_where=text("status = 'active'")),
    )

    id = Column(Integer, primary_key=True)
    party_id = Column(Integer, ForeignKey("parties.id", ondelete="RESTRICT"), nullable=False, index=True)
    role = Column(String(15), nullable=False)
    status = Column(String(10), nullable=False, default="active", server_default="active")
    started_on = Column(Date, nullable=False)
    ended_on = Column(Date, nullable=True)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=True)

    def to_dict(self) -> dict:
        return {"id": self.id, "role": self.role, "status": self.status, "started_on": iso(self.started_on),
                "ended_on": iso(self.ended_on)}


class PartyRelationship(Base, db.Model):
    __tablename__ = "party_relationships"
    __table_args__ = (
        CheckConstraint(_in("relationship", RELATIONSHIPS), name="ck_party_relationships_kind"),
        CheckConstraint(_in("status", ROW_STATUSES), name="ck_party_relationships_status"),
        CheckConstraint("from_party_id <> to_party_id", name="ck_party_relationships_not_self"),
        CheckConstraint("committed_amount IS NULL OR (relationship = 'guarantor_of' AND committed_amount > 0)",
                        name="ck_party_relationships_committed"),
        CheckConstraint("share_pct IS NULL OR (share_pct > 0 AND share_pct <= 100)", name="ck_party_relationships_share"),
        CheckConstraint("signatory_list IS NULL OR signatory_list IN ('A', 'B')", name="ck_party_relationships_list"),
        CheckConstraint("currency = 'KES'", name="ck_party_relationships_currency_kes"),
        Index("uq_party_relationships_active", "from_party_id", "to_party_id", "relationship", unique=True,
              postgresql_where=text("status = 'active'")),
    )

    id = Column(Integer, primary_key=True)
    from_party_id = Column(Integer, ForeignKey("parties.id", ondelete="RESTRICT"), nullable=False, index=True)
    to_party_id = Column(Integer, ForeignKey("parties.id", ondelete="RESTRICT"), nullable=False, index=True)
    relationship = Column(String(15), nullable=False)
    share_pct = Column(Numeric(7, 4), nullable=True)
    kin_relationship = Column(String(50), nullable=True)   # spouse, parent, sibling …
    signatory_list = Column(String(1), nullable=True)
    committed_amount = Column(Numeric(20, 2), nullable=True)  # KYC-03: what a guarantor commits
    currency = Column(String(3), nullable=False, default="KES", server_default="KES")
    status = Column(String(10), nullable=False, default="active", server_default="active")
    started_on = Column(Date, nullable=False)
    ended_on = Column(Date, nullable=True)
    created_by = Column(String(120), nullable=False)

    def to_dict(self) -> dict:
        return {"id": self.id, "from_party_id": self.from_party_id, "to_party_id": self.to_party_id,
                "relationship": self.relationship, "share_pct": f"{self.share_pct:.4f}" if self.share_pct is not None else None,
                "kin_relationship": self.kin_relationship, "signatory_list": self.signatory_list,
                "committed_amount": as_str(self.committed_amount), "currency": self.currency,
                "status": self.status, "started_on": iso(self.started_on), "ended_on": iso(self.ended_on)}


class PartyMandate(Base, db.Model):
    """Who may sign for an organisation or joint holding (KYC-02 signatories)."""
    __tablename__ = "party_mandates"
    __table_args__ = (
        CheckConstraint(_in("rule", MANDATE_RULES), name="ck_party_mandates_rule"),
        CheckConstraint(_in("status", ROW_STATUSES), name="ck_party_mandates_status"),
        CheckConstraint("rule <> 'custom' OR description IS NOT NULL", name="ck_party_mandates_custom_described"),
        Index("uq_party_mandates_active", "party_id", unique=True, postgresql_where=text("status = 'active'")),
    )

    id = Column(Integer, primary_key=True)
    party_id = Column(Integer, ForeignKey("parties.id", ondelete="RESTRICT"), nullable=False, index=True)
    rule = Column(String(10), nullable=False)
    description = Column(Text, nullable=True)
    effective_from = Column(Date, nullable=False)
    status = Column(String(10), nullable=False, default="active", server_default="active")
    created_by = Column(String(120), nullable=False)

    def to_dict(self) -> dict:
        return {"id": self.id, "rule": self.rule, "description": self.description,
                "effective_from": iso(self.effective_from), "status": self.status, "created_by": self.created_by}


ACCOUNT_TYPES = ("investment",)
ACCOUNT_STATUSES = ("active", "closed")


class Account(Base, db.Model):
    """A customer-facing ledger (02 ADR-02-2). Today only investment accounts, numbered with the
    investor's ACL- client code; the balance itself still comes from app/Transactions/ledger.py."""
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint(_in("account_type", ACCOUNT_TYPES), name="ck_accounts_type"),
        CheckConstraint(_in("status", ACCOUNT_STATUSES), name="ck_accounts_status"),
        CheckConstraint("currency = 'KES'", name="ck_accounts_currency_kes"),
        CheckConstraint("(status = 'closed') = (closed_on IS NOT NULL)", name="ck_accounts_closed_on"),
    )

    id = Column(Integer, primary_key=True)
    account_no = Column(String(20), nullable=False, unique=True)
    account_type = Column(String(12), nullable=False)
    party_id = Column(Integer, ForeignKey("parties.id", ondelete="RESTRICT"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True)
    currency = Column(String(3), nullable=False, default="KES", server_default="KES")
    status = Column(String(10), nullable=False, default="active", server_default="active")
    opened_on = Column(Date, nullable=False)
    closed_on = Column(Date, nullable=True)
    created_by = Column(String(120), nullable=False)

    def to_dict(self) -> dict:
        return {"id": self.id, "account_no": self.account_no, "account_type": self.account_type,
                "party_id": self.party_id, "branch_id": self.branch_id, "currency": self.currency,
                "status": self.status, "opened_on": iso(self.opened_on), "closed_on": iso(self.closed_on)}


# ── Screening (KYC-06) and PEP (KYC-07) ────────────────────────────────────

WATCHLISTS = ("internal_blacklist", "pep", "sanctions_un")
SCREENING_TRIGGERS = ("onboarding", "identity_change", "watchlist_change", "rescreen")
REVIEW_STATUSES = ("not_required", "pending", "cleared", "confirmed")
PEP_RELATIONSHIPS = ("self", "family_member", "close_associate")
PEP_STATUSES = ("pending", "approved", "cleared")


class WatchlistEntry(Base, db.Model):
    """A name (and optional identifiers) on Anchorstone's internal blacklist or PEP list."""
    __tablename__ = "watchlist_entries"
    __table_args__ = (
        CheckConstraint(_in("list", WATCHLISTS), name="ck_watchlist_entries_list"),
        CheckConstraint("status IN ('active', 'removed')", name="ck_watchlist_entries_status"),
        Index("ix_watchlist_entries_name", "name_normalised"),
    )

    id = Column(Integer, primary_key=True)
    list = Column(String(20), nullable=False)
    full_name = Column(String(200), nullable=False)
    name_normalised = Column(String(200), nullable=False)
    identifiers = Column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    reason = Column(Text, nullable=False)
    source = Column(String(200), nullable=True)
    status = Column(String(10), nullable=False, default="active", server_default="active")
    added_by = Column(String(120), nullable=False)
    added_at = Column(DateTime(timezone=True), nullable=False)
    removed_by = Column(String(120), nullable=True)
    removed_at = Column(DateTime(timezone=True), nullable=True)

    def to_dict(self) -> dict:
        return {"id": self.id, "list": self.list, "full_name": self.full_name, "identifiers": self.identifiers,
                "reason": self.reason, "source": self.source, "status": self.status, "added_by": self.added_by,
                "added_at": iso(self.added_at), "removed_by": self.removed_by, "removed_at": iso(self.removed_at)}


class ScreeningResult(Base, db.Model):
    """One screening of a party. A potential match blocks KYC verification until a reviewer
    (never the person who onboarded the party) clears or confirms it."""
    __tablename__ = "screening_results"
    __table_args__ = (
        CheckConstraint(_in("trigger", SCREENING_TRIGGERS), name="ck_screening_results_trigger"),
        CheckConstraint("outcome IN ('clear', 'potential_match')", name="ck_screening_results_outcome"),
        CheckConstraint(_in("review_status", REVIEW_STATUSES), name="ck_screening_results_review"),
        CheckConstraint("(outcome = 'clear') = (review_status = 'not_required')", name="ck_screening_results_review_needed"),
        CheckConstraint("(review_status IN ('cleared', 'confirmed')) = (reviewed_by IS NOT NULL)",
                        name="ck_screening_results_reviewed"),
        # Maker-checker, backed by the database: the person who onboarded the party can't review it.
        CheckConstraint("reviewed_by IS NULL OR lower(reviewed_by) <> lower(maker_email)",
                        name="ck_screening_results_maker_not_checker"),
        Index("ix_screening_results_pending", "review_status"),
    )

    id = Column(Integer, primary_key=True)
    party_id = Column(Integer, ForeignKey("parties.id", ondelete="RESTRICT"), nullable=False, index=True)
    trigger = Column(String(20), nullable=False)
    lists = Column(JSONB, nullable=False)
    matches = Column(JSONB, nullable=False)
    outcome = Column(String(16), nullable=False)
    review_status = Column(String(12), nullable=False)
    maker_email = Column(String(120), nullable=False)
    screened_by = Column(String(120), nullable=False)
    screened_at = Column(DateTime(timezone=True), nullable=False)
    reviewed_by = Column(String(120), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_note = Column(Text, nullable=True)

    def to_dict(self) -> dict:
        return {"id": self.id, "party_id": self.party_id, "trigger": self.trigger, "lists": self.lists,
                "matches": self.matches, "outcome": self.outcome, "review_status": self.review_status,
                "maker_email": self.maker_email, "screened_by": self.screened_by, "screened_at": iso(self.screened_at),
                "reviewed_by": self.reviewed_by, "reviewed_at": iso(self.reviewed_at), "review_note": self.review_note}


class PartyPepDetails(Base, db.Model):
    """The extra information asked for when a party is a politically exposed person (KYC-07)."""
    __tablename__ = "party_pep_details"
    __table_args__ = (
        CheckConstraint(_in("pep_relationship", PEP_RELATIONSHIPS), name="ck_party_pep_details_relationship"),
        CheckConstraint(_in("status", PEP_STATUSES), name="ck_party_pep_details_status"),
        CheckConstraint("pep_relationship = 'self' OR related_pep_name IS NOT NULL", name="ck_party_pep_details_related"),
        CheckConstraint("(status = 'approved') = (approved_at IS NOT NULL)", name="ck_party_pep_details_approved"),
    )

    party_id = Column(Integer, ForeignKey("parties.id", ondelete="RESTRICT"), primary_key=True)
    position_held = Column(String(200), nullable=False)
    country = Column(String(2), nullable=False, default="KE", server_default="KE")
    since = Column(Date, nullable=True)
    until = Column(Date, nullable=True)
    pep_relationship = Column(String(16), nullable=False)
    related_pep_name = Column(String(200), nullable=True)
    source_of_funds = Column(Text, nullable=False)
    source_of_wealth = Column(Text, nullable=False)
    status = Column(String(10), nullable=False, default="pending", server_default="pending")
    recorded_by = Column(String(120), nullable=False)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_by = Column(String(250), nullable=True)

    def to_dict(self) -> dict:
        return {"position_held": self.position_held, "country": self.country, "since": iso(self.since),
                "until": iso(self.until), "pep_relationship": self.pep_relationship,
                "related_pep_name": self.related_pep_name, "source_of_funds": self.source_of_funds,
                "source_of_wealth": self.source_of_wealth, "status": self.status, "recorded_by": self.recorded_by,
                "approved_at": iso(self.approved_at), "approved_by": self.approved_by}


# ── Consent (Kenya DPA; FSD v0.1 AI-01, 05 §9.1) ──────────────────────────

CONSENT_PURPOSES = ("kyc_processing", "ai_document_processing", "credit_bureau_check", "marketing")
CONSENT_METHODS = ("signed_form", "in_branch", "email")


class PartyConsent(Base, db.Model):
    """A client's consent for one purpose: when, how, who captured it and the notice version shown.
    Withdrawal is recorded on the row; consents are never deleted."""
    __tablename__ = "party_consents"
    __table_args__ = (
        CheckConstraint(_in("purpose", CONSENT_PURPOSES), name="ck_party_consents_purpose"),
        CheckConstraint(_in("method", CONSENT_METHODS), name="ck_party_consents_method"),
        CheckConstraint("status IN ('active', 'withdrawn')", name="ck_party_consents_status"),
        CheckConstraint("(status = 'withdrawn') = (withdrawn_at IS NOT NULL)", name="ck_party_consents_withdrawn"),
        CheckConstraint("method <> 'signed_form' OR evidence_document_id IS NOT NULL",
                        name="ck_party_consents_signed_form_evidence"),
        Index("uq_party_consents_active", "party_id", "purpose", unique=True, postgresql_where=text("status = 'active'")),
    )

    id = Column(Integer, primary_key=True)
    party_id = Column(Integer, ForeignKey("parties.id", ondelete="RESTRICT"), nullable=False, index=True)
    purpose = Column(String(30), nullable=False)
    granted_on = Column(Date, nullable=False)
    method = Column(String(12), nullable=False)
    notice_version = Column(String(30), nullable=False)
    evidence_document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="RESTRICT"), nullable=True)
    captured_by = Column(String(120), nullable=False)
    captured_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(10), nullable=False, default="active", server_default="active")
    withdrawn_at = Column(DateTime(timezone=True), nullable=True)
    withdrawn_by = Column(String(120), nullable=True)
    withdrawal_note = Column(Text, nullable=True)

    def to_dict(self) -> dict:
        return {"id": self.id, "party_id": self.party_id, "purpose": self.purpose, "granted_on": iso(self.granted_on),
                "method": self.method, "notice_version": self.notice_version,
                "evidence_document_id": str(self.evidence_document_id) if self.evidence_document_id else None,
                "captured_by": self.captured_by, "captured_at": iso(self.captured_at), "status": self.status,
                "withdrawn_at": iso(self.withdrawn_at), "withdrawn_by": self.withdrawn_by,
                "withdrawal_note": self.withdrawal_note}
