import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { extractionService } from "@/services";
import type { ChangeRequest, ExtractionReviewDetail } from "@/lib/types";
import { ROUTES } from "@/lib/constants";

/** For an ai.review request: what the reviewer corrected, beside what the AI read. */
export function AiReviewSummary({ cr }: { cr: ChangeRequest }) {
  const extractionId = Number(cr.entity_id);
  const [data, setData] = useState<ExtractionReviewDetail | null>(null);
  useEffect(() => { extractionService.review(extractionId).then(setData).catch(() => setData(null)); }, [extractionId]);
  if (!data) return <p className="tw:text-[13px] tw:text-text-tertiary">Loading the review…</p>;
  const changed = data.fields.filter((f) => f.review && f.review.action !== "accept");
  const lowAccepted = data.fields.filter((f) => f.review?.action === "accept" && f.low_confidence);
  const rows = data.transactions.filter((t) => t.review);
  return (
    <div className="mb-3 tw:text-[13px]">
      <p className="app-section-label mb-1">{data.extraction.label} · reading {data.extraction.id}</p>
      {changed.length === 0 && rows.length === 0 && <p className="tw:text-text-secondary">Every value accepted as read.</p>}
      {changed.map((f) => (
        <div key={f.id}>• {f.path}: AI read “{f.value ?? "—"}” → {f.review!.action === "correct" ? <b>{f.review!.corrected_value}</b> : "not present"}
          {f.review!.reason && <span className="tw:text-text-tertiary"> ({f.review!.reason})</span>}</div>
      ))}
      {rows.map((t) => (
        <div key={t.id}>• page {t.page_number} row {t.row_no}: debit {t.debit ?? "—"} → {t.review!.debit ?? "—"}, credit {t.credit ?? "—"} → {t.review!.credit ?? "—"} ({t.review!.reason})</div>
      ))}
      {lowAccepted.length > 0 && <p className="tw:text-warning mt-1 mb-0">{lowAccepted.length} low-confidence value(s) accepted as read: {lowAccepted.map((f) => f.path).join(", ")}.</p>}
      {data.review?.statement_unreliable && <p className="mt-1 mb-0">Statement marked not reliable: {data.review.unreliable_reason}</p>}
      <Link to={ROUTES.REVIEW_EXTRACTION(data.extraction.id)} className="d-inline-block mt-1">Open the review with the document</Link>
    </div>
  );
}
