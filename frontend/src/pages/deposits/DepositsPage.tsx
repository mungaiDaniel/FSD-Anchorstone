import { useCallback, useEffect, useState } from "react";
import { ArrowDownToLine, Undo2 } from "lucide-react";
import { Actor, EmptyState, InvestorCell, LoadingRow, PageHeader, Pagination, SearchField } from "@/components/ui/Page";
import { StatusBadge } from "@/components/data/StatusBadge";
import { RecordDepositModal, ReverseDepositModal } from "@/components/transactions/TransactionModals";
import { transactionService } from "@/services";
import { useAuth } from "@/context/AuthContext";
import type { Deposit, Paginated } from "@/lib/types";
import { PAYMENT_METHOD_LABELS, ROUTES } from "@/lib/constants";
import { apiErrorMessage, formatDate, formatKES } from "@/lib/utils";
import { useRequestGuard } from "@/lib/useRequestGuard";

const PER_PAGE = 50;

export default function DepositsPage() {
  const { isAdmin } = useAuth();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Paginated<Deposit> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [recordOpen, setRecordOpen] = useState(false);
  const [reverseTarget, setReverseTarget] = useState<Deposit | null>(null);
  const startRequest = useRequestGuard();

  const load = useCallback(() => {
    const isLatest = startRequest();
    transactionService
      .deposits({ search: search || undefined, status: status || undefined, from: from || undefined, to: to || undefined, page, per_page: PER_PAGE })
      .then((d) => {
        if (!isLatest()) return;
        setData(d);
        setError(null);
      })
      .catch((err) => isLatest() && setError(apiErrorMessage(err)));
  }, [search, status, from, to, page, startRequest]);

  useEffect(() => {
    const t = window.setTimeout(load, 250);
    return () => window.clearTimeout(t);
  }, [load]);

  const resetPage = <T,>(setter: (v: T) => void) => (v: T) => {
    setter(v);
    setPage(1);
  };

  return (
    <div className="app-page">
      <PageHeader
        title="Deposits"
        subtitle="Every deposit is confirmed to the investor by email automatically. Mistakes are reversed by an admin, never deleted."
        actions={
          <button className="btn btn-primary btn-sm d-flex align-items-center gap-1" onClick={() => setRecordOpen(true)}>
            <ArrowDownToLine size={14} /> Record deposit
          </button>
        }
      />
      <div className="card shadow">
        <div className="card-body">
          <div className="d-flex flex-wrap gap-2 mb-3">
            <SearchField className="flex-grow-1" value={search} label="Search deposits"
              placeholder="Investor name, code or email" onChange={resetPage(setSearch)} />
            <select className="form-select" style={{ width: 150 }} value={status} onChange={(e) => resetPage(setStatus)(e.target.value)} aria-label="Status">
              <option value="">All statuses</option>
              <option value="posted">Posted</option>
              <option value="reversed">Reversed</option>
            </select>
            <input type="date" className="form-control" style={{ width: 160 }} value={from} onChange={(e) => resetPage(setFrom)(e.target.value)} aria-label="From date" />
            <input type="date" className="form-control" style={{ width: 160 }} value={to} onChange={(e) => resetPage(setTo)(e.target.value)} aria-label="To date" />
          </div>
          {error && <div className="alert alert-danger py-2" style={{ fontSize: 13 }}>{error}</div>}
          <div className="app-table-scroll">
            <table className="table app-table align-middle mb-0">
              <thead>
                <tr>
                  <th>Date received</th><th>Investor</th><th>Reference</th><th>Method</th>
                  <th className="text-end">Amount</th><th>Status</th><th>Recorded by</th><th />
                </tr>
              </thead>
              <tbody>
                {!data && !error && <LoadingRow colSpan={8} />}
                {data?.items.map((d) => (
                  <tr key={d.id}>
                    <td className="nowrap tw:text-text-secondary">{formatDate(d.value_date)}</td>
                    <td><InvestorCell name={d.investor_name} code={d.client_code} to={ROUTES.INVESTOR_DETAIL(d.investor_id)} /></td>
                    <td className="font-tabular nowrap tw:text-text-secondary">{d.reference}</td>
                    <td className="nowrap">{PAYMENT_METHOD_LABELS[d.method]}</td>
                    <td className={`text-end font-tabular tw:font-semibold ${d.status === "reversed" ? "tw:text-text-disabled tw:line-through" : "tw:text-brand-400"}`}>
                      {formatKES(d.amount)}
                    </td>
                    <td>
                      <StatusBadge status={d.status} />
                      {d.reversal_reason && (
                        <div className="tw:text-[11px] tw:text-text-tertiary tw:truncate tw:max-w-[140px] tw:mt-0.5" title={d.reversal_reason}>
                          {d.reversal_reason}
                        </div>
                      )}
                    </td>
                    <td><Actor email={d.recorded_by} /></td>
                    <td className="text-end">
                      {isAdmin && d.status === "posted" && (
                        <button className="btn btn-sm app-btn-ghost-danger d-inline-flex align-items-center gap-1" onClick={() => setReverseTarget(d)}>
                          <Undo2 size={13} /> Reverse
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data && data.items.length === 0 && (
            <EmptyState icon={<ArrowDownToLine size={22} />} title="No deposits found"
              message={search || status || from || to ? "No deposits match these filters." : "Deposits you record appear here."} />
          )}
          {data && <Pagination page={page} perPage={PER_PAGE} total={data.total} onPage={setPage} />}
        </div>
      </div>
      <RecordDepositModal open={recordOpen} onClose={() => setRecordOpen(false)} onDone={load} />
      <ReverseDepositModal deposit={reverseTarget} onClose={() => setReverseTarget(null)} onDone={load} />
    </div>
  );
}
