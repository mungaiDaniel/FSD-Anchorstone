import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { partyService } from "@/services";
import type { ChangeRequest, PartyDetail } from "@/lib/types";
import { ID_TYPE_LABELS, ROUTES } from "@/lib/constants";

type Row = { field: string; current: string; proposed: string };

const LABELS: Record<string, string> = {
  salutation: "Salutation", first_name: "First name", middle_name: "Middle name", last_name: "Last name",
  gender: "Gender", date_of_birth: "Date of birth", nationality: "Nationality", marital_status: "Marital status",
  residency: "Residency", sector: "Sector", nature_of_business: "Nature of business", employer_name: "Employer",
  legal_name: "Registered name", registration_date: "Registration date", trading_name: "Trading name", org_type: "Type",
  full_name: "Name", id_number: "ID number", kra_pin: "KRA PIN", payout_method: "Paid by", bank_name: "Bank",
  payout_account: "Payout account", email: "Email", phone: "Phone",
};

const show = (v: unknown) => (v === null || v === undefined || v === "" ? "—" : String(v));

function listOf(items: unknown, fmt: (x: Record<string, unknown>) => string) {
  return Array.isArray(items) && items.length ? items.map((x) => fmt(x as Record<string, unknown>)).join("; ") : "—";
}

const identText = (i: Record<string, unknown>) => `${ID_TYPE_LABELS[i.id_type as keyof typeof ID_TYPE_LABELS] ?? i.id_type} ${show(i.value)}`;
const bankText = (b: Record<string, unknown>) =>
  `${b.kind === "mpesa" ? "M-Pesa" : show(b.bank_name)} ${show(b.account_no)}${b.is_default_payout ? " (payout)" : ""}`;
const contactText = (c: Record<string, unknown>) => `${show(c.value)}`;
const addressText = (a: Record<string, unknown>) => `${show(a.kind)}: ${[a.line1, a.town].filter(Boolean).join(", ")}`;

function rows(cr: ChangeRequest, p: PartyDetail): Row[] {
  const out: Row[] = [];
  const changes = cr.payload.changes as Record<string, unknown> | undefined;
  if (changes) {
    for (const [key, value] of Object.entries(changes)) {
      if (key === "groups") continue;
      const [part, field] = key.split(".") as [string, string | undefined];
      if (part === "person" && field) {
        out.push({ field: LABELS[field] ?? field, current: show(p.person?.[field as keyof typeof p.person]), proposed: show(value) });
      } else if (part === "organisation" && field) {
        out.push({ field: LABELS[field] ?? field, current: show(p.organisation?.[field as keyof typeof p.organisation]), proposed: show(value) });
      } else if (key === "identifiers") {
        out.push({ field: "Identifiers", current: listOf(p.identifiers, (i) => identText(i)), proposed: listOf(value, identText) });
      } else if (key === "bank_accounts") {
        out.push({ field: "Bank and payout", current: listOf(p.bank_accounts, (b) => bankText(b)), proposed: listOf(value, bankText) });
      } else if (part === "contacts" && field) {
        const kinds = field === "email" ? ["email"] : ["mobile", "phone"];
        out.push({ field: field === "email" ? "Email" : "Phone numbers",
          current: listOf(p.contacts.filter((c) => kinds.includes(c.kind)), (c) => contactText(c)), proposed: listOf(value, contactText) });
      } else if (key === "addresses") {
        out.push({ field: "Addresses", current: listOf(p.addresses, (a) => addressText(a)), proposed: listOf(value, addressText) });
      } else {
        out.push({ field: LABELS[key] ?? key, current: show(p[key as keyof PartyDetail]), proposed: show(value) });
      }
    }
  }
  const investor = cr.payload.investor_fields as Record<string, unknown> | undefined;
  if (investor) {
    const ident = (t: string) => p.identifiers.find((i) => i.id_type === t)?.value;
    const payout = p.bank_accounts.find((b) => b.is_default_payout);
    const current: Record<string, unknown> = {
      full_name: p.display_name, id_number: ident("national_id") ?? ident("passport") ?? ident("alien_id"),
      kra_pin: ident("kra_pin"), payout_method: payout?.kind, bank_name: payout?.bank_name, payout_account: payout?.account_no,
      email: p.contacts.find((c) => c.kind === "email")?.value, phone: p.contacts.find((c) => c.kind === "mobile")?.value,
    };
    for (const [key, value] of Object.entries(investor)) {
      out.push({ field: LABELS[key] ?? key, current: show(current[key]), proposed: show(value) });
    }
  }
  return out;
}

/** A party.change request shown as current → proposed, read against the client as it is now. */
export function PartyChangeDiff({ cr }: { cr: ChangeRequest }) {
  const [party, setParty] = useState<PartyDetail | null>(null);
  const partyId = Number(cr.entity_id);
  useEffect(() => {
    let live = true;
    partyService.get(partyId).then((p) => live && setParty(p)).catch(() => live && setParty(null));
    return () => { live = false; };
  }, [partyId]);
  if (!party) return <p className="tw:text-xs tw:text-text-tertiary">Loading the client…</p>;
  const applied = cr.status === "applied";
  return (
    <div className="mb-3">
      <p className="app-section-label mb-1">
        Changes to <Link to={ROUTES.CLIENT_DETAIL(party.id)}>{party.party_no} {party.display_name}</Link>
      </p>
      <table className="table table-sm mb-0" style={{ fontSize: 13 }}>
        <thead>
          <tr><th>Field</th><th>{applied ? "Now" : "Current"}</th><th>{applied ? "Requested" : "Proposed"}</th></tr>
        </thead>
        <tbody>
          {rows(cr, party).map((r) => (
            <tr key={r.field}>
              <td className="tw:text-text-tertiary">{r.field}</td>
              <td className="tw:break-words">{r.current}</td>
              <td className="tw:break-words tw:font-semibold tw:text-brand-400">{r.proposed}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
