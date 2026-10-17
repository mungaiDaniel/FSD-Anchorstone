import type {
  ConsentMethod, ConsentPurpose, IdType, KycStatus, OrgType, PartyRoleName, PaymentMethod, RelationshipKind,
  SettingSource, UserRole, Watchlist,
} from "./types";

export const APP_NAME = "Anchorstone Capital Ltd";

/** Path to a logo image (e.g. "/logo.svg" in public/). null = use the text wordmark. */
export const BRAND_LOGO_URL: string | null = null;

export const ROLES = {
  USER: "user" as UserRole,
  ADMIN: "admin" as UserRole,
  SUPER_ADMIN: "super_admin" as UserRole,
} as const;

export const ROLE_LABELS: Record<UserRole, string> = {
  user: "Staff",
  admin: "Admin",
  super_admin: "Super admin",
};

export const PAYMENT_METHOD_LABELS: Record<PaymentMethod, string> = {
  bank_transfer: "Bank transfer",
  mpesa: "M-Pesa",
  cheque: "Cheque",
  cash: "Cash",
};

// ── Routes ──

export const ROUTES = {
  LOGIN: "/login",
  CHANGE_PASSWORD: "/change-password",
  OVERVIEW: "/overview",
  INVESTORS: "/investors",
  INVESTOR_ADD: "/investors/add",
  INVESTOR_DETAIL: (id: number | string) => `/investors/${id}`,
  DEPOSITS: "/deposits",
  WITHDRAWALS: "/withdrawals",
  INTEREST: "/interest",
  INTEREST_PERIOD: (id: number | string) => `/interest/periods/${id}`,
  EMAILS: "/emails",
  USERS: "/users",
  AUDIT_LOG: "/audit-log",
  BACKUPS: "/backups",
  REPORTS: "/reports",
  APPROVALS: "/approvals",
  CLIENTS: "/clients",
  CLIENT_NEW: "/clients/new",
  CLIENT_DETAIL: (id: number | string) => `/clients/${id}`,
  CLIENT_EDIT: (id: number | string) => `/clients/${id}/edit`,
  WATCHLIST: "/watchlist",
  SETTINGS: "/settings",
  APPLICATIONS: "/applications",
  APPLICATION_NEW: "/applications/new",
  APPLICATION_DETAIL: (id: number | string) => `/applications/${id}`,
  REVIEW_EXTRACTION: (id: number | string) => `/readings/${id}/review`,
  AI_OVERSIGHT: "/ai-oversight",
} as const;

// ── API paths (relative to VITE_API_URL) ──

export const API = {
  LOGIN: "/login",
  ME: "/me",
  CHANGE_PASSWORD: "/me/password",
  USERS: "/users",
  USER_BY_ID: (id: number) => `/users/${id}`,
  SET_USER_ROLE: (id: number) => `/users/${id}/role`,
  SET_USER_STATUS: (id: number) => `/users/${id}/status`,
  RESET_USER_PASSWORD: (id: number) => `/users/${id}/reset-password`,
  UNLOCK_USER: (id: number) => `/users/${id}/unlock`,

  INVESTORS: "/investors",
  INVESTOR: (id: number) => `/investors/${id}`,
  INVESTOR_STATUS: (id: number) => `/investors/${id}/status`,
  INVESTOR_LEDGER: (id: number) => `/investors/${id}/ledger`,
  INVESTOR_DEPOSITS: (id: number) => `/investors/${id}/deposits`,
  INVESTOR_WITHDRAWALS: (id: number) => `/investors/${id}/withdrawals`,
  INVESTOR_PAYOUTS: (id: number) => `/investors/${id}/payouts`,
  INVESTOR_EMAILS: (id: number) => `/investors/${id}/emails`,

  DEPOSITS: "/deposits",
  DEPOSIT_REVERSE: (id: number) => `/deposits/${id}/reverse`,
  WITHDRAWALS: "/withdrawals",
  WITHDRAWAL_APPROVE: (id: number) => `/withdrawals/${id}/approve`,
  WITHDRAWAL_REJECT: (id: number) => `/withdrawals/${id}/reject`,

  INTEREST_RATES: "/interest/rates",
  INTEREST_PERIODS: "/interest/periods",
  INTEREST_CALCULATE: "/interest/periods/calculate",
  INTEREST_PERIOD: (id: number) => `/interest/periods/${id}`,
  INTEREST_APPROVE: (id: number) => `/interest/periods/${id}/approve`,
  INTEREST_MARK_PAID: (id: number) => `/interest/periods/${id}/mark-paid`,
  PAYOUT_STATEMENT_PDF: (id: number) => `/interest/payouts/${id}/statement.pdf`,

  EMAILS: "/emails",
  EMAILS_STATUS: "/emails/status",
  EMAIL_RETRY: (id: number) => `/emails/${id}/retry`,
  EMAIL_CANCEL: (id: number) => `/emails/${id}/cancel`,
  EMAILS_SEND_NOW: "/emails/send-now",
  EMAILS_CONFIRM: "/emails/confirm",
  EMAILS_SUPPRESS: "/emails/suppress",
  EMAIL_ATTACHMENT: (id: number) => `/emails/${id}/attachment`,
  STATEMENTS_BULK: "/emails/statements/bulk",
  INVESTOR_STATEMENT_EMAIL: (id: number) => `/investors/${id}/statement-email`,

  OVERVIEW_STATS: "/stats/overview",

  AUDIT_LOGS: "/audit-logs",
  REPORTS: "/reports",
  REPORT_XLSX: (name: string) => `/reports/${name}.xlsx`,
  SCHEDULED_REPORTS: "/settings/scheduled-reports",
  SCHEDULED_REPORTS_RUN: "/settings/scheduled-reports/run-now",

  BACKUPS: "/backups",
  BACKUPS_STATUS: "/backups/status",
  BACKUPS_RUN_NOW: "/backups/run-now",

  SETTINGS_EMAIL: "/settings/email",
  SETTINGS_EMAIL_TEST: "/settings/email/test",
  SETTINGS_EMAIL_QUEUE: "/settings/email-queue",
  SETTINGS_BUSINESS: "/settings/business",
  SETTINGS_BUSINESS_KEY: (key: string) => `/settings/business/${encodeURIComponent(key)}`,

  CHANGE_REQUESTS: "/change-requests",
  CHANGE_REQUEST: (id: number) => `/change-requests/${id}`,
  CHANGE_REQUEST_APPROVE: (id: number) => `/change-requests/${id}/approve`,
  CHANGE_REQUEST_REJECT: (id: number) => `/change-requests/${id}/reject`,
  CHANGE_REQUEST_RETURN: (id: number) => `/change-requests/${id}/return`,
  CHANGE_REQUEST_RESUBMIT: (id: number) => `/change-requests/${id}/resubmit`,
  CHANGE_REQUEST_CANCEL: (id: number) => `/change-requests/${id}/cancel`,

  PARTIES: "/parties",
  PARTY: (id: number) => `/parties/${id}`,
  PARTY_OVERVIEW: (id: number) => `/parties/${id}/overview`,
  PARTY_CHECK_DUPLICATES: "/parties/check-duplicates",
  PARTY_RELATIONSHIPS: (id: number) => `/parties/${id}/relationships`,
  PARTY_RELATIONSHIP_END: (id: number, rid: number) => `/parties/${id}/relationships/${rid}/end`,
  PARTY_MANDATE: (id: number) => `/parties/${id}/mandate`,
  PARTY_VERIFY: (id: number) => `/parties/${id}/verify`,
  PARTY_INVESTOR: (id: number) => `/parties/${id}/investor`,
  PARTY_PEP: (id: number) => `/parties/${id}/pep`,
  PARTY_DOCUMENTS: (id: number) => `/parties/${id}/documents`,
  PARTY_CONSENTS: (id: number) => `/parties/${id}/consents`,
  PARTY_CONSENT_WITHDRAW: (id: number, cid: number) => `/parties/${id}/consents/${cid}/withdraw`,
  PARTY_MERGE: (id: number) => `/parties/${id}/merge`,
  PARTY_TRANSFER: (id: number) => `/parties/${id}/transfer`,
  INVESTOR_PARTY: (id: number) => `/investors/${id}/party`,
  SCREENING_RESULTS: "/screening-results",
  SCREENING_REVIEW: (id: number) => `/screening-results/${id}/review`,
  WATCHLIST: "/watchlist",
  WATCHLIST_REMOVE: (id: number) => `/watchlist/${id}/remove`,
  DOCUMENT_CONTENT: (id: string) => `/documents/${id}/content`,

  APPLICATIONS: "/applications",
  APPLICATION_ESTIMATE: "/applications/estimate",
  APPLICATION: (id: number) => `/applications/${id}`,
  APPLICATION_GUARANTORS: (id: number) => `/applications/${id}/guarantors`,
  APPLICATION_DOCUMENTS: (id: number) => `/applications/${id}/documents`,
  APPLICATION_CRB: (id: number) => `/applications/${id}/crb`,
  APPLICATION_CHECKS: (id: number) => `/applications/${id}/checks`,
  APPLICATION_SCREEN: (id: number) => `/applications/${id}/screen`,
  APPLICATION_DECISION: (id: number) => `/applications/${id}/decision`,
  APPLICATION_LOG: (id: number) => `/applications/${id}/log`,
  EXTRACTION_REQUEST: (partyId: number, documentId: string) => `/parties/${partyId}/documents/${documentId}/extractions`,
  EXTRACTION_RETRY: (id: number) => `/extractions/${id}/retry`,
  EXTRACTION_REVIEW: (id: number) => `/extractions/${id}/review`,
  EXTRACTION_REVIEW_FIELD: (id: number, fieldId: number) => `/extractions/${id}/review/fields/${fieldId}`,
  EXTRACTION_REVIEW_ROW: (id: number, rowId: number) => `/extractions/${id}/review/transactions/${rowId}`,
  EXTRACTION_REVIEW_UNRELIABLE: (id: number) => `/extractions/${id}/review/unreliable`,
  EXTRACTION_REVIEW_SUBMIT: (id: number) => `/extractions/${id}/review/submit`,
  RULE_SET: "/screening/rule-set",
  AI_USAGE: "/ai/usage",
  AI_ACCURACY: "/ai/accuracy",
  BRANCHES: "/branches",
} as const;

// ── Clients ──

export const PARTY_ROLE_LABELS: Record<PartyRoleName, string> = {
  investor: "Investor",
  borrower: "Borrower",
  guarantor: "Guarantor",
  director: "Director",
  shareholder: "Shareholder",
  signatory: "Signatory",
  agent: "Agent",
  next_of_kin: "Next of kin",
};

export const RELATIONSHIP_LABELS: Record<RelationshipKind, { incoming: string; outgoing: string }> = {
  director: { incoming: "Director", outgoing: "Director of" },
  shareholder: { incoming: "Shareholder", outgoing: "Shareholder in" },
  signatory: { incoming: "Signatory", outgoing: "Signatory for" },
  next_of_kin: { incoming: "Next of kin", outgoing: "Next of kin of" },
  guarantor_of: { incoming: "Guarantor", outgoing: "Guarantor for" },
  related_party: { incoming: "Related party", outgoing: "Related party of" },
  referred_by: { incoming: "Referred by (agent)", outgoing: "Agent for" },
};

export const ORG_TYPE_LABELS: Record<OrgType, string> = {
  sme: "SME",
  corporate: "Corporate",
  cooperative: "Cooperative",
  ngo: "NGO",
  investment_group: "Investment group",
  public_institution: "Public institution",
  sacco: "SACCO",
  church: "Church",
  fund_manager: "Fund manager",
  insurer: "Insurer",
};

export const ID_TYPE_LABELS: Record<IdType, string> = {
  national_id: "National ID",
  passport: "Passport",
  alien_id: "Alien ID",
  kra_pin: "KRA PIN",
  company_reg_no: "Registration no.",
};

export const KYC_STATUS_LABELS: Record<KycStatus, string> = {
  incomplete: "Incomplete",
  pending_review: "Ready to verify",
  verified: "Verified",
};

export const DOCUMENT_TYPE_LABELS: Record<string, string> = {
  national_id: "National ID",
  passport: "Passport",
  kra_pin: "KRA PIN certificate",
  cr12: "CR12",
  certificate_of_incorporation: "Certificate of incorporation / business registration",
  bank_statement: "Bank statement",
  mpesa_statement: "M-Pesa statement",
  audited_financial_statements: "Audited financial statements",
  title_deed: "Title deed",
  logbook: "Logbook",
  valuation_report: "Valuation report",
  photo: "Photo",
  signature: "Signature",
  consent_form: "Signed consent form",
  other: "Other",
};

export const CONSENT_PURPOSE_LABELS: Record<ConsentPurpose, string> = {
  kyc_processing: "KYC processing",
  ai_document_processing: "Automatic document reading",
  credit_bureau_check: "Credit bureau checks",
  marketing: "Marketing",
};

export const CONSENT_METHOD_LABELS: Record<ConsentMethod, string> = {
  signed_form: "Signed form",
  in_branch: "In branch",
  email: "Email",
};

export const WATCHLIST_LABELS: Record<Watchlist, string> = {
  internal_blacklist: "Internal blacklist",
  pep: "PEP list",
  sanctions_un: "UN sanctions",
};

/** Compulsory-detail names from kyc.required_fields.* as staff read them. */
export const REQUIRED_FIELD_LABELS: Record<string, string> = {
  name: "first and last name",
  id_document: "ID or passport",
  kra_pin: "KRA PIN",
  date_of_birth: "date of birth",
  mobile: "mobile number",
  physical_address: "physical address",
  next_of_kin: "next of kin",
  legal_name: "registered name",
  registration_no: "registration number",
  registration_date: "registration date",
  director_with_id: "a director with an ID",
  phone: "phone number",
};

// ── Approvals & business rules ──

export const SETTING_SOURCE_LABELS: Record<SettingSource, string> = {
  working_assumption: "Working assumption",
  client_confirmed: "Confirmed by client",
  internal_decision: "Internal decision",
};

/** Plain-English names for change-request types; unknown types show as sent. */
export const REQUEST_TYPE_LABELS: Record<string, string> = {
  "settings.change": "Business rule change",
  "settings.change_security": "Security setting change",
  "rbac.grant_role": "Grant role",
  "rbac.revoke_role": "Revoke role",
  "rbac.set_limit": "Approval limit",
  "rbac.set_branch_scope": "Branch access",
  "rbac.set_role_active": "Role on/off",
  "document.destroy": "Destroy document",
  "party.change": "Client details change",
  "party.verify": "KYC verification",
  "party.pep_approve": "PEP approval",
  "party.merge": "Merge clients",
  "party.branch_transfer": "Branch transfer",
  "watchlist.remove": "Watchlist removal",
  "ai.review": "AI reading review",
  "application.crb_confirm": "CRB status",
  "credit.override": "Credit override",
};

export const PRODUCT_LABELS: Record<string, string> = {
  business_loan: "Business loan (3–24 months)",
  bridge_loan: "Short-term bridge loan (1–3 months, principal at maturity)",
  asset_finance: "Asset finance (6–36 months)",
};

export const OUTCOME_TONES: Record<string, string> = {
  shortlisted: "badge-positive",
  needs_review: "badge-waiting",
  not_qualified: "badge-negative",
};

export const OUTCOME_LABELS: Record<string, string> = {
  shortlisted: "Shortlisted",
  needs_review: "Needs review",
  not_qualified: "Not qualified",
};

export const CHECK_TONES: Record<string, string> = {
  pass: "badge-positive",
  fail: "badge-negative",
  needs_review: "badge-waiting",
  missing: "badge-waiting",
  not_applicable: "badge-neutral",
};

export const CRB_STATUS_LABELS: Record<string, string> = {
  clear: "Clear",
  listed: "Listed",
  previously_listed_cleared: "Previously listed, now cleared",
};
