import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ChevronLeft, ChevronRight, Inbox, Search, X } from "lucide-react";

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="page-header-row mb-4">
      <div className="tw:min-w-0">
        <h1 className="app-page-title">{title}</h1>
        {subtitle && <p className="app-page-subtitle">{subtitle}</p>}
      </div>
      {actions && <div className="d-flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function Card({ title, actions, children, className }: { title?: string; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={`card shadow ${className ?? ""}`}>
      <div className="card-body">
        {(title || actions) && (
          <div className="d-flex flex-wrap align-items-center justify-content-between gap-2 mb-3">
            {title && <h2 className="app-section-title mb-0">{title}</h2>}
            {actions}
          </div>
        )}
        {children}
      </div>
    </div>
  );
}

export function EmptyState({ message, action, icon, title }: { message: string; action?: ReactNode; icon?: ReactNode; title?: string }) {
  return (
    <div className="text-center tw:py-12 tw:px-4">
      <span className="tw:inline-flex tw:items-center tw:justify-center tw:size-12 tw:rounded-full tw:bg-bg-tint tw:text-brand-400 tw:mb-3">
        {icon ?? <Inbox size={22} />}
      </span>
      {title && <p className="tw:mb-1 tw:text-sm tw:font-semibold tw:text-text-primary">{title}</p>}
      <p className="tw:mb-3 tw:text-[13px] tw:text-text-tertiary tw:max-w-sm tw:mx-auto">{message}</p>
      {action}
    </div>
  );
}

/** Placeholder rows while a table loads, shaped like the real ones. */
export function LoadingRow({ colSpan, rows = 5 }: { colSpan: number; rows?: number }) {
  return (
    <>
      {Array.from({ length: rows }, (_, r) => (
        <tr key={r} aria-hidden={r > 0 ? true : undefined}>
          {Array.from({ length: colSpan }, (_, c) => (
            <td key={c}>
              <span
                className="tw:block tw:h-3 tw:rounded tw:bg-bg-tint tw:animate-pulse"
                style={{ width: `${45 + ((r * 7 + c * 13) % 45)}%` }}
              />
            </td>
          ))}
        </tr>
      ))}
      <tr className="visually-hidden"><td colSpan={colSpan}>Loading…</td></tr>
    </>
  );
}

export function Pagination({ page, perPage, total, onPage }: { page: number; perPage: number; total: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / perPage));
  const count = (
    <span className="tw:text-xs tw:text-text-tertiary">
      {total <= perPage
        ? `${total} record${total === 1 ? "" : "s"}`
        : <>Showing <strong className="tw:text-text-secondary">{(page - 1) * perPage + 1}–{Math.min(page * perPage, total)}</strong> of {total}</>}
    </span>
  );
  if (total <= perPage) return <div className="tw:mt-3">{count}</div>;
  return (
    <div className="d-flex align-items-center justify-content-between tw:mt-3 tw:pt-3 tw:border-t tw:border-border-subtle">
      {count}
      <div className="d-flex align-items-center gap-1">
        <button className="btn btn-sm btn-outline-secondary" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="Previous page">
          <ChevronLeft size={14} />
        </button>
        <span className="tw:px-2 tw:text-xs tw:text-text-secondary font-tabular">
          Page {page} of {pages}
        </span>
        <button className="btn btn-sm btn-outline-secondary" disabled={page >= pages} onClick={() => onPage(page + 1)} aria-label="Next page">
          <ChevronRight size={14} />
        </button>
      </div>
    </div>
  );
}

/** Search box with a leading icon, for table toolbars. */
export function SearchField({ value, onChange, placeholder, label, className }: {
  value: string; onChange: (v: string) => void; placeholder: string; label: string; className?: string;
}) {
  return (
    <div className={`position-relative ${className ?? ""}`}>
      <Search size={15} className="position-absolute tw:left-3 tw:top-1/2 tw:-translate-y-1/2 tw:text-text-tertiary tw:pointer-events-none" />
      <input className="form-control tw:pl-9" placeholder={placeholder} value={value} aria-label={label}
        onChange={(e) => onChange(e.target.value)} />
      {value && (
        <button type="button" onClick={() => onChange("")} aria-label="Clear search"
          className="position-absolute tw:right-2 tw:top-1/2 tw:-translate-y-1/2 tw:p-1 tw:rounded-md tw:border-0 tw:bg-transparent tw:text-text-tertiary tw:hover:bg-bg-tint tw:hover:text-brand-400">
          <X size={14} />
        </button>
      )}
    </div>
  );
}

/** Pill tabs for a table's main filter, with optional counts. */
export function SegmentedTabs<K extends string>({ items, value, onChange, label }: {
  items: { key: K; label: string; count?: number }[]; value: K; onChange: (k: K) => void; label: string;
}) {
  return (
    <div role="tablist" aria-label={label}
      className="tw:inline-flex tw:flex-wrap tw:gap-1 tw:p-1 tw:rounded-xl tw:bg-bg-surface-alt tw:border tw:border-border-subtle">
      {items.map((it) => {
        const active = it.key === value;
        return (
          <button key={it.key} type="button" role="tab" aria-selected={active} onClick={() => onChange(it.key)}
            className={`tw:inline-flex tw:items-center tw:gap-1.5 tw:px-3 tw:py-1.5 tw:rounded-lg tw:border-0 tw:text-[13px] tw:font-medium tw:transition-all ${
              active ? "tw:bg-white tw:text-brand-400 tw:shadow-sm tw:font-semibold" : "tw:bg-transparent tw:text-text-secondary tw:hover:text-brand-400"
            }`}>
            {it.label}
            {it.count !== undefined && (
              <span className={`font-tabular tw:min-w-5 tw:px-1.5 tw:rounded-full tw:text-[11px] tw:font-semibold ${
                active ? "tw:bg-brand-400 tw:text-white" : "tw:bg-border-default tw:text-text-secondary"
              }`}>
                {it.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

/** Investor name with initials and client code, kept on one line. */
export function InvestorCell({ name, code, to }: { name: string | null; code: string | null; to?: string }) {
  const initials = (name ?? "?").split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]!.toUpperCase()).join("");
  const label = <span className="tw:font-semibold tw:text-text-primary tw:truncate">{name}</span>;
  return (
    <div className="d-flex align-items-center gap-2 tw:min-w-0 tw:whitespace-nowrap">
      <span aria-hidden className="tw:inline-flex tw:items-center tw:justify-center tw:shrink-0 tw:size-8 tw:rounded-full tw:bg-bg-tint tw:text-brand-400 tw:text-[11px] tw:font-bold">
        {initials}
      </span>
      <div className="tw:min-w-0 tw:leading-tight">
        {to ? <Link to={to} onClick={(e) => e.stopPropagation()} className="tw:block tw:truncate">{label}</Link> : label}
        {code && <div className="font-tabular tw:text-[11px] tw:text-text-tertiary">{code}</div>}
      </div>
    </div>
  );
}

/** Who did something: the part of the email before "@", full address on hover. */
export function Actor({ email, prefix }: { email: string | null | undefined; prefix?: string }) {
  if (!email) return <span className="tw:text-text-disabled">—</span>;
  return (
    <span title={email} className="tw:whitespace-nowrap tw:text-xs tw:text-text-secondary">
      {prefix && <span className="tw:text-text-tertiary">{prefix} </span>}
      {email.split("@")[0]}
    </span>
  );
}

export function Field({ label, hint, error, children }: { label: string; hint?: ReactNode; error?: string; children: ReactNode }) {
  return (
    <div className="mb-3">
      <label className="form-label" style={{ fontSize: 12 }}>
        {label}
        {children}
      </label>
      {hint && !error && <div className="form-text" style={{ color: "var(--color-text-tertiary)", fontSize: 11 }}>{hint}</div>}
      {error && <div style={{ color: "var(--color-destructive)", fontSize: 11 }}>{error}</div>}
    </div>
  );
}

export function Stat({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div>
      <div style={{ color: "var(--color-text-tertiary)", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 600 }}>
        {label}
      </div>
      <div className="font-tabular fw-semibold" style={{ color: "var(--color-text-primary)", fontSize: 15 }}>{value}</div>
      {sub && <div style={{ color: "var(--color-text-tertiary)", fontSize: 11 }}>{sub}</div>}
    </div>
  );
}
