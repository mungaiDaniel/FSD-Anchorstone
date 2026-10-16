import { useState, type FormEvent } from "react";
import { Field } from "@/components/ui/Page";
import type { Investor, InvestorInput, PayoutMethod } from "@/lib/types";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

interface Props {
  initial?: Partial<Investor>;
  submitLabel: string;
  submitting: boolean;
  onSubmit: (data: InvestorInput) => void;
  onCancel: () => void;
}

export function InvestorForm({ initial, submitLabel, submitting, onSubmit, onCancel }: Props) {
  const [form, setForm] = useState<InvestorInput>({
    full_name: initial?.full_name ?? "",
    email: initial?.email ?? "",
    phone: initial?.phone ?? "",
    id_number: initial?.id_number ?? "",
    kra_pin: initial?.kra_pin ?? "",
    payout_method: initial?.payout_method ?? "mpesa",
    bank_name: initial?.bank_name ?? "",
    payout_account: initial?.payout_account ?? "",
    notes: initial?.notes ?? "",
  });
  const [touched, setTouched] = useState(false);

  const set = <K extends keyof InvestorInput>(key: K, value: InvestorInput[K]) => setForm((f) => ({ ...f, [key]: value }));
  const nameError = !form.full_name?.trim() ? "Full name is required." : undefined;
  const emailError = !EMAIL_RE.test(form.email?.trim() ?? "") ? "A valid email is required — statements are sent here." : undefined;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (nameError || emailError) return;
    onSubmit({
      ...form,
      payout_method: form.payout_method || null,
      bank_name: form.payout_method === "bank" ? form.bank_name : "",
    });
  };

  return (
    <form onSubmit={submit} noValidate>
      <h3 className="app-section-label">Personal details</h3>
      <div className="row g-2">
        <div className="col-md-6">
          <Field label="Full name" error={touched ? nameError : undefined}>
            <input className="form-control" value={form.full_name ?? ""} onChange={(e) => set("full_name", e.target.value)} maxLength={150} />
          </Field>
        </div>
        <div className="col-md-6">
          <Field label="Email" error={touched ? emailError : undefined}>
            <input type="email" className="form-control" value={form.email ?? ""} onChange={(e) => set("email", e.target.value)} maxLength={150} />
          </Field>
        </div>
        <div className="col-md-4">
          <Field label="Phone">
            <input className="form-control" value={form.phone ?? ""} onChange={(e) => set("phone", e.target.value)} maxLength={30} />
          </Field>
        </div>
        <div className="col-md-4">
          <Field label="National ID / passport no.">
            <input className="form-control" value={form.id_number ?? ""} onChange={(e) => set("id_number", e.target.value)} maxLength={50} />
          </Field>
        </div>
        <div className="col-md-4">
          <Field label="KRA PIN">
            <input className="form-control" value={form.kra_pin ?? ""} onChange={(e) => set("kra_pin", e.target.value.toUpperCase())} maxLength={20} />
          </Field>
        </div>
      </div>

      <h3 className="app-section-label mt-2">Where interest and withdrawals are paid</h3>
      <div className="row g-2">
        <div className="col-md-4">
          <Field label="Method">
            <select className="form-select" value={form.payout_method ?? ""} onChange={(e) => set("payout_method", (e.target.value || null) as PayoutMethod | null)}>
              <option value="mpesa">M-Pesa</option>
              <option value="bank">Bank account</option>
              <option value="">Not set</option>
            </select>
          </Field>
        </div>
        {form.payout_method === "bank" && (
          <div className="col-md-4">
            <Field label="Bank">
              <input className="form-control" value={form.bank_name ?? ""} onChange={(e) => set("bank_name", e.target.value)} maxLength={100} />
            </Field>
          </div>
        )}
        {form.payout_method && (
          <div className="col-md-4">
            <Field label={form.payout_method === "bank" ? "Account number" : "M-Pesa number"}>
              <input className="form-control" value={form.payout_account ?? ""} onChange={(e) => set("payout_account", e.target.value)} maxLength={100} />
            </Field>
          </div>
        )}
      </div>

      <Field label="Notes (internal)">
        <textarea className="form-control" rows={2} value={form.notes ?? ""} onChange={(e) => set("notes", e.target.value)} />
      </Field>

      <div className="d-flex gap-2 justify-content-end">
        <button type="button" className="btn btn-outline-secondary btn-sm" onClick={onCancel} disabled={submitting}>Cancel</button>
        <button type="submit" className="btn btn-primary btn-sm" disabled={submitting}>{submitting ? "Saving…" : submitLabel}</button>
      </div>
    </form>
  );
}
