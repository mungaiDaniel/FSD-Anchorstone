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

export type EmailType = "DEPOSIT_CONFIRMATION" | "WITHDRAWAL_CONFIRMATION" | "INTEREST_STATEMENT" | "ACCOUNT_STATEMENT" | "AUM_REPORT";

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
