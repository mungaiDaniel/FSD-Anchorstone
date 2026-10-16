import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface KPICardProps {
  label: string;
  value: string;
  subtitle?: string;
  icon?: ReactNode;
  /** "featured": the one headline figure on a page, on a navy panel. */
  variant?: "default" | "featured";
  className?: string;
}

/** Headline figure for the dashboard. Bootstrap card; Tailwind for the finish
 *  (gradient, hover lift, responsive type). */
export function KPICard({ label, value, subtitle, icon, variant = "default", className }: KPICardProps) {
  const featured = variant === "featured";
  return (
    <div
      className={cn(
        "card h-100 tw:overflow-hidden tw:transition tw:duration-200 tw:hover:-translate-y-0.5 tw:hover:shadow-lg",
        featured
          ? "tw:border-0 tw:bg-linear-135 tw:from-brand-400 tw:to-brand-300 tw:text-white tw:shadow-md"
          : "tw:shadow-xs tw:hover:border-brand-100",
        className,
      )}
    >
      <div className="card-body tw:relative tw:p-3.5 tw:sm:p-5">
        {featured && (
          // Soft ring in the corner: depth without adding a colour.
          <span aria-hidden className="tw:absolute tw:-top-10 tw:-right-10 tw:size-32 tw:rounded-full tw:bg-white/10" />
        )}
        <div className="d-flex align-items-start justify-content-between gap-2 tw:mb-2 tw:sm:mb-3">
          <span
            className={cn(
              "tw:text-xs tw:sm:text-[13px] tw:font-medium tw:leading-snug",
              featured ? "tw:text-white/80" : "tw:text-text-secondary",
            )}
          >
            {label}
          </span>
          {icon && (
            <span
              className={cn(
                "tw:hidden tw:sm:inline-flex tw:items-center tw:justify-center tw:shrink-0 tw:size-9 tw:rounded-lg",
                featured ? "tw:bg-white/15 tw:text-white" : "tw:bg-bg-tint tw:text-brand-400",
              )}
            >
              {icon}
            </span>
          )}
        </div>
        <p
          className={cn(
            "font-tabular tw:mb-1 tw:font-bold tw:leading-tight tw:tracking-tight tw:text-xl tw:sm:text-[26px]",
            featured ? "tw:text-white" : "tw:text-brand-400",
          )}
        >
          {value}
        </p>
        {subtitle && (
          <p className={cn("tw:mb-0 tw:text-[11.5px] tw:sm:text-[12.5px] tw:truncate", featured ? "tw:text-white/75" : "tw:text-text-tertiary")}>
            {subtitle}
          </p>
        )}
      </div>
    </div>
  );
}
