import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { FileText, Search, UserPlus, X } from "lucide-react";
import { toast } from "sonner";
import { EmptyState, LoadingRow, PageHeader, Pagination } from "@/components/ui/Page";
import { StatusBadge } from "@/components/data/StatusBadge";
import { Modal } from "@/components/ui/Modal";
import { emailService, investorService } from "@/services";
import { useAuth } from "@/context/AuthContext";
import type { InvestorListItem, Paginated, RecipientSelection } from "@/lib/types";
import { ROUTES } from "@/lib/constants";
import { apiErrorMessage, formatKES, newRequestKey } from "@/lib/utils";

const PER_PAGE = 25;

/**
 * Recipient selection for bulk email:
 *  - "ids": individually ticked investors
 *  - "all": everyone matching the current search/status, minus any unticked
 */
type Selection = { mode: "ids"; ids: Set<number> } | { mode: "all"; exclude: Set<number> };
const NONE: Selection = { mode: "ids", ids: new Set() };

export default function InvestorDirectoryPage() {
  const navigate = useNavigate();
  const { isAdmin } = useAuth();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("active");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Paginated<InvestorListItem> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sel, setSel] = useState<Selection>(NONE);
  const [confirming, setConfirming] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [requestKey, setRequestKey] = useState(newRequestKey);
  const [reloadTick, setReloadTick] = useState(0);

  useEffect(() => {
    setLoading(true);
    const t = window.setTimeout(() => {
      investorService
        .list({ search: search || undefined, status: status || undefined, page, per_page: PER_PAGE })
        .then((d) => {
          setData(d);
          setError(null);
        })
        .catch((err) => setError(apiErrorMessage(err)))
        .finally(() => setLoading(false));
    }, 250);
    return () => window.clearTimeout(t);
  }, [search, status, page, reloadTick]);

  // Changing the filter changes who "all" means: start the selection over.
  const changeFilter = (fn: () => void) => {
    fn();
    setPage(1);
    setSel(NONE);
  };

  const total = data?.total ?? 0;
  const count = sel.mode === "ids" ? sel.ids.size : Math.max(total - sel.exclude.size, 0);
  const isChecked = (id: number) => (sel.mode === "ids" ? sel.ids.has(id) : !sel.exclude.has(id));

  const toggle = (id: number) => {
    setSel((prev) => {
      if (prev.mode === "ids") {
        const ids = new Set(prev.ids);
        if (ids.has(id)) ids.delete(id); else ids.add(id);
        return { mode: "ids", ids };
      }
      const exclude = new Set(prev.exclude);
      if (exclude.has(id)) exclude.delete(id); else exclude.add(id);
      return { mode: "all", exclude };
    });
  };

  const pageIds = data?.items.map((i) => i.id) ?? [];
  const pageAllChecked = pageIds.length > 0 && pageIds.every(isChecked);
  const togglePage = () => {
    setSel((prev) => {
      if (prev.mode === "ids") {
        const ids = new Set(prev.ids);
        pageIds.forEach((id) => (pageAllChecked ? ids.delete(id) : ids.add(id)));
        return { mode: "ids", ids };
      }
      const exclude = new Set(prev.exclude);
      pageIds.forEach((id) => (pageAllChecked ? exclude.add(id) : exclude.delete(id)));
      return { mode: "all", exclude };
    });
  };

  const recipients: RecipientSelection = useMemo(
    () =>
      sel.mode === "ids"
        ? { investor_ids: [...sel.ids] }
        : { filter: { search: search || undefined, status: status || undefined }, exclude_ids: [...sel.exclude] },
    [sel, search, status],
  );

  const cols = isAdmin ? 8 : 7;

  return (
    <div className="app-page">
      <PageHeader
        title="Investors"
        subtitle={isAdmin ? "One account per investor. Click a row to open it, or tick investors to send them statements." : "One account per investor. Click a row to open the account."}
        actions={
          <>
            {isAdmin && (
              <button className="btn btn-outline-secondary btn-sm d-flex align-items-center gap-1" disabled={count === 0}
                onClick={() => { setRequestKey(newRequestKey()); setConfirming(true); }}
                title={count === 0 ? "Tick investors first" : undefined}>
                <FileText size={14} /> Send statements{count > 0 ? ` (${count})` : ""}
              </button>
            )}
            <Link to={ROUTES.INVESTOR_ADD} className="btn btn-primary btn-sm d-flex align-items-center gap-1">
              <UserPlus size={14} /> Add investor
            </Link>
          </>
        }
      />

      <div className="card shadow">
        <div className="card-body">
          <div className="d-flex flex-wrap gap-2 mb-3">
            <div className="position-relative flex-grow-1" style={{ minWidth: 220 }}>
              <Search size={14} className="position-absolute" style={{ left: 12, top: 11, color: "var(--color-text-tertiary)" }} />
              <input className="form-control ps-5" placeholder="Search name, client code, email, phone or ID" value={search}
                onChange={(e) => changeFilter(() => setSearch(e.target.value))} aria-label="Search investors" />
            </div>
            <select className="form-select" style={{ width: 160 }} value={status}
              onChange={(e) => changeFilter(() => setStatus(e.target.value))} aria-label="Account status">
              <option value="active">Active</option>
              <option value="closed">Closed</option>
              <option value="">All</option>
            </select>
          </div>

          {isAdmin && count > 0 && (
            <div className="app-tint d-flex flex-wrap align-items-center gap-3 px-3 py-2 mb-3" style={{ borderRadius: 8, fontSize: 13.5 }}>
              <strong style={{ color: "var(--color-brand-400)" }}>
                {count} investor{count === 1 ? "" : "s"} selected
                {sel.mode === "all" && (search || status) ? " (all matching this search)" : ""}
              </strong>
              {sel.mode === "ids" && total > sel.ids.size && (
                <button type="button" className="btn btn-link p-0" style={{ fontSize: 13.5 }}
                  onClick={() => setSel({ mode: "all", exclude: new Set() })}>
                  Select all {total} matching
                </button>
              )}
              <button type="button" className="btn btn-link p-0 d-inline-flex align-items-center gap-1 ms-auto" style={{ fontSize: 13.5 }}
                onClick={() => setSel(NONE)}>
                <X size={13} /> Clear selection
              </button>
            </div>
          )}

          {error && <div className="alert alert-danger py-2" style={{ fontSize: 13 }}>{error}</div>}

          <div className="app-table-scroll">
            <table className="table app-table table-hover align-middle mb-0">
              <thead>
                <tr>
                  {isAdmin && (
                    <th style={{ width: 40 }}>
                      <input type="checkbox" className="form-check-input m-0" checked={pageAllChecked} onChange={togglePage}
                        aria-label="Select every investor on this page" disabled={pageIds.length === 0} />
                    </th>
                  )}
                  <th>Client code</th>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Phone</th>
                  <th className="text-end">Balance</th>
                  <th className="text-end">Pending withdrawals</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {loading && !data && <LoadingRow colSpan={cols} />}
                {data?.items.map((inv) => (
                  <tr key={inv.id} onClick={() => navigate(ROUTES.INVESTOR_DETAIL(inv.id))}>
                    {isAdmin && (
                      <td onClick={(e) => e.stopPropagation()} style={{ cursor: "default" }}>
                        <input type="checkbox" className="form-check-input m-0" checked={isChecked(inv.id)}
                          onChange={() => toggle(inv.id)} aria-label={`Select ${inv.full_name}`} />
                      </td>
                    )}
                    <td className="font-tabular">{inv.client_code}</td>
                    <td className="fw-semibold">{inv.full_name}</td>
                    <td>{inv.email}</td>
                    <td className="nowrap">{inv.phone ?? "—"}</td>
                    <td className="text-end font-tabular">{formatKES(inv.balance)}</td>
                    <td className="text-end font-tabular">{Number(inv.pending_withdrawals) > 0 ? formatKES(inv.pending_withdrawals) : "—"}</td>
                    <td><StatusBadge status={inv.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data && data.items.length === 0 && (
            <EmptyState message={search ? "No investors match your search." : "No investors yet."}
              action={!search && <Link to={ROUTES.INVESTOR_ADD} className="btn btn-sm btn-primary">Add the first investor</Link>} />
          )}
          {data && <Pagination page={page} perPage={PER_PAGE} total={data.total} onPage={setPage} />}
        </div>
      </div>

      <Modal title={`Send statements to ${count} investor${count === 1 ? "" : "s"}`} open={confirming}
        onClose={() => setConfirming(false)} submitting={generating}
        submitLabel={generating ? "Generating…" : `Generate ${count} statement${count === 1 ? "" : "s"}`}
        onSubmit={async () => {
          setGenerating(true);
          try {
            const res = await emailService.generateStatements(recipients, requestKey);
            toast.success(res.message, {
              action: { label: "Open Emails", onClick: () => navigate(`${ROUTES.EMAILS}?status=pending`) },
            });
            setConfirming(false);
            setSel(NONE);
            setReloadTick((n) => n + 1);
          } catch (err) {
            toast.error(apiErrorMessage(err));
          } finally {
            setGenerating(false);
          }
        }}>
        <p style={{ fontSize: 14 }}>
          Each investor gets their <strong>own</strong> PDF statement as of today, showing their balance, totals, interest
          paid and due, and every transaction.
        </p>
        <div className="alert alert-info py-2" style={{ fontSize: 13.5 }}>
          Nothing is sent yet. The {count} statement{count === 1 ? "" : "s"} wait on the Emails page under{" "}
          <strong>Awaiting confirmation</strong>, where an admin confirms or suppresses each one, or all at once.
        </div>
        <p className="mb-0" style={{ fontSize: 12.5, color: "var(--color-text-tertiary)" }}>
          Investors who already have a statement waiting are skipped. Generating many statements can take a few seconds.
        </p>
      </Modal>
    </div>
  );
}
