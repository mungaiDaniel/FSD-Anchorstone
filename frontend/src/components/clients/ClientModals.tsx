import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Modal } from "@/components/ui/Modal";
import { Field } from "@/components/ui/Page";
import { partyService, screeningService } from "@/services";
import type {
  ConsentMethod,
  ConsentPurpose,
  PartyDetail,
  PartyDocument,
  PartyListItem,
  PepInput,
  RelationshipKind,
  ScreeningResult,
} from "@/lib/types";
import {
  CONSENT_METHOD_LABELS,
  CONSENT_PURPOSE_LABELS,
  DOCUMENT_TYPE_LABELS,
  RELATIONSHIP_LABELS,
  WATCHLIST_LABELS,
} from "@/lib/constants";
import { apiErrorMessage, todayISO } from "@/lib/utils";

type Done = () => void;

function useSubmit(onDone: Done, onClose: () => void) {
  const [saving, setSaving] = useState(false);
  const run = async (call: () => Promise<{ message: string }>) => {
    setSaving(true);
    try {
      const res = await call();
      toast.success(res.message);
      onDone();
      onClose();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };
  return { saving, run };
}

// ── Related party (KYC-02 directors and signatories, KYC-03 next of kin and guarantors, KYC-05 links) ──

const ORG_ONLY: RelationshipKind[] = ["director", "shareholder"];

export function RelatedPartyModal({ party, open, onClose, onDone }: { party: PartyDetail; open: boolean; onClose: () => void; onDone: Done }) {
  const kinds = (Object.keys(RELATIONSHIP_LABELS) as RelationshipKind[])
    .filter((k) => party.party_type === "organisation" || !ORG_ONLY.includes(k));
  const [kind, setKind] = useState<RelationshipKind>(party.party_type === "organisation" ? "director" : "next_of_kin");
  const [mode, setMode] = useState<"new" | "existing">("new");
  const [search, setSearch] = useState("");
  const [matches, setMatches] = useState<PartyListItem[]>([]);
  const [picked, setPicked] = useState<PartyListItem | null>(null);
  const [first, setFirst] = useState("");
  const [last, setLast] = useState("");
  const [idNo, setIdNo] = useState("");
  const [phone, setPhone] = useState("");
  const [kin, setKin] = useState("");
  const [share, setShare] = useState("");
  const [list, setList] = useState<"" | "A" | "B">("");
  const [amount, setAmount] = useState("");
  const { saving, run } = useSubmit(onDone, onClose);

  useEffect(() => {
    if (mode !== "existing" || search.trim().length < 2) { setMatches([]); return; }
    const t = window.setTimeout(() => {
      partyService.list({ search: search.trim(), per_page: 8 })
        .then((d) => setMatches(d.items.filter((p) => p.id !== party.id))).catch(() => setMatches([]));
    }, 250);
    return () => window.clearTimeout(t);
  }, [mode, search, party.id]);

  const ready = (mode === "existing" ? !!picked : !!(first.trim() || last.trim()))
    && (kind !== "guarantor_of" || Number(amount.replace(/,/g, "")) > 0);

  const submit = () => run(() => partyService.addRelationship(party.id, {
    relationship: kind,
    ...(mode === "existing" ? { related_party_id: picked!.id } : {
      related: {
        party_type: "person", person: { first_name: first.trim() || null, last_name: last.trim() || null },
        identifiers: idNo.trim() ? [{ id_type: "national_id", value: idNo.trim() }] : [],
        contacts: phone.trim() ? [{ kind: "mobile", value: phone.trim() }] : [],
      },
    }),
    ...(kind === "next_of_kin" && kin.trim() ? { kin_relationship: kin.trim() } : {}),
    ...(kind === "shareholder" && share.trim() ? { share_pct: share.trim() } : {}),
    ...(kind === "signatory" && list ? { signatory_list: list } : {}),
    ...(kind === "guarantor_of" ? { committed_amount: amount.trim() } : {}),
  }));

  return (
    <Modal title="Add related party" open={open} onClose={onClose} onSubmit={submit} submitting={saving}
      submitLabel="Add" submitDisabled={!ready}>
      <Field label="Relationship to this client">
        <select className="form-select mt-1" value={kind} onChange={(e) => setKind(e.target.value as RelationshipKind)}>
          {kinds.map((k) => <option key={k} value={k}>{RELATIONSHIP_LABELS[k].incoming}</option>)}
        </select>
      </Field>
      <div className="btn-group btn-group-sm mb-3" role="group">
        <button type="button" className={`btn ${mode === "new" ? "btn-primary" : "btn-outline-secondary"}`} onClick={() => setMode("new")}>New person</button>
        <button type="button" className={`btn ${mode === "existing" ? "btn-primary" : "btn-outline-secondary"}`} onClick={() => setMode("existing")}>Existing client</button>
      </div>
      {mode === "existing" ? (
        <Field label="Find the client" hint="A person already on file is linked, never captured twice.">
          <input className="form-control mt-1" value={search} placeholder="Name, client no., ID or phone"
            onChange={(e) => { setSearch(e.target.value); setPicked(null); }} />
          {matches.length > 0 && !picked && (
            <div className="list-group mt-1">
              {matches.map((m) => (
                <button type="button" key={m.id} className="list-group-item list-group-item-action py-1" style={{ fontSize: 13 }}
                  onClick={() => { setPicked(m); setSearch(`${m.display_name} (${m.party_no})`); }}>
                  {m.display_name} <span className="tw:text-text-tertiary font-tabular">{m.party_no}</span>
                </button>
              ))}
            </div>
          )}
        </Field>
      ) : (
        <div className="row g-2">
          <div className="col-6"><Field label="First name"><input className="form-control mt-1" value={first} onChange={(e) => setFirst(e.target.value)} /></Field></div>
          <div className="col-6"><Field label="Last name"><input className="form-control mt-1" value={last} onChange={(e) => setLast(e.target.value)} /></Field></div>
          <div className="col-6"><Field label="ID number" hint="Optional for next of kin"><input className="form-control mt-1 font-tabular" value={idNo} onChange={(e) => setIdNo(e.target.value)} /></Field></div>
          <div className="col-6"><Field label="Mobile"><input className="form-control mt-1 font-tabular" value={phone} onChange={(e) => setPhone(e.target.value)} /></Field></div>
        </div>
      )}
      {kind === "next_of_kin" && (
        <Field label="Relationship" hint="e.g. spouse, parent, sibling"><input className="form-control mt-1" value={kin} onChange={(e) => setKin(e.target.value)} /></Field>
      )}
      {kind === "shareholder" && (
        <Field label="Shareholding (%)"><input className="form-control mt-1 font-tabular" inputMode="decimal" value={share} onChange={(e) => setShare(e.target.value)} /></Field>
      )}
      {kind === "signatory" && (
        <Field label="Signatory list" hint="For an 'A and B' signing rule">
          <select className="form-select mt-1" value={list} onChange={(e) => setList(e.target.value as "" | "A" | "B")}>
            <option value="">—</option><option value="A">List A</option><option value="B">List B</option>
          </select>
        </Field>
      )}
      {kind === "guarantor_of" && (
        <Field label="Amount guaranteed (KES)"><input className="form-control mt-1 font-tabular" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} /></Field>
      )}
    </Modal>
  );
}

// ── Signing rule ──

export function MandateModal({ party, open, onClose, onDone }: { party: PartyDetail; open: boolean; onClose: () => void; onDone: Done }) {
  const [rule, setRule] = useState(party.mandate?.rule ?? "any_one");
  const [description, setDescription] = useState(party.mandate?.description ?? "");
  const { saving, run } = useSubmit(onDone, onClose);
  return (
    <Modal title="Signing rule" open={open} onClose={onClose} submitting={saving} submitLabel="Save"
      submitDisabled={rule === "custom" && !description.trim()}
      onSubmit={() => run(() => partyService.setMandate(party.id, rule, description.trim() || undefined))}>
      <Field label="Who may sign">
        <select className="form-select mt-1" value={rule} onChange={(e) => setRule(e.target.value as typeof rule)}>
          <option value="any_one">Any one signatory</option><option value="all">All signatories</option>
          <option value="a_and_b">One from list A and one from list B</option><option value="custom">Other (describe)</option>
        </select>
      </Field>
      <Field label="Details"><textarea className="form-control mt-1" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
    </Modal>
  );
}

// ── Documents ──

export function UploadDocumentModal({ partyId, open, onClose, onDone }: { partyId: number; open: boolean; onClose: () => void; onDone: Done }) {
  const [type, setType] = useState("national_id");
  const [file, setFile] = useState<File | null>(null);
  const { saving, run } = useSubmit(onDone, onClose);
  useEffect(() => { if (open) setFile(null); }, [open]);
  return (
    <Modal title="Upload document" open={open} onClose={onClose} submitting={saving} submitLabel="Upload" submitDisabled={!file}
      onSubmit={() => run(() => partyService.uploadDocument(partyId, file!, type))}>
      <Field label="Document">
        <select className="form-select mt-1" value={type} onChange={(e) => setType(e.target.value)}>
          {Object.entries(DOCUMENT_TYPE_LABELS).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
        </select>
      </Field>
      <Field label="File" hint="PDF, JPEG, PNG, HEIC or TIFF. Stored encrypted; every view is logged.">
        <input type="file" className="form-control mt-1" accept=".pdf,.jpg,.jpeg,.png,.heic,.tif,.tiff"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </Field>
      <p className="tw:text-xs tw:text-text-tertiary mb-0">A newer upload of the same type is shown first; the older file is kept.</p>
    </Modal>
  );
}

// ── Consent ──

export function ConsentModal({ partyId, documents, open, onClose, onDone }: {
  partyId: number; documents: PartyDocument[]; open: boolean; onClose: () => void; onDone: Done;
}) {
  const [purpose, setPurpose] = useState<ConsentPurpose>("kyc_processing");
  const [method, setMethod] = useState<ConsentMethod>("in_branch");
  const [date, setDate] = useState(todayISO());
  const [evidence, setEvidence] = useState("");
  const { saving, run } = useSubmit(onDone, onClose);
  const forms = documents.filter((d) => d.status === "active" && d.document_type === "consent_form");
  return (
    <Modal title="Record consent" open={open} onClose={onClose} submitting={saving} submitLabel="Record"
      submitDisabled={method === "signed_form" && !evidence}
      onSubmit={() => run(() => partyService.recordConsent(partyId, { purpose, method, granted_on: date,
        evidence_document_id: evidence || undefined }))}>
      <Field label="Purpose">
        <select className="form-select mt-1" value={purpose} onChange={(e) => setPurpose(e.target.value as ConsentPurpose)}>
          {Object.entries(CONSENT_PURPOSE_LABELS).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
        </select>
      </Field>
      <div className="row g-2">
        <div className="col-6">
          <Field label="How it was given">
            <select className="form-select mt-1" value={method} onChange={(e) => setMethod(e.target.value as ConsentMethod)}>
              {Object.entries(CONSENT_METHOD_LABELS).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
            </select>
          </Field>
        </div>
        <div className="col-6">
          <Field label="Date given"><input type="date" className="form-control mt-1" max={todayISO()} value={date} onChange={(e) => setDate(e.target.value)} /></Field>
        </div>
      </div>
      <Field label="Signed form" hint={forms.length === 0 ? "Upload the signed consent form first to record a signed-form consent." : "Required for a signed form."}>
        <select className="form-select mt-1" value={evidence} onChange={(e) => setEvidence(e.target.value)} disabled={forms.length === 0}>
          <option value="">None</option>
          {forms.map((d) => <option key={d.id} value={d.id}>{d.filename}</option>)}
        </select>
      </Field>
      <p className="tw:text-xs tw:text-text-tertiary mb-0">The privacy notice version in force is stored with the consent, and you are recorded as capturing it.</p>
    </Modal>
  );
}

// ── PEP (KYC-07) ──

export function PepModal({ party, open, onClose, onDone }: { party: PartyDetail; open: boolean; onClose: () => void; onDone: Done }) {
  const pep = party.pep;
  const [clear, setClear] = useState(false);
  const [v, setV] = useState<PepInput>({ is_pep: true });
  const { saving, run } = useSubmit(onDone, onClose);
  useEffect(() => {
    if (!open) return;
    setClear(false);
    setV({ is_pep: true, position_held: pep?.position_held ?? "", country: pep?.country ?? "KE", since: pep?.since ?? "",
      pep_relationship: pep?.pep_relationship ?? "self", related_pep_name: pep?.related_pep_name ?? "",
      source_of_funds: pep?.source_of_funds ?? "", source_of_wealth: pep?.source_of_wealth ?? "" });
  }, [open, pep]);
  const set = (k: keyof PepInput, value: string) => setV((cur) => ({ ...cur, [k]: value }));
  const ready = clear || (v.position_held?.trim() && v.source_of_funds?.trim() && v.source_of_wealth?.trim()
    && (v.pep_relationship === "self" || v.related_pep_name?.trim()));
  return (
    <Modal title="Politically exposed person" open={open} onClose={onClose} submitting={saving} wide
      submitLabel={clear ? "Ask to clear the PEP flag" : "Submit for senior approval"} submitDisabled={!ready}
      onSubmit={() => run(() => partyService.setPep(party.id, clear ? { is_pep: false, reason: v.reason } : { ...v, since: v.since || null }))}>
      {party.is_pep && (
        <label className="form-check d-flex align-items-center gap-2 mb-3">
          <input type="checkbox" className="form-check-input mt-0" checked={clear} onChange={(e) => setClear(e.target.checked)} />
          <span className="form-check-label" style={{ fontSize: 13.5 }}>This client is no longer a PEP</span>
        </label>
      )}
      {!clear && (
        <div className="row g-2">
          <div className="col-md-8"><Field label="Position held"><input className="form-control mt-1" value={v.position_held ?? ""} onChange={(e) => set("position_held", e.target.value)} /></Field></div>
          <div className="col-md-4"><Field label="Since"><input type="date" className="form-control mt-1" value={v.since ?? ""} onChange={(e) => set("since", e.target.value)} /></Field></div>
          <div className="col-md-4">
            <Field label="PEP is">
              <select className="form-select mt-1" value={v.pep_relationship} onChange={(e) => set("pep_relationship", e.target.value)}>
                <option value="self">The client</option><option value="family_member">A family member</option><option value="close_associate">A close associate</option>
              </select>
            </Field>
          </div>
          <div className="col-md-2"><Field label="Country"><input className="form-control mt-1 text-uppercase" maxLength={2} value={v.country ?? ""} onChange={(e) => set("country", e.target.value.toUpperCase())} /></Field></div>
          {v.pep_relationship !== "self" && (
            <div className="col-md-6"><Field label="Name of the PEP"><input className="form-control mt-1" value={v.related_pep_name ?? ""} onChange={(e) => set("related_pep_name", e.target.value)} /></Field></div>
          )}
          <div className="col-md-6"><Field label="Source of funds"><textarea className="form-control mt-1" rows={2} value={v.source_of_funds ?? ""} onChange={(e) => set("source_of_funds", e.target.value)} /></Field></div>
          <div className="col-md-6"><Field label="Source of wealth"><textarea className="form-control mt-1" rows={2} value={v.source_of_wealth ?? ""} onChange={(e) => set("source_of_wealth", e.target.value)} /></Field></div>
        </div>
      )}
      <Field label="Note for the approvers"><input className="form-control mt-1" value={v.reason ?? ""} onChange={(e) => set("reason", e.target.value)} /></Field>
      <p className="tw:text-xs tw:text-text-tertiary mb-0">Two senior approvers, neither of them you, must approve. KYC can't be verified until they do.</p>
    </Modal>
  );
}

// ── Screening review (KYC-06) ──

export function ScreeningReviewModal({ result, onClose, onDone }: { result: ScreeningResult | null; onClose: () => void; onDone: Done }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  useEffect(() => setNote(""), [result]);
  if (!result) return null;
  const decide = async (decision: "clear" | "confirmed") => {
    setBusy(decision);
    try {
      const res = await screeningService.review(result.id, decision, note.trim());
      toast.success(res.message);
      onDone();
      onClose();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setBusy(null);
    }
  };
  return (
    <Modal title="Review possible watchlist match" open onClose={() => !busy && onClose()}>
      <ul className="list-unstyled mb-3" style={{ fontSize: 13.5 }}>
        {result.matches.map((m) => (
          <li key={m.entry_id} className="mb-1">
            <strong>{m.name}</strong> on the {WATCHLIST_LABELS[m.list]} — matched on {m.matched_on.join(" and ")}
          </li>
        ))}
      </ul>
      <Field label="Note" hint="Required: why this is, or isn't, the same person.">
        <textarea className="form-control mt-1" rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>
      <p className="tw:text-xs tw:text-text-tertiary">Confirming a blacklist match blacklists the client; confirming a PEP-list match flags them as a PEP.
        The person who onboarded the client can't review it.</p>
      <div className="d-flex justify-content-end gap-2">
        <button className="btn btn-sm app-btn-ghost-danger" disabled={!!busy || !note.trim()} onClick={() => decide("confirmed")}>
          {busy === "confirmed" ? "Saving…" : "Confirm match"}
        </button>
        <button className="btn btn-sm btn-primary" disabled={!!busy || !note.trim()} onClick={() => decide("clear")}>
          {busy === "clear" ? "Saving…" : "Not the same person"}
        </button>
      </div>
    </Modal>
  );
}

// ── Investment account (investor role) ──

export function OpenInvestmentModal({ party, open, onClose, onDone }: { party: PartyDetail; open: boolean; onClose: () => void; onDone: Done }) {
  const primary = party.contacts.find((c) => c.kind === "email")?.value ?? "";
  const [email, setEmail] = useState(primary);
  const { saving, run } = useSubmit(onDone, onClose);
  useEffect(() => { if (open) setEmail(primary); }, [open, primary]);
  return (
    <Modal title="Open an investment account" open={open} onClose={onClose} submitting={saving} submitLabel="Open account"
      submitDisabled={!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim())}
      onSubmit={() => run(() => partyService.openInvestment(party.id, email.trim()))}>
      <p style={{ fontSize: 13.5 }}>{party.display_name} gets the next ACL- client code. Their name, ID, PIN and payout account come from this record.</p>
      <Field label="Statement email" hint="Statements and confirmations go here. One investor per email.">
        <input type="email" className="form-control mt-1" value={email} onChange={(e) => setEmail(e.target.value)} />
      </Field>
    </Modal>
  );
}

// ── Merge (KYC-10) and branch transfer (KYC-12) ──

export function MergeModal({ party, open, onClose, onDone }: { party: PartyDetail; open: boolean; onClose: () => void; onDone: Done }) {
  const [search, setSearch] = useState("");
  const [matches, setMatches] = useState<PartyListItem[]>([]);
  const [picked, setPicked] = useState<PartyListItem | null>(null);
  const [reason, setReason] = useState("");
  const { saving, run } = useSubmit(onDone, onClose);
  useEffect(() => { if (open) { setSearch(""); setPicked(null); setReason(""); } }, [open]);
  useEffect(() => {
    if (search.trim().length < 2 || picked) { setMatches([]); return; }
    const t = window.setTimeout(() => {
      partyService.list({ search: search.trim(), type: party.party_type, per_page: 8 })
        .then((d) => setMatches(d.items.filter((p) => p.id !== party.id))).catch(() => setMatches([]));
    }, 250);
    return () => window.clearTimeout(t);
  }, [search, picked, party.id, party.party_type]);
  return (
    <Modal title={`Merge ${party.party_no} into another record`} open={open} onClose={onClose} submitting={saving}
      submitVariant="danger" submitLabel="Submit merge for approval" submitDisabled={!picked || !reason.trim()}
      onSubmit={() => run(() => partyService.merge(party.id, picked!.id, reason.trim()))}>
      <p style={{ fontSize: 13.5 }}>
        Use this when {party.display_name} is a duplicate. Everything on this record (identifiers, contacts, accounts,
        documents, consents, links and history) moves to the record you keep; this one is marked merged and kept for the record.
      </p>
      <Field label="Keep this record" hint="Search by name, client number, ID or phone.">
        <input className="form-control mt-1" value={search} onChange={(e) => { setSearch(e.target.value); setPicked(null); }} />
        {matches.length > 0 && (
          <div className="list-group mt-1">
            {matches.map((m) => (
              <button type="button" key={m.id} className="list-group-item list-group-item-action py-1" style={{ fontSize: 13 }}
                onClick={() => { setPicked(m); setSearch(`${m.display_name} (${m.party_no})`); }}>
                {m.display_name} <span className="tw:text-text-tertiary font-tabular">{m.party_no}</span>
              </button>
            ))}
          </div>
        )}
      </Field>
      <Field label="Reason"><textarea className="form-control mt-1" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
      <p className="tw:text-xs tw:text-text-tertiary mb-0">Refused if both records hold an investment account or have different ID numbers.</p>
    </Modal>
  );
}

export function TransferModal({ party, open, onClose, onDone }: { party: PartyDetail; open: boolean; onClose: () => void; onDone: Done }) {
  const [branches, setBranches] = useState<{ id: number; code: string; name: string }[]>([]);
  const [to, setTo] = useState<number | "">("");
  const [reason, setReason] = useState("");
  const { saving, run } = useSubmit(onDone, onClose);
  useEffect(() => {
    if (!open) return;
    setTo("");
    setReason("");
    partyService.branches().then(setBranches).catch(() => setBranches([]));
  }, [open]);
  const others = branches.filter((b) => b.id !== party.home_branch_id);
  return (
    <Modal title="Transfer to another branch" open={open} onClose={onClose} submitting={saving}
      submitLabel="Submit for approval" submitDisabled={to === "" || !reason.trim()}
      onSubmit={() => run(() => partyService.transfer(party.id, Number(to), reason.trim()))}>
      <Field label="Move to" hint={others.length === 0 ? "There is no other active branch yet." : "The client, their accounts and investor record move. Numbers don't change."}>
        <select className="form-select mt-1" value={to} onChange={(e) => setTo(e.target.value ? Number(e.target.value) : "")} disabled={others.length === 0}>
          <option value="">Choose a branch…</option>
          {others.map((b) => <option key={b.id} value={b.id}>{b.code} {b.name}</option>)}
        </select>
      </Field>
      <Field label="Reason"><textarea className="form-control mt-1" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
    </Modal>
  );
}
