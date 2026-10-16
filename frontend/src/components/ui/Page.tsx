import type { ReactNode } from "react";
import { ChevronLeft, ChevronRight, Inbox } from "lucide-react";

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="page-header-row mb-4">
      <div className="min-w-0">
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

export function EmptyState({ message, action }: { message: string; action?: ReactNode }) {
  return (
    <div className="text-center py-5" style={{ color: "var(--color-text-tertiary)" }}>
      <Inbox size={28} className="mb-2" style={{ opacity: 0.6 }} />
      <p className="mb-2" style={{ fontSize: 13 }}>{message}</p>
      {action}
    </div>
  );
}

export function LoadingRow({ colSpan }: { colSpan: number }) {
  return (
    <tr>
      <td colSpan={colSpan} className="text-center py-4" style={{ color: "var(--color-text-tertiary)", fontSize: 13 }}>
        Loading…
      </td>
    </tr>
  );
}

export function Pagination({ page, perPage, total, onPage }: { page: number; perPage: number; total: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / perPage));
  if (total <= perPage) {
    return <p className="mb-0 mt-3" style={{ color: "var(--color-text-tertiary)", fontSize: 12 }}>{total} record{total === 1 ? "" : "s"}</p>;
  }
  return (
    <div className="d-flex align-items-center justify-content-between mt-3" style={{ fontSize: 12, color: "var(--color-text-tertiary)" }}>
      <span>
        {(page - 1) * perPage + 1}–{Math.min(page * perPage, total)} of {total}
      </span>
      <div className="d-flex gap-1">
        <button className="btn btn-sm btn-outline-secondary" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="Previous page">
          <ChevronLeft size={14} />
        </button>
        <span className="px-2 align-self-center">
          {page} / {pages}
        </span>
        <button className="btn btn-sm btn-outline-secondary" disabled={page >= pages} onClick={() => onPage(page + 1)} aria-label="Next page">
          <ChevronRight size={14} />
        </button>
      </div>
    </div>
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
