import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { FilePlus2, FileSearch } from "lucide-react";
import { EmptyState, InvestorCell, LoadingRow, PageHeader, Pagination, SearchField, SegmentedTabs } from "@/components/ui/Page";
import { OutcomeBadge } from "@/components/applications/ApplicationBits";
import { applicationService } from "@/services";
import type { ApplicationListItem, Paginated } from "@/lib/types";
import { ROUTES } from "@/lib/constants";
import { apiErrorMessage, formatDate, formatKES } from "@/lib/utils";
import { useRequestGuard } from "@/lib/useRequestGuard";

const PER_PAGE = 50;
type Queue = "" | "ready_for_credit";
const TABS: { key: Queue; label: string }[] = [
  { key: "", label: "All applications" },
  { key: "ready_for_credit", label: "Ready for credit analysis" },
];
const DECISION_LABELS: Record<string, string> = { proceed: "Proceed", decline: "Declined", more_info: "More info requested" };

export default function ApplicationListPage() {
  const navigate = useNavigate();
  const [queue, setQueue] = useState<Queue>("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Paginated<ApplicationListItem> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const startRequest = useRequestGuard();

  const load = useCallback(() => {
    const isLatest = startRequest();
    applicationService
      .list({ queue: queue || undefined, search: search || undefined, page, per_page: PER_PAGE })
      .then((d) => {
        if (!isLatest()) return;
        setData(d);
        setError(null);
      })
      .catch((err) => isLatest() && setError(apiErrorMessage(err)));
  }, [queue, search, page, startRequest]);

  useEffect(() => {
    const t = window.setTimeout(load, 250);
    return () => window.clearTimeout(t);
  }, [load]);

  return (
    <div className="app-page">
      <PageHeader
        title="Pre-screen applications"
        subtitle="Documents read by AI and confirmed by staff, checked against Anchorstone's pre-selection rules. The rules recommend; a credit officer decides."
        actions={
          <Link to={ROUTES.APPLICATION_NEW} className="btn btn-primary btn-sm d-flex align-items-center gap-1">
            <FilePlus2 size={14} /> New application
          </Link>
        }
      />
      <div className="mb-3">
        <SegmentedTabs label="Queue" items={TABS} value={queue} onChange={(k) => { setQueue(k); setPage(1); }} />
      </div>
      <div className="card shadow">
        <div className="card-body">
          <SearchField className="mb-3 tw:max-w-md" value={search} label="Search applications"
            placeholder="Application no., client name or number" onChange={(v) => { setSearch(v); setPage(1); }} />
          {error && <div className="alert alert-danger py-2" style={{ fontSize: 13 }}>{error}</div>}
          <div className="app-table-scroll">
            <table className="table app-table align-middle mb-0">
              <thead>
                <tr><th>Application</th><th>Client</th><th>Product</th><th className="text-end">Amount</th>
                  <th className="text-end">Est. instalment</th><th>Recommendation</th><th>Decision</th><th>Created</th></tr>
              </thead>
              <tbody>
                {!data && !error && <LoadingRow colSpan={8} />}
                {data?.items.map((a) => (
                  <tr key={a.id} className="tw:cursor-pointer" onClick={() => navigate(ROUTES.APPLICATION_DETAIL(a.id))}>
                    <td className="nowrap fw-medium">{a.application_no}</td>
                    <td><InvestorCell name={a.party?.display_name ?? null} code={a.party?.party_no ?? null} /></td>
                    <td className="tw:text-text-secondary">{a.product_label} · {a.term_months} mo</td>
                    <td className="text-end font-tabular">{formatKES(a.amount_requested)}</td>
                    <td className="text-end font-tabular tw:text-text-secondary" title={a.estimate_note}>
                      {formatKES(a.estimated_instalment)}<span className="tw:text-text-tertiary"> est.</span>
                    </td>
                    <td><OutcomeBadge outcome={a.recommendation} /></td>
                    <td className="tw:text-text-secondary">{a.decision ? DECISION_LABELS[a.decision] : "—"}</td>
                    <td className="nowrap tw:text-text-secondary">{formatDate(a.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data && data.items.length === 0 && (
            <EmptyState icon={<FileSearch size={22} />}
              title={queue ? "Nothing ready for credit analysis" : "No applications yet"}
              message={queue ? "Shortlisted applications appear here." : "Create an application for a client to start."} />
          )}
          {data && <Pagination page={page} perPage={PER_PAGE} total={data.total} onPage={setPage} />}
        </div>
      </div>
    </div>
  );
}
