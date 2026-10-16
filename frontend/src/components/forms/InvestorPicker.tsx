import { useEffect, useRef, useState } from "react";
import { investorService } from "@/services";
import type { InvestorListItem } from "@/lib/types";
import { formatKES } from "@/lib/utils";

interface Props {
  value: InvestorListItem | null;
  onChange: (investor: InvestorListItem | null) => void;
  activeOnly?: boolean;
}

/** Type-ahead search over investors by name, client code, email or phone. */
export function InvestorPicker({ value, onChange, activeOnly = true }: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<InvestorListItem[]>([]);
  const [open, setOpen] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (value || query.trim().length < 2) {
      setResults([]);
      return;
    }
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(async () => {
      try {
        const res = await investorService.list({ search: query, per_page: 8, status: activeOnly ? "active" : undefined });
        setResults(res.items);
        setOpen(true);
      } catch {
        setResults([]);
      }
    }, 250);
    return () => window.clearTimeout(timer.current);
  }, [query, value, activeOnly]);

  if (value) {
    return (
      <div className="d-flex align-items-center justify-content-between form-control" style={{ height: "auto" }}>
        <div>
          <div className="fw-semibold" style={{ fontSize: 13 }}>{value.full_name}</div>
          <div style={{ fontSize: 11, color: "var(--color-text-tertiary)" }}>
            {value.client_code} · balance {formatKES(value.balance)}
          </div>
        </div>
        <button type="button" className="btn btn-sm btn-link p-0" onClick={() => { onChange(null); setQuery(""); }}>
          Change
        </button>
      </div>
    );
  }

  return (
    <div style={{ position: "relative" }}>
      <input
        className="form-control"
        placeholder="Search by name, client code, email or phone"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onFocus={() => results.length && setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 150)}
        aria-label="Search investors"
      />
      {open && results.length > 0 && (
        <ul className="dropdown-menu show w-100 mt-1" style={{ maxHeight: 260, overflowY: "auto" }}>
          {results.map((inv) => (
            <li key={inv.id}>
              <button type="button" className="dropdown-item" onMouseDown={() => { onChange(inv); setOpen(false); }}>
                <div className="fw-semibold" style={{ fontSize: 13 }}>{inv.full_name}</div>
                <div style={{ fontSize: 11, color: "var(--color-text-tertiary)" }}>
                  {inv.client_code} · {inv.email} · {formatKES(inv.balance)}
                </div>
              </button>
            </li>
          ))}
        </ul>
      )}
      {open && query.trim().length >= 2 && results.length === 0 && (
        <div className="dropdown-menu show w-100 mt-1 px-3 py-2" style={{ fontSize: 12 }}>No matching investors.</div>
      )}
    </div>
  );
}
