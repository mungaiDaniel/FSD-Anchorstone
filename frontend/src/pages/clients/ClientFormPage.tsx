import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import { AlertTriangle, ChevronLeft, ShieldAlert } from "lucide-react";
import { Card, PageHeader } from "@/components/ui/Page";
import { partyService } from "@/services";
import type { DuplicateCheck, IdType, PartyDetail, PartyInput, PartyRoleName } from "@/lib/types";
import { ID_TYPE_LABELS, ORG_TYPE_LABELS, PARTY_ROLE_LABELS, ROUTES } from "@/lib/constants";
import { apiErrorMessage, todayISO } from "@/lib/utils";

// ── Schema: what staff must fill in before saving (the server re-checks everything) ──

const opt = z.string().trim().max(200).optional().or(z.literal(""));
const PERSON_ID_TYPES = ["national_id", "passport", "alien_id"] as const;
const ORG_TYPES = Object.keys(ORG_TYPE_LABELS) as [string, ...string[]];
const CREATE_ROLES: PartyRoleName[] = ["borrower", "guarantor", "agent"];

const schema = z.object({
  party_type: z.enum(["person", "organisation"]),
  classification: opt,
  risk_rating: z.enum(["", "low", "medium", "high"]),
  notes: z.string().max(2000).optional(),
  // individual
  salutation: opt, first_name: opt, middle_name: opt, last_name: opt,
  gender: z.enum(["", "male", "female", "other"]),
  date_of_birth: z.string().optional().refine((v) => !v || v <= todayISO(), "Date of birth can't be in the future."),
  marital_status: z.enum(["", "single", "married", "divorced", "widowed", "other"]),
  nationality: z.string().trim().length(2, "Two-letter country code").toUpperCase(),
  residency: z.enum(["local", "foreign"]),
  employer_name: opt,
  id_document_type: z.enum(PERSON_ID_TYPES),
  id_document_value: z.string().trim().max(50).optional(),
  // organisation
  legal_name: opt, trading_name: opt,
  org_type: z.enum(["", ...ORG_TYPES]),
  registration_date: z.string().optional().refine((v) => !v || v <= todayISO(), "Registration date can't be in the future."),
  company_reg_no: z.string().trim().max(50).optional(),
  // both
  sector: opt, nature_of_business: opt,
  kra_pin: z.string().trim().max(20).optional(),
  mobile: z.string().trim().max(30).optional(),
  phone: z.string().trim().max(30).optional(),
  email: z.string().trim().max(150).optional().refine((v) => !v || /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v), "Enter a valid email."),
  address_line1: opt, address_town: opt, address_county: opt,
  business_line1: opt, business_town: opt,
  payout_kind: z.enum(["", "mpesa", "bank"]),
  bank_name: opt, bank_branch: opt, account_no: z.string().trim().max(100).optional(), account_name: opt,
  roles: z.array(z.string()),
  is_pep: z.boolean(),
  pep_position: opt, pep_relationship: z.enum(["self", "family_member", "close_associate"]), pep_related_name: opt,
  pep_since: z.string().optional(), pep_source_of_funds: z.string().max(2000).optional(),
  pep_source_of_wealth: z.string().max(2000).optional(),
  reason: z.string().max(2000).optional(),
}).superRefine((v, ctx) => {
  const need = (field: keyof typeof v, message: string) => {
    if (!String(v[field] ?? "").trim()) ctx.addIssue({ code: z.ZodIssueCode.custom, path: [field], message });
  };
  if (v.party_type === "person") {
    if (!v.first_name?.trim() && !v.last_name?.trim()) need("last_name", "Enter at least a first or last name.");
  } else {
    need("legal_name", "Enter the registered name.");
    need("org_type", "Choose the organisation type.");
  }
  if (v.payout_kind) need("account_no", v.payout_kind === "mpesa" ? "Enter the M-Pesa number." : "Enter the account number.");
  if (v.payout_kind === "bank") need("bank_name", "Enter the bank.");
  if (v.is_pep) {
    need("pep_position", "Position held is required for a PEP.");
    need("pep_source_of_funds", "Source of funds is required for a PEP.");
    need("pep_source_of_wealth", "Source of wealth is required for a PEP.");
    if (v.pep_relationship !== "self") need("pep_related_name", "Name the PEP this client is related to.");
  }
});

type FormValues = z.infer<typeof schema>;

const EMPTY: FormValues = {
  party_type: "person", classification: "", risk_rating: "", notes: "", salutation: "", first_name: "", middle_name: "",
  last_name: "", gender: "", date_of_birth: "", marital_status: "", nationality: "KE", residency: "local",
  employer_name: "", id_document_type: "national_id", id_document_value: "", legal_name: "", trading_name: "",
  org_type: "", registration_date: "", company_reg_no: "", sector: "", nature_of_business: "", kra_pin: "", mobile: "",
  phone: "", email: "", address_line1: "", address_town: "", address_county: "", business_line1: "", business_town: "",
  payout_kind: "", bank_name: "", bank_branch: "", account_no: "", account_name: "", roles: [], is_pep: false,
  pep_position: "", pep_relationship: "self", pep_related_name: "", pep_since: "", pep_source_of_funds: "",
  pep_source_of_wealth: "", reason: "",
};

function fromParty(p: PartyDetail): FormValues {
  const ident = (t: IdType) => p.identifiers.find((i) => i.id_type === t)?.value ?? "";
  const doc = p.identifiers.find((i) => (PERSON_ID_TYPES as readonly string[]).includes(i.id_type));
  const contact = (k: string) => p.contacts.find((c) => c.kind === k && c.is_primary)?.value ?? p.contacts.find((c) => c.kind === k)?.value ?? "";
  const home = p.addresses.find((a) => a.kind === (p.party_type === "person" ? "home" : "registered"));
  const business = p.addresses.find((a) => a.kind === "business");
  const payout = p.bank_accounts.find((b) => b.is_default_payout);
  const s = (v: string | null | undefined) => v ?? "";
  return {
    ...EMPTY, party_type: p.party_type, classification: s(p.classification), risk_rating: p.risk_rating ?? "",
    notes: s(p.notes),
    salutation: s(p.person?.salutation), first_name: s(p.person?.first_name), middle_name: s(p.person?.middle_name),
    last_name: s(p.person?.last_name), gender: p.person?.gender ?? "", date_of_birth: s(p.person?.date_of_birth),
    marital_status: p.person?.marital_status ?? "", nationality: p.person?.nationality ?? "KE",
    residency: p.person?.residency ?? "local", employer_name: s(p.person?.employer_name),
    id_document_type: (doc?.id_type as FormValues["id_document_type"]) ?? "national_id", id_document_value: doc?.value ?? "",
    legal_name: s(p.organisation?.legal_name), trading_name: s(p.organisation?.trading_name),
    org_type: p.organisation?.org_type ?? "", registration_date: s(p.organisation?.registration_date),
    company_reg_no: ident("company_reg_no"),
    sector: s(p.person?.sector ?? p.organisation?.sector), nature_of_business: s(p.person?.nature_of_business ?? p.organisation?.nature_of_business),
    kra_pin: ident("kra_pin"), mobile: contact("mobile"), phone: contact("phone"), email: contact("email"),
    address_line1: s(home?.line1), address_town: s(home?.town), address_county: s(home?.county),
    business_line1: s(business?.line1), business_town: s(business?.town),
    payout_kind: payout?.kind ?? "", bank_name: s(payout?.bank_name), bank_branch: s(payout?.branch_name),
    account_no: s(payout?.account_no), account_name: s(payout?.account_name),
  };
}

/** Form values → the API body. On edit, details the form doesn't show (extra accounts, postal address…) are kept. */
function toInput(v: FormValues, existing: PartyDetail | null): PartyInput {
  const t = (x?: string | null) => (x ?? "").trim() || null;
  const person = v.party_type === "person";
  const identifiers: PartyInput["identifiers"] = [];
  if (person && t(v.id_document_value)) identifiers.push({ id_type: v.id_document_type, value: t(v.id_document_value)! });
  if (!person && t(v.company_reg_no)) identifiers.push({ id_type: "company_reg_no", value: t(v.company_reg_no)! });
  if (t(v.kra_pin)) identifiers.push({ id_type: "kra_pin", value: t(v.kra_pin)! });
  const shownKinds = ["mobile", "phone", "email"];
  const contacts: NonNullable<PartyInput["contacts"]> = [
    ...(existing?.contacts.filter((c) => !c.is_primary && shownKinds.includes(c.kind))
      .map((c) => ({ kind: c.kind, value: c.value })) ?? []),
  ];
  if (t(v.mobile)) contacts.unshift({ kind: "mobile", value: t(v.mobile)!, is_primary: true });
  if (t(v.phone)) contacts.unshift({ kind: "phone", value: t(v.phone)!, is_primary: true });
  if (t(v.email)) contacts.unshift({ kind: "email", value: t(v.email)!, is_primary: true });
  const mainKind = person ? "home" : "registered";
  const addresses: NonNullable<PartyInput["addresses"]> = [
    ...(existing?.addresses.filter((a) => a.kind !== mainKind && a.kind !== "business")
      .map(({ kind, line1, line2, town, county }) => ({ kind, line1, line2, town, county })) ?? []),
  ];
  if (t(v.address_line1)) addresses.push({ kind: mainKind, line1: t(v.address_line1)!, town: t(v.address_town), county: t(v.address_county) });
  if (t(v.business_line1)) addresses.push({ kind: "business", line1: t(v.business_line1)!, town: t(v.business_town) });
  const bank_accounts: NonNullable<PartyInput["bank_accounts"]> = [
    ...(existing?.bank_accounts.filter((b) => !b.is_default_payout)
      .map(({ kind, bank_name, branch_name, account_no, account_name }) => ({ kind, bank_name, branch_name, account_no, account_name })) ?? []),
  ];
  if (v.payout_kind && t(v.account_no)) {
    bank_accounts.push({ kind: v.payout_kind, bank_name: v.payout_kind === "bank" ? t(v.bank_name) : null,
      branch_name: v.payout_kind === "bank" ? t(v.bank_branch) : null, account_no: t(v.account_no)!,
      account_name: t(v.account_name), is_default_payout: true });
  }
  const body: PartyInput = {
    classification: t(v.classification), risk_rating: v.risk_rating || null, notes: t(v.notes),
    identifiers, contacts, addresses, bank_accounts,
  };
  if (person) {
    body.person = {
      salutation: t(v.salutation), first_name: t(v.first_name), middle_name: t(v.middle_name), last_name: t(v.last_name),
      gender: v.gender || null, date_of_birth: t(v.date_of_birth), marital_status: v.marital_status || null,
      nationality: v.nationality, residency: v.residency, sector: t(v.sector), nature_of_business: t(v.nature_of_business),
      employer_name: t(v.employer_name),
    };
  } else {
    body.organisation = {
      legal_name: t(v.legal_name) ?? "", trading_name: t(v.trading_name), org_type: (v.org_type || undefined) as never,
      registration_date: t(v.registration_date), sector: t(v.sector), nature_of_business: t(v.nature_of_business),
    };
  }
  if (!existing) {
    body.party_type = v.party_type;
    body.roles = v.roles as PartyRoleName[];
    if (v.is_pep) {
      body.pep = { is_pep: true, position_held: t(v.pep_position) ?? "", country: v.nationality,
        since: t(v.pep_since), pep_relationship: v.pep_relationship, related_pep_name: t(v.pep_related_name),
        source_of_funds: t(v.pep_source_of_funds) ?? "", source_of_wealth: t(v.pep_source_of_wealth) ?? "" };
    }
  } else if (t(v.reason)) {
    body.reason = t(v.reason)!;
  }
  return body;
}

// ── Layout helpers ──

function Section({ title, hint, children }: { title: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <Card title={title} className="mb-3">
      {hint && <p className="tw:text-xs tw:text-text-tertiary tw:-mt-2 mb-3">{hint}</p>}
      <div className="row g-3">{children}</div>
    </Card>
  );
}

function Input({ label, error, col = "col-md-6", children, hint }: {
  label: string; error?: string; col?: string; children: ReactNode; hint?: string;
}) {
  return (
    <div className={col}>
      <label className="form-label mb-1" style={{ fontSize: 12 }}>{label}</label>
      {children}
      {hint && !error && <div className="form-text" style={{ fontSize: 11 }}>{hint}</div>}
      {error && <div style={{ color: "var(--color-destructive)", fontSize: 11 }}>{error}</div>}
    </div>
  );
}

const CONTROLLED_HINT = "Changes here need a second person's approval before they apply.";

// ── Page ──

export default function ClientFormPage() {
  const params = useParams();
  const editId = params.id ? Number(params.id) : null;
  const navigate = useNavigate();
  const [existing, setExisting] = useState<PartyDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [dupes, setDupes] = useState<DuplicateCheck | null>(null);

  const { register, handleSubmit, reset, control, setValue, formState: { errors, isSubmitting } } = useForm<FormValues>({
    resolver: zodResolver(schema), defaultValues: EMPTY,
  });
  const v = useWatch({ control });

  useEffect(() => {
    if (editId === null) return;
    partyService.get(editId).then((p) => { setExisting(p); reset(fromParty(p)); })
      .catch((err) => setLoadError(apiErrorMessage(err)));
  }, [editId, reset]);

  // KYC-04/05 as you type: identifiers already on file (would be refused), phones and emails in use (warnings).
  const probe = useMemo(() => JSON.stringify([v.party_type, v.id_document_type, v.id_document_value, v.kra_pin,
    v.company_reg_no, v.mobile, v.phone, v.email]), [v]);
  useEffect(() => {
    const values = { ...EMPTY, ...v } as FormValues;
    const body = toInput(values, null);
    if (!body.identifiers?.length && !body.contacts?.length) { setDupes(null); return; }
    let live = true;
    const t = window.setTimeout(() => {
      partyService.checkDuplicates({ party_type: values.party_type, identifiers: body.identifiers, contacts: body.contacts,
        exclude_party_id: editId ?? undefined })
        .then((d) => live && setDupes(d)).catch(() => live && setDupes(null));
    }, 400);
    return () => { live = false; window.clearTimeout(t); };
  }, [probe]); // eslint-disable-line react-hooks/exhaustive-deps

  const onSubmit = async (values: FormValues) => {
    try {
      if (existing) {
        const res = await partyService.update(existing.id, toInput(values, existing));
        const cr = res.data?.change_request;
        if (cr) toast.info(res.message, { duration: 8000 }); else toast.success(res.message);
        navigate(ROUTES.CLIENT_DETAIL(existing.id));
      } else {
        const res = await partyService.create(toInput(values, null));
        toast.success(res.message);
        for (const w of res.data?.warnings ?? []) toast.warning(w.message, { duration: 8000 });
        navigate(ROUTES.CLIENT_DETAIL(res.data!.id));
      }
    } catch (err) {
      toast.error(apiErrorMessage(err));
    }
  };

  if (loadError) return <div className="app-page"><div className="alert alert-danger">{loadError}</div></div>;
  if (editId !== null && !existing) return <div className="app-page tw:text-text-tertiary">Loading…</div>;

  const person = v.party_type === "person";
  const err = (k: keyof FormValues) => errors[k]?.message as string | undefined;
  const editing = existing !== null;

  return (
    <div className="app-page">
      <Link to={editing ? ROUTES.CLIENT_DETAIL(existing.id) : ROUTES.CLIENTS}
        className="d-inline-flex align-items-center gap-1 mb-2 text-decoration-none" style={{ fontSize: 12, color: "var(--color-text-tertiary)" }}>
        <ChevronLeft size={14} /> {editing ? existing.display_name : "Clients"}
      </Link>
      <PageHeader
        title={editing ? `Edit ${existing.party_no}` : "New client"}
        subtitle={editing
          ? "Contact details save at once. Identity, bank and payout changes go to a second person for approval."
          : "Capture the client's KYC details. ID numbers, passports, KRA PINs and registration numbers can belong to one client only."}
      />

      <form onSubmit={handleSubmit(onSubmit)} noValidate className="row g-3">
        <div className="col-xl-8">
          {!editing && (
            <Card className="mb-3">
              <div role="radiogroup" aria-label="Client type" className="d-flex gap-2">
                {(["person", "organisation"] as const).map((t) => (
                  <label key={t} className={`btn btn-sm ${v.party_type === t ? "btn-primary" : "btn-outline-secondary"}`}>
                    <input type="radio" value={t} className="visually-hidden" {...register("party_type")} />
                    {t === "person" ? "Individual" : "Organisation"}
                  </label>
                ))}
              </div>
            </Card>
          )}

          {person ? (
            <Section title="Individual" hint={editing ? CONTROLLED_HINT + " (names, gender, date of birth, nationality)" : undefined}>
              <Input label="Salutation" col="col-md-2"><input className="form-control" {...register("salutation")} /></Input>
              <Input label="First name" col="col-md-4" error={err("first_name")}><input className="form-control" {...register("first_name")} /></Input>
              <Input label="Middle name" col="col-md-3"><input className="form-control" {...register("middle_name")} /></Input>
              <Input label="Last name" col="col-md-3" error={err("last_name")}><input className="form-control" {...register("last_name")} /></Input>
              <Input label="Gender" col="col-md-3">
                <select className="form-select" {...register("gender")}>
                  <option value="">—</option><option value="female">Female</option><option value="male">Male</option><option value="other">Other</option>
                </select>
              </Input>
              <Input label="Date of birth" col="col-md-3" error={err("date_of_birth")}>
                <input type="date" className="form-control" max={todayISO()} {...register("date_of_birth")} />
              </Input>
              <Input label="Marital status" col="col-md-3">
                <select className="form-select" {...register("marital_status")}>
                  <option value="">—</option>
                  {["single", "married", "divorced", "widowed", "other"].map((m) => <option key={m} value={m}>{m.charAt(0).toUpperCase() + m.slice(1)}</option>)}
                </select>
              </Input>
              <Input label="Nationality" col="col-md-3" error={err("nationality")} hint="Two-letter code, e.g. KE">
                <input className="form-control text-uppercase" maxLength={2} {...register("nationality")} />
              </Input>
              <Input label="Residency" col="col-md-3">
                <select className="form-select" {...register("residency")}><option value="local">Local</option><option value="foreign">Foreign</option></select>
              </Input>
              <Input label="Employer" col="col-md-5"><input className="form-control" {...register("employer_name")} /></Input>
            </Section>
          ) : (
            <Section title="Organisation" hint={editing ? CONTROLLED_HINT + " (registered name, registration date)" : undefined}>
              <Input label="Registered name (as per certificate)" col="col-md-7" error={err("legal_name")}>
                <input className="form-control" {...register("legal_name")} />
              </Input>
              <Input label="Trading name" col="col-md-5"><input className="form-control" {...register("trading_name")} /></Input>
              <Input label="Type" col="col-md-4" error={err("org_type")}>
                <select className="form-select" {...register("org_type")}>
                  <option value="">Choose…</option>
                  {Object.entries(ORG_TYPE_LABELS).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
                </select>
              </Input>
              <Input label="Date of registration" col="col-md-4" error={err("registration_date")}>
                <input type="date" className="form-control" max={todayISO()} {...register("registration_date")} />
              </Input>
            </Section>
          )}

          <Section title="Identification" hint={editing ? CONTROLLED_HINT : "Checked against every client, in every branch."}>
            {person ? (
              <>
                <Input label="Document" col="col-md-4">
                  <select className="form-select" {...register("id_document_type")}>
                    {PERSON_ID_TYPES.map((t) => <option key={t} value={t}>{ID_TYPE_LABELS[t]}</option>)}
                  </select>
                </Input>
                <Input label="Number" col="col-md-4"><input className="form-control font-tabular" {...register("id_document_value")} /></Input>
              </>
            ) : (
              <Input label="Registration number" col="col-md-4"><input className="form-control font-tabular" {...register("company_reg_no")} /></Input>
            )}
            <Input label="KRA PIN" col="col-md-4">
              <input className="form-control font-tabular text-uppercase" {...register("kra_pin", {
                onChange: (e) => setValue("kra_pin", e.target.value.toUpperCase()) })} />
            </Input>
          </Section>

          <Section title="Contact and address">
            <Input label="Mobile" col="col-md-4"><input className="form-control font-tabular" inputMode="tel" {...register("mobile")} /></Input>
            <Input label="Other phone" col="col-md-4"><input className="form-control font-tabular" inputMode="tel" {...register("phone")} /></Input>
            <Input label="Email" col="col-md-4" error={err("email")}><input type="email" className="form-control" {...register("email")} /></Input>
            <Input label={person ? "Home address" : "Registered address"} col="col-md-6">
              <input className="form-control" {...register("address_line1")} />
            </Input>
            <Input label="Town" col="col-md-3"><input className="form-control" {...register("address_town")} /></Input>
            <Input label="County" col="col-md-3"><input className="form-control" {...register("address_county")} /></Input>
            <Input label="Business address" col="col-md-6"><input className="form-control" {...register("business_line1")} /></Input>
            <Input label="Town" col="col-md-3"><input className="form-control" {...register("business_town")} /></Input>
          </Section>

          <Section title="Business and classification">
            <Input label="Industry / sector" col="col-md-4"><input className="form-control" {...register("sector")} /></Input>
            <Input label="Nature of business" col="col-md-8"><input className="form-control" {...register("nature_of_business")} /></Input>
            <Input label="Classification" col="col-md-4" hint={person ? "e.g. retail, HNI, civil servant" : "e.g. SME small, corporate"}>
              <input className="form-control" {...register("classification")} />
            </Input>
            <Input label="Risk rating" col="col-md-4">
              <select className="form-select" {...register("risk_rating")}>
                <option value="">Not rated</option><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option>
              </select>
            </Input>
          </Section>

          <Section title="Payout account" hint={editing ? CONTROLLED_HINT : "Where interest and withdrawals are paid."}>
            <Input label="Paid by" col="col-md-4">
              <select className="form-select" {...register("payout_kind")}>
                <option value="">Not set</option><option value="mpesa">M-Pesa</option><option value="bank">Bank transfer</option>
              </select>
            </Input>
            {v.payout_kind === "bank" && (
              <>
                <Input label="Bank" col="col-md-4" error={err("bank_name")}><input className="form-control" {...register("bank_name")} /></Input>
                <Input label="Bank branch" col="col-md-4"><input className="form-control" {...register("bank_branch")} /></Input>
              </>
            )}
            {v.payout_kind && (
              <>
                <Input label={v.payout_kind === "mpesa" ? "M-Pesa number" : "Account number"} col="col-md-4" error={err("account_no")}>
                  <input className="form-control font-tabular" {...register("account_no")} />
                </Input>
                <Input label="Account name" col="col-md-4"><input className="form-control" {...register("account_name")} /></Input>
              </>
            )}
          </Section>

          {!editing && (
            <Section title="Roles and PEP" hint="Investor accounts, directors, next of kin and guarantors are added from the client view once saved.">
              <div className="col-12 d-flex flex-wrap gap-3">
                {CREATE_ROLES.map((r) => (
                  <label key={r} className="form-check d-flex align-items-center gap-2 mb-0">
                    <input type="checkbox" className="form-check-input mt-0" value={r} {...register("roles")} />
                    <span className="form-check-label" style={{ fontSize: 13.5 }}>{PARTY_ROLE_LABELS[r]}</span>
                  </label>
                ))}
              </div>
              <div className="col-12">
                <label className="form-check d-flex align-items-center gap-2 mb-0">
                  <input type="checkbox" className="form-check-input mt-0" {...register("is_pep")} />
                  <span className="form-check-label" style={{ fontSize: 13.5 }}>Politically exposed person (PEP)</span>
                </label>
              </div>
              {v.is_pep && (
                <>
                  <div className="col-12 tw:text-xs tw:text-text-tertiary d-flex align-items-center gap-1">
                    <ShieldAlert size={13} /> Two senior approvers must approve these details before KYC can be verified.
                  </div>
                  <Input label="Position held" col="col-md-6" error={err("pep_position")}><input className="form-control" {...register("pep_position")} /></Input>
                  <Input label="Since" col="col-md-3"><input type="date" className="form-control" {...register("pep_since")} /></Input>
                  <Input label="PEP is" col="col-md-3">
                    <select className="form-select" {...register("pep_relationship")}>
                      <option value="self">The client</option><option value="family_member">A family member</option>
                      <option value="close_associate">A close associate</option>
                    </select>
                  </Input>
                  {v.pep_relationship !== "self" && (
                    <Input label="Name of the PEP" col="col-md-6" error={err("pep_related_name")}><input className="form-control" {...register("pep_related_name")} /></Input>
                  )}
                  <Input label="Source of funds" col="col-md-6" error={err("pep_source_of_funds")}>
                    <textarea className="form-control" rows={2} {...register("pep_source_of_funds")} />
                  </Input>
                  <Input label="Source of wealth" col="col-md-6" error={err("pep_source_of_wealth")}>
                    <textarea className="form-control" rows={2} {...register("pep_source_of_wealth")} />
                  </Input>
                </>
              )}
            </Section>
          )}

          <Section title="Notes">
            <div className="col-12"><textarea className="form-control" rows={2} {...register("notes")} /></div>
            {editing && (
              <Input label="Reason for identity, bank or payout changes" col="col-12" hint="Shown to the approver.">
                <input className="form-control" {...register("reason")} />
              </Input>
            )}
          </Section>
        </div>

        <div className="col-xl-4">
          <div className="tw:sticky tw:top-4">
            <Card title="Duplicate check" className="mb-3">
              {!dupes && <p className="tw:text-xs tw:text-text-tertiary mb-0">Enter an ID, PIN, phone or email to check it against every client.</p>}
              {dupes && dupes.conflicts.length === 0 && dupes.warnings.length === 0 && (
                <p className="tw:text-xs tw:text-success mb-0">No other client uses these details.</p>
              )}
              {dupes?.conflicts.map((c) => (
                <div key={c.id_type} className="alert alert-danger py-2 d-flex gap-2" style={{ fontSize: 12.5 }}>
                  <ShieldAlert size={15} className="flex-shrink-0 mt-1" />
                  <div>
                    {c.message} It can't be saved twice.
                    {c.party && <> <Link to={ROUTES.CLIENT_DETAIL(c.party.id)}>Open {c.party.party_no}</Link></>}
                  </div>
                </div>
              ))}
              {dupes?.warnings.map((w) => (
                <div key={`${w.kind}-${w.party.id}`} className="alert alert-warning py-2 d-flex gap-2" style={{ fontSize: 12.5 }}>
                  <AlertTriangle size={15} className="flex-shrink-0 mt-1" />
                  <div>{w.message} <Link to={ROUTES.CLIENT_DETAIL(w.party.id)}>Open</Link></div>
                </div>
              ))}
            </Card>
            <div className="d-flex gap-2">
              <button type="submit" className="btn btn-primary" disabled={isSubmitting || (dupes?.conflicts.length ?? 0) > 0}>
                {isSubmitting ? "Saving…" : editing ? "Save changes" : "Create client"}
              </button>
              <Link to={editing ? ROUTES.CLIENT_DETAIL(existing.id) : ROUTES.CLIENTS} className="btn btn-outline-secondary">Cancel</Link>
            </div>
          </div>
        </div>
      </form>
    </div>
  );
}
