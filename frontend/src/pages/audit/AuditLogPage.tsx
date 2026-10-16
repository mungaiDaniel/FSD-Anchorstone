import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Download } from "lucide-react";
import { Card, EmptyState, LoadingRow, PageHeader, Pagination } from "@/components/ui/Page";
import { StatusBadge } from "@/components/data/StatusBadge";
import { auditService, reportService } from "@/services";
import type { AuditLogEntry, Paginated } from "@/lib/types";
import { apiErrorMessage, formatDateTime } from "@/lib/utils";

const PER_PAGE = 50;
const TARGET_TYPES = ["", "investor", "deposit", "withdrawal", "interest_period", "interest_rate", "email", "report", "user", "settings"];

function humanise(action: string) {
  return action.toLowerCase().replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

export default function AuditLogPage() {
  const [targetType, setTargetType] = useState("");
  const [user, setUser] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [page, setPage] = useState(1);
  const [exporting, setExporting] = useState(false);
  const filters = { target_type: targetType || undefined, user: user || undefined, from: from || undefined, to: to || undefined };
  const [data, setData] = useState<Paginated<AuditLogEntry> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    const t = window.setTimeout(() => auditService
      .list({ ...filters, page, per_page: PER_PAGE })
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((err) => setError(apiErrorMessage(err, "Couldn't load the audit log."))), 250);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [targetType, user, from, to, page]);

  return (
    <div className="app-page">
      <PageHeader
        title="Audit log"
        subtitle="Every change made in the system: who did it, when, and to what. Entries can't be edited or deleted."
        actions={
          <button className="btn btn-outline-secondary btn-sm d-flex align-items-center gap-1" disabled={exporting}
            onClick={async () => {
              setExporting(true);
              try {
                toast.success(`Downloaded ${await reportService.download("audit-log", filters)}`);
              } catch (err) {
                toast.error(apiErrorMessage(err, "Export failed."));
              } finally {
                setExporting(false);
              }
            }}>
            <Download size={14} /> {exporting ? "Preparing…" : "Export to Excel"}
          </button>
        }
      />
      <Card>
        <div className="d-flex flex-wrap gap-2 mb-3 align-items-end">
          <select className="form-select" style={{ width: 220 }} value={targetType} onChange={(e) => { setTargetType(e.target.value); setPage(1); }} aria-label="Filter by record type">
            {TARGET_TYPES.map((t) => <option key={t} value={t}>{t ? humanise(t) : "All record types"}</option>)}
          </select>
          <input className="form-control" style={{ width: 220 }} placeholder="User name or email" value={user}
            onChange={(e) => { setUser(e.target.value); setPage(1); }} aria-label="Filter by user" />
          <label className="form-label mb-0" style={{ fontSize: 12 }}>From
            <input type="date" className="form-control" value={from} max={to || undefined} onChange={(e) => { setFrom(e.target.value); setPage(1); }} />
          </label>
          <label className="form-label mb-0" style={{ fontSize: 12 }}>To
            <input type="date" className="form-control" value={to} min={from || undefined} onChange={(e) => { setTo(e.target.value); setPage(1); }} />
          </label>
        </div>
        {error && <div className="alert alert-danger py-2">{error}</div>}
        <div className="app-table-scroll">
          <table className="table app-table align-middle">
            <thead>
              <tr><th>When</th><th>Who</th><th>Action</th><th>Record</th><th>Details</th><th>Result</th></tr>
            </thead>
            <tbody>
              {!data && !error && <LoadingRow colSpan={6} />}
              {data?.items.map((l) => (
                <tr key={l.id}>
                  <td className="text-nowrap" style={{ fontSize: 13 }}>{formatDateTime(l.timestamp)}</td>
                  <td>
                    {l.user_name ?? "System"}
                    {l.user_email && <div style={{ fontSize: 12, color: "var(--color-text-tertiary)" }}>{l.user_email}</div>}
                  </td>
                  <td className="fw-semibold">{humanise(l.action)}</td>
                  <td style={{ fontSize: 13 }}>
                    {l.target_type ? humanise(l.target_type) : "—"}
                    {l.target_name && <div style={{ color: "var(--color-text-tertiary)" }}>{l.target_name}</div>}
                  </td>
                  <td style={{ fontSize: 13, maxWidth: 360 }}>{l.description ?? "—"}</td>
                  <td>
                    {l.success ? <StatusBadge status="active" label="OK" /> : <StatusBadge status="failed" />}
                    {l.error_message && <div style={{ fontSize: 12, color: "var(--color-destructive)" }}>{l.error_message}</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {data && data.items.length === 0 && <EmptyState message="No entries yet." />}
        {data && <Pagination page={page} perPage={PER_PAGE} total={data.total} onPage={setPage} />}
      </Card>
    </div>
  );
}
