import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Check, FileText, Send, X } from "lucide-react";
import { EmptyState, LoadingRow, PageHeader, Pagination } from "@/components/ui/Page";
import { Modal } from "@/components/ui/Modal";
import { StatusBadge } from "@/components/data/StatusBadge";
import { emailService } from "@/services";
import { useAuth } from "@/context/AuthContext";
import type { EmailQueueStatus, OutboxEmail, Paginated } from "@/lib/types";
import { ROUTES } from "@/lib/constants";
import { apiErrorMessage, formatDateTime } from "@/lib/utils";

const PER_PAGE = 50;
const TYPE_LABELS: Record<string, string> = {
  DEPOSIT_CONFIRMATION: "Deposit confirmation",
  DEPOSIT_REVERSAL: "Deposit reversal notice",
  WITHDRAWAL_CONFIRMATION: "Withdrawal confirmation",
  INTEREST_STATEMENT: "Interest statement",
  ACCOUNT_STATEMENT: "Account statement",
  AUM_REPORT: "Monthly AUM summary",
};
const STATUS_FILTERS = [
  { key: "pending", label: "Awaiting confirmation" },
  { key: "queued", label: "Queued" },
  { key: "sent", label: "Sent" },
  { key: "failed", label: "Failed" },
  { key: "cancelled", label: "Suppressed / cancelled" },
] as const;

/** A bulk decision waiting for the admin's second click. */
type Pending = { confirm: boolean; ids: number[] | "all"; count: number } | null;

function badgeLabel(e: OutboxEmail) {
  if (e.status === "pending") return "Awaiting confirmation";
  if (e.status === "cancelled" && e.decided_by) return "Suppressed";
  return undefined;
}

export default function EmailsPage() {
  const { isAdmin } = useAuth();
  const [params, setParams] = useSearchParams();
  const [status, setStatusState] = useState(params.get("status") ?? "");
  const [type, setType] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Paginated<OutboxEmail> | null>(null);
  const [queue, setQueue] = useState<EmailQueueStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [viewing, setViewing] = useState<OutboxEmail | null>(null);
  const [sending, setSending] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [decision, setDecision] = useState<Pending>(null);
  const [deciding, setDeciding] = useState(false);

  const setStatus = (s: string) => {
    setStatusState(s);
    setPage(1);
    setSelected(new Set());
    setParams(s ? { status: s } : {}, { replace: true });
  };

  const load = useCallback(async () => {
    try {
      const [list, q] = await Promise.all([
        emailService.list({ status: status || undefined, type: type || undefined, search: search || undefined, page, per_page: PER_PAGE }),
        emailService.status(),
      ]);
      setData(list);
      setQueue(q);
      setError(null);
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }, [status, type, search, page]);

  useEffect(() => {
    const t = window.setTimeout(load, 250);
    return () => window.clearTimeout(t);
  }, [load]);

  const act = async (fn: () => Promise<{ message: string }>) => {
    try {
      toast.success((await fn()).message);
      load();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    }
  };

  const decide = async (confirm: boolean, ids: number[]) => {
    await act(() => (confirm ? emailService.confirm(ids) : emailService.suppress(ids)));
    setSelected((prev) => {
      const next = new Set(prev);
      ids.forEach((id) => next.delete(id));
      return next;
    });
  };

  const runDecision = async () => {
    if (!decision) return;
    setDeciding(true);
    try {
      const res = decision.ids === "all"
        ? await (decision.confirm ? emailService.confirmAll() : emailService.suppressAll())
        : await (decision.confirm ? emailService.confirm(decision.ids) : emailService.suppress(decision.ids));
      toast.success(res.message);
      setSelected(new Set());
      setDecision(null);
      load();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setDeciding(false);
    }
  };

  const counts = queue?.counts ?? {};
  const pendingTotal = counts.pending ?? 0;
  const pendingOnPage = data?.items.filter((e) => e.status === "pending").map((e) => e.id) ?? [];
  const allPageSelected = pendingOnPage.length > 0 && pendingOnPage.every((id) => selected.has(id));
  const canSelect = isAdmin && pendingOnPage.length > 0;
  const toggle = (id: number) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  const togglePage = () =>
    setSelected((prev) => {
      const next = new Set(prev);
      pendingOnPage.forEach((id) => (allPageSelected ? next.delete(id) : next.add(id)));
      return next;
    });

  const cols = canSelect ? 8 : 7;

  return (
    <div className="app-page">
      <PageHeader
        title="Emails"
        subtitle={
          queue
            ? `Queued emails go out automatically${queue.next_run_at ? `, next batch ${formatDateTime(queue.next_run_at)}` : ""}. Statements generated on request wait for an admin to confirm or suppress them.`
            : "Every investor email and its delivery status."
        }
        actions={
          isAdmin && (
            <button className="btn btn-outline-secondary btn-sm d-flex align-items-center gap-1" disabled={sending || !counts.queued}
              onClick={async () => { setSending(true); await act(emailService.sendNow); setSending(false); }}>
              <Send size={14} /> {sending ? "Sending…" : `Send ${counts.queued ?? 0} queued now`}
            </button>
          )
        }
      />
      {queue?.suppressed && (
        <div className="alert alert-warning py-2" style={{ fontSize: 13 }}>
          Sending is switched off on this server (MAIL_SUPPRESS_SEND). Emails are marked sent but nothing actually goes out.
        </div>
      )}
      {error && <div className="alert alert-danger py-2" style={{ fontSize: 13 }}>{error}</div>}

      {pendingTotal > 0 && status !== "pending" && (
        <div className="alert alert-info d-flex flex-wrap align-items-center justify-content-between gap-2 py-2">
          <span><strong>{pendingTotal}</strong> statement{pendingTotal === 1 ? " is" : "s are"} waiting for an admin to confirm or suppress.</span>
          <button className="btn btn-sm btn-primary" onClick={() => setStatus("pending")}>Review them</button>
        </div>
      )}

      <div className="d-flex flex-wrap gap-2 mb-3">
        {STATUS_FILTERS.map((s) => (
          <button key={s.key} className={`btn btn-sm ${status === s.key ? "btn-primary" : "btn-outline-secondary"}`}
            onClick={() => setStatus(status === s.key ? "" : s.key)}>
            {s.label} <span className="ms-1 font-tabular">{counts[s.key] ?? 0}</span>
          </button>
        ))}
      </div>

      <div className="card shadow">
        <div className="card-body">
          <div className="d-flex flex-wrap gap-2 mb-3">
            <input className="form-control" style={{ maxWidth: 320 }} placeholder="Recipient or subject" value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(1); }} aria-label="Search emails" />
            <select className="form-select" style={{ width: 220 }} value={type} onChange={(e) => { setType(e.target.value); setPage(1); }} aria-label="Email type">
              <option value="">All types</option>
              {Object.entries(TYPE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </div>

          {isAdmin && status === "pending" && pendingTotal > 0 && (
            <div className="app-tint d-flex flex-wrap align-items-center gap-2 px-3 py-2 mb-3" style={{ borderRadius: 8, fontSize: 13.5 }}>
              <strong style={{ color: "var(--color-brand-400)" }}>
                {selected.size > 0 ? `${selected.size} selected` : `${pendingTotal} awaiting confirmation`}
              </strong>
              <div className="ms-auto d-flex flex-wrap gap-2">
                {selected.size > 0 ? (
                  <>
                    <button className="btn btn-sm btn-primary d-flex align-items-center gap-1"
                      onClick={() => setDecision({ confirm: true, ids: [...selected], count: selected.size })}>
                      <Check size={14} /> Confirm &amp; send {selected.size}
                    </button>
                    <button className="btn btn-sm btn-outline-danger d-flex align-items-center gap-1"
                      onClick={() => setDecision({ confirm: false, ids: [...selected], count: selected.size })}>
                      <X size={14} /> Suppress {selected.size}
                    </button>
                  </>
                ) : (
                  <>
                    <button className="btn btn-sm btn-primary d-flex align-items-center gap-1"
                      onClick={() => setDecision({ confirm: true, ids: "all", count: pendingTotal })}>
                      <Check size={14} /> Confirm &amp; send all {pendingTotal}
                    </button>
                    <button className="btn btn-sm btn-outline-danger d-flex align-items-center gap-1"
                      onClick={() => setDecision({ confirm: false, ids: "all", count: pendingTotal })}>
                      <X size={14} /> Suppress all {pendingTotal}
                    </button>
                  </>
                )}
              </div>
            </div>
          )}

          <div className="app-table-scroll">
            <table className="table app-table table-hover align-middle mb-0">
              <thead>
                <tr>
                  {canSelect && (
                    <th style={{ width: 40 }}>
                      <input type="checkbox" className="form-check-input m-0" checked={allPageSelected} onChange={togglePage}
                        aria-label="Select every awaiting email on this page" />
                    </th>
                  )}
                  <th>Created</th><th>Type</th><th>Recipient</th><th>Subject</th><th>Status</th><th>Sent</th><th />
                </tr>
              </thead>
              <tbody>
                {!data && !error && <LoadingRow colSpan={cols} />}
                {data?.items.map((e) => (
                  <tr key={e.id} onClick={() => setViewing(e)}>
                    {canSelect && (
                      <td onClick={(ev) => ev.stopPropagation()} style={{ cursor: "default" }}>
                        {e.status === "pending" && (
                          <input type="checkbox" className="form-check-input m-0" checked={selected.has(e.id)}
                            onChange={() => toggle(e.id)} aria-label={`Select email to ${e.recipient_name ?? e.recipient_email}`} />
                        )}
                      </td>
                    )}
                    <td className="nowrap" style={{ fontSize: 12 }}>{formatDateTime(e.queued_at)}</td>
                    <td style={{ fontSize: 12 }}>{TYPE_LABELS[e.email_type] ?? e.email_type}</td>
                    <td>
                      {e.investor_id ? (
                        <Link to={ROUTES.INVESTOR_DETAIL(e.investor_id)} onClick={(ev) => ev.stopPropagation()}>{e.recipient_name ?? e.recipient_email}</Link>
                      ) : (
                        <span>Internal (management)</span>
                      )}
                      <div style={{ fontSize: 11, color: "var(--color-text-tertiary)" }}>{e.recipient_email}</div>
                    </td>
                    <td style={{ minWidth: 240 }}>{e.subject}</td>
                    <td>
                      <StatusBadge status={e.status} label={badgeLabel(e)} />
                      {e.decided_by && <div style={{ fontSize: 11, color: "var(--color-text-tertiary)" }}>by {e.decided_by}</div>}
                      {e.last_error && e.status !== "cancelled" && (
                        <div className="text-truncate" style={{ fontSize: 11, color: "var(--color-text-tertiary)", maxWidth: 220 }} title={e.last_error}>{e.last_error}</div>
                      )}
                    </td>
                    <td className="nowrap" style={{ fontSize: 12 }}>{formatDateTime(e.sent_at)}</td>
                    <td className="text-end text-nowrap" onClick={(ev) => ev.stopPropagation()}>
                      {e.attachment_name && (
                        <button className="btn btn-sm btn-outline-secondary me-1 d-inline-flex align-items-center gap-1"
                          onClick={() => emailService.openAttachment(e.id, e.attachment_name!).catch((err) => toast.error(apiErrorMessage(err)))}>
                          <FileText size={13} /> PDF
                        </button>
                      )}
                      {isAdmin && e.status === "pending" && (
                        <>
                          <button className="btn btn-sm btn-primary me-1" onClick={() => decide(true, [e.id])}>Confirm</button>
                          <button className="btn btn-sm btn-outline-danger" onClick={() => decide(false, [e.id])}>Suppress</button>
                        </>
                      )}
                      {isAdmin && (e.status === "failed" || (e.status === "cancelled" && e.email_type !== "ACCOUNT_STATEMENT")) && (
                        <button className="btn btn-sm btn-outline-secondary" onClick={() => act(() => emailService.retry(e.id))}>Retry</button>
                      )}
                      {isAdmin && e.status === "queued" && (
                        <button className="btn btn-sm btn-outline-danger" onClick={() => act(() => emailService.cancel(e.id))}>Cancel</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data && data.items.length === 0 && (
            <EmptyState message={status === "pending" ? "Nothing is waiting for confirmation." : "No emails match these filters."} />
          )}
          {data && <Pagination page={page} perPage={PER_PAGE} total={data.total} onPage={setPage} />}
        </div>
      </div>

      <Modal title={viewing?.subject ?? "Email"} open={!!viewing} onClose={() => setViewing(null)} wide>
        {viewing && (
          <>
            <p style={{ fontSize: 12, color: "var(--color-text-tertiary)" }}>
              To {viewing.recipient_name} &lt;{viewing.recipient_email}&gt; · {TYPE_LABELS[viewing.email_type]}
              {viewing.email_type === "INTEREST_STATEMENT" && " · PDF statement attached"}
            </p>
            {viewing.attachment_name && (
              <button className="btn btn-sm btn-outline-secondary mb-3 d-inline-flex align-items-center gap-1"
                onClick={() => emailService.openAttachment(viewing.id, viewing.attachment_name!).catch((err) => toast.error(apiErrorMessage(err)))}>
                <FileText size={13} /> Open attached PDF ({viewing.attachment_name})
              </button>
            )}
            <pre style={{ whiteSpace: "pre-wrap", fontFamily: "var(--font-body)", fontSize: 13, color: "var(--color-text-primary)" }}>
              {viewing.body}
            </pre>
            {isAdmin && viewing.status === "pending" && (
              <div className="d-flex gap-2 justify-content-end">
                <button className="btn btn-sm btn-outline-danger" onClick={() => { decide(false, [viewing.id]); setViewing(null); }}>Suppress</button>
                <button className="btn btn-sm btn-primary" onClick={() => { decide(true, [viewing.id]); setViewing(null); }}>Confirm &amp; send</button>
              </div>
            )}
          </>
        )}
      </Modal>

      <Modal title={decision?.confirm ? "Confirm and send" : "Suppress statements"} open={!!decision} onClose={() => setDecision(null)}
        onSubmit={runDecision} submitting={deciding} submitVariant={decision?.confirm ? "primary" : "danger"}
        submitLabel={decision ? `${decision.confirm ? "Send" : "Suppress"} ${decision.count} email${decision.count === 1 ? "" : "s"}` : ""}>
        {decision && (
          <p className="mb-0" style={{ fontSize: 14 }}>
            {decision.confirm
              ? <>This queues <strong>{decision.count}</strong> email{decision.count === 1 ? "" : "s"} to send, each to its own investor with their own PDF. They go out with the next email run.</>
              : <>This discards <strong>{decision.count}</strong> email{decision.count === 1 ? "" : "s"}. Nothing is sent, and each investor's Emails tab shows it as suppressed.</>}
          </p>
        )}
      </Modal>
    </div>
  );
}
