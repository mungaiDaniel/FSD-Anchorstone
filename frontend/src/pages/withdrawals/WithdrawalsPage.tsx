import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpFromLine, Search } from "lucide-react";
import { EmptyState, LoadingRow, PageHeader, Pagination } from "@/components/ui/Page";
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

const PER_PAGE = 50;
const TABS = [
  { key: "pending", label: "Awaiting approval" },
  { key: "approved", label: "Approved" },
  { key: "rejected", label: "Rejected" },
  { key: "", label: "All" },
];

export default function WithdrawalsPage() {
  const { isAdmin, userEmail } = useAuth();
  const [status, setStatus] = useState("pending");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Paginated<Withdrawal> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [requestOpen, setRequestOpen] = useState(false);
  const [approveTarget, setApproveTarget] = useState<Withdrawal | null>(null);
  const [rejectTarget, setRejectTarget] = useState<Withdrawal | null>(null);

  const load = useCallback(() => {
    transactionService
      .withdrawals({ status: status || undefined, search: search || undefined, page, per_page: PER_PAGE })
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((err) => setError(apiErrorMessage(err)));
  }, [status, search, page]);

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

      <ul className="nav nav-tabs app-tabs mb-3" role="tablist">
        {TABS.map((t) => (
          <li className="nav-item" key={t.key}>
            <button className={`nav-link${status === t.key ? " active" : ""}`} role="tab" aria-selected={status === t.key}
              onClick={() => { setStatus(t.key); setPage(1); }}>
              {t.label}
            </button>
          </li>
        ))}
      </ul>

      <div className="card shadow">
        <div className="card-body">
          <div className="position-relative mb-3" style={{ maxWidth: 420 }}>
            <Search size={14} className="position-absolute" style={{ left: 12, top: 11, color: "var(--color-text-tertiary)" }} />
            <input className="form-control ps-5" placeholder="Investor name, code or email" value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(1); }} aria-label="Search withdrawals" />
          </div>
          {error && <div className="alert alert-danger py-2" style={{ fontSize: 13 }}>{error}</div>}
          <div className="app-table-scroll">
            <table className="table app-table align-middle mb-0">
              <thead>
                <tr>
                  <th>Requested</th><th>Investor</th><th className="text-end">Amount</th><th>Pay out by</th>
                  <th>Status</th><th>Effective</th><th>Recorded by</th><th>Decided by</th><th />
                </tr>
              </thead>
              <tbody>
                {!data && !error && <LoadingRow colSpan={9} />}
                {data?.items.map((w) => (
                  <tr key={w.id}>
                    <td className="nowrap">{formatDate(w.requested_date)}</td>
                    <td>
                      <Link to={ROUTES.INVESTOR_DETAIL(w.investor_id)}>{w.investor_name}</Link>
                      <div className="font-tabular" style={{ fontSize: 11, color: "var(--color-text-tertiary)" }}>{w.client_code}</div>
                    </td>
                    <td className="text-end font-tabular">{formatKES(w.amount)}</td>
                    <td>{PAYMENT_METHOD_LABELS[w.method]}</td>
                    <td>
                      <StatusBadge status={w.status} />
                      {w.rejection_reason && <div style={{ fontSize: 11, color: "var(--color-text-tertiary)" }}>{w.rejection_reason}</div>}
                      {w.payment_reference && <div style={{ fontSize: 11, color: "var(--color-text-tertiary)" }}>Ref {w.payment_reference}</div>}
                    </td>
                    <td className="nowrap">{formatDate(w.value_date)}</td>
                    <td style={{ fontSize: 12 }}>{w.requested_by}</td>
                    <td style={{ fontSize: 12 }}>{w.decided_by ?? "—"}</td>
                    <td className="text-end text-nowrap">
                      {w.status === "pending" && isAdmin && !isOwn(w) && (
                        <>
                          <button className="btn btn-sm btn-primary me-1" onClick={() => setApproveTarget(w)}>Approve</button>
                          <button className="btn btn-sm btn-outline-danger" onClick={() => setRejectTarget(w)}>Reject</button>
                        </>
                      )}
                      {w.status === "pending" && (isOwn(w) || !isAdmin) && (
                        <span style={{ fontSize: 11, color: "var(--color-text-tertiary)" }}>
                          {isOwn(w) ? "You recorded this — another admin must approve" : "Awaiting an admin"}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data && data.items.length === 0 && (
            <EmptyState message={status === "pending" ? "No withdrawals are waiting for approval." : "No withdrawals match these filters."} />
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
