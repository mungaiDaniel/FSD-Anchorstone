import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ClipboardCheck } from "lucide-react";
import { Actor, EmptyState, LoadingRow, PageHeader, Pagination, SegmentedTabs } from "@/components/ui/Page";
import { StatusBadge } from "@/components/data/StatusBadge";
import { ChangeRequestModal, isMaker, requestTypeLabel } from "@/components/approvals/ChangeRequestModal";
import { approvalService } from "@/services";
import { useAuth } from "@/context/AuthContext";
import type { ChangeRequest, ChangeRequestStatus, Paginated } from "@/lib/types";
import { apiErrorMessage, formatDateTime, formatKES } from "@/lib/utils";
import { useRequestGuard } from "@/lib/useRequestGuard";

const PER_PAGE = 50;
type View = "decide" | "mine" | "status";
const VIEWS: { key: View; label: string }[] = [
  { key: "decide", label: "For me to decide" },
  { key: "mine", label: "My requests" },
  { key: "status", label: "All by status" },
];
const STATUSES: { key: ChangeRequestStatus; label: string }[] = [
  { key: "pending", label: "Pending" },
  { key: "returned", label: "Returned" },
  { key: "applied", label: "Applied" },
  { key: "rejected", label: "Rejected" },
  { key: "cancelled", label: "Cancelled" },
  { key: "expired", label: "Expired" },
  { key: "failed", label: "Failed" },
];

/** Levels signed off, plus how many people the current level needs when it is more than one. */
function Levels({ cr }: { cr: ChangeRequest }) {
  const { levels_done: done, levels_required: required } = cr;
  const people = cr.levels?.[done]?.count ?? 1;
  const open = cr.status === "pending" || cr.status === "returned";
  return (
    <div className="tw:min-w-[72px]">
      <div className="font-tabular tw:text-xs tw:font-semibold tw:text-text-primary">{done} of {required} level{required === 1 ? "" : "s"}</div>
      <div className="d-flex gap-1 tw:mt-1" aria-hidden>
        {Array.from({ length: required }, (_, i) => (
          <span key={i} className={`tw:h-1 tw:flex-1 tw:rounded-full ${i < done ? "tw:bg-brand-400" : "tw:bg-border-default"}`} />
        ))}
      </div>
      {open && done < required && people > 1 && (
        <div className="tw:text-[11px] tw:text-text-tertiary tw:mt-0.5">Level {done + 1}: {people} approvers</div>
      )}
    </div>
  );
}

export default function ApprovalsPage() {
  const { userEmail } = useAuth();
  const [params, setParams] = useSearchParams();
  const [view, setView] = useState<View>("decide");
  const [status, setStatus] = useState<ChangeRequestStatus>("pending");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Paginated<ChangeRequest> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const startRequest = useRequestGuard();
  // ?id=<n> opens a request directly (e.g. from the Business rules page).
  const openId = Number(params.get("id")) || null;
  const setOpenId = (id: number | null) => setParams(id ? { id: String(id) } : {}, { replace: true });

  const load = useCallback(() => {
    const isLatest = startRequest();
    setData(null);
    approvalService
      .list({ page, per_page: PER_PAGE, mine: view === "mine", status: view === "status" ? status : undefined })
      .then((d) => {
        if (!isLatest()) return;
        setData(d);
        setError(null);
      })
      .catch((err) => isLatest() && setError(apiErrorMessage(err)));
  }, [view, status, page, startRequest]);

  useEffect(load, [load]);

  const emptyTitle = view === "decide" ? "All caught up" : "No change requests";
  const emptyMessage =
    view === "decide" ? "Nothing is waiting for your approval."
      : view === "mine" ? "You haven't submitted any change requests."
        : "No change requests have this status.";

  return (
    <div className="app-page">
      <PageHeader
        title="Approvals"
        subtitle="Changes to access, business rules and documents wait here until a different person approves them. Nothing applies until every level has signed off."
      />

      <div className="d-flex flex-wrap align-items-center gap-2 mb-3">
        <SegmentedTabs label="Which requests" items={VIEWS} value={view} onChange={(k) => { setView(k); setPage(1); }} />
        {view === "status" && (
          <select className="form-select form-select-sm tw:w-auto" aria-label="Status" value={status}
            onChange={(e) => { setStatus(e.target.value as ChangeRequestStatus); setPage(1); }}>
            {STATUSES.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
          </select>
        )}
      </div>

      <div className="card shadow">
        <div className="card-body">
          {error && <div className="alert alert-danger py-2" style={{ fontSize: 13 }}>{error}</div>}
          <div className="app-table-scroll">
            <table className="table app-table align-middle mb-0">
              <thead>
                <tr>
                  <th>Submitted</th><th>Request</th><th>Maker</th><th className="text-end">Amount</th>
                  <th>Approvals</th><th>Status</th><th />
                </tr>
              </thead>
              <tbody>
                {!data && !error && <LoadingRow colSpan={7} />}
                {data?.items.map((cr) => (
                  <tr key={cr.id} className="tw:cursor-pointer" onClick={() => setOpenId(cr.id)}>
                    <td className="nowrap tw:text-text-secondary">
                      {formatDateTime(cr.submitted_at)}
                      <div className="font-tabular tw:text-[11px] tw:text-text-tertiary">#{cr.id}</div>
                    </td>
                    <td className="tw:min-w-[220px]">
                      <div className="tw:text-[11px] tw:font-semibold tw:uppercase tw:tracking-wide tw:text-text-tertiary">
                        {requestTypeLabel(cr.request_type)}
                      </div>
                      <div className="tw:text-[13px] tw:text-text-primary tw:line-clamp-2 tw:break-words" title={cr.summary ?? undefined}>
                        {cr.summary ?? cr.request_type}
                      </div>
                    </td>
                    <td><Actor email={cr.maker_email} />{isMaker(cr, userEmail) && <div className="tw:text-[11px] tw:text-text-tertiary">You</div>}</td>
                    <td className="text-end font-tabular nowrap">{cr.amount ? formatKES(cr.amount) : <span className="tw:text-text-disabled">—</span>}</td>
                    <td><Levels cr={cr} /></td>
                    <td><StatusBadge status={cr.status} /></td>
                    <td className="text-end text-nowrap">
                      <button className={`btn btn-sm ${cr.can_decide ? "btn-primary" : "app-btn-ghost"}`}
                        onClick={(e) => { e.stopPropagation(); setOpenId(cr.id); }}>
                        {cr.can_decide ? "Review" : "View"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data && data.items.length === 0 && (
            <EmptyState icon={<ClipboardCheck size={22} />} title={emptyTitle} message={emptyMessage} />
          )}
          {data && <Pagination page={page} perPage={PER_PAGE} total={data.total} onPage={setPage} />}
        </div>
      </div>

      <ChangeRequestModal id={openId} onClose={() => setOpenId(null)} onDone={load} />
    </div>
  );
}
