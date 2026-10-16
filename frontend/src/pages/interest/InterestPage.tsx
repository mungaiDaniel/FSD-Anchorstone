import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Calculator, Percent } from "lucide-react";
import { Card, EmptyState, Field, PageHeader } from "@/components/ui/Page";
import { Modal } from "@/components/ui/Modal";
import { StatusBadge } from "@/components/data/StatusBadge";
import { interestService } from "@/services";
import { useAuth } from "@/context/AuthContext";
import type { InterestPeriod, RatesResponse } from "@/lib/types";
import { ROUTES } from "@/lib/constants";
import { apiErrorMessage, formatDate, formatDateTime, formatKES, formatRate, todayISO } from "@/lib/utils";

/** First day of the month after `iso` (YYYY-MM-DD) as YYYY-MM. */
function monthAfter(iso: string): string {
  const [y, m] = iso.split("-").map(Number) as [number, number];
  return m === 12 ? `${y + 1}-01` : `${y}-${String(m + 1).padStart(2, "0")}`;
}

function lastCompletedMonth(): string {
  const [y, m] = todayISO().split("-").map(Number) as [number, number];
  return m === 1 ? `${y - 1}-12` : `${y}-${String(m - 1).padStart(2, "0")}`;
}

export default function InterestPage() {
  const { isAdmin } = useAuth();
  const navigate = useNavigate();
  const [rates, setRates] = useState<RatesResponse | null>(null);
  const [periods, setPeriods] = useState<InterestPeriod[] | null>(null);
  const [lockedThrough, setLockedThrough] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [rateOpen, setRateOpen] = useState(false);
  const [ratePercent, setRatePercent] = useState("");
  const [effectiveFrom, setEffectiveFrom] = useState("");
  const [rateNote, setRateNote] = useState("");

  const [calcOpen, setCalcOpen] = useState(false);
  const [month, setMonth] = useState(lastCompletedMonth());
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    try {
      const [r, p] = await Promise.all([interestService.rates(), interestService.periods()]);
      setRates(r);
      setPeriods(p.items);
      setLockedThrough(p.locked_through);
      setError(null);
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const draft = periods?.find((p) => p.status === "draft");
  const suggestedMonth = lockedThrough ? monthAfter(lockedThrough) : lastCompletedMonth();

  const saveRate = async () => {
    setSubmitting(true);
    try {
      const res = await interestService.setRate(ratePercent.trim(), effectiveFrom, rateNote.trim() || undefined);
      toast.success(res.message);
      setRateOpen(false);
      load();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  const calculate = async () => {
    const [y, m] = month.split("-").map(Number) as [number, number];
    setSubmitting(true);
    try {
      const res = await interestService.calculate(y, m);
      toast.success(res.message);
      navigate(ROUTES.INTEREST_PERIOD(res.data!.id));
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  const rateValid = /^\d{1,3}(\.\d{1,4})?$/.test(ratePercent.trim()) && Number(ratePercent) <= 100;

  return (
    <div className="app-page">
      <PageHeader
        title="Interest"
        subtitle="One flat annual rate for every investor. Simple interest on each day's closing balance (365-day year), calculated monthly and paid out."
        actions={
          isAdmin && (
            <button className="btn btn-primary btn-sm d-flex align-items-center gap-1" disabled={!!draft}
              title={draft ? `Finish the ${draft.label} draft first` : undefined}
              onClick={() => { setMonth(suggestedMonth); setCalcOpen(true); }}>
              <Calculator size={14} /> Calculate a month
            </button>
          )
        }
      />
      {error && <div className="alert alert-danger py-2" style={{ fontSize: 13 }}>{error}</div>}
      {draft && (
        <div className="alert alert-warning d-flex justify-content-between align-items-center py-2" style={{ fontSize: 13 }}>
          <span>{draft.label} has been calculated and is waiting for review and approval by a second admin.</span>
          <button className="btn btn-sm btn-warning" onClick={() => navigate(ROUTES.INTEREST_PERIOD(draft.id))}>Review</button>
        </div>
      )}

      <div className="row g-3">
        <div className="col-lg-4">
          <Card
            title="Interest rate"
            actions={isAdmin && (
              <button className="btn btn-sm btn-outline-secondary d-flex align-items-center gap-1"
                onClick={() => { setRatePercent(""); setEffectiveFrom(lockedThrough ? `${monthAfter(lockedThrough)}-01` : todayISO()); setRateNote(""); setRateOpen(true); }}>
                <Percent size={13} /> Change rate
              </button>
            )}
          >
            <div className="font-tabular fw-bold mb-1" style={{ fontSize: 28, color: "var(--color-text-primary)" }}>
              {rates?.current ? formatRate(rates.current.rate_percent) : "Not set"}
            </div>
            <p style={{ fontSize: 12, color: "var(--color-text-tertiary)" }}>
              {rates?.current ? `In effect since ${formatDate(rates.current.effective_from)}` : "Set a rate before calculating interest."}
            </p>
            {rates && rates.history.length > 0 && (
              <table className="table app-table table-sm mb-0" style={{ fontSize: 12 }}>
                <thead><tr><th>From</th><th>Rate</th><th>Set by</th></tr></thead>
                <tbody>
                  {rates.history.map((r) => (
                    <tr key={r.id} title={r.note ?? undefined}>
                      <td className="nowrap">{formatDate(r.effective_from)}</td>
                      <td className="font-tabular">{formatRate(r.rate_percent)}</td>
                      <td>{r.set_by}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </div>
        <div className="col-lg-8">
          <Card title="Monthly interest runs"
            actions={lockedThrough && <span style={{ fontSize: 12, color: "var(--color-text-tertiary)" }}>Locked through {formatDate(lockedThrough)}</span>}>
            {periods && periods.length === 0 ? (
              <EmptyState message="No months calculated yet." />
            ) : (
              <div className="app-table-scroll">
                <table className="table app-table table-hover align-middle mb-0">
                  <thead>
                    <tr><th>Month</th><th>Status</th><th className="text-end">Investors</th><th className="text-end">Interest</th><th>Calculated</th><th>Approved</th></tr>
                  </thead>
                  <tbody>
                    {periods?.map((p) => (
                      <tr key={p.id} onClick={() => navigate(ROUTES.INTEREST_PERIOD(p.id))}>
                        <td className="fw-semibold nowrap">{p.label}</td>
                        <td><StatusBadge status={p.status} /></td>
                        <td className="text-end">{p.investor_count}</td>
                        <td className="text-end font-tabular">{formatKES(p.total_net)}</td>
                        <td style={{ fontSize: 12 }}>{p.calculated_by}<div style={{ color: "var(--color-text-tertiary)" }}>{formatDateTime(p.calculated_at)}</div></td>
                        <td style={{ fontSize: 12 }}>{p.approved_by ?? "—"}{p.approved_at && <div style={{ color: "var(--color-text-tertiary)" }}>{formatDateTime(p.approved_at)}</div>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      </div>

      <Modal title="Change interest rate" open={rateOpen} onClose={() => setRateOpen(false)} onSubmit={saveRate}
        submitLabel="Save rate" submitting={submitting} submitDisabled={!rateValid || !effectiveFrom}>
        <div className="row g-2">
          <div className="col-6">
            <Field label="Annual rate (%)" error={ratePercent && !rateValid ? "Enter a percentage, e.g. 12.5" : undefined}>
              <input className="form-control font-tabular" inputMode="decimal" value={ratePercent} onChange={(e) => setRatePercent(e.target.value)} placeholder="12.5" />
            </Field>
          </div>
          <div className="col-6">
            <Field label="Effective from">
              <input type="date" className="form-control" value={effectiveFrom} onChange={(e) => setEffectiveFrom(e.target.value)} />
            </Field>
          </div>
        </div>
        <Field label="Note (optional)">
          <input className="form-control" value={rateNote} onChange={(e) => setRateNote(e.target.value)} placeholder="e.g. Board resolution ref." />
        </Field>
        <p className="mb-0" style={{ fontSize: 12, color: "var(--color-text-tertiary)" }}>
          Applies to every investor from that date, day by day. It can't take effect inside a month that's already approved
          {lockedThrough ? ` (locked through ${formatDate(lockedThrough)})` : ""}.
        </p>
      </Modal>

      <Modal title="Calculate monthly interest" open={calcOpen} onClose={() => setCalcOpen(false)} onSubmit={calculate}
        submitLabel="Calculate draft" submitting={submitting} submitDisabled={!month}>
        <Field label="Month" hint={lockedThrough ? `Months go in order — the next one is ${suggestedMonth}.` : "Only months that have ended can be calculated."}>
          <input type="month" className="form-control" value={month} max={lastCompletedMonth()} onChange={(e) => setMonth(e.target.value)} />
        </Field>
        <p className="mb-0" style={{ fontSize: 12, color: "var(--color-text-tertiary)" }}>
          This creates a draft only. Nothing is emailed until a different admin reviews and approves it.
        </p>
      </Modal>
    </div>
  );
}
