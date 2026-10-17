import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { AlertTriangle, Check, Pencil, X } from "lucide-react";
import { Card, PageHeader } from "@/components/ui/Page";
import { Modal } from "@/components/ui/Modal";
import { CheckBadge } from "@/components/applications/ApplicationBits";
import { useAuth } from "@/context/AuthContext";
import { applicationService, extractionService } from "@/services";
import type { ExtractionReviewDetail, ReviewField, ReviewTransaction } from "@/lib/types";
import { ROUTES } from "@/lib/constants";
import { apiErrorMessage, cn, formatKES } from "@/lib/utils";

const STATE_LABELS: Record<string, string> = {
  draft: "In progress", submitted: "Waiting for a second person's approval", returned: "Returned for correction",
  approved: "Approved", rejected: "Rejected",
};

export default function ReviewExtractionPage() {
  const { id } = useParams();
  const extractionId = Number(id);
  const [params] = useSearchParams();
  const applicationId = params.get("application") ? Number(params.get("application")) : undefined;
  const { isAdmin } = useAuth();
  const [data, setData] = useState<ExtractionReviewDetail | null>(null);
  const [docUrl, setDocUrl] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [correcting, setCorrecting] = useState<ReviewField | null>(null);
  const [row, setRow] = useState<ReviewTransaction | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    extractionService.review(extractionId).then((d) => { setData(d); setError(null); })
      .catch((e) => setError(apiErrorMessage(e)));
  }, [extractionId]);
  useEffect(load, [load]);

  const documentId = data?.document.id;
  const contentType = data?.document.content_type;
  useEffect(() => {
    if (!documentId || !contentType) return;
    let url: string | null = null;
    applicationService.documentUrl(documentId, contentType)
      .then((u) => { url = u; setDocUrl(u); }).catch(() => setDocUrl(null));
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [documentId, contentType]);

  const editable = isAdmin && data && ["draft", "returned", "rejected"].includes(data.state);
  const act = (fn: () => Promise<{ data?: ExtractionReviewDetail }>) =>
    fn().then((r) => r.data && setData(r.data)).catch((e) => toast.error(apiErrorMessage(e)));
  const accept = (f: ReviewField) => act(() => extractionService.setField(extractionId, f.id, "accept", undefined, undefined, applicationId));
  const notPresent = (f: ReviewField) => act(() => extractionService.setField(extractionId, f.id, "not_present", undefined, undefined, applicationId));
  const submit = () => extractionService.submit(extractionId, applicationId)
    .then(() => { toast.success("Submitted. A different person approves it in Approvals."); load(); })
    .catch((e) => toast.error(apiErrorMessage(e)));
  const unreliable = () => {
    const reason = window.prompt("Why isn't this statement reliable?");
    if (reason) act(() => extractionService.markUnreliable(extractionId, reason, applicationId));
  };

  // Keyboard first: Enter accepts the first value still waiting (if it can be accepted as read).
  const next = useMemo(() => data?.fields.find((f) => !f.review) ?? null, [data]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Enter" || !editable || !next || correcting || row) return;
      if ((e.target as HTMLElement)?.tagName === "TEXTAREA" || (e.target as HTMLElement)?.tagName === "INPUT") return;
      if (next.value !== null && next.validation !== "failed") { e.preventDefault(); accept(next); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editable, next, correcting, row]);

  if (error) return <div className="app-page"><div className="alert alert-danger">{error}</div></div>;
  if (!data) return <div className="app-page tw:text-text-tertiary">Loading…</div>;
  const ex = data.extraction;
  const isImage = data.document.content_type.startsWith("image/");

  return (
    <div className="app-page">
      <PageHeader title={`Review: ${ex.label}`}
        subtitle={<>Reading {ex.id} · {ex.status_label} · {STATE_LABELS[data.state]}
          {applicationId && <> · <Link to={ROUTES.APPLICATION_DETAIL(applicationId)}>back to the application</Link></>}</>}
        actions={editable ? (
          <div className="d-flex gap-2">
            {data.statement && <button className="btn btn-sm btn-outline-secondary" onClick={unreliable}>Mark not reliable</button>}
            <button className="btn btn-sm btn-primary" disabled={data.missing_actions > 0} onClick={submit}
              title={data.missing_actions ? `${data.missing_actions} value(s) still need an action` : undefined}>Submit for approval</button>
          </div>
        ) : undefined} />
      {ex.status_reason && <div className="alert alert-warning py-2 d-flex gap-2" style={{ fontSize: 13 }}><AlertTriangle size={16} /> {ex.status_reason}</div>}
      {data.review?.statement_unreliable && <div className="alert alert-secondary py-2" style={{ fontSize: 13 }}>Marked not reliable: {data.review.unreliable_reason}</div>}

      <div className="row g-3">
        <div className="col-xl-6">
          <Card title={`Document · page ${page} of ${ex.page_count ?? 1}`}
            actions={(ex.page_count ?? 1) > 1 ? (
              <div className="btn-group btn-group-sm">
                <button className="btn btn-outline-secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>‹</button>
                <button className="btn btn-outline-secondary" disabled={page >= (ex.page_count ?? 1)} onClick={() => setPage(page + 1)}>›</button>
              </div>) : undefined}>
            <div className="tw:h-[70vh] tw:rounded-lg tw:border tw:border-border-subtle tw:overflow-hidden tw:bg-bg-surface-alt">
              {!docUrl ? <p className="p-3 tw:text-text-tertiary">Loading the document…</p> : isImage
                ? <img src={docUrl} alt="The uploaded document" className="tw:w-full tw:h-full tw:object-contain" />
                : <iframe key={page} title="The uploaded document" src={`${docUrl}#page=${page}`} className="tw:w-full tw:h-full" />}
            </div>
          </Card>
        </div>

        <div className="col-xl-6 d-flex flex-column gap-3">
          {data.statement && (
            <Card title="Statement pages (pages that don't add up first)">
              {data.pages.map((p) => (
                <div key={p.page_number} className={cn("tw:py-2 tw:border-b tw:border-border-subtle tw:text-[13px]", p.reviewed_status !== "balanced" && "tw:bg-warning-bg tw:px-2 tw:rounded")}>
                  <div className="d-flex align-items-center justify-content-between">
                    <button className="btn btn-link p-0" onClick={() => setPage(p.page_number)}>Page {p.page_number}</button>
                    <CheckBadge status={p.reviewed_status === "balanced" ? "pass" : p.reviewed_status === "rescan_needed" ? "fail" : "needs_review"} />
                  </div>
                  <div className="tw:text-text-secondary font-tabular">
                    As read: opening {formatKES(p.opening_balance)} + credits {formatKES(p.credits_total)} − debits {formatKES(p.debits_total)} · closing {formatKES(p.closing_balance)}
                    {!!p.corrected_rows && <span className="tw:text-text-tertiary"> · {p.corrected_rows} row(s) corrected, re-checked</span>}
                  </div>
                  {p.reviewed_reason && <div className="tw:text-text-secondary">{p.reviewed_reason}</div>}
                  {p.reviewed_status !== "balanced" && (
                    <table className="table table-sm mt-2 mb-0">
                      <thead><tr><th>#</th><th>Date</th><th>Description</th><th className="text-end">Debit</th><th className="text-end">Credit</th><th className="text-end">Balance</th><th /></tr></thead>
                      <tbody>
                        {data.transactions.filter((t) => t.page_number === p.page_number).map((t) => (
                          <tr key={t.id} className={cn(t.review && "tw:bg-bg-tint")}>
                            <td>{t.row_no}</td><td className="nowrap">{t.review?.date ?? t.date}</td><td>{t.description}</td>
                            <td className="text-end font-tabular">{t.review ? t.review.debit : t.debit}</td>
                            <td className="text-end font-tabular">{t.review ? t.review.credit : t.credit}</td>
                            <td className="text-end font-tabular">{t.review ? t.review.balance : t.balance}</td>
                            <td>{editable && <button className="btn btn-sm app-btn-ghost" onClick={() => setRow(t)} aria-label={`Correct row ${t.row_no}`}><Pencil size={13} /></button>}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              ))}
            </Card>
          )}

          <Card title={`Values read (${data.missing_actions} waiting) · highlighted below ${data.confidence_threshold} confidence`}>
            {data.fields.map((f) => (
              <div key={f.id} className={cn("tw:py-2 tw:border-b tw:border-border-subtle tw:text-[13px]",
                (f.low_confidence || f.validation === "failed") && !f.review && "tw:bg-warning-bg tw:px-2 tw:rounded",
                next?.id === f.id && "tw:ring-2 tw:ring-brand-400")}>
                <div className="d-flex align-items-start justify-content-between gap-2">
                  <div>
                    <div className="tw:text-text-tertiary">{f.path} · p. {f.source_page ?? "?"} · confidence {f.confidence ?? "—"}</div>
                    <div className="fw-medium">{f.value ?? <span className="tw:text-text-disabled">not read</span>}</div>
                    {f.review?.action === "correct" && <div>Corrected to <b>{f.review.corrected_value}</b> <span className="tw:text-text-tertiary">({f.review.reason})</span></div>}
                    {f.validation === "failed" && <div className="tw:text-destructive">{f.validation_reason}</div>}
                    {f.source_text && <div className="tw:text-text-tertiary">“{f.source_text}”</div>}
                  </div>
                  <div className="d-flex gap-1 tw:shrink-0">
                    {f.review && <span className="app-badge badge-neutral">{f.review.action === "accept" ? "Accepted" : f.review.action === "correct" ? "Corrected" : "Not present"}</span>}
                    {editable && (
                      <>
                        <button className="btn btn-sm app-btn-ghost" title="Accept as read" disabled={f.value === null || f.validation === "failed"} onClick={() => accept(f)}><Check size={14} /></button>
                        <button className="btn btn-sm app-btn-ghost" title="Correct" onClick={() => setCorrecting(f)}><Pencil size={14} /></button>
                        <button className="btn btn-sm app-btn-ghost" title="Not present" onClick={() => notPresent(f)}><X size={14} /></button>
                      </>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </Card>
        </div>
      </div>
      <CorrectModal field={correcting} onClose={() => setCorrecting(null)}
        onSave={(value, reason) => act(() => extractionService.setField(extractionId, correcting!.id, "correct", value, reason, applicationId)).then(() => setCorrecting(null))} />
      <RowModal row={row} onClose={() => setRow(null)}
        onSave={(d) => act(() => extractionService.setRow(extractionId, row!.id, d, applicationId)).then(() => setRow(null))} />
    </div>
  );
}

function CorrectModal({ field, onClose, onSave }: { field: ReviewField | null; onClose: () => void; onSave: (v: string, r: string) => void }) {
  const [value, setValue] = useState("");
  const [reason, setReason] = useState("");
  useEffect(() => { setValue(field?.value ?? ""); setReason(""); }, [field]);
  return (
    <Modal title={`Correct ${field?.path ?? ""}`} open={!!field} onClose={onClose} onSubmit={() => onSave(value, reason)}
      submitLabel="Save correction" submitDisabled={!value.trim() || !reason.trim()}>
      <p className="tw:text-[13px] tw:text-text-secondary">The AI read “{field?.value ?? "nothing"}”. Your correction is kept beside it; the AI value is never changed.</p>
      <label className="form-label" htmlFor="correct-value">Correct value</label>
      <input id="correct-value" className="form-control mb-2" value={value} onChange={(e) => setValue(e.target.value)} />
      <label className="form-label" htmlFor="correct-reason">Reason</label>
      <input id="correct-reason" className="form-control" value={reason} onChange={(e) => setReason(e.target.value)} />
    </Modal>
  );
}

function RowModal({ row, onClose, onSave }: { row: ReviewTransaction | null; onClose: () => void;
  onSave: (d: { date?: string; debit?: string; credit?: string; balance?: string; reason: string }) => void }) {
  const [d, setD] = useState({ date: "", debit: "", credit: "", balance: "", reason: "" });
  useEffect(() => {
    if (row) setD({ date: row.date ?? "", debit: row.debit ?? "", credit: row.credit ?? "", balance: row.balance ?? "", reason: "" });
  }, [row]);
  return (
    <Modal title={`Correct page ${row?.page_number} row ${row?.row_no}`} open={!!row} onClose={onClose}
      onSubmit={() => onSave({ date: d.date || undefined, debit: d.debit || undefined, credit: d.credit || undefined, balance: d.balance || undefined, reason: d.reason })}
      submitLabel="Save row" submitDisabled={!d.reason.trim()}>
      <p className="tw:text-[13px] tw:text-text-secondary">{row?.description}. The page is re-checked in Python after you save.</p>
      <div className="row g-2">
        {(["date", "debit", "credit", "balance"] as const).map((k) => (
          <div className="col-6" key={k}>
            <label className="form-label text-capitalize" htmlFor={`row-${k}`}>{k}</label>
            <input id={`row-${k}`} className="form-control font-tabular" type={k === "date" ? "date" : "text"} value={d[k]} onChange={(e) => setD({ ...d, [k]: e.target.value })} />
          </div>
        ))}
        <div className="col-12">
          <label className="form-label" htmlFor="row-reason">Reason</label>
          <input id="row-reason" className="form-control" value={d.reason} onChange={(e) => setD({ ...d, reason: e.target.value })} />
        </div>
      </div>
    </Modal>
  );
}
