import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Card, Field, PageHeader } from "@/components/ui/Page";
import { ClientSearch, EstimateNote } from "@/components/applications/ApplicationBits";
import { applicationService } from "@/services";
import type { Estimate, PartyListItem, ProductCode } from "@/lib/types";
import { PRODUCT_LABELS, ROUTES } from "@/lib/constants";
import { apiErrorMessage, formatKES, todayISO } from "@/lib/utils";

const TERMS: Record<ProductCode, [number, number]> = { business_loan: [3, 24], bridge_loan: [1, 3], asset_finance: [6, 36] };

export default function ApplicationFormPage() {
  const navigate = useNavigate();
  const [client, setClient] = useState<PartyListItem | null>(null);
  const [product, setProduct] = useState<ProductCode>("business_loan");
  const [amount, setAmount] = useState("");
  const [term, setTerm] = useState("12");
  const [rate, setRate] = useState("");
  const [started, setStarted] = useState("");
  const [estimate, setEstimate] = useState<Estimate | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [lo, hi] = TERMS[product];

  useEffect(() => {
    setEstimate(null);
    const n = Number(term);
    if (!amount || !rate || !Number.isInteger(n) || n < lo || n > hi) return;
    const t = window.setTimeout(() => {
      applicationService.estimate({ product_code: product, amount_requested: amount, term_months: n,
        indicative_rate_percent: rate }).then(setEstimate).catch(() => setEstimate(null));
    }, 300);
    return () => window.clearTimeout(t);
  }, [product, amount, term, rate, lo, hi]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!client) return setError("Choose the client applying.");
    setSaving(true);
    setError(null);
    try {
      const res = await applicationService.create({ party_id: client.id, product_code: product, amount_requested: amount,
        term_months: Number(term), indicative_rate_percent: rate, business_start_date: started || undefined });
      toast.success(`Application ${res.data!.application_no} created.`);
      navigate(ROUTES.APPLICATION_DETAIL(res.data!.id));
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="app-page">
      <PageHeader title="New pre-screen application"
        subtitle="A short-lived pre-screen record for AI document reading and the pre-selection rules. Phase 5's product engine replaces it." />
      <form onSubmit={submit} className="row g-3">
        <div className="col-lg-7">
          <Card title="Application">
            {error && <div className="alert alert-danger py-2" style={{ fontSize: 13 }}>{error}</div>}
            <Field label="Client"><ClientSearch value={client} onChange={setClient} /></Field>
            <Field label="Product" hint="WA-04 starting products. All reducing balance.">
              <select className="form-select" value={product} onChange={(e) => setProduct(e.target.value as ProductCode)}>
                {(Object.keys(TERMS) as ProductCode[]).map((p) => <option key={p} value={p}>{PRODUCT_LABELS[p]}</option>)}
              </select>
            </Field>
            <div className="row g-3">
              <div className="col-sm-6">
                <Field label="Amount requested (KES)">
                  <input className="form-control font-tabular" inputMode="decimal" value={amount} required
                    onChange={(e) => setAmount(e.target.value)} placeholder="500,000.00" />
                </Field>
              </div>
              <div className="col-sm-3">
                <Field label="Term (months)" hint={`${lo} to ${hi}`}>
                  <input className="form-control" type="number" min={lo} max={hi} value={term} required
                    onChange={(e) => setTerm(e.target.value)} />
                </Field>
              </div>
              <div className="col-sm-3">
                <Field label="Indicative rate (% p.a.)">
                  <input className="form-control" inputMode="decimal" value={rate} required onChange={(e) => setRate(e.target.value)} />
                </Field>
              </div>
            </div>
            <Field label="Business started (optional)" hint="Used for time in business when there is no registration date.">
              <input className="form-control tw:max-w-[220px]" type="date" max={todayISO()} value={started}
                onChange={(e) => setStarted(e.target.value)} />
            </Field>
            <div className="d-flex justify-content-end gap-2">
              <button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => navigate(ROUTES.APPLICATIONS)}>Cancel</button>
              <button type="submit" className="btn btn-primary btn-sm" disabled={saving}>{saving ? "Creating…" : "Create application"}</button>
            </div>
          </Card>
        </div>
        <div className="col-lg-5">
          <Card title="Estimated instalment">
            {estimate ? (
              <>
                <p className="tw:text-[26px] tw:font-semibold font-tabular mb-1">
                  {formatKES(estimate.estimated_instalment)} <span className="tw:text-[14px] tw:text-text-tertiary">a month (estimate)</span>
                </p>
                {estimate.repayment === "interest_only" && (
                  <p className="tw:text-[13px] tw:text-text-secondary mb-2">
                    Interest only; {formatKES(estimate.estimated_final_payment)} due at maturity (principal and last interest).
                  </p>
                )}
              </>
            ) : <p className="tw:text-text-tertiary tw:text-[13px]">Enter the amount, term and rate to see an estimate.</p>}
            <EstimateNote />
          </Card>
        </div>
      </form>
    </div>
  );
}
