// ============================================================================
// Anchorstone types — mirror the Flask API (app/*/model.py to_dict()).
// Money and rates arrive as strings (exact decimals); format, never do maths
// on them in floating point.
// ============================================================================

// ── API envelope ──

export interface ApiResponse<T = unknown> {
  status: number;
  message: string;
  data?: T;
}

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
}

// ── Staff users ──

export type UserRole = "user" | "admin" | "super_admin";
export type UserStatus = "active" | "disabled";

export interface User {
  id: number;
  name: string;
  email: string;
  role: UserRole;
  status: UserStatus;
  must_change_password: boolean;
  password_changed_at: string | null;
  created: string;
  /** Set while sign-in is locked after too many failed attempts (users list only). */
  locked_until?: string | null;
}

export interface UserWithTemporaryPassword {
  user: User;
  temporary_password: string;
}

export interface LoginResponse {
  access_token: string;
  role: UserRole;
  name: string;
  email: string;
  must_change_password: boolean;
}

// ── Investors ──

export type InvestorStatus = "active" | "closed";
export type PayoutMethod = "bank" | "mpesa";

export interface Investor {
  id: number;
  client_code: string;
  full_name: string;
  email: string;
  phone: string | null;
  id_number: string | null;
  kra_pin: string | null;
  payout_method: PayoutMethod | null;
  bank_name: string | null;
  payout_account: string | null;
  status: InvestorStatus;
  notes: string | null;
  created_at: string;
  created_by: string;
  closed_at: string | null;
}

export interface InvestorListItem extends Investor {
  balance: string;
  pending_withdrawals: string;
}

export interface InvestorSummary extends Investor {
  balance: string;
  total_deposited: string;
  total_withdrawn: string;
  pending_withdrawals: string;
  interest_paid: string;
  interest_payable: string;
}

export type InvestorInput = Partial<
  Pick<
    Investor,
    "full_name" | "email" | "phone" | "id_number" | "kra_pin" | "payout_method" | "bank_name" | "payout_account" | "notes"
  >
>;

export interface LedgerEntry {
  kind: "deposit" | "withdrawal";
  id: number;
  date: string;
  reference: string;
  method: PaymentMethod;
  amount: string; // signed
  balance: string;
}

export interface Ledger {
  opening_balance: string;
  closing_balance: string;
  entries: LedgerEntry[]; // newest first
}

// ── Transactions ──

export type PaymentMethod = "bank_transfer" | "mpesa" | "cheque" | "cash";

export interface Deposit {
  id: number;
  investor_id: number;
  client_code: string;
  investor_name: string;
  amount: string;
  value_date: string;
  method: PaymentMethod;
  reference: string;
  notes: string | null;
  status: "posted" | "reversed";
  recorded_by: string;
  created_at: string;
  reversed_by: string | null;
  reversed_at: string | null;
  reversal_reason: string | null;
}

export interface Withdrawal {
  id: number;
  investor_id: number;
  client_code: string;
  investor_name: string;
  amount: string;
  requested_date: string;
  method: PaymentMethod;
  notes: string | null;
  status: "pending" | "approved" | "rejected";
  requested_by: string;
  created_at: string;
  decided_by: string | null;
  decided_at: string | null;
  value_date: string | null;
  payment_reference: string | null;
  rejection_reason: string | null;
}

// ── Interest ──

export interface InterestRate {
  id: number;
  rate_percent: string;
  effective_from: string;
  note: string | null;
  set_by: string;
  created_at: string;
}

export interface RatesResponse {
  current: InterestRate | null;
  history: InterestRate[];
  locked_through: string | null;
}

export type PeriodStatus = "draft" | "approved" | "paid";

export interface InterestPeriod {
  id: number;
  label: string;
  period_start: string;
  period_end: string;
  status: PeriodStatus;
  tax_rate_percent: string;
  investor_count: number;
  total_gross: string;
  total_tax: string;
  total_net: string;
  calculated_by: string;
  calculated_at: string;
  approved_by: string | null;
  approved_at: string | null;
  paid_at: string | null;
}

export interface InterestPayout {
  id: number;
  period_id: number;
  period_label: string;
  period_status: PeriodStatus;
  investor_id: number;
  client_code: string;
  investor_name: string;
  days: number;
  opening_balance: string;
  closing_balance: string;
  average_daily_balance: string;
  rate_percent: string;
  gross_interest: string;
  tax_rate_percent: string;
  tax_amount: string;
  net_interest: string;
  status: "pending" | "paid";
  paid_at: string | null;
  paid_by: string | null;
  payment_reference: string | null;
}

export interface InterestPeriodDetail extends InterestPeriod {
  payouts: InterestPayout[];
}

// ── Emails ──

export type EmailType = "DEPOSIT_CONFIRMATION" | "DEPOSIT_REVERSAL" | "WITHDRAWAL_CONFIRMATION" | "INTEREST_STATEMENT" | "ACCOUNT_STATEMENT" | "AUM_REPORT";

/** Who to generate statements for: chosen ids, or everything matching the list's filter. */
export type RecipientSelection =
  | { investor_ids: number[] }
  | { filter: { search?: string; status?: string }; exclude_ids?: number[] };

export interface BulkStatementResult {
  generated: number;
  skipped_pending: number;
  selected: number;
  duplicate: boolean;
}

export interface EmailDecisionResult {
  changed: number;
  skipped: number;
}
export type EmailStatus = "pending" | "queued" | "sending" | "sent" | "failed" | "cancelled";

export interface OutboxEmail {
  id: number;
  email_type: EmailType;
  investor_id: number;
  client_code: string;
  deposit_id: number | null;
  withdrawal_id: number | null;
  payout_id: number | null;
  recipient_email: string;
  recipient_name: string | null;
  subject: string;
  body: string;
  status: EmailStatus;
  attempts: number;
  last_error: string | null;
  queued_at: string;
  sent_at: string | null;
  created_by: string | null;
  send_key: string | null;
  decided_by: string | null;
  decided_at: string | null;
  attachment_name: string | null;
}

export interface EmailQueueStatus {
  counts: Partial<Record<EmailStatus, number>>;
  next_run_at: string | null;
  suppressed: boolean;
}

// ── Dashboard ──

export interface OverviewStats {
  total_balance: string;
  active_investors: number;
  funded_investors: number;
  deposits_this_month: string;
  withdrawals_this_month: string;
  pending_withdrawals: { count: number; total: string };
  current_rate: InterestRate | null;
  interest_outstanding: string;
  last_period: InterestPeriod | null;
  draft_period: InterestPeriod | null;
  emails: { queued: number; failed: number; pending: number };
  monthly_flows: { month: string; deposits: string; withdrawals: string }[];
  as_of: string;
}

// ── Audit / backups / settings ──

export type ReportName = "investors" | "deposits" | "withdrawals" | "interest" | "aum" | "audit-log" | "email-log";

export interface ReportInfo {
  name: ReportName;
  title: string;
  min_role: UserRole;
}

export interface ReportSchedule {
  aum_enabled: boolean;
  aum_recipients: string[];
  aum_last_month: string | null;
  aum_last_run_at: string | null;
  updated_by: string | null;
}

export interface AuditLogEntry {
  id: number;
  user_id: number | null;
  user_email?: string | null;
  user_name?: string | null;
  action: string;
  target_type: string | null;
  target_id: number | null;
  target_name: string | null;
  description: string | null;
  old_value: string | null;
  new_value: string | null;
  ip_address: string | null;
  user_agent: string | null;
  timestamp: string;
  success: boolean;
  error_message: string | null;
}

export interface BackupLogEntry {
  id: number;
  filename: string;
  status: "running" | "success" | "failed";
  triggered_by: "scheduled" | "manual";
  triggered_by_email: string | null;
  file_size_bytes: number | null;
  onedrive_web_url: string | null;
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
}

export interface BackupStatus {
  enabled: boolean;
  next_run_at: string | null;
  last_backup: BackupLogEntry | null;
}

export interface EmailSettingsData {
  mail_server: string | null;
  mail_port: number | null;
  mail_use_tls: boolean | null;
  mail_use_ssl: boolean | null;
  mail_username: string | null;
  mail_default_sender: string | null;
  mail_bcc: string | null;
  has_password: boolean;
  email_queue_batch_size: number | null;
  email_queue_interval_minutes: number | null;
}

export interface EmailSettingsUpdate {
  mail_server?: string;
  mail_port?: number;
  mail_use_tls?: boolean;
  mail_use_ssl?: boolean;
  mail_username?: string;
  mail_password?: string;
  mail_default_sender?: string;
  mail_bcc?: string;
}

export interface EmailQueueSettingsData {
  batch_size: number;
  interval_minutes: number;
  next_run_at: string | null;
}

// ── Approvals (change requests, app/Approvals) ──

export type ChangeRequestStatus = "pending" | "returned" | "applied" | "rejected" | "cancelled" | "expired" | "failed";
export type ChangeRequestAction =
  | "submit" | "approve" | "reject" | "return" | "resubmit" | "cancel" | "apply" | "expire" | "fail";

export interface ApprovalLevel {
  permission: string;
  count?: number;
}

export interface ChangeRequestEvent {
  id: number;
  round: number;
  action: ChangeRequestAction;
  level: number | null;
  actor_email: string;
  comment: string | null;
  at: string;
}

export interface ChangeRequest {
  id: number;
  request_type: string;
  entity_type: string | null;
  entity_id: string | null;
  payload: Record<string, unknown>;
  summary: string | null;
  amount: string | null;
  currency: "KES";
  branch_id: number | null;
  status: ChangeRequestStatus;
  reason: string | null;
  maker_email: string;
  submitted_at: string;
  expires_at: string;
  decided_at: string | null;
  applied_at: string | null;
  levels_required: number;
  levels_done: number;
  round: number;
  levels: ApprovalLevel[] | null;
  result: unknown;
  error: string | null;
  /** Whether the server would let me decide it now. Cosmetic: the server re-checks. */
  can_decide?: boolean;
  events?: ChangeRequestEvent[];
}

// ── Business-rule settings (app/Settings/registry.py, business.overview) ──

export type SettingSource = "working_assumption" | "client_confirmed" | "internal_decision";
export type SettingType = "int" | "decimal" | "bool" | "enum" | "list" | "json" | "text";

/** A setting value as JSON: decimals arrive as strings. */
export type SettingValue = string | number | boolean | null | SettingValue[] | { [k: string]: SettingValue };

export interface SettingVersion {
  id: number;
  key: string;
  scope_type: "global" | "branch" | "product";
  scope_id: number | null;
  value: SettingValue;
  effective_from: string;
  version_no: number;
  source: SettingSource;
  evidence: string | null;
  reason: string | null;
  change_request_id: number | null;
  created_by: string;
  approved_by: string;
  approved_at: string | null;
}

export interface BusinessSetting {
  key: string;
  category: string;
  type: SettingType;
  description: string;
  binding: "immediate" | "event_date" | "at_booking" | "new_versions_only";
  scopes: string[];
  approvals_required: number;
  in_use: boolean;
  wa_ref: string | null;
  questionnaire_ref: string | null;
  choices: string[];
  default: SettingValue;
  value: SettingValue;
  /** null only before the key is seeded (the registry default is shown). */
  source: SettingSource | null;
  effective_from: string | null;
  history: SettingVersion[];
}

export interface BusinessSettingProposal {
  value: SettingValue;
  effective_from: string;
  source: SettingSource;
  evidence?: string;
  reason: string;
}

// ── Clients (parties, app/Parties) ──

export type PartyType = "person" | "organisation";
export type KycStatus = "incomplete" | "pending_review" | "verified";
export type PartyStatus = "active" | "blacklisted" | "merged";
export type PartyRoleName =
  | "investor" | "borrower" | "guarantor" | "director" | "shareholder" | "signatory" | "agent" | "next_of_kin";
export type RelationshipKind =
  | "director" | "shareholder" | "signatory" | "next_of_kin" | "guarantor_of" | "related_party" | "referred_by";
export type IdType = "national_id" | "passport" | "alien_id" | "kra_pin" | "company_reg_no";
export type ContactKind = "email" | "mobile" | "phone";
export type AddressKind = "home" | "business" | "postal" | "registered";
export type OrgType =
  | "sme" | "corporate" | "cooperative" | "ngo" | "investment_group" | "public_institution" | "sacco" | "church"
  | "fund_manager" | "insurer";
export type ConsentPurpose = "kyc_processing" | "ai_document_processing" | "credit_bureau_check" | "marketing";
export type ConsentMethod = "signed_form" | "in_branch" | "email";
export type Watchlist = "internal_blacklist" | "pep" | "sanctions_un";

export interface PartySummary {
  id: number;
  party_no: string;
  party_type: PartyType;
  display_name: string;
  kyc_status: KycStatus;
  status: PartyStatus;
  is_pep: boolean;
}

export interface PartyListItem extends PartySummary {
  home_branch_id: number;
  roles: PartyRoleName[];
  email: string | null;
  phone: string | null;
}

export interface PartyPersonDetails {
  salutation: string | null;
  first_name: string | null;
  middle_name: string | null;
  last_name: string | null;
  gender: "male" | "female" | "other" | null;
  date_of_birth: string | null;
  marital_status: "single" | "married" | "divorced" | "widowed" | "other" | null;
  nationality: string;
  residency: "local" | "foreign";
  sector: string | null;
  nature_of_business: string | null;
  employer_name: string | null;
  employer_party_id: number | null;
  name_needs_review: boolean;
}

export interface PartyOrganisationDetails {
  legal_name: string;
  trading_name: string | null;
  registration_date: string | null;
  org_type: OrgType;
  sector: string | null;
  nature_of_business: string | null;
}

export interface PartyIdentifier {
  id: number;
  id_type: IdType;
  issuing_country: string;
  value: string;
  issued_on: string | null;
  expires_on: string | null;
}

export interface PartyContact {
  id: number;
  kind: ContactKind;
  value: string;
  is_primary: boolean;
  needs_review: boolean;
}

export interface PartyAddress {
  id: number;
  kind: AddressKind;
  line1: string;
  line2: string | null;
  town: string | null;
  county: string | null;
  country: string;
}

export interface PartyBankAccount {
  id: number;
  kind: "bank" | "mpesa";
  bank_name: string | null;
  branch_name: string | null;
  account_no: string;
  account_name: string | null;
  is_default_payout: boolean;
  status: "active" | "ended";
}

export interface PartyRoleRow {
  id: number;
  role: PartyRoleName;
  status: "active" | "ended";
  started_on: string;
  ended_on: string | null;
}

export interface PartyRelationship {
  id: number;
  from_party_id: number;
  to_party_id: number;
  relationship: RelationshipKind;
  share_pct: string | null;
  kin_relationship: string | null;
  signatory_list: "A" | "B" | null;
  committed_amount: string | null;
  status: "active" | "ended";
  started_on: string;
  ended_on: string | null;
  /** incoming: the other party relates to this one (a director, next of kin); outgoing: this one relates to it. */
  direction: "incoming" | "outgoing";
  party: PartySummary;
}

export interface PartyPep {
  position_held: string;
  country: string;
  since: string | null;
  until: string | null;
  pep_relationship: "self" | "family_member" | "close_associate";
  related_pep_name: string | null;
  source_of_funds: string;
  source_of_wealth: string;
  status: "pending" | "approved" | "cleared";
  recorded_by: string;
  approved_at: string | null;
  approved_by: string | null;
}

export interface ScreeningMatch {
  entry_id: number;
  list: Watchlist;
  name: string;
  matched_on: ("name" | "identifier")[];
}

export interface ScreeningResult {
  id: number;
  party_id: number;
  trigger: "onboarding" | "identity_change" | "watchlist_change" | "rescreen";
  lists: string[];
  matches: ScreeningMatch[];
  outcome: "clear" | "potential_match";
  review_status: "not_required" | "pending" | "cleared" | "confirmed";
  maker_email: string;
  screened_by: string;
  screened_at: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_note: string | null;
  party?: PartySummary;
}

export interface PartyMandate {
  id: number;
  rule: "any_one" | "all" | "a_and_b" | "custom";
  description: string | null;
  effective_from: string;
}

export interface PartyDetail extends PartySummary {
  home_branch_id: number;
  classification: string | null;
  risk_rating: "low" | "medium" | "high" | null;
  merged_into_party_id: number | null;
  relationship_officer_user_id: number | null;
  notes: string | null;
  verified_at: string | null;
  verified_by: string | null;
  created_at: string;
  created_by: string;
  person: PartyPersonDetails | null;
  organisation: PartyOrganisationDetails | null;
  identifiers: PartyIdentifier[];
  contacts: PartyContact[];
  addresses: PartyAddress[];
  bank_accounts: PartyBankAccount[];
  roles: PartyRoleRow[];
  relationships: PartyRelationship[];
  mandate: PartyMandate | null;
  missing_fields: string[];
  verification_blockers: string[];
  pep: PartyPep | null;
  screening: { last: ScreeningResult | null; pending: number };
  /** Only in the create response. */
  warnings?: DuplicateWarning[];
}

export interface PartyAccount {
  id: number;
  account_no: string;
  account_type: "investment";
  party_id: number;
  branch_id: number;
  currency: "KES";
  status: "active" | "closed";
  opened_on: string;
  closed_on: string | null;
  investor_id?: number;
  statement_email?: string;
  balance?: string;
  pending_withdrawals?: string;
  interest_paid?: string;
}

export interface PartyDocument {
  id: string;
  document_type: string;
  label: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  sensitive: boolean;
  status: "active" | "destroyed";
  uploaded_by: string;
  uploaded_at: string;
  current: boolean;
}

export interface PartyConsent {
  id: number;
  party_id: number;
  purpose: ConsentPurpose;
  granted_on: string;
  method: ConsentMethod;
  notice_version: string;
  evidence_document_id: string | null;
  captured_by: string;
  captured_at: string;
  status: "active" | "withdrawn";
  withdrawn_at: string | null;
  withdrawn_by: string | null;
  withdrawal_note: string | null;
}

export interface PartyOverview extends PartyDetail {
  accounts: PartyAccount[];
  loans: unknown[];
  guarantees: PartyRelationship[];
  directorships: PartyRelationship[];
  documents: PartyDocument[];
  consents: PartyConsent[];
  screening_results: ScreeningResult[];
  pending_changes: ChangeRequest[];
  merged_into: PartySummary | null;
}

export interface DuplicateWarning {
  kind: ContactKind;
  value: string;
  party: PartySummary;
  message: string;
}

export interface DuplicateCheck {
  conflicts: { id_type: IdType; value: string; message: string; party: PartySummary | null }[];
  warnings: DuplicateWarning[];
}

export interface PepInput {
  is_pep: boolean;
  position_held?: string;
  country?: string;
  since?: string | null;
  until?: string | null;
  pep_relationship?: PartyPep["pep_relationship"];
  related_pep_name?: string | null;
  source_of_funds?: string;
  source_of_wealth?: string;
  reason?: string;
}

/** The body for creating or editing a client: raw values, which the server cleans and checks. */
export interface PartyInput {
  party_type?: PartyType;
  classification?: string | null;
  risk_rating?: "low" | "medium" | "high" | null;
  notes?: string | null;
  person?: Partial<Omit<PartyPersonDetails, "employer_party_id" | "name_needs_review">>;
  organisation?: Partial<PartyOrganisationDetails>;
  identifiers?: { id_type: IdType; value: string }[];
  contacts?: { kind: ContactKind; value: string; is_primary?: boolean }[];
  addresses?: { kind: AddressKind; line1: string; line2?: string | null; town?: string | null; county?: string | null }[];
  bank_accounts?: { kind: "bank" | "mpesa"; bank_name?: string | null; branch_name?: string | null; account_no: string;
    account_name?: string | null; is_default_payout?: boolean }[];
  roles?: PartyRoleName[];
  pep?: PepInput;
  reason?: string;
}

export interface PartyEditResult extends PartyDetail {
  saved: string[];
  change_request: ChangeRequest | null;
}

export interface WatchlistEntry {
  id: number;
  list: Watchlist;
  full_name: string;
  identifiers: { id_type: IdType; value: string }[];
  reason: string;
  source: string | null;
  status: "active" | "removed";
  added_by: string;
  added_at: string;
  removed_by: string | null;
  removed_at: string | null;
  matched_parties?: number;
}

// ── AI extraction review and pre-selection (phase 3b) ──

export type ProductCode = "business_loan" | "bridge_loan" | "asset_finance";
export type CrbStatusValue = "clear" | "listed" | "previously_listed_cleared";
export type Outcome = "shortlisted" | "needs_review" | "not_qualified";
export type DecisionValue = "proceed" | "decline" | "more_info";
export type CheckStatus = "pass" | "fail" | "needs_review" | "missing" | "not_applicable";
export type RuleResultValue = "pass" | "fail" | "missing" | "not_applicable";
export type ReviewState = "draft" | "submitted" | "returned" | "approved" | "rejected";

export interface Extraction {
  id: number;
  party_id: number;
  document_id: string;
  declared_type: string;
  status: "queued" | "running" | "completed" | "needs_review" | "rescan_needed" | "failed";
  status_label: string;
  status_reason: string | null;
  detected_document_type: string | null;
  readable: boolean | null;
  page_count: number | null;
  warnings: string[];
  model_requested: string;
  prompt_version: string;
  schema_version: string;
  document_sha256: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: string;
  requested_by: string;
  requested_at: string;
  finished_at: string | null;
}

export interface ApplicationDocument {
  id: string;
  document_type: string;
  label: string;
  filename: string;
  content_type: string;
  status: string;
  uploaded_at: string;
  extraction: Extraction | null;
}

export interface CrbStatus {
  id: number;
  status: CrbStatusValue;
  status_label: string;
  status_date: string;
  bureau: string;
  extraction_id: number | null;
  source: "entered" | "crb_report";
  change_request_id: number | null;
  entered_by: string;
  confirmed_by: string | null;
  confirmed_at: string | null;
}

export interface RuleResult {
  position: number;
  rule_id: string;
  description: string;
  metric: string;
  value: unknown;
  comparison: string;
  threshold: unknown;
  result: RuleResultValue;
  outcome_if_failed: Outcome | null;
  reason: string;
}

export interface ScreeningRunResult {
  id: number;
  application_id: number;
  outcome: Outcome;
  outcome_label: string;
  recommendation_only: true;
  rule_set_version_id: number;
  rule_set_version_no: number;
  inputs_sha256: string;
  evaluated_by: string;
  evaluated_at: string;
  rules: RuleResult[];
}

export interface CreditDecision {
  id: number;
  decision: DecisionValue;
  decision_label: string;
  reason: string;
  override: boolean;
  decided_by: string;
  decided_at: string;
  approved_by: string | null;
}

export interface PartySummaryRef {
  id: number;
  party_no: string;
  party_type: "person" | "organisation";
  display_name: string;
}

export interface ApplicationListItem {
  id: number;
  application_no: string;
  party_id: number;
  product_code: ProductCode;
  product_label: string;
  repayment: "amortising" | "interest_only";
  amount_requested: string;
  term_months: number;
  indicative_rate_percent: string;
  estimated_instalment: string;
  estimated_final_payment: string;
  estimate_note: string;
  business_start_date: string | null;
  status: "open" | "decided";
  created_by: string;
  created_at: string;
  party: PartySummaryRef | null;
  recommendation: Outcome | null;
  decision: DecisionValue | null;
}

export interface ApplicationDetail extends ApplicationListItem {
  guarantors: PartySummaryRef[];
  crb: CrbStatus | null;
  documents: ApplicationDocument[];
  latest_run: ScreeningRunResult | null;
  decisions: CreditDecision[];
  pending_override: number | null;
}

export interface ApplicationInput {
  party_id: number;
  product_code: ProductCode;
  amount_requested: string;
  term_months: number;
  indicative_rate_percent: string;
  business_start_date?: string;
}

export interface Estimate {
  estimated_instalment: string;
  estimated_final_payment: string;
  repayment: "amortising" | "interest_only";
  estimate_note: string;
}

export interface CheckEvidence {
  source: string;
  field: string;
  value: string | null;
  page: number | null;
}

export interface CrossCheck {
  check: string;
  status: CheckStatus;
  reason: string;
  evidence: CheckEvidence[];
}

export type ReviewAction = "accept" | "correct" | "not_present";

export interface ReviewField {
  id: number;
  path: string;
  value: string | null;
  confidence: string | null;
  source_page: number | null;
  source_text: string | null;
  legibility: string | null;
  notes: string | null;
  validation: "passed" | "failed" | "empty";
  validation_reason: string | null;
  low_confidence: boolean;
  review: { action: ReviewAction; corrected_value: string | null; reason: string | null; reviewed_by: string } | null;
}

export interface ReviewPage {
  page_number: number;
  status: string;
  opening_balance: string | null;
  closing_balance: string | null;
  credits_total: string | null;
  debits_total: string | null;
  difference: string | null;
  reason: string | null;
  reviewed_status: string;
  reviewed_difference?: string | null;
  reviewed_reason: string | null;
  corrected_rows?: number;
}

export interface ReviewTransaction {
  id: number;
  page_number: number;
  row_no: number;
  date: string | null;
  description: string | null;
  reference: string | null;
  debit: string | null;
  credit: string | null;
  balance: string | null;
  confidence: string | null;
  low_confidence: boolean;
  review: { date: string | null; debit: string | null; credit: string | null; balance: string | null;
    reason: string; reviewed_by: string } | null;
}

export interface ExtractionReviewDetail {
  extraction: Extraction & { label: string };
  document: { id: string; filename: string; content_type: string };
  statement: boolean;
  confidence_threshold: string;
  state: ReviewState;
  review: {
    id: number;
    state: ReviewState;
    reviewed_by: string;
    submitted_at: string | null;
    approved_by: string | null;
    change_request_id: number | null;
    statement_unreliable: boolean;
    unreliable_reason: string | null;
    confirmed_metrics: { period_from: string | null; period_to: string | null; metrics: Record<string, string> } | null;
    party_updates: { written: string[]; kept_existing: string[]; refused: string[] } | null;
  } | null;
  fields: ReviewField[];
  pages: ReviewPage[];
  transactions: ReviewTransaction[];
  missing_actions: number;
}

export interface Rule {
  id: string;
  description: string;
  metric: string;
  comparison: string;
  threshold: unknown;
  outcome_if_failed: Outcome | Record<string, Outcome>;
  applies_to?: { party_types?: string[]; products?: string[] };
}

export interface RuleSetInfo {
  version_id: number | null;
  version_no: number | null;
  effective_from: string | null;
  rule_set: { rules: Rule[] } | null;
  metrics: { name: string; kind: "number" | "text"; description: string }[];
  comparisons: string[];
  outcomes: string[];
  products: string[];
  protected_attributes: string[];
}

export interface AiUsageMonth {
  month: string;
  calls: number;
  readings: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: string;
  refusals: AiRefusal[];
  by_type: { document_type: string; label: string; model: string; calls: number; ok_calls: number; readings: number;
    input_tokens: number; output_tokens: number; cost_usd: string; cost_per_reading_usd: string | null }[];
}

export interface AiAccuracyRow {
  document_type: string;
  label: string;
  values: number;
  accepted: number;
  corrected: number;
  not_present: number;
  confident_but_corrected: number;
  accepted_as_read_percent: string | null;
  statement_rows_corrected: number;
}

export interface DecisionLogReading {
  document_id: string;
  extraction: Extraction;
  label: string;
  calls: number;
  review: {
    state: ReviewState;
    reviewed_by: string;
    submitted_at: string | null;
    approved_by: string | null;
    approved_at: string | null;
    statement_unreliable: boolean;
    unreliable_reason: string | null;
    values: { field: string; ai_value: string | null; ai_confidence: string | null; page: number | null;
      action: string; confirmed_value: string | null; reason: string | null; reviewed_by: string }[];
    rows_corrected: { page: number; row: number; description: string | null;
      ai: Record<string, string | null>; confirmed: Record<string, string | null>; reason: string }[];
    confirmed_metrics: { metrics: Record<string, string> } | null;
  } | null;
}

export interface DecisionLog {
  application: ApplicationDetail;
  documents: ApplicationDocument[];
  readings: DecisionLogReading[];
  crb_statuses: CrbStatus[];
  checks: CrossCheck[];
  runs: ScreeningRunResult[];
  decisions: CreditDecision[];
  audit: { action: string; description: string | null; user: string | null; at: string }[];
}

export interface AiRefusal {
  id: number;
  extraction_id: number;
  application_id: number | null;
  page_number: number | null;
  kind: "disabled" | "paused" | "pricing" | "monthly" | "per_application" | "per_run";
  label: string;
  limit_usd: string | null;
  spent_usd: string | null;
  estimate_usd: string | null;
  message: string;
  refused_at: string;
}

export interface AiStatus {
  status: "running" | "paused";
  paused_at: string | null;
  paused_reason: string | null;
  resumed_at: string | null;
  resumed_by: string | null;
  resume_reason: string | null;
  enabled: boolean;
  budgets: { monthly_usd: string; per_application_usd: string; per_run_usd: string };
  spent_this_month_usd: string;
  breaker: { consecutive_failures: number; window_failures: number; window_minutes: number };
  recent_refusals: AiRefusal[];
}
