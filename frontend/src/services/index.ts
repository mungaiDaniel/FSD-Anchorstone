import api from "./api";
import { API } from "@/lib/constants";
import type {
  ApiResponse,
  AuditLogEntry,
  BackupLogEntry,
  BackupStatus,
  BusinessSetting,
  BusinessSettingProposal,
  ChangeRequest,
  ChangeRequestStatus,
  ConsentMethod,
  ConsentPurpose,
  DuplicateCheck,
  KycStatus,
  PartyConsent,
  PartyDetail,
  PartyDocument,
  PartyEditResult,
  PartyInput,
  PartyListItem,
  PartyMandate,
  PartyOverview,
  PartyRelationship,
  PartyType,
  PepInput,
  ScreeningResult,
  Watchlist,
  WatchlistEntry,
  Deposit,
  EmailQueueSettingsData,
  EmailQueueStatus,
  EmailSettingsData,
  EmailSettingsUpdate,
  InterestPayout,
  InterestPeriod,
  InterestPeriodDetail,
  InterestRate,
  Investor,
  InvestorInput,
  InvestorListItem,
  InvestorSummary,
  Ledger,
  LoginResponse,
  OutboxEmail,
  OverviewStats,
  Paginated,
  PaymentMethod,
  RatesResponse,
  User,
  UserRole,
  UserStatus,
  UserWithTemporaryPassword,
  Withdrawal,
  BulkStatementResult,
  EmailDecisionResult,
  RecipientSelection,
  ReportInfo,
  ReportName,
  ReportSchedule,
  AiAccuracyRow,
  AiUsageMonth,
  ApplicationDetail,
  ApplicationInput,
  ApplicationListItem,
  CreditDecision,
  CrbStatus,
  CrbStatusValue,
  CrossCheck,
  DecisionLog,
  DecisionValue,
  Estimate,
  Extraction,
  ExtractionReviewDetail,
  ReviewAction,
  Rule,
  RuleSetInfo,
  ScreeningRunResult,
} from "@/lib/types";

/** Unwraps the API envelope {status, message, data}. */
async function get<T>(url: string, params?: object): Promise<T> {
  const res = await api.get<ApiResponse<T>>(url, { params });
  return res.data.data as T;
}

async function send<T>(method: "post" | "patch" | "put" | "delete", url: string, body?: object): Promise<ApiResponse<T>> {
  const res =
    method === "delete" ? await api.delete<ApiResponse<T>>(url) : await api[method]<ApiResponse<T>>(url, body ?? {});
  return res.data;
}

async function openBlob(url: string, filename: string, type: string) {
  // Fetched with the auth header (not a token in the URL), then opened locally.
  const res = await api.get(url, { responseType: "blob" });
  const objectUrl = URL.createObjectURL(new Blob([res.data], { type }));
  const win = window.open(objectUrl, "_blank");
  if (!win) {
    const a = document.createElement("a");
    a.href = objectUrl;
    a.download = filename;
    a.click();
  }
  setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
}

export interface ListParams {
  page?: number;
  per_page?: number;
  search?: string;
  status?: string;
}

// ── Auth & users ──

export const authService = {
  login: (email: string, password: string) =>
    api.post<ApiResponse<LoginResponse>>(API.LOGIN, { email, password }).then((r) => r.data.data as LoginResponse),
  changePassword: (current_password: string, new_password: string) =>
    send<User>("post", API.CHANGE_PASSWORD, { current_password, new_password }),
  me: () => get<User>(API.ME),
};

export const userService = {
  getAll: () => get<User[]>(API.USERS),
  create: (name: string, email: string, role: UserRole) =>
    send<UserWithTemporaryPassword>("post", API.USERS, { name, email, role }),
  setStatus: (id: number, status: UserStatus) => send<User>("patch", API.SET_USER_STATUS(id), { status }),
  setRole: (id: number, role: UserRole) => send<User>("patch", API.SET_USER_ROLE(id), { role }),
  resetPassword: (id: number) => send<UserWithTemporaryPassword>("post", API.RESET_USER_PASSWORD(id)),
  unlock: (id: number) => send<User>("post", API.UNLOCK_USER(id)),
  delete: (id: number) => send("delete", API.USER_BY_ID(id)),
};

// ── Investors ──

export const investorService = {
  list: (params: ListParams) => get<Paginated<InvestorListItem>>(API.INVESTORS, params),
  get: (id: number) => get<InvestorSummary>(API.INVESTOR(id)),
  create: (data: InvestorInput) => send<InvestorSummary>("post", API.INVESTORS, data),
  update: (id: number, data: InvestorInput) => send<InvestorSummary>("patch", API.INVESTOR(id), data),
  setStatus: (id: number, status: Investor["status"]) => send<InvestorSummary>("patch", API.INVESTOR_STATUS(id), { status }),
  ledger: (id: number) => get<Ledger>(API.INVESTOR_LEDGER(id)),
  deposits: (id: number) => get<Deposit[]>(API.INVESTOR_DEPOSITS(id)),
  withdrawals: (id: number) => get<Withdrawal[]>(API.INVESTOR_WITHDRAWALS(id)),
  payouts: (id: number) => get<InterestPayout[]>(API.INVESTOR_PAYOUTS(id)),
  emails: (id: number) => get<OutboxEmail[]>(API.INVESTOR_EMAILS(id)),
};

// ── Deposits & withdrawals ──

export interface DepositInput {
  investor_id: number;
  amount: string;
  value_date: string;
  method: PaymentMethod;
  reference: string;
  notes?: string;
}

export interface WithdrawalInput {
  investor_id: number;
  amount: string;
  requested_date: string;
  method: PaymentMethod;
  notes?: string;
}

export const transactionService = {
  deposits: (params: ListParams & { from?: string; to?: string }) => get<Paginated<Deposit>>(API.DEPOSITS, params),
  recordDeposit: (data: DepositInput) => send<Deposit>("post", API.DEPOSITS, data),
  reverseDeposit: (id: number, reason: string) => send<Deposit>("post", API.DEPOSIT_REVERSE(id), { reason }),

  withdrawals: (params: ListParams) => get<Paginated<Withdrawal>>(API.WITHDRAWALS, params),
  requestWithdrawal: (data: WithdrawalInput) => send<Withdrawal>("post", API.WITHDRAWALS, data),
  approveWithdrawal: (id: number, body: { value_date?: string; payment_reference?: string }) =>
    send<Withdrawal>("post", API.WITHDRAWAL_APPROVE(id), body),
  rejectWithdrawal: (id: number, reason: string) => send<Withdrawal>("post", API.WITHDRAWAL_REJECT(id), { reason }),
};

// ── Interest ──

export const interestService = {
  rates: () => get<RatesResponse>(API.INTEREST_RATES),
  setRate: (rate_percent: string, effective_from: string, note?: string) =>
    send<InterestRate>("post", API.INTEREST_RATES, { rate_percent, effective_from, note }),
  periods: () => get<{ items: InterestPeriod[]; locked_through: string | null }>(API.INTEREST_PERIODS),
  period: (id: number) => get<InterestPeriodDetail>(API.INTEREST_PERIOD(id)),
  calculate: (year: number, month: number) => send<InterestPeriod>("post", API.INTEREST_CALCULATE, { year, month }),
  approve: (id: number) => send<InterestPeriod>("post", API.INTEREST_APPROVE(id)),
  discard: (id: number) => send("delete", API.INTEREST_PERIOD(id)),
  markPaid: (id: number, payments: { payout_id: number; reference: string }[]) =>
    send<InterestPeriod>("post", API.INTEREST_MARK_PAID(id), { payments }),
  openStatement: (payout: InterestPayout) =>
    openBlob(API.PAYOUT_STATEMENT_PDF(payout.id), `statement-${payout.client_code}-${payout.period_label}.pdf`, "application/pdf"),
};

// ── Emails ──

export const emailService = {
  list: (params: ListParams & { type?: string }) => get<Paginated<OutboxEmail>>(API.EMAILS, params),
  status: () => get<EmailQueueStatus>(API.EMAILS_STATUS),
  retry: (id: number) => send<OutboxEmail>("post", API.EMAIL_RETRY(id)),
  cancel: (id: number) => send<OutboxEmail>("post", API.EMAIL_CANCEL(id)),
  sendNow: () => send<{ claimed: number; sent: number; failed: number }>("post", API.EMAILS_SEND_NOW),
  // Pending emails: an admin confirms (sends) or suppresses them
  confirm: (ids: number[]) => send<EmailDecisionResult>("post", API.EMAILS_CONFIRM, { ids }),
  suppress: (ids: number[]) => send<EmailDecisionResult>("post", API.EMAILS_SUPPRESS, { ids }),
  confirmAll: () => send<EmailDecisionResult>("post", API.EMAILS_CONFIRM, { all_pending: true }),
  suppressAll: () => send<EmailDecisionResult>("post", API.EMAILS_SUPPRESS, { all_pending: true }),
  /** Opens the stored attachment (the exact PDF the investor will get) in a new tab. */
  openAttachment: (id: number, filename: string) => openBlob(API.EMAIL_ATTACHMENT(id), filename, "application/pdf"),
  // On-demand "as of today" statements (admins only); they arrive as pending
  generateStatement: (investorId: number) => send<OutboxEmail>("post", API.INVESTOR_STATEMENT_EMAIL(investorId)),
  generateStatements: (recipients: RecipientSelection, send_key: string) =>
    send<BulkStatementResult>("post", API.STATEMENTS_BULK, { recipients, send_key }),
};

export const statsService = {
  overview: () => get<OverviewStats>(API.OVERVIEW_STATS),
};

// ── Super admin ──

export const auditService = {
  list: (params: { action?: string; target_type?: string; user?: string; from?: string; to?: string; page?: number; per_page?: number }) =>
    get<Paginated<AuditLogEntry>>(API.AUDIT_LOGS, params),
};

// ── Reports (Excel) ──

export const reportService = {
  list: () => get<ReportInfo[]>(API.REPORTS),
  /** Builds the report on the server and saves the .xlsx it returns. */
  async download(name: ReportName, params: Record<string, string | undefined>) {
    const clean = Object.fromEntries(Object.entries(params).filter(([, v]) => v));
    const res = await api.get(API.REPORT_XLSX(name), { params: clean, responseType: "blob", timeout: 120000 });
    const disposition = String(res.headers["content-disposition"] ?? "");
    const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? `Anchorstone_${name}.xlsx`;
    const url = URL.createObjectURL(res.data as Blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    return filename;
  },
  getSchedule: () => get<ReportSchedule>(API.SCHEDULED_REPORTS),
  saveSchedule: (data: { aum_enabled?: boolean; aum_recipients?: string[] }) =>
    send<ReportSchedule>("patch", API.SCHEDULED_REPORTS, data),
  runScheduleNow: () => send<{ generated: number }>("post", API.SCHEDULED_REPORTS_RUN),
};

export const backupService = {
  getAll: (limit = 50) => get<BackupLogEntry[]>(`${API.BACKUPS}?limit=${limit}`),
  getStatus: () => get<BackupStatus>(API.BACKUPS_STATUS),
  // Queues the backup for the worker; it shows in the list when it finishes.
  runNow: () => send<{ job_id: number }>("post", API.BACKUPS_RUN_NOW),
};

export const settingsService = {
  getEmailSettings: () => get<EmailSettingsData>(API.SETTINGS_EMAIL),
  updateEmailSettings: (data: EmailSettingsUpdate) => send<EmailSettingsData>("patch", API.SETTINGS_EMAIL, data),
  sendTestEmail: (recipient: string) => send<{ suppressed: boolean }>("post", API.SETTINGS_EMAIL_TEST, { recipient }),
  getEmailQueueSettings: () => get<EmailQueueSettingsData>(API.SETTINGS_EMAIL_QUEUE),
  updateEmailQueueSettings: (batchSize: number, intervalMinutes: number) =>
    send("patch", API.SETTINGS_EMAIL_QUEUE, { batch_size: batchSize, interval_minutes: intervalMinutes }),
  // Business rules: reading is direct; a change is a change request decided in the Approvals inbox.
  getBusinessSettings: (source?: string) => get<BusinessSetting[]>(API.SETTINGS_BUSINESS, source ? { source } : undefined),
  proposeBusinessSetting: (key: string, data: BusinessSettingProposal) =>
    send<ChangeRequest>("post", API.SETTINGS_BUSINESS_KEY(key), data),
};

// ── Approvals (change requests) ──

export interface ChangeRequestListParams {
  page?: number;
  per_page?: number;
  /** Requests I made (any status). */
  mine?: boolean;
  /** Every request in this status. Without mine/status: what I may decide now. */
  status?: ChangeRequestStatus;
}

export const approvalService = {
  list: ({ mine, ...params }: ChangeRequestListParams) =>
    get<Paginated<ChangeRequest>>(API.CHANGE_REQUESTS, { ...params, ...(mine ? { mine: 1 } : {}) }),
  get: (id: number) => get<ChangeRequest>(API.CHANGE_REQUEST(id)),
  approve: (id: number, comment?: string) => send<ChangeRequest>("post", API.CHANGE_REQUEST_APPROVE(id), { comment }),
  reject: (id: number, reason: string) => send<ChangeRequest>("post", API.CHANGE_REQUEST_REJECT(id), { reason }),
  returnForCorrection: (id: number, reason: string) =>
    send<ChangeRequest>("post", API.CHANGE_REQUEST_RETURN(id), { reason }),
  resubmit: (id: number, payload: Record<string, unknown>, reason?: string) =>
    send<ChangeRequest>("post", API.CHANGE_REQUEST_RESUBMIT(id), { payload, reason }),
  cancel: (id: number) => send<ChangeRequest>("post", API.CHANGE_REQUEST_CANCEL(id)),
};

// ── Clients (parties) ──

export interface PartyListParams {
  page?: number;
  per_page?: number;
  search?: string;
  type?: PartyType;
  kyc_status?: KycStatus;
  role?: string;
}

export interface RelationshipInput {
  relationship: string;
  related_party_id?: number;
  related?: PartyInput;
  kin_relationship?: string;
  share_pct?: string;
  signatory_list?: "A" | "B";
  committed_amount?: string;
}

export const partyService = {
  list: (params: PartyListParams) => get<Paginated<PartyListItem>>(API.PARTIES, params),
  get: (id: number) => get<PartyDetail>(API.PARTY(id)),
  overview: (id: number) => get<PartyOverview>(API.PARTY_OVERVIEW(id)),
  create: (data: PartyInput) => send<PartyDetail>("post", API.PARTIES, data),
  /** Direct fields save; identity, bank and payout changes come back as a change request. */
  update: (id: number, data: PartyInput) => send<PartyEditResult>("patch", API.PARTY(id), data),
  checkDuplicates: (data: PartyInput & { exclude_party_id?: number }) =>
    send<DuplicateCheck>("post", API.PARTY_CHECK_DUPLICATES, data).then((r) => r.data as DuplicateCheck),
  addRelationship: (id: number, data: RelationshipInput) =>
    send<PartyRelationship>("post", API.PARTY_RELATIONSHIPS(id), data),
  endRelationship: (id: number, relationshipId: number) =>
    send<PartyRelationship>("post", API.PARTY_RELATIONSHIP_END(id, relationshipId)),
  setMandate: (id: number, rule: string, description?: string) =>
    send<PartyMandate>("put", API.PARTY_MANDATE(id), { rule, description }),
  requestVerification: (id: number, reason?: string) => send<ChangeRequest>("post", API.PARTY_VERIFY(id), { reason }),
  setPep: (id: number, data: PepInput) => send<ChangeRequest>("put", API.PARTY_PEP(id), data),
  openInvestment: (id: number, email?: string) =>
    send<{ id: number; client_code: string }>("post", API.PARTY_INVESTOR(id), { email }),
  documents: (id: number) => get<PartyDocument[]>(API.PARTY_DOCUMENTS(id)),
  async uploadDocument(id: number, file: File, documentType: string) {
    const form = new FormData();
    form.append("file", file);
    form.append("document_type", documentType);
    const res = await api.post<ApiResponse<PartyDocument>>(API.PARTY_DOCUMENTS(id), form, {
      headers: { "Content-Type": "multipart/form-data" }, timeout: 120000,
    });
    return res.data;
  },
  /** Fetched with the auth header and opened locally; the server logs the read. */
  openDocument: (doc: PartyDocument) => openBlob(API.DOCUMENT_CONTENT(doc.id), doc.filename, doc.content_type),
  consents: (id: number) => get<PartyConsent[]>(API.PARTY_CONSENTS(id)),
  recordConsent: (id: number, data: { purpose: ConsentPurpose; method: ConsentMethod; granted_on?: string;
    evidence_document_id?: string }) => send<PartyConsent>("post", API.PARTY_CONSENTS(id), data),
  withdrawConsent: (id: number, consentId: number, note?: string) =>
    send<PartyConsent>("post", API.PARTY_CONSENT_WITHDRAW(id, consentId), { note }),
  /** Merge this duplicate into survivorId (party.merge, approved by someone else). */
  merge: (id: number, survivorId: number, reason: string) =>
    send<ChangeRequest>("post", API.PARTY_MERGE(id), { survivor_id: survivorId, reason }),
  transfer: (id: number, toBranchId: number, reason: string) =>
    send<ChangeRequest>("post", API.PARTY_TRANSFER(id), { to_branch_id: toBranchId, reason }),
  branches: () => get<{ id: number; code: string; name: string; status: string }[]>(API.BRANCHES),
  investorParty: (investorId: number) =>
    get<{ party_id: number; party_no: string; account_id: number }>(API.INVESTOR_PARTY(investorId)),
};

export const screeningService = {
  queue: (params: { review_status?: string; page?: number; per_page?: number }) =>
    get<Paginated<ScreeningResult>>(API.SCREENING_RESULTS, params),
  review: (id: number, decision: "clear" | "confirmed", note: string) =>
    send<ScreeningResult>("post", API.SCREENING_REVIEW(id), { decision, note }),
};

export const watchlistService = {
  list: (params: { list?: Watchlist; search?: string; page?: number; per_page?: number }) =>
    get<Paginated<WatchlistEntry>>(API.WATCHLIST, params),
  add: (data: { list: Watchlist; full_name: string; reason: string; source?: string;
    identifiers?: { id_type: string; value: string }[] }) => send<WatchlistEntry>("post", API.WATCHLIST, data),
  remove: (id: number, reason: string) => send<ChangeRequest>("post", API.WATCHLIST_REMOVE(id), { reason }),
};

// ── Pre-screen applications, AI review and pre-selection (phase 3b) ──

export const applicationService = {
  list: (params: { queue?: "ready_for_credit"; search?: string; page?: number; per_page?: number }) =>
    get<Paginated<ApplicationListItem>>(API.APPLICATIONS, params),
  get: (id: number) => get<ApplicationDetail>(API.APPLICATION(id)),
  create: (data: ApplicationInput) => send<ApplicationDetail>("post", API.APPLICATIONS, data),
  /** An ESTIMATE only: phase 5's product engine calculates the real schedule. */
  estimate: (params: { product_code: string; amount_requested: string; term_months: number;
    indicative_rate_percent: string }) => get<Estimate>(API.APPLICATION_ESTIMATE, params),
  addGuarantor: (id: number, partyId: number) =>
    send<ApplicationDetail>("post", API.APPLICATION_GUARANTORS(id), { party_id: partyId }),
  addDocument: (id: number, documentId: string) =>
    send<{ document_id: string }>("post", API.APPLICATION_DOCUMENTS(id), { document_id: documentId }),
  enterCrb: (id: number, data: { status: CrbStatusValue; status_date: string; bureau: string; extraction_id?: number }) =>
    send<CrbStatus>("post", API.APPLICATION_CRB(id), data),
  checks: (id: number) => get<CrossCheck[]>(API.APPLICATION_CHECKS(id)),
  screen: (id: number) => send<ScreeningRunResult>("post", API.APPLICATION_SCREEN(id)),
  decide: (id: number, decision: DecisionValue, reason: string) =>
    send<{ status: "recorded" | "pending_approval"; decision?: CreditDecision; change_request_id?: number }>(
      "post", API.APPLICATION_DECISION(id), { decision, reason }),
  log: (id: number) => get<DecisionLog>(API.APPLICATION_LOG(id)),
  openDocument: (id: string, filename: string, contentType: string) =>
    openBlob(API.DOCUMENT_CONTENT(id), filename, contentType),
  /** The document's bytes as a local object URL (revoke it when done). */
  async documentUrl(id: string, contentType: string): Promise<string> {
    const res = await api.get(API.DOCUMENT_CONTENT(id), { responseType: "blob" });
    return URL.createObjectURL(new Blob([res.data], { type: contentType }));
  },
};

export const extractionService = {
  request: (partyId: number, documentId: string) =>
    send<Extraction>("post", API.EXTRACTION_REQUEST(partyId, documentId)),
  retry: (id: number) => send<Extraction>("post", API.EXTRACTION_RETRY(id)),
  review: (id: number) => get<ExtractionReviewDetail>(API.EXTRACTION_REVIEW(id)),
  setField: (id: number, fieldId: number, action: ReviewAction, value?: string, reason?: string,
    applicationId?: number) =>
    send<ExtractionReviewDetail>("post", API.EXTRACTION_REVIEW_FIELD(id, fieldId),
      { action, value, reason, application_id: applicationId }),
  setRow: (id: number, rowId: number, data: { date?: string; debit?: string; credit?: string; balance?: string;
    reason: string }, applicationId?: number) =>
    send<ExtractionReviewDetail>("post", API.EXTRACTION_REVIEW_ROW(id, rowId), { ...data, application_id: applicationId }),
  markUnreliable: (id: number, reason: string, applicationId?: number) =>
    send<ExtractionReviewDetail>("post", API.EXTRACTION_REVIEW_UNRELIABLE(id), { reason, application_id: applicationId }),
  submit: (id: number, applicationId?: number) =>
    send<{ review_id: number; change_request_id: number }>("post", API.EXTRACTION_REVIEW_SUBMIT(id),
      { application_id: applicationId }),
};

export const aiService = {
  ruleSet: () => get<RuleSetInfo>(API.RULE_SET),
  proposeRuleSet: (rules: Rule[], evidence: string, reason: string) =>
    send<ChangeRequest>("post", API.SETTINGS_BUSINESS_KEY("screening.rule_set"),
      { value: { rules }, source: "client_confirmed", evidence, reason }),
  usage: (months = 12) => get<{ months: AiUsageMonth[]; currency: string; note: string }>(API.AI_USAGE, { months }),
  accuracy: () => get<AiAccuracyRow[]>(API.AI_ACCURACY),
};
