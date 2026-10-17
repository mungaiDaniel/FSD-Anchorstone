import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2 } from "lucide-react";
import { Card, PageHeader, SegmentedTabs } from "@/components/ui/Page";
import { Modal } from "@/components/ui/Modal";
import { aiService } from "@/services";
import type { AiAccuracyRow, AiStatus, AiUsageMonth, Rule, RuleSetInfo } from "@/lib/types";
import { apiErrorMessage, formatDateTime } from "@/lib/utils";

type Tab = "rules" | "usage" | "accuracy";
const TABS: { key: Tab; label: string }[] = [
  { key: "rules", label: "Pre-selection rules" }, { key: "usage", label: "Usage and cost" }, { key: "accuracy", label: "Accuracy" },
];

export default function AiOversightPage() {
  const [tab, setTab] = useState<Tab>("rules");
  return (
    <div className="app-page">
      <PageHeader title="AI oversight"
        subtitle="The rules that recommend Shortlisted, Needs review or Not qualified; what document reading costs; and how often staff correct it." />
      <div className="mb-3"><SegmentedTabs label="Section" items={TABS} value={tab} onChange={setTab} /></div>
      {tab === "rules" && <RuleSetEditor />}
      {tab === "usage" && <Usage />}
      {tab === "accuracy" && <Accuracy />}
    </div>
  );
}

// ── Rule-set editor: edit a draft, see the diff against the version in force, submit for approval ──

function show(v: unknown): string {
  if (v === undefined) return "—";
  return typeof v === "string" ? v : JSON.stringify(v);
}

function parseLoose(text: string): unknown {
  const t = text.trim();
  if (t === "") return "";
  try {
    return JSON.parse(t);
  } catch {
    return t;
  }
}

interface Change { id: string; kind: "added" | "removed" | "changed"; fields: { field: string; before: string; after: string }[] }

function diff(current: Rule[], draft: Rule[]): Change[] {
  const out: Change[] = [];
  const before = new Map(current.map((r) => [r.id, r]));
  const after = new Map(draft.map((r) => [r.id, r]));
  for (const r of draft) {
    const old = before.get(r.id);
    if (!old) { out.push({ id: r.id, kind: "added", fields: [{ field: "rule", before: "—", after: r.description }] }); continue; }
    const fields = (["description", "metric", "comparison", "threshold", "outcome_if_failed", "applies_to"] as const)
      .filter((k) => show(old[k]) !== show(r[k])).map((k) => ({ field: k, before: show(old[k]), after: show(r[k]) }));
    if (fields.length) out.push({ id: r.id, kind: "changed", fields });
  }
  for (const r of current) if (!after.has(r.id)) out.push({ id: r.id, kind: "removed", fields: [{ field: "rule", before: r.description, after: "—" }] });
  return out;
}

function RuleSetEditor() {
  const [info, setInfo] = useState<RuleSetInfo | null>(null);
  const [draft, setDraft] = useState<Rule[]>([]);
  const [reviewing, setReviewing] = useState(false);
  const [evidence, setEvidence] = useState("");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    aiService.ruleSet().then((i) => { setInfo(i); setDraft(structuredClone(i.rule_set?.rules ?? [])); })
      .catch((e) => toast.error(apiErrorMessage(e)));
  }, []);
  useEffect(load, [load]);

  const changes = useMemo(() => diff(info?.rule_set?.rules ?? [], draft), [info, draft]);
  if (!info) return <p className="tw:text-text-tertiary">Loading…</p>;

  const update = (i: number, patch: Partial<Rule>) => setDraft(draft.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const submit = async () => {
    setSaving(true);
    try {
      await aiService.proposeRuleSet(draft, evidence, reason);
      toast.success("Submitted. The new version applies once a second person approves it.");
      setReviewing(false);
    } catch (e) {
      toast.error(apiErrorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card title={`Rule set v${info.version_no} (in force from ${info.effective_from})`}
      actions={<button className="btn btn-sm btn-primary" disabled={changes.length === 0} onClick={() => setReviewing(true)}>
        Review changes ({changes.length})</button>}>
      <p className="tw:text-[13px] tw:text-text-secondary">
        Rules only recommend: any Not-qualified failure → Not qualified; any other failure or missing data → Needs review;
        otherwise Shortlisted. Protected attributes ({info.protected_attributes.join(", ")}) can never be used.
      </p>
      <div className="app-table-scroll">
        <table className="table app-table align-middle">
          <thead><tr><th>Id</th><th>Description</th><th>Metric</th><th>Comparison</th><th>Threshold</th><th>If failed</th><th>Applies to</th><th /></tr></thead>
          <tbody>
            {draft.map((r, i) => (
              <tr key={i}>
                <td><input className="form-control form-control-sm tw:w-16" aria-label="Rule id" value={r.id} onChange={(e) => update(i, { id: e.target.value })} /></td>
                <td><input className="form-control form-control-sm tw:min-w-[260px]" aria-label={`${r.id} description`} value={r.description} onChange={(e) => update(i, { description: e.target.value })} /></td>
                <td>
                  <select className="form-select form-select-sm tw:min-w-[210px]" aria-label={`${r.id} metric`} value={r.metric} onChange={(e) => update(i, { metric: e.target.value })}>
                    {info.metrics.map((m) => <option key={m.name} value={m.name} title={m.description}>{m.name}</option>)}
                  </select>
                </td>
                <td>
                  <select className="form-select form-select-sm tw:min-w-[96px]" aria-label={`${r.id} comparison`} value={r.comparison} onChange={(e) => update(i, { comparison: e.target.value })}>
                    {info.comparisons.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </td>
                <td><input className="form-control form-control-sm font-tabular tw:min-w-[180px]" aria-label={`${r.id} threshold`} value={show(r.threshold)} onChange={(e) => update(i, { threshold: parseLoose(e.target.value) })} /></td>
                <td><input className="form-control form-control-sm tw:min-w-[200px]" aria-label={`${r.id} outcome if failed`} value={show(r.outcome_if_failed)} onChange={(e) => update(i, { outcome_if_failed: parseLoose(e.target.value) as Rule["outcome_if_failed"] })} /></td>
                <td><input className="form-control form-control-sm tw:min-w-[200px]" aria-label={`${r.id} applies to`} value={r.applies_to ? JSON.stringify(r.applies_to) : ""} placeholder="all"
                  onChange={(e) => update(i, { applies_to: e.target.value.trim() ? (parseLoose(e.target.value) as Rule["applies_to"]) : undefined })} /></td>
                <td><button className="btn btn-sm app-btn-ghost-danger" aria-label={`Remove ${r.id}`} onClick={() => setDraft(draft.filter((_, j) => j !== i))}><Trash2 size={14} /></button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button className="btn btn-sm app-btn-ghost d-flex align-items-center gap-1" onClick={() => setDraft([...draft,
        { id: `R${draft.length + 1}`, description: "", metric: info.metrics[0]?.name ?? "months_in_business", comparison: ">=", threshold: 0, outcome_if_failed: "needs_review" }])}>
        <Plus size={14} /> Add rule</button>

      <Modal title="Changes against the version in force" open={reviewing} onClose={() => setReviewing(false)} wide
        onSubmit={submit} submitLabel="Submit for approval" submitting={saving} submitDisabled={!evidence.trim() || !reason.trim()}>
        <table className="table table-sm">
          <thead><tr><th>Rule</th><th>Change</th><th>Field</th><th>Before</th><th>After</th></tr></thead>
          <tbody>
            {changes.flatMap((c) => c.fields.map((f, j) => (
              <tr key={`${c.id}-${j}`}>
                <td>{c.id}</td><td className="text-capitalize">{c.kind}</td><td>{f.field}</td>
                <td className="tw:text-destructive tw:break-all">{f.before}</td><td className="tw:text-success tw:break-all">{f.after}</td>
              </tr>
            )))}
          </tbody>
        </table>
        <label className="form-label" htmlFor="rules-evidence">Evidence (e.g. credit committee minute)</label>
        <input id="rules-evidence" className="form-control mb-2" value={evidence} onChange={(e) => setEvidence(e.target.value)} />
        <label className="form-label" htmlFor="rules-reason">Reason</label>
        <input id="rules-reason" className="form-control" value={reason} onChange={(e) => setReason(e.target.value)} />
      </Modal>
    </Card>
  );
}

// ── Usage and accuracy ──

function ServiceStatus() {
  const [status, setStatus] = useState<AiStatus | null>(null);
  const [resuming, setResuming] = useState(false);
  const [reason, setReason] = useState("");
  const load = useCallback(() => { aiService.status().then(setStatus).catch((e) => toast.error(apiErrorMessage(e))); }, []);
  useEffect(load, [load]);
  if (!status) return null;
  const resume = () => aiService.resume(reason).then(() => { toast.success("AI reading resumed."); setResuming(false); setReason(""); load(); })
    .catch((e) => toast.error(apiErrorMessage(e)));
  return (
    <Card title="Service and budgets">
      {status.status === "paused" ? (
        <div className="alert alert-danger d-flex flex-wrap align-items-center justify-content-between gap-2 py-2" style={{ fontSize: 13 }}>
          <span><b>Paused by the circuit breaker</b> since {formatDateTime(status.paused_at)}: {status.paused_reason}</span>
          <button className="btn btn-sm btn-outline-danger" onClick={() => setResuming(true)}>Resume</button>
        </div>
      ) : (
        <p className="tw:text-[13px] mb-2">
          {status.enabled ? "Running." : "Switched off (ai.enabled)."} The breaker pauses after {status.breaker.consecutive_failures} failed
          calls in a row, or more than {status.breaker.window_failures} in {status.breaker.window_minutes} minutes.
          {status.resumed_by && <span className="tw:text-text-tertiary"> Last resumed by {status.resumed_by} on {formatDateTime(status.resumed_at)}.</span>}
        </p>
      )}
      <div className="row g-3 tw:text-[13px]">
        <div className="col-sm-4">This month: <b>US${Number(status.spent_this_month_usd).toFixed(2)}</b> of US${status.budgets.monthly_usd}</div>
        <div className="col-sm-4">Per application: US${status.budgets.per_application_usd}</div>
        <div className="col-sm-4">Per reading: US${status.budgets.per_run_usd}</div>
      </div>
      {status.recent_refusals.length > 0 && (
        <>
          <p className="app-section-label mt-3 mb-1">Calls refused before they were made</p>
          <table className="table table-sm mb-0 tw:text-[13px]">
            <thead><tr><th>When</th><th>Why</th><th>Reading</th><th className="text-end">Spent + estimate / limit (US$)</th></tr></thead>
            <tbody>
              {status.recent_refusals.map((r) => (
                <tr key={r.id} title={r.message}>
                  <td className="nowrap">{formatDateTime(r.refused_at)}</td><td>{r.label}</td>
                  <td>{r.extraction_id}{r.page_number ? ` p. ${r.page_number}` : ""}{r.application_id ? ` · application ${r.application_id}` : ""}</td>
                  <td className="text-end font-tabular">{r.limit_usd ? `${Number(r.spent_usd).toFixed(4)} + ${Number(r.estimate_usd).toFixed(4)} / ${Number(r.limit_usd).toFixed(2)}` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      <Modal title="Resume AI document reading" open={resuming} onClose={() => setResuming(false)} onSubmit={resume}
        submitLabel="Resume" submitDisabled={!reason.trim()}>
        <p className="tw:text-[13px] tw:text-text-secondary">Readings that failed while paused stay failed: retry them from their application.</p>
        <label className="form-label" htmlFor="resume-reason">Why is it safe to resume? (recorded in the audit log)</label>
        <input id="resume-reason" className="form-control" value={reason} onChange={(e) => setReason(e.target.value)} />
      </Modal>
    </Card>
  );
}

function Usage() {
  const [months, setMonths] = useState<AiUsageMonth[] | null>(null);
  useEffect(() => { aiService.usage().then((d) => setMonths(d.months)).catch((e) => toast.error(apiErrorMessage(e))); }, []);
  if (!months) return <p className="tw:text-text-tertiary">Loading…</p>;
  if (months.length === 0) return <div className="d-flex flex-column gap-3"><ServiceStatus /><Card title="Usage"><p className="tw:text-text-tertiary mb-0">No documents read yet.</p></Card></div>;
  return (
    <div className="d-flex flex-column gap-3">
      <ServiceStatus />
      {months.map((m) => (
        <Card key={m.month} title={`${m.month} · US$${Number(m.cost_usd).toFixed(2)} · ${m.readings} reading(s), ${m.calls} call(s)${m.refusals.length ? ` · ${m.refusals.length} refused` : ""}`}>
          <table className="table app-table mb-0">
            <thead><tr><th>Document type</th><th>Model</th><th className="text-end">Readings</th><th className="text-end">Calls</th>
              <th className="text-end">Tokens in / out</th><th className="text-end">Cost (US$)</th><th className="text-end">Per reading</th></tr></thead>
            <tbody>
              {m.by_type.map((r) => (
                <tr key={`${r.document_type}-${r.model}`}>
                  <td>{r.label}</td><td className="tw:text-text-secondary">{r.model}</td>
                  <td className="text-end">{r.readings}</td><td className="text-end">{r.calls}</td>
                  <td className="text-end font-tabular">{r.input_tokens.toLocaleString()} / {r.output_tokens.toLocaleString()}</td>
                  <td className="text-end font-tabular">{Number(r.cost_usd).toFixed(4)}</td>
                  <td className="text-end font-tabular">{r.cost_per_reading_usd ? Number(r.cost_per_reading_usd).toFixed(4) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      ))}
    </div>
  );
}

function Accuracy() {
  const [rows, setRows] = useState<AiAccuracyRow[] | null>(null);
  useEffect(() => { aiService.accuracy().then(setRows).catch((e) => toast.error(apiErrorMessage(e))); }, []);
  if (!rows) return <p className="tw:text-text-tertiary">Loading…</p>;
  return (
    <Card title="Accuracy from approved reviews (evidence for the sign-off before live use)">
      <table className="table app-table mb-0">
        <thead><tr><th>Document type</th><th className="text-end">Values</th><th className="text-end">Accepted as read</th>
          <th className="text-end">Corrected</th><th className="text-end">Not present</th><th className="text-end">Confident but wrong</th><th className="text-end">Rows corrected</th></tr></thead>
        <tbody>
          {rows.length === 0 && <tr><td colSpan={7} className="tw:text-text-tertiary">No approved reviews yet.</td></tr>}
          {rows.map((r) => (
            <tr key={r.document_type}>
              <td>{r.label}</td><td className="text-end">{r.values}</td>
              <td className="text-end">{r.accepted} {r.accepted_as_read_percent && <span className="tw:text-text-tertiary">({r.accepted_as_read_percent}%)</span>}</td>
              <td className="text-end">{r.corrected}</td><td className="text-end">{r.not_present}</td>
              <td className="text-end">{r.confident_but_corrected}</td><td className="text-end">{r.statement_rows_corrected}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}
