import { useEffect, useState } from "react";
import { Info } from "lucide-react";
import { partyService } from "@/services";
import type { PartyListItem } from "@/lib/types";
import { CHECK_TONES, OUTCOME_LABELS, OUTCOME_TONES } from "@/lib/constants";
import { cn } from "@/lib/utils";

export function OutcomeBadge({ outcome }: { outcome: string | null | undefined }) {
  if (!outcome) return <span className="app-badge badge-neutral">Not screened</span>;
  return <span className={`app-badge ${OUTCOME_TONES[outcome]} tw:whitespace-nowrap`}>{OUTCOME_LABELS[outcome]}</span>;
}

const CHECK_LABELS: Record<string, string> = {
  pass: "Pass", fail: "Fail", needs_review: "Needs review", missing: "Missing data", not_applicable: "Not applicable",
};

export function CheckBadge({ status }: { status: string }) {
  return <span className={`app-badge ${CHECK_TONES[status] ?? "badge-neutral"} tw:whitespace-nowrap`}>{CHECK_LABELS[status] ?? status}</span>;
}

/** Every instalment shown before phase 5 is an estimate: say so wherever it appears. */
export function EstimateNote({ className }: { className?: string }) {
  return (
    <p className={cn("d-flex align-items-start gap-1 tw:text-[12px] tw:text-text-tertiary mb-0", className)}>
      <Info size={13} className="tw:mt-[2px] tw:shrink-0" />
      Estimate only. The product engine (phase 5) will calculate the actual schedule, fees and dates.
    </p>
  );
}

/** Pick a client by name, number, ID or KRA PIN. */
export function ClientSearch({ value, onChange, label = "Client" }: {
  value: PartyListItem | null; onChange: (p: PartyListItem | null) => void; label?: string;
}) {
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<PartyListItem[]>([]);

  useEffect(() => {
    if (value || query.trim().length < 2) {
      setItems([]);
      return;
    }
    const t = window.setTimeout(() => {
      partyService.list({ search: query.trim(), per_page: 8 }).then((d) => setItems(d.items)).catch(() => setItems([]));
    }, 250);
    return () => window.clearTimeout(t);
  }, [query, value]);

  if (value) {
    return (
      <div className="d-flex align-items-center justify-content-between gap-2 form-control">
        <span>{value.display_name} <span className="tw:text-text-tertiary">· {value.party_no}</span></span>
        <button type="button" className="btn btn-sm app-btn-ghost" onClick={() => onChange(null)}>Change</button>
      </div>
    );
  }
  return (
    <div className="tw:relative">
      <input className="form-control" aria-label={label} placeholder="Name, client no., ID number or KRA PIN"
        value={query} onChange={(e) => setQuery(e.target.value)} />
      {items.length > 0 && (
        <ul className="list-group tw:absolute tw:z-10 tw:w-full tw:shadow-lg tw:mt-1">
          {items.map((p) => (
            <li key={p.id}>
              <button type="button" className="list-group-item list-group-item-action"
                onClick={() => { onChange(p); setQuery(""); }}>
                {p.display_name} <span className="tw:text-text-tertiary">· {p.party_no}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
