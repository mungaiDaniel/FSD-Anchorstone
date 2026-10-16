import type { PaymentMethod, UserRole } from "./types";

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
  SETTINGS: "/settings",
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
} as const;
