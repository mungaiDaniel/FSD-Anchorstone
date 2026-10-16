import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface KPICardProps {
  label: string;
  value: string;
  subtitle?: string;
  icon?: ReactNode;
  className?: string;
}

/** Headline figure for the dashboard: navy value on white, line-art icon. */
export function KPICard({ label, value, subtitle, icon, className }: KPICardProps) {
  return (
    <div className={cn("card shadow h-100", className)}>
      <div className="card-body">
        <div className="d-flex align-items-start justify-content-between gap-2 mb-2">
          <span style={{ color: "var(--color-text-secondary)", fontSize: 13, fontWeight: 500 }}>{label}</span>
          {icon && (
            <span className="d-inline-flex align-items-center justify-content-center flex-shrink-0"
              style={{ width: 34, height: 34, borderRadius: 8, background: "var(--color-bg-tint)", color: "var(--color-brand-400)" }}>
              {icon}
            </span>
          )}
        </div>
        <p className="mb-1 font-tabular fw-bold" style={{ fontSize: 24, lineHeight: 1.15, color: "var(--color-brand-400)" }}>{value}</p>
        {subtitle && <p className="mb-0" style={{ color: "var(--color-text-tertiary)", fontSize: 12.5 }}>{subtitle}</p>}
      </div>
    </div>
  );
}
