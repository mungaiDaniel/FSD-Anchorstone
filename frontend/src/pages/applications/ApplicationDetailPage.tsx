import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { FileText, Play, ScanText, ShieldCheck } from "lucide-react";
import { Card, EmptyState, Field, PageHeader, Stat } from "@/components/ui/Page";
import { CheckBadge, ClientSearch, EstimateNote, OutcomeBadge } from "@/components/applications/ApplicationBits";
import { useAuth } from "@/context/AuthContext";
import { applicationService, extractionService, partyService } from "@/services";
import type {
  ApplicationDetail, CrbStatusValue, CrossCheck, DecisionLog, DecisionValue, PartyDocument, PartyListItem, RuleResult,
} from "@/lib/types";
import { CRB_STATUS_LABELS, ROUTES } from "@/lib/constants";
import { apiErrorMessage, formatDate, formatDateTime, formatKES, todayISO } from "@/lib/utils";

type Tab = "documents" | "crb" | "checks" | "screening" | "decision" | "log";
const CHECK_NAMES: Record<string, string> = {
  name_consistent: "Name matches across documents", id_number_consistent: "ID number and KRA PIN match",
  cr12_directors_match: "CR12 directors match captured directors", collateral_owner_match: "Collateral owner is the applicant or a guarantor",
};
const READABLE = new Set(["national_id", "passport", "kra_pin", "cr12", "certificate_of_incorporation", "bank_statement",
  "mpesa_statement", "audited_financial_statements", "title_deed", "logbook", "valuation_report", "crb_report"]);

export default function ApplicationDetailPage() {
  const { id } = useParams();
  const appId = Number(id);
  const { isAdmin } = useAuth();
  const [app, setApp] = useState<ApplicationDetail | null>(null);
  const [tab, setTab] = useState<Tab>("documents");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    applicationService.get(appId).then((a) => { setApp(a); setError(null); }).catch((e) => setError(apiErrorMessage(e)));
  }, [appId]);
  useEffect(load, [load]);

  if (error) return <div className="app-page"><div className="alert alert-danger">{error}</div></div>;
  if (!app) return <div className="app-page tw:text-text-tertiary">Loading…</div>;

  const tabs: { key: Tab; label: string }[] = [
    { key: "documents", label: `Documents (${app.documents.length})` }, { key: "crb", label: "CRB" },
    { key: "checks", label: "Cross-checks" }, { key: "screening", label: "Pre-selection" },
    { key: "decision", label: "Decision" }, { key: "log", label: "Decision log" },
  ];

  return (
    <div className="app-page">
      <PageHeader title={`${app.application_no} · ${app.party?.display_name ?? ""}`}
        subtitle={<>{app.product_label} · <Link to={ROUTES.CLIENT_DETAIL(app.party_id)}>{app.party?.party_no}</Link></>}
        actions={<OutcomeBadge outcome={app.latest_run?.outcome} />} />
      <div className="row g-3 mb-3">
        <div className="col-6 col-md-3"><Stat label="Amount requested" value={formatKES(app.amount_requested)} /></div>
        <div className="col-6 col-md-3"><Stat label="Term" value={`${app.term_months} months`} sub={`${Number(app.indicative_rate_percent)}% p.a. indicative`} /></div>
        <div className="col-6 col-md-3"><Stat label="Instalment (estimate)" value={formatKES(app.estimated_instalment)}
          sub={app.repayment === "interest_only" ? `${formatKES(app.estimated_final_payment)} at maturity` : "a month"} /></div>
        <div className="col-6 col-md-3"><Stat label="Status" value={app.status === "decided" ? "Decided" : "Open"}
          sub={app.guarantors.length ? `Guarantors: ${app.guarantors.map((g) => g.display_name).join(", ")}` : "No guarantors"} /></div>
      </div>
      <EstimateNote className="mb-3" />
      <ul className="nav nav-tabs mb-3" role="tablist">
        {tabs.map((t) => (
          <li className="nav-item" key={t.key}>
            <button className={`nav-link${tab === t.key ? " active" : ""}`} role="tab" aria-selected={tab === t.key}
              onClick={() => setTab(t.key)}>{t.label}</button>
          </li>
        ))}
      </ul>
      {tab === "documents" && <DocumentsTab app={app} reload={load} isAdmin={isAdmin} />}
      {tab === "crb" && <CrbTab app={app} reload={load} />}
      {tab === "checks" && <ChecksTab appId={app.id} />}
      {tab === "screening" && <ScreeningTab app={app} reload={load} />}
      {tab === "decision" && <DecisionTab app={app} reload={load} isAdmin={isAdmin} />}
      {tab === "log" && <LogTab appId={app.id} isAdmin={isAdmin} />}
    </div>
  );
}

function DocumentsTab({ app, reload, isAdmin }: { app: ApplicationDetail; reload: () => void; isAdmin: boolean }) {
  const [available, setAvailable] = useState<(PartyDocument & { owner: string; partyId: number })[]>([]);
  const [chosen, setChosen] = useState("");
  const [guarantor, setGuarantor] = useState<PartyListItem | null>(null);
  const owners = [{ id: app.party_id, name: app.party?.display_name ?? "Applicant" },
    ...app.guarantors.map((g) => ({ id: g.id, name: g.display_name }))];
  const ownerKey = owners.map((o) => o.id).join(",");

  useEffect(() => {
    Promise.all(owners.map((o) => partyService.documents(o.id).then((docs) =>
      docs.filter((d) => d.current && d.status === "active").map((d) => ({ ...d, owner: o.name, partyId: o.id })))))
      .then((lists) => setAvailable(lists.flat())).catch(() => setAvailable([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ownerKey]);

  const linked = new Set(app.documents.map((d) => d.id));
  const ownerOf = (docId: string) => available.find((d) => d.id === docId)?.partyId ?? app.party_id;
  const run = (fn: () => Promise<unknown>, done: string) =>
    fn().then(() => { toast.success(done); reload(); }).catch((e) => toast.error(apiErrorMessage(e)));

  return (
    <div className="row g-3">
      <div className="col-lg-8">
        <Card title="Documents and AI readings">
          {app.documents.length === 0 ? <EmptyState icon={<FileText size={22} />} message="Add documents uploaded to the applicant or a guarantor." /> : (
            <table className="table app-table align-middle mb-0">
              <thead><tr><th>Document</th><th>Reading</th><th className="text-end">Actions</th></tr></thead>
              <tbody>
                {app.documents.map((d) => (
                  <tr key={d.id}>
                    <td>
                      <button className="btn btn-link p-0 tw:text-left" onClick={() => applicationService.openDocument(d.id, d.filename, d.content_type)}>{d.label}</button>
                      <div className="tw:text-[12px] tw:text-text-tertiary">{d.filename}</div>
                    </td>
                    <td>
                      {d.extraction ? (
                        <>
                          <span className="app-badge badge-neutral">{d.extraction.status_label}</span>
                          {d.extraction.status_reason && <div className="tw:text-[12px] tw:text-text-tertiary tw:max-w-[360px] tw:line-clamp-2" title={d.extraction.status_reason}>{d.extraction.status_reason}</div>}
                        </>
                      ) : <span className="tw:text-text-tertiary">Not read</span>}
                    </td>
                    <td className="text-end nowrap">
                      {isAdmin && READABLE.has(d.document_type) && (!d.extraction || ["failed", "rescan_needed"].includes(d.extraction.status)) && (
                        <button className="btn btn-sm app-btn-ghost" onClick={() => run(() => d.extraction
                          ? extractionService.retry(d.extraction.id) : extractionService.request(ownerOf(d.id), d.id), "Queued for AI reading.")}>
                          <ScanText size={14} /> {d.extraction ? "Read again" : "Read with AI"}
                        </button>
                      )}
                      {d.extraction && ["completed", "needs_review"].includes(d.extraction.status) && (
                        <Link className="btn btn-sm app-btn-ghost" to={`${ROUTES.REVIEW_EXTRACTION(d.extraction.id)}?application=${app.id}`}>Review</Link>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="tw:text-[12px] tw:text-text-tertiary mt-2 mb-0">
            Documents are read automatically only for clients who consented. Without consent, capture the details by hand.
          </p>
        </Card>
      </div>
      <div className="col-lg-4">
        <Card title="Add a document">
          <Field label="From the applicant's or a guarantor's documents">
            <select className="form-select form-select-sm" value={chosen} onChange={(e) => setChosen(e.target.value)}>
              <option value="">Choose…</option>
              {available.filter((d) => !linked.has(d.id)).map((d) => <option key={d.id} value={d.id}>{d.label} · {d.owner}</option>)}
            </select>
          </Field>
          <button className="btn btn-sm btn-primary" disabled={!chosen || app.status !== "open"}
            onClick={() => run(() => applicationService.addDocument(app.id, chosen), "Document added.").then(() => setChosen(""))}>Add</button>
        </Card>
        <Card title="Guarantors" className="tw:mt-3">
          <ClientSearch value={guarantor} onChange={setGuarantor} label="Guarantor" />
          <button className="btn btn-sm btn-primary mt-2" disabled={!guarantor || app.status !== "open"}
            onClick={() => guarantor && run(() => applicationService.addGuarantor(app.id, guarantor.id), "Guarantor added.").then(() => setGuarantor(null))}>Add guarantor</button>
        </Card>
      </div>
    </div>
  );
}

function CrbTab({ app, reload }: { app: ApplicationDetail; reload: () => void }) {
  const [status, setStatus] = useState<CrbStatusValue>("clear");
  const [date, setDate] = useState(todayISO());
  const [bureau, setBureau] = useState("");
  const [fromReport, setFromReport] = useState("");
  const reports = app.documents.filter((d) => d.document_type === "crb_report" && d.extraction);
  const save = () => applicationService.enterCrb(app.id, { status, status_date: date, bureau,
    extraction_id: fromReport ? Number(fromReport) : undefined })
    .then(() => { toast.success("Entered. A second person confirms it in Approvals."); reload(); })
    .catch((e) => toast.error(apiErrorMessage(e)));
  return (
    <div className="row g-3">
      <div className="col-lg-6">
        <Card title="Confirmed CRB status">
          {app.crb ? (
            <dl className="mb-0" style={{ fontSize: 13 }}>
              <dt>Status</dt><dd>{app.crb.status_label}</dd>
              <dt>Date · bureau</dt><dd>{formatDate(app.crb.status_date)} · {app.crb.bureau}</dd>
              <dt>Source</dt><dd>{app.crb.source === "crb_report" ? "CRB report reading" : "Entered by staff"}</dd>
              <dt>Entered · confirmed</dt><dd>{app.crb.entered_by} · {app.crb.confirmed_by}</dd>
            </dl>
          ) : <EmptyState icon={<ShieldCheck size={22} />} message="No confirmed CRB status. The CRB rule sees missing data until one is confirmed." />}
        </Card>
      </div>
      <div className="col-lg-6">
        <Card title="Enter CRB status">
          <Field label="Status">
            <select className="form-select form-select-sm" value={status} onChange={(e) => setStatus(e.target.value as CrbStatusValue)}>
              {Object.entries(CRB_STATUS_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </Field>
          <div className="row g-2">
            <div className="col-6"><Field label="Date"><input type="date" className="form-control form-control-sm" max={todayISO()} value={date} onChange={(e) => setDate(e.target.value)} /></Field></div>
            <div className="col-6"><Field label="Bureau"><input className="form-control form-control-sm" value={bureau} onChange={(e) => setBureau(e.target.value)} /></Field></div>
          </div>
          {reports.length > 0 && (
            <Field label="From a CRB report reading (optional)">
              <select className="form-select form-select-sm" value={fromReport} onChange={(e) => setFromReport(e.target.value)}>
                <option value="">Entered by hand</option>
                {reports.map((d) => <option key={d.id} value={d.extraction!.id}>{d.filename} (reading {d.extraction!.id})</option>)}
              </select>
            </Field>
          )}
          <button className="btn btn-sm btn-primary" disabled={!bureau || app.status !== "open"} onClick={save}>Submit for confirmation</button>
        </Card>
      </div>
    </div>
  );
}

function ChecksTab({ appId }: { appId: number }) {
  const [checks, setChecks] = useState<CrossCheck[] | null>(null);
  useEffect(() => { applicationService.checks(appId).then(setChecks).catch((e) => toast.error(apiErrorMessage(e))); }, [appId]);
  if (!checks) return <p className="tw:text-text-tertiary">Loading…</p>;
  return (
    <Card title="Cross-document checks (approved values only)">
      {checks.map((c) => (
        <div key={c.check} className="tw:py-2 tw:border-b tw:border-border-subtle">
          <div className="d-flex align-items-center justify-content-between gap-2">
            <span className="fw-medium">{CHECK_NAMES[c.check] ?? c.check}</span><CheckBadge status={c.status} />
          </div>
          <p className="tw:text-[13px] tw:text-text-secondary mb-1">{c.reason}</p>
          {c.evidence.length > 0 && (
            <ul className="tw:text-[12px] tw:text-text-tertiary mb-0">
              {c.evidence.map((e, i) => <li key={i}>{e.source}: {e.value ?? "—"}{e.page ? ` (p. ${e.page})` : ""}</li>)}
            </ul>
          )}
        </div>
      ))}
    </Card>
  );
}

function RulesTable({ rules }: { rules: RuleResult[] }) {
  return (
    <table className="table app-table align-middle mb-0">
      <thead><tr><th>Rule</th><th>Result</th><th>Reason</th></tr></thead>
      <tbody>
        {rules.map((r) => (
          <tr key={r.rule_id}>
            <td className="nowrap"><span className="fw-medium">{r.rule_id}</span> <span className="tw:text-text-secondary">{r.description}</span></td>
            <td><CheckBadge status={r.result === "fail" ? (r.outcome_if_failed === "not_qualified" ? "fail" : "needs_review") : r.result} /></td>
            <td className="tw:text-[13px] tw:text-text-secondary">{r.reason}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ScreeningTab({ app, reload }: { app: ApplicationDetail; reload: () => void }) {
  const [running, setRunning] = useState(false);
  const screen = () => {
    setRunning(true);
    applicationService.screen(app.id).then(() => { toast.success("Pre-selection run."); reload(); })
      .catch((e) => toast.error(apiErrorMessage(e))).finally(() => setRunning(false));
  };
  const run = app.latest_run;
  return (
    <Card title="Pre-selection (a recommendation, never a decision)"
      actions={<button className="btn btn-sm btn-primary d-flex align-items-center gap-1" disabled={running || app.status !== "open"} onClick={screen}><Play size={13} /> Run pre-selection</button>}>
      {!run ? <EmptyState message="Not run yet. It uses only values confirmed by a reviewer and a second approver." /> : (
        <>
          <div className="d-flex flex-wrap align-items-center gap-3 mb-3 tw:text-[13px]">
            <OutcomeBadge outcome={run.outcome} />
            <span className="tw:text-text-secondary">Rule set v{run.rule_set_version_no} · {formatDateTime(run.evaluated_at)} · {run.evaluated_by}</span>
            <span className="tw:text-text-tertiary font-tabular" title="SHA-256 of the inputs">{run.inputs_sha256.slice(0, 12)}…</span>
          </div>
          <RulesTable rules={run.rules} />
        </>
      )}
    </Card>
  );
}

function DecisionTab({ app, reload, isAdmin }: { app: ApplicationDetail; reload: () => void; isAdmin: boolean }) {
  const [decision, setDecision] = useState<DecisionValue>("proceed");
  const [reason, setReason] = useState("");
  const save = () => applicationService.decide(app.id, decision, reason).then((r) => {
    toast.success(r.data?.status === "pending_approval" ? "Override submitted: a second credit approver must approve it." : "Decision recorded.");
    setReason("");
    reload();
  }).catch((e) => toast.error(apiErrorMessage(e)));
  return (
    <div className="row g-3">
      <div className="col-lg-6">
        <Card title="Record the decision">
          {!app.latest_run ? <p className="tw:text-text-tertiary tw:text-[13px]">Run the pre-selection first.</p> : (
            <>
              <p className="tw:text-[13px] tw:text-text-secondary">Recommendation: <OutcomeBadge outcome={app.latest_run.outcome} />.
                {app.latest_run.outcome === "not_qualified" && " Proceeding is an override that a second credit approver must approve."}</p>
              {app.pending_override && <div className="alert alert-warning py-2" style={{ fontSize: 13 }}>An override is waiting in Approvals.</div>}
              <Field label="Decision">
                <select className="form-select form-select-sm" value={decision} onChange={(e) => setDecision(e.target.value as DecisionValue)}>
                  <option value="proceed">Proceed to credit analysis</option>
                  <option value="decline">Decline</option>
                  <option value="more_info">Request more information</option>
                </select>
              </Field>
              <Field label="Reason (required)"><textarea className="form-control" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
              <button className="btn btn-sm btn-primary" disabled={!isAdmin || !reason.trim() || app.status !== "open" || !!app.pending_override} onClick={save}>Record decision</button>
            </>
          )}
        </Card>
      </div>
      <div className="col-lg-6">
        <Card title="Decisions">
          {app.decisions.length === 0 ? <p className="tw:text-text-tertiary tw:text-[13px]">None yet. The system never declines on its own.</p> : (
            <ul className="list-unstyled mb-0">
              {app.decisions.map((d) => (
                <li key={d.id} className="tw:py-2 tw:border-b tw:border-border-subtle tw:text-[13px]">
                  <span className="fw-medium">{d.decision_label}</span>{d.override && <span className="app-badge badge-waiting ms-2">Override</span>}
                  <div className="tw:text-text-secondary">{d.reason}</div>
                  <div className="tw:text-text-tertiary">{d.decided_by} · {formatDateTime(d.decided_at)}{d.approved_by ? ` · approved by ${d.approved_by}` : ""}</div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}

function LogTab({ appId, isAdmin }: { appId: number; isAdmin: boolean }) {
  const [log, setLog] = useState<DecisionLog | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { if (isAdmin) applicationService.log(appId).then(setLog).catch((e) => setError(apiErrorMessage(e))); }, [appId, isAdmin]);
  if (!isAdmin) return <p className="tw:text-text-tertiary">The decision log shows AI-read personal data and is available to admins.</p>;
  if (error) return <div className="alert alert-danger">{error}</div>;
  if (!log) return <p className="tw:text-text-tertiary">Loading…</p>;
  return (
    <div className="d-flex flex-column gap-3">
      <Card title="Readings and reviews">
        {log.readings.map((r) => (
          <div key={r.extraction.id} className="tw:py-2 tw:border-b tw:border-border-subtle tw:text-[13px]">
            <div className="fw-medium">{r.label} · reading {r.extraction.id} · {r.extraction.status_label}</div>
            <div className="tw:text-text-tertiary">{r.extraction.model_requested} · prompt {r.extraction.prompt_version} · schema {r.extraction.schema_version}
              · {r.calls} call(s) · US${r.extraction.cost_usd} · document {r.extraction.document_sha256.slice(0, 12)}…</div>
            {r.review && (
              <>
                <div className="tw:text-text-secondary">Review: {r.review.state} · reviewed by {r.review.reviewed_by}{r.review.approved_by ? ` · approved by ${r.review.approved_by}` : ""}</div>
                {r.review.values.filter((v) => v.action !== "accept").map((v) => (
                  <div key={v.field} className="tw:text-text-secondary">• {v.field}: AI read “{v.ai_value ?? "—"}” ({v.ai_confidence ?? "?"}, p. {v.page ?? "?"}) → {v.action === "correct" ? `“${v.confirmed_value}”` : "not present"}{v.reason ? ` (${v.reason})` : ""}</div>
                ))}
                {r.review.rows_corrected.map((row) => (
                  <div key={`${row.page}-${row.row}`} className="tw:text-text-secondary">• page {row.page} row {row.row}: AI {JSON.stringify(row.ai)} → {JSON.stringify(row.confirmed)} ({row.reason})</div>
                ))}
              </>
            )}
          </div>
        ))}
      </Card>
      <Card title="Pre-selection runs">
        {log.runs.length === 0 ? <p className="tw:text-text-tertiary tw:text-[13px]">None.</p> : log.runs.map((run) => (
          <div key={run.id} className="mb-3">
            <div className="d-flex align-items-center gap-2 mb-2 tw:text-[13px]"><OutcomeBadge outcome={run.outcome} />
              <span className="tw:text-text-secondary">Rule set v{run.rule_set_version_no} · {formatDateTime(run.evaluated_at)} · {run.evaluated_by}</span></div>
            <RulesTable rules={run.rules} />
          </div>
        ))}
      </Card>
      <Card title="Audit trail">
        <ul className="list-unstyled mb-0 tw:text-[13px]">
          {log.audit.map((a, i) => <li key={i} className="tw:py-1"><span className="tw:text-text-tertiary">{formatDateTime(a.at)}</span> · {a.action} · {a.user} · {a.description}</li>)}
        </ul>
      </Card>
    </div>
  );
}
