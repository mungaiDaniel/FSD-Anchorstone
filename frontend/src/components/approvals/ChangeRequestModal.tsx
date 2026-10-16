import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Ban, Check, CornerUpLeft, RotateCcw, X } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { Actor, Field, Stat } from "@/components/ui/Page";
import { StatusBadge } from "@/components/data/StatusBadge";
import { PartyChangeDiff } from "@/components/approvals/PartyChangeDiff";
import { approvalService } from "@/services";
import { useAuth } from "@/context/AuthContext";
import { REQUEST_TYPE_LABELS } from "@/lib/constants";
import type { ChangeRequest, ChangeRequestAction, ChangeRequestEvent } from "@/lib/types";
import { apiErrorMessage, formatDateTime, formatKES } from "@/lib/utils";

const ACTION_LABELS: Record<ChangeRequestAction, string> = {
  submit: "Submitted",
  approve: "Approved",
  reject: "Rejected",
  return: "Returned for correction",
  resubmit: "Resubmitted",
  cancel: "Cancelled",
  apply: "Applied",
  expire: "Expired",
  fail: "Failed",
};

const ACTION_DOT: Partial<Record<ChangeRequestAction, string>> = {
  approve: "var(--color-success)",
  apply: "var(--color-success)",
  reject: "var(--color-destructive)",
  fail: "var(--color-destructive)",
  expire: "var(--color-destructive)",
  cancel: "var(--color-text-disabled)",
  return: "var(--color-warning)",
};

export function requestTypeLabel(type: string) {
  return REQUEST_TYPE_LABELS[type] ?? type;
}

export function isMaker(cr: ChangeRequest, email: string | null) {
  return cr.maker_email.toLowerCase() === (email ?? "").toLowerCase();
}

function showValue(v: unknown) {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function History({ events }: { events: ChangeRequestEvent[] }) {
  if (events.length === 0) return <p className="tw:text-xs tw:text-text-tertiary mb-0">No history yet.</p>;
  return (
    <ol className="list-unstyled mb-0 tw:relative tw:pl-5">
      <span aria-hidden className="tw:absolute tw:left-[5px] tw:top-1.5 tw:bottom-1.5 tw:w-px tw:bg-border-default" />
      {events.map((e) => (
        <li key={e.id} className="tw:relative tw:pb-3 tw:last:pb-0">
          <span aria-hidden className="tw:absolute tw:-left-5 tw:top-1 tw:size-[11px] tw:rounded-full tw:border-2 tw:border-white"
            style={{ background: ACTION_DOT[e.action] ?? "var(--color-brand-400)" }} />
          <div className="d-flex flex-wrap align-items-baseline tw:gap-x-2">
            <span className="tw:text-[13px] tw:font-semibold tw:text-text-primary">
              {ACTION_LABELS[e.action]}{e.level ? ` · level ${e.level}` : ""}
            </span>
            <Actor email={e.actor_email} prefix="by" />
            <span className="tw:text-[11px] tw:text-text-tertiary font-tabular">{formatDateTime(e.at)}</span>
            {e.round > 1 && <span className="tw:text-[10px] tw:font-semibold tw:uppercase tw:text-text-tertiary">Round {e.round}</span>}
          </div>
          {e.comment && <p className="mb-0 tw:mt-0.5 tw:text-xs tw:text-text-secondary tw:whitespace-pre-wrap">{e.comment}</p>}
        </li>
      ))}
    </ol>
  );
}

/**
 * One change request: what it does, who asked, the approvals so far and its
 * history, with the actions open to me. Buttons only appear when the server
 * says I could use them; it checks again on every call.
 */
export function ChangeRequestModal({ id, onClose, onDone }: { id: number | null; onClose: () => void; onDone: () => void }) {
  const { userEmail } = useAuth();
  const [cr, setCr] = useState<ChangeRequest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [payloadText, setPayloadText] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    if (id === null) return;
    let live = true;
    setCr(null);
    setError(null);
    setNote("");
    approvalService.get(id)
      .then((d) => {
        if (!live) return;
        setCr(d);
        setPayloadText(JSON.stringify(d.payload, null, 2));
      })
      .catch((err) => live && setError(apiErrorMessage(err)));
    return () => { live = false; };
  }, [id]);

  const run = async (label: string, call: () => Promise<{ message: string }>) => {
    setBusy(label);
    try {
      const res = await call();
      toast.success(res.message);
      onDone();
      onClose();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  const resubmit = () => {
    let payload: Record<string, unknown>;
    try {
      payload = JSON.parse(payloadText);
    } catch {
      toast.error("The payload isn't valid JSON.");
      return;
    }
    run("resubmit", () => approvalService.resubmit(cr!.id, payload, note.trim() || undefined));
  };

  const mine = cr ? isMaker(cr, userEmail) : false;
  // People who have approved the current level this round, against how many it needs.
  const levelNeeds = cr?.levels?.[cr.levels_done]?.count ?? 1;
  const levelHas = cr?.events?.filter((e) => e.action === "approve" && e.round === cr.round && e.level === cr.levels_done + 1).length ?? 0;
  const open = cr?.status === "pending" || cr?.status === "returned";
  const trimmed = note.trim();

  return (
    <Modal title={cr ? `Change request #${cr.id}` : "Change request"} open={id !== null} onClose={() => !busy && onClose()} wide>
      {error && <div className="alert alert-danger py-2" style={{ fontSize: 13 }}>{error}</div>}
      {!cr && !error && <p className="tw:text-sm tw:text-text-tertiary">Loading…</p>}
      {cr && (
        <>
          <div className="d-flex flex-wrap align-items-center gap-2 mb-1">
            <span className="tw:text-[11px] tw:font-semibold tw:uppercase tw:tracking-wide tw:text-text-tertiary">
              {requestTypeLabel(cr.request_type)}
            </span>
            <StatusBadge status={cr.status} />
          </div>
          <p className="tw:text-[15px] tw:font-semibold tw:text-text-primary tw:mb-3 tw:break-words">{cr.summary ?? cr.request_type}</p>

          <div className="row g-3 mb-3">
            <div className="col-6 col-md-3"><Stat label="Maker" value={<Actor email={cr.maker_email} />} sub={formatDateTime(cr.submitted_at)} /></div>
            <div className="col-6 col-md-3"><Stat label="Amount" value={cr.amount ? formatKES(cr.amount) : "—"} /></div>
            <div className="col-6 col-md-3">
              <Stat label="Approvals"
                value={`${cr.levels_done} of ${cr.levels_required} level${cr.levels_required === 1 ? "" : "s"}`
                  + (open && levelNeeds > 1 && cr.levels_done < cr.levels_required ? ` · ${levelHas} of ${levelNeeds} people` : "")}
                sub={cr.levels?.map((l, i) => `L${i + 1}: ${l.permission}${(l.count ?? 1) > 1 ? ` ×${l.count}` : ""}`).join(" · ")} />
            </div>
            <div className="col-6 col-md-3">
              <Stat label={open ? "Expires" : "Decided"} value={formatDateTime(open ? cr.expires_at : cr.decided_at)}
                sub={cr.round > 1 ? `Round ${cr.round}` : undefined} />
            </div>
          </div>

          {cr.reason && (
            <div className="mb-3">
              <p className="app-section-label mb-1">Maker's reason</p>
              <p className="tw:text-[13px] tw:text-text-secondary tw:whitespace-pre-wrap mb-0">{cr.reason}</p>
            </div>
          )}
          {cr.error && <div className="alert alert-warning py-2" style={{ fontSize: 13 }}>{cr.error}</div>}

          {cr.request_type === "party.change" && cr.entity_id ? <PartyChangeDiff cr={cr} /> : (
            <>
              <p className="app-section-label mb-1">Details</p>
              <dl className="tw:mb-3 tw:rounded-lg tw:border tw:border-border-subtle tw:bg-bg-surface-alt tw:px-3 tw:py-2" style={{ fontSize: 13 }}>
                {Object.entries(cr.payload).map(([k, v]) => (
                  <div key={k} className="d-flex gap-3 tw:py-0.5">
                    <dt className="fw-normal tw:w-36 tw:shrink-0 tw:text-text-tertiary">{k}</dt>
                    <dd className="mb-0 font-tabular tw:break-all tw:text-text-primary">{showValue(v)}</dd>
                  </div>
                ))}
              </dl>
            </>
          )}

          <p className="app-section-label mb-2">History</p>
          <div className="mb-3"><History events={cr.events ?? []} /></div>

          {cr.status === "pending" && cr.can_decide && (
            <div className="tw:border-t tw:border-border-subtle tw:pt-3">
              <Field label="Comment or reason" hint="Optional to approve. Required to return or reject; the maker sees it.">
                <textarea className="form-control mt-1" rows={2} value={note} maxLength={2000} onChange={(e) => setNote(e.target.value)} />
              </Field>
              <div className="d-flex flex-wrap justify-content-end gap-2">
                <button className="btn btn-sm app-btn-ghost-danger d-inline-flex align-items-center gap-1" disabled={!!busy || !trimmed}
                  onClick={() => run("reject", () => approvalService.reject(cr.id, trimmed))}>
                  <X size={14} /> {busy === "reject" ? "Rejecting…" : "Reject"}
                </button>
                <button className="btn btn-sm btn-outline-secondary d-inline-flex align-items-center gap-1" disabled={!!busy || !trimmed}
                  onClick={() => run("return", () => approvalService.returnForCorrection(cr.id, trimmed))}>
                  <CornerUpLeft size={14} /> {busy === "return" ? "Returning…" : "Return to maker"}
                </button>
                <button className="btn btn-sm btn-primary d-inline-flex align-items-center gap-1" disabled={!!busy}
                  onClick={() => run("approve", () => approvalService.approve(cr.id, trimmed || undefined))}>
                  <Check size={14} /> {busy === "approve" ? "Approving…" : "Approve"}
                </button>
              </div>
            </div>
          )}

          {cr.status === "pending" && !cr.can_decide && (
            <p className="tw:text-xs tw:text-text-tertiary tw:border-t tw:border-border-subtle tw:pt-3 mb-0">
              {mine
                ? "Maker-checker: you made this request, so someone else must approve it."
                : "You can't decide this level: it needs a permission or limit you don't hold, or you've already approved it."}
            </p>
          )}

          {mine && cr.status === "returned" && (
            <div className="tw:border-t tw:border-border-subtle tw:pt-3">
              <Field label="Corrected request (JSON)" hint="Edit the details the checker asked about. The server validates it again.">
                <textarea className="form-control mt-1 font-monospace" rows={8} value={payloadText} spellCheck={false}
                  style={{ fontSize: 12 }} onChange={(e) => setPayloadText(e.target.value)} />
              </Field>
              <Field label="Note for the checker">
                <textarea className="form-control mt-1" rows={2} value={note} maxLength={2000} onChange={(e) => setNote(e.target.value)} />
              </Field>
            </div>
          )}

          {mine && open && (
            <div className="d-flex flex-wrap justify-content-end gap-2 tw:pt-2">
              <button className="btn btn-sm app-btn-ghost-danger d-inline-flex align-items-center gap-1" disabled={!!busy}
                onClick={() => run("cancel", () => approvalService.cancel(cr.id))}>
                <Ban size={14} /> {busy === "cancel" ? "Cancelling…" : "Cancel request"}
              </button>
              {cr.status === "returned" && (
                <button className="btn btn-sm btn-primary d-inline-flex align-items-center gap-1" disabled={!!busy} onClick={resubmit}>
                  <RotateCcw size={14} /> {busy === "resubmit" ? "Resubmitting…" : "Resubmit"}
                </button>
              )}
            </div>
          )}
        </>
      )}
    </Modal>
  );
}
