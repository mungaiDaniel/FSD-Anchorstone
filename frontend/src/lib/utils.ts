import { clsx, type ClassValue } from "clsx";

/** Join class names (Bootstrap and tw:-prefixed Tailwind). No merging: the two
 *  frameworks' names never overlap, so there is nothing to deduplicate. */
export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}

const kes = new Intl.NumberFormat("en-KE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** "KES 1,234,567.89". Accepts the API's decimal strings. */
export function formatKES(value: string | number | null | undefined): string {
  const n = Number(value ?? 0);
  return `KES ${kes.format(Number.isFinite(n) ? n : 0)}`;
}

/** Compact: KES 1.2M, KES 500K. */
export function formatKESCompact(value: string | number | null | undefined): string {
  const n = Number(value ?? 0);
  if (Math.abs(n) >= 1_000_000) return `KES ${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 1_000) return `KES ${(n / 1_000).toFixed(0)}K`;
  return formatKES(n);
}

export function formatRate(value: string | number | null | undefined): string {
  if (value == null) return "—";
  return `${Number(value).toFixed(2)}% p.a.`;
}

/** 10 Mar 2026 */
export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return "—";
  // Date-only strings are calendar dates: parse as local, not UTC midnight.
  const date = /^\d{4}-\d{2}-\d{2}$/.test(dateStr) ? new Date(`${dateStr}T00:00:00`) : new Date(dateStr);
  if (isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", year: "numeric" }).format(date);
}

/** 10 Mar 2026, 14:30 */
export function formatDateTime(dateStr: string | null | undefined): string {
  if (!dateStr) return "—";
  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

/** Today's date (Nairobi, UTC+3) as YYYY-MM-DD, for date inputs. */
export function todayISO(): string {
  const nairobi = new Date(Date.now() + 3 * 60 * 60 * 1000);
  return nairobi.toISOString().slice(0, 10);
}

/** Pull a readable message out of an axios error. */
export function apiErrorMessage(err: unknown, fallback = "Something went wrong."): string {
  const data = (err as { response?: { data?: { message?: unknown } } })?.response?.data;
  if (data && typeof data.message === "string") return data.message;
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

/** A one-time UUID for a request, so a double click or retry can't run it twice. */
export function newRequestKey(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  // randomUUID needs a secure context (https/localhost); build a v4 UUID by hand otherwise.
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6]! & 0x0f) | 0x40;
  b[8] = (b[8]! & 0x3f) | 0x80;
  const h = Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}
