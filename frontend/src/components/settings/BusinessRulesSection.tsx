import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { ChevronDown, ChevronRight, History, Pencil, SlidersHorizontal } from "lucide-react";
import { Card, EmptyState, Field, LoadingRow, SearchField, SegmentedTabs } from "@/components/ui/Page";
import { Modal } from "@/components/ui/Modal";
import { approvalService, settingsService } from "@/services";
import { ROUTES, SETTING_SOURCE_LABELS } from "@/lib/constants";
import type { BusinessSetting, ChangeRequest, SettingSource, SettingValue } from "@/lib/types";
import { apiErrorMessage, formatDate, formatDateTime, todayISO } from "@/lib/utils";
import { useRequestGuard } from "@/lib/useRequestGuard";

type Filter = "all" | "working_assumption";

const CATEGORY_LABELS: Record<string, string> = {
  security: "Security",
  investments: "Investments",
  operations: "Operations",
  lending: "Lending",
  compliance: "Compliance",
  documents: "Documents",
  ai: "AI",
};

const SOURCE_TONES: Record<SettingSource, string> = {
  working_assumption: "badge-waiting",
  client_confirmed: "badge-positive",
  internal_decision: "badge-neutral",
};

export function SourceBadge({ source }: { source: SettingSource | null }) {
  const s = source ?? "working_assumption";
  return <span className={`app-badge ${SOURCE_TONES[s]} tw:whitespace-nowrap`}>{SETTING_SOURCE_LABELS[s]}</span>;
}

export function formatSettingValue(s: Pick<BusinessSetting, "key" | "type">, v: SettingValue): string {
  if (v === null || v === undefined) return "—";
  if (s.type === "bool") return v ? "On" : "Off";
  if (Array.isArray(v)) return v.length ? v.map(String).join(", ") : "None";
  if (typeof v === "object") return JSON.stringify(v);
  if (s.key.endsWith("_percent")) return `${v}%`;
  return String(v);
}

/** The value as the form edits it: lists as "a, b", JSON as text. */
function toInput(s: BusinessSetting): string {
  const v = s.value;
  if (s.type === "list" && Array.isArray(v)) return v.map(String).join(", ");
  if (s.type === "json") return JSON.stringify(v, null, 2);
  if (s.type === "bool") return v ? "true" : "false";
  return v === null || v === undefined ? "" : String(v);
}

/** Back to JSON for the server, which validates and normalises it (the client never decides). */
function fromInput(s: BusinessSetting, text: string): SettingValue {
  if (s.type === "bool") return text === "true";
  if (s.type === "list") return text.split(",").map((p) => p.trim()).filter(Boolean);
  if (s.type === "json") return JSON.parse(text) as SettingValue;
  return text.trim();
}

function ProposeModal({ setting, onClose, onDone }: { setting: BusinessSetting | null; onClose: () => void; onDone: () => void }) {
  const [value, setValue] = useState("");
  const [effectiveFrom, setEffectiveFrom] = useState(todayISO());
  const [source, setSource] = useState<SettingSource>("client_confirmed");
  const [evidence, setEvidence] = useState("");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!setting) return;
    setValue(toInput(setting));
    setEffectiveFrom(todayISO());
    setSource("client_confirmed");
    setEvidence("");
    setReason("");
  }, [setting]);

  if (!setting) return null;
  const needsEvidence = source === "client_confirmed" && !evidence.trim();

  const submit = async () => {
    let parsed: SettingValue;
    try {
      parsed = fromInput(setting, value);
    } catch {
      toast.error("The value isn't valid JSON.");
      return;
    }
    setSaving(true);
    try {
      const res = await settingsService.proposeBusinessSetting(setting.key, {
        value: parsed, effective_from: effectiveFrom, source, evidence: evidence.trim() || undefined, reason: reason.trim(),
      });
      toast.success(res.message);
      onDone();
      onClose();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const approvers = setting.approvals_required;
  return (
    <Modal title="Propose a change" open onClose={onClose} onSubmit={submit} submitting={saving}
      submitLabel="Submit for approval" submitDisabled={needsEvidence || !value.trim() || !effectiveFrom}>
      <p className="font-monospace tw:text-[13px] tw:font-semibold tw:text-brand-400 mb-1">{setting.key}</p>
      <p className="tw:text-xs tw:text-text-secondary mb-3">{setting.description}</p>
      <div className="tw:rounded-lg tw:bg-bg-surface-alt tw:border tw:border-border-subtle tw:px-3 tw:py-2 tw:text-xs tw:text-text-secondary mb-3">
        Now: <strong className="tw:text-text-primary">{formatSettingValue(setting, setting.value)}</strong>
        {setting.effective_from && <> since {formatDate(setting.effective_from)}</>} · <SourceBadge source={setting.source} />
      </div>

      <Field label="New value" hint={
        setting.type === "list" ? "Separate items with commas." : setting.key.endsWith("_percent") ? "Percent, up to 4 decimal places." : undefined}>
        {setting.type === "bool" ? (
          <select className="form-select mt-1" value={value} onChange={(e) => setValue(e.target.value)}>
            <option value="true">On</option>
            <option value="false">Off</option>
          </select>
        ) : setting.type === "enum" ? (
          <select className="form-select mt-1" value={value} onChange={(e) => setValue(e.target.value)}>
            {setting.choices.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        ) : setting.type === "json" ? (
          <textarea className="form-control mt-1 font-monospace" rows={5} value={value} onChange={(e) => setValue(e.target.value)} />
        ) : (
          <input className="form-control mt-1 font-tabular" value={value} inputMode={setting.type === "list" ? "text" : "decimal"}
            onChange={(e) => setValue(e.target.value)} />
        )}
      </Field>

      <div className="row g-2">
        <div className="col-sm-6">
          <Field label="Takes effect from" hint="Today or later. Settings are never changed retroactively.">
            <input type="date" className="form-control mt-1" value={effectiveFrom} min={todayISO()} onChange={(e) => setEffectiveFrom(e.target.value)} />
          </Field>
        </div>
        <div className="col-sm-6">
          <Field label="Source">
            <select className="form-select mt-1" value={source} onChange={(e) => setSource(e.target.value as SettingSource)}>
              {(Object.keys(SETTING_SOURCE_LABELS) as SettingSource[]).map((s) => (
                <option key={s} value={s}>{SETTING_SOURCE_LABELS[s]}</option>
              ))}
            </select>
          </Field>
        </div>
      </div>

      <Field label="Evidence" hint={source === "client_confirmed"
        ? `Required: where the client confirmed it${setting.questionnaire_ref ? ` (e.g. questionnaire ${setting.questionnaire_ref} answer)` : ""}.` : "Optional."}>
        <input className="form-control mt-1" value={evidence} maxLength={2000} onChange={(e) => setEvidence(e.target.value)} />
      </Field>
      <Field label="Reason" hint="Shown to the approver.">
        <textarea className="form-control mt-1" rows={2} value={reason} maxLength={2000} onChange={(e) => setReason(e.target.value)} />
      </Field>
      <p className="tw:text-xs tw:text-text-tertiary mb-0">
        This creates a change request. {approvers > 1 ? `${approvers} people other than you` : "Someone other than you"} must
        approve it in Approvals; the current value stays in force until then.
      </p>
    </Modal>
  );
}

function HistoryRows({ setting }: { setting: BusinessSetting }) {
  if (setting.history.length === 0) {
    return <p className="tw:text-xs tw:text-text-tertiary mb-0">Not seeded yet: the registry default is in use.</p>;
  }
  return (
    <table className="table table-sm mb-0 tw:text-xs">
      <thead>
        <tr><th>v</th><th>Value</th><th>From</th><th>Source</th><th>Evidence / reason</th><th>Made / approved</th></tr>
      </thead>
      <tbody>
        {setting.history.map((h) => (
          <tr key={h.id}>
            <td className="font-tabular">{h.version_no}</td>
            <td className="font-tabular tw:font-semibold">{formatSettingValue(setting, h.value)}</td>
            <td className="nowrap">{formatDate(h.effective_from)}</td>
            <td><SourceBadge source={h.source} /></td>
            <td className="tw:max-w-[260px]">
              {h.evidence && <div className="tw:break-words">{h.evidence}</div>}
              {h.reason && <div className="tw:text-text-tertiary tw:break-words">{h.reason}</div>}
              {h.change_request_id && (
                <Link to={`${ROUTES.APPROVALS}?id=${h.change_request_id}`} className="tw:text-[11px]">Request #{h.change_request_id}</Link>
              )}
            </td>
            <td className="nowrap tw:text-text-secondary">
              <span title={h.created_by}>{h.created_by.split("@")[0]}</span> → <span title={h.approved_by}>{h.approved_by.split("@")[0]}</span>
              <div className="tw:text-[11px] tw:text-text-tertiary">{formatDateTime(h.approved_at)}</div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/**
 * Settings → Business rules (admins). Every client-changeable rule with its
 * value today, whether it is still a working assumption, and its history.
 * Changes go through maker-checker; the server enforces who may propose.
 */
export default function BusinessRulesSection() {
  const [filter, setFilter] = useState<Filter>("all");
  const [search, setSearch] = useState("");
  const [rows, setRows] = useState<BusinessSetting[] | null>(null);
  const [pending, setPending] = useState<Record<string, ChangeRequest>>({});
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [editing, setEditing] = useState<BusinessSetting | null>(null);
  const startRequest = useRequestGuard();

  const load = useCallback(() => {
    const isLatest = startRequest();
    setRows(null);
    settingsService.getBusinessSettings(filter === "all" ? undefined : filter)
      .then((d) => {
        if (!isLatest()) return;
        setRows(d);
        setError(null);
      })
      .catch((err) => isLatest() && setError(apiErrorMessage(err)));
    // Open changes per key, so nobody proposes the same change twice. Best effort.
    approvalService.list({ status: "pending", per_page: 200 })
      .then((d) => isLatest() && setPending(Object.fromEntries(
        d.items.filter((cr) => cr.entity_type === "setting" && cr.entity_id).map((cr) => [cr.entity_id!, cr]))))
      .catch(() => isLatest() && setPending({}));
  }, [filter, startRequest]);

  useEffect(load, [load]);

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (rows ?? []).filter((s) => !q || s.key.toLowerCase().includes(q) || s.description.toLowerCase().includes(q));
  }, [rows, search]);

  return (
    <Card title="Business rules" className="mb-3"
      actions={
        <SegmentedTabs label="Business rule filter" value={filter} onChange={setFilter} items={[
          { key: "all", label: "All" },
          { key: "working_assumption", label: "Still on working assumptions" },
        ]} />
      }>
      <p className="tw:text-xs tw:text-text-tertiary tw:-mt-1 mb-3">
        Values the client may change. Each change is a new dated version approved by a second person (two for security
        keys); nothing is backdated. Working assumptions are defaults still to be confirmed by the client.
      </p>
      <SearchField className="mb-3 tw:max-w-sm" value={search} onChange={setSearch} label="Search business rules" placeholder="Key or description" />
      {error && <div className="alert alert-danger py-2" style={{ fontSize: 13 }}>{error}</div>}
      <div className="app-table-scroll">
        <table className="table app-table align-middle mb-0">
          <thead>
            <tr><th>Setting</th><th>Value</th><th>Source</th><th>Refs</th><th>Since</th><th /></tr>
          </thead>
          <tbody>
            {!rows && !error && <LoadingRow colSpan={6} rows={6} />}
            {visible.map((s, i) => {
              const open = expanded === s.key;
              const change = pending[s.key];
              // Approved versions that start later (history is newest first).
              const scheduled = s.history.filter((h) => h.scope_type === "global" && h.effective_from > todayISO()).at(-1);
              const newCategory = i === 0 || visible[i - 1]!.category !== s.category;
              return (
                <Fragment key={s.key}>
                  {newCategory && (
                    <tr className="tw:bg-bg-surface-alt">
                      <td colSpan={6} className="tw:py-1.5 tw:text-[11px] tw:font-bold tw:uppercase tw:tracking-wider tw:text-text-tertiary">
                        {CATEGORY_LABELS[s.category] ?? s.category}
                      </td>
                    </tr>
                  )}
                  <tr>
                    <td className="tw:min-w-[240px] tw:max-w-[380px]">
                      <div className="font-monospace tw:text-[12.5px] tw:font-semibold tw:text-text-primary tw:break-all">{s.key}</div>
                      <div className="tw:text-xs tw:text-text-tertiary tw:line-clamp-2" title={s.description}>{s.description}</div>
                      <div className="d-flex flex-wrap gap-1 tw:mt-1">
                        {!s.in_use && <span className="app-badge badge-neutral">Not used yet</span>}
                        {s.approvals_required > 1 && <span className="app-badge badge-neutral">{s.approvals_required} approvers</span>}
                        {change && (
                          <Link to={`${ROUTES.APPROVALS}?id=${change.id}`} className="app-badge badge-waiting tw:no-underline">
                            Change pending #{change.id}
                          </Link>
                        )}
                      </div>
                    </td>
                    <td className="tw:max-w-[220px] tw:break-words">
                      <span className="font-tabular tw:font-semibold tw:text-brand-400">{formatSettingValue(s, s.value)}</span>
                      {scheduled && (
                        <div className="tw:text-[11px] tw:text-text-tertiary tw:whitespace-nowrap">
                          → {formatSettingValue(s, scheduled.value)} from {formatDate(scheduled.effective_from)}
                        </div>
                      )}
                    </td>
                    <td><SourceBadge source={s.source} /></td>
                    <td className="nowrap tw:text-xs tw:text-text-secondary">
                      {s.wa_ref && <div title="Working assumption / FSD reference">{s.wa_ref}</div>}
                      {s.questionnaire_ref && <div className="tw:text-text-tertiary" title="Client questionnaire question">Q {s.questionnaire_ref}</div>}
                      {!s.wa_ref && !s.questionnaire_ref && "—"}
                    </td>
                    <td className="nowrap tw:text-xs tw:text-text-secondary">{formatDate(s.effective_from)}</td>
                    <td className="text-end text-nowrap">
                      <button className="btn btn-sm app-btn-ghost d-inline-flex align-items-center gap-1" aria-expanded={open}
                        onClick={() => setExpanded(open ? null : s.key)}>
                        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />} <History size={13} /> {s.history.length}
                      </button>
                      <button className="btn btn-sm app-btn-ghost d-inline-flex align-items-center gap-1" onClick={() => setEditing(s)}>
                        <Pencil size={13} /> Change
                      </button>
                    </td>
                  </tr>
                  {open && (
                    <tr>
                      <td colSpan={6} className="tw:bg-bg-surface-alt tw:px-4 tw:py-3"><HistoryRows setting={s} /></td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      {rows && visible.length === 0 && (
        <EmptyState icon={<SlidersHorizontal size={22} />}
          title={filter === "working_assumption" && !search ? "Everything is confirmed" : "No business rules found"}
          message={filter === "working_assumption" && !search ? "No setting is still on a working assumption." : "No setting matches this search."} />
      )}
      <ProposeModal setting={editing} onClose={() => setEditing(null)} onDone={load} />
    </Card>
  );
}
