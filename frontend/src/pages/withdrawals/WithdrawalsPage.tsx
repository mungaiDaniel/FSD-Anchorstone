import { useCallback, useEffect, useState } from "react";
import { ArrowUpFromLine, Check, X } from "lucide-react";
import { Actor, EmptyState, InvestorCell, LoadingRow, PageHeader, Pagination, SearchField, SegmentedTabs } from "@/components/ui/Page";
import { StatusBadge } from "@/components/data/StatusBadge";
import {
  ApproveWithdrawalModal,
  RejectWithdrawalModal,
  RequestWithdrawalModal,
} from "@/components/transactions/TransactionModals";
import { transactionService } from "@/services";
import { useAuth } from "@/context/AuthContext";
import type { Paginated, Withdrawal } from "@/lib/types";
import { PAYMENT_METHOD_LABELS, ROUTES } from "@/lib/constants";
import { apiErrorMessage, formatDate, formatKES } from "@/lib/utils";
import { useRequestGuard } from "@/lib/useRequestGuard";

const PER_PAGE = 50;
type Tab = "pending" | "approved" | "rejected" | "";
const TABS: { key: Tab; label: string }[] = [
  { key: "pending", label: "Awaiting approval" },
  { key: "approved", label: "Approved" },
  { key: "rejected", label: "Rejected" },
  { key: "", label: "All" },
];

export default function WithdrawalsPage() {
  const { isAdmin, userEmail } = useAuth();
  const [status, setStatus] = useState<Tab>("pending");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Paginated<Withdrawal> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [requestOpen, setRequestOpen] = useState(false);
  const [approveTarget, setApproveTarget] = useState<Withdrawal | null>(null);
  const [rejectTarget, setRejectTarget] = useState<Withdrawal | null>(null);
  const startRequest = useRequestGuard();

  const load = useCallback(() => {
    const isLatest = startRequest();
    transactionService
      .withdrawals({ status: status || undefined, search: search || undefined, page, per_page: PER_PAGE })
      .then((d) => {
        if (!isLatest()) return;
        setData(d);
        setError(null);
      })
      .catch((err) => isLatest() && setError(apiErrorMessage(err)));
  }, [status, search, page, startRequest]);

  useEffect(() => {
    const t = window.setTimeout(load, 250);
    return () => window.clearTimeout(t);
  }, [load]);

  const isOwn = (w: Withdrawal) => w.requested_by.toLowerCase() === (userEmail ?? "").toLowerCase();

  return (
    <div className="app-page">
      <PageHeader
        title="Withdrawals"
        subtitle="Staff record requests; a different admin approves them. The balance only changes, and the investor is only emailed, on approval."
        actions={
          <button className="btn btn-primary btn-sm d-flex align-items-center gap-1" onClick={() => setRequestOpen(true)}>
            <ArrowUpFromLine size={14} /> Record withdrawal
          </button>
        }
      />

      <div className="mb-3">
        <SegmentedTabs label="Withdrawal status" items={TABS} value={status}
          onChange={(k) => { setStatus(k); setPage(1); }} />
      </div>

      <div className="card shadow">
        <div className="card-body">
          <SearchField className="mb-3 tw:max-w-md" value={search} label="Search withdrawals"
            placeholder="Investor name, code or email" onChange={(v) => { setSearch(v); setPage(1); }} />
          {error && <div className="alert alert-danger py-2" style={{ fontSize: 13 }}>{error}</div>}
          <div className="app-table-scroll">
            <table className="table app-table align-middle mb-0">
              <thead>
                <tr>
                  <th>Requested</th><th>Investor</th><th className="text-end">Amount</th><th>Pay out by</th>
                  <th>Status</th><th>Effective</th><th>Recorded / decided</th><th />
                </tr>
              </thead>
              <tbody>
                {!data && !error && <LoadingRow colSpan={8} />}
                {data?.items.map((w) => (
                  <tr key={w.id}>
                    <td className="nowrap tw:text-text-secondary">{formatDate(w.requested_date)}</td>
                    <td><InvestorCell name={w.investor_name} code={w.client_code} to={ROUTES.INVESTOR_DETAIL(w.investor_id)} /></td>
                    <td className="text-end font-tabular tw:font-semibold tw:text-brand-400">{formatKES(w.amount)}</td>
                    <td className="nowrap">{PAYMENT_METHOD_LABELS[w.method]}</td>
                    <td>
                      <StatusBadge status={w.status} />
                      {w.rejection_reason && (
                        <div className="tw:text-[11px] tw:text-text-tertiary tw:truncate tw:max-w-[140px] tw:mt-0.5" title={w.rejection_reason}>
                          {w.rejection_reason}
                        </div>
                      )}
                      {w.payment_reference && <div className="font-tabular tw:text-[11px] tw:text-text-tertiary tw:mt-0.5">Ref {w.payment_reference}</div>}
                    </td>
                    <td className="nowrap tw:text-text-secondary">{w.value_date ? formatDate(w.value_date) : "—"}</td>
                    <td>
                      <div className="tw:leading-snug">
                        <Actor email={w.requested_by} />
                        {w.decided_by && <div><Actor email={w.decided_by} prefix="→" /></div>}
                      </div>
                    </td>
                    <td className="text-end text-nowrap">
                      {w.status === "pending" && isAdmin && !isOwn(w) && (
                        <>
                          <button className="btn btn-sm btn-primary me-1 d-inline-flex align-items-center gap-1" onClick={() => setApproveTarget(w)}>
                            <Check size={13} /> Approve
                          </button>
                          <button className="btn btn-sm app-btn-ghost-danger d-inline-flex align-items-center gap-1" onClick={() => setRejectTarget(w)}>
                            <X size={13} /> Reject
                          </button>
                        </>
                      )}
                      {w.status === "pending" && (isOwn(w) || !isAdmin) && (
                        <span className="tw:text-[11px] tw:text-text-tertiary"
                          title={isOwn(w) ? "Maker-checker: you recorded this, so another admin must approve it." : undefined}>
                          {isOwn(w) ? "Needs another admin" : "Awaiting an admin"}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data && data.items.length === 0 && (
            <EmptyState icon={<ArrowUpFromLine size={22} />} title={status === "pending" ? "All caught up" : "No withdrawals found"}
              message={status === "pending" ? "No withdrawals are waiting for approval." : "No withdrawals match these filters."} />
          )}
          {data && <Pagination page={page} perPage={PER_PAGE} total={data.total} onPage={setPage} />}
        </div>
      </div>

      <RequestWithdrawalModal open={requestOpen} onClose={() => setRequestOpen(false)} onDone={load} />
      <ApproveWithdrawalModal withdrawal={approveTarget} onClose={() => setApproveTarget(null)} onDone={load} />
      <RejectWithdrawalModal withdrawal={rejectTarget} onClose={() => setRejectTarget(null)} onDone={load} />
    </div>
  );
}
