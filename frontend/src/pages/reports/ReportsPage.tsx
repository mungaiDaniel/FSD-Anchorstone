import { useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";
import {
  ArrowDownToLine,
  ArrowUpFromLine,
  BookUser,
  Download,
  Loader2,
  Mail,
  Percent,
  ShieldCheck,
  TrendingUp,
} from "lucide-react";
import { PageHeader } from "@/components/ui/Page";
import { interestService, reportService } from "@/services";
import { useAuth } from "@/context/AuthContext";
import type { InterestPeriod, ReportName } from "@/lib/types";
import { apiErrorMessage, todayISO } from "@/lib/utils";

type Params = Record<string, string | undefined>;

function DateRange({ value, onChange }: { value: Params; onChange: (v: Params) => void }) {
  return (
    <div className="d-flex flex-wrap gap-2">
      <label className="form-label mb-0" style={{ fontSize: 12 }}>
        From
        <input type="date" className="form-control form-control-sm" value={value.from ?? ""} max={value.to || todayISO()}
          onChange={(e) => onChange({ ...value, from: e.target.value || undefined })} />
      </label>
      <label className="form-label mb-0" style={{ fontSize: 12 }}>
        To
        <input type="date" className="form-control form-control-sm" value={value.to ?? ""} min={value.from}
          onChange={(e) => onChange({ ...value, to: e.target.value || undefined })} />
      </label>
    </div>
  );
}

function StatusSelect({ value, options, onChange }: { value?: string; options: [string, string][]; onChange: (v?: string) => void }) {
  return (
    <label className="form-label mb-0" style={{ fontSize: 12 }}>
      Status
      <select className="form-select form-select-sm" value={value ?? ""} onChange={(e) => onChange(e.target.value || undefined)}>
        <option value="">All</option>
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </label>
  );
}

function ReportCard({
  name, icon, title, description, children, params, note,
}: {
  name: ReportName;
  icon: ReactNode;
  title: string;
  description: string;
  children?: ReactNode;
  params: Params;
  note?: string;
}) {
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    try {
      const file = await reportService.download(name, params);
      toast.success(`Downloaded ${file}`);
    } catch (err) {
      // Error bodies come back as a Blob when responseType is blob.
      const data = (err as { response?: { data?: unknown } })?.response?.data;
      if (data instanceof Blob) {
        try {
          toast.error(JSON.parse(await data.text()).message ?? "Export failed.");
          return;
        } catch { /* fall through */ }
      }
      toast.error(apiErrorMessage(err, "Export failed."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="card shadow h-100">
      <div className="card-body d-flex flex-column gap-3">
        <div className="d-flex gap-3">
          <div className="d-flex align-items-center justify-content-center flex-shrink-0"
            style={{ width: 40, height: 40, borderRadius: 10, background: "var(--color-bg-tint)", color: "var(--color-brand-400)" }}>
            {icon}
          </div>
          <div>
            <h2 className="app-section-title mb-1">{title}</h2>
            <p className="mb-0" style={{ fontSize: 13, color: "var(--color-text-secondary)" }}>{description}</p>
          </div>
        </div>
        {children && <div className="d-flex flex-wrap gap-3 align-items-end">{children}</div>}
        <div className="mt-auto d-flex align-items-center justify-content-between gap-2">
          <span style={{ fontSize: 11.5, color: "var(--color-text-tertiary)" }}>{note ?? "Excel (.xlsx)"}</span>
          <button className="btn btn-primary btn-sm d-flex align-items-center gap-1" onClick={run} disabled={busy}>
            {busy ? <Loader2 size={14} className="app-spin" /> : <Download size={14} />} {busy ? "Preparing…" : "Export to Excel"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function ReportsPage() {
  const { isAdmin } = useAuth();
  const [investors, setInvestors] = useState<Params>({});
  const [deposits, setDeposits] = useState<Params>({});
  const [withdrawals, setWithdrawals] = useState<Params>({});
  const [interestMode, setInterestMode] = useState<"month" | "range">("month");
  const [interest, setInterest] = useState<Params>({});
  const [audit, setAudit] = useState<Params>({});
  const [emails, setEmails] = useState<Params>({});
  const [months, setMonths] = useState<InterestPeriod[]>([]);

  useEffect(() => {
    interestService.periods()
      .then((d) => {
        const approved = d.items.filter((p) => p.status === "approved" || p.status === "paid");
        setMonths(approved);
        if (approved[0]) setInterest({ period_id: String(approved[0].id) });
      })
      .catch(() => setMonths([]));
  }, []);

  const interestParams = interestMode === "month" ? { period_id: interest.period_id } : { from: interest.from, to: interest.to };

  return (
    <div className="app-page">
      <PageHeader title="Reports"
        subtitle="Each report is built from live data when you export it. Every export is recorded in the audit log." />

      <div className="row g-3">
        <div className="col-lg-6 col-xxl-4">
          <ReportCard name="aum" icon={<TrendingUp size={19} />} title="Portfolio summary (AUM)" params={{}}
            description="Funds under management at each month end since the first deposit, with month-on-month change. One sheet, for management."
            note="Point in time · no filters" />
        </div>
        <div className="col-lg-6 col-xxl-4">
          <ReportCard name="investors" icon={<BookUser size={19} />} title="Investors" params={investors}
            description="Every investor with balance, total deposited and withdrawn, interest paid and interest due, as of today.">
            <StatusSelect value={investors.status} options={[["active", "Active"], ["closed", "Closed"]]}
              onChange={(status) => setInvestors({ status })} />
          </ReportCard>
        </div>
        <div className="col-lg-6 col-xxl-4">
          <ReportCard name="deposits" icon={<ArrowDownToLine size={19} />} title="Deposits" params={deposits}
            description="Date, investor, reference, method, amount, who recorded it and status, with a total of posted deposits.">
            <DateRange value={deposits} onChange={setDeposits} />
            <StatusSelect value={deposits.status} options={[["posted", "Posted"], ["reversed", "Reversed"]]}
              onChange={(status) => setDeposits({ ...deposits, status })} />
          </ReportCard>
        </div>
        <div className="col-lg-6 col-xxl-4">
          <ReportCard name="withdrawals" icon={<ArrowUpFromLine size={19} />} title="Withdrawals" params={withdrawals}
            description="Requests with who recorded and who approved or rejected them, and a total of approved withdrawals.">
            <DateRange value={withdrawals} onChange={setWithdrawals} />
            <StatusSelect value={withdrawals.status} options={[["pending", "Pending"], ["approved", "Approved"], ["rejected", "Rejected"]]}
              onChange={(status) => setWithdrawals({ ...withdrawals, status })} />
          </ReportCard>
        </div>
        <div className="col-lg-6 col-xxl-4">
          <ReportCard name="interest" icon={<Percent size={19} />} title="Interest payouts" params={interestParams}
            description="Per approved month: each investor's opening, closing and average balance, interest, payment status and reference, and who calculated and approved it.">
            <div className="btn-group btn-group-sm" role="group" aria-label="Interest report scope">
              <button type="button" className={`btn ${interestMode === "month" ? "btn-primary" : "btn-outline-secondary"}`}
                onClick={() => setInterestMode("month")}>One month</button>
              <button type="button" className={`btn ${interestMode === "range" ? "btn-primary" : "btn-outline-secondary"}`}
                onClick={() => setInterestMode("range")}>Date range</button>
            </div>
            {interestMode === "month" ? (
              <label className="form-label mb-0" style={{ fontSize: 12 }}>
                Month
                <select className="form-select form-select-sm" value={interest.period_id ?? ""} disabled={!months.length}
                  onChange={(e) => setInterest({ period_id: e.target.value })}>
                  {!months.length && <option value="">No approved months yet</option>}
                  {months.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
                </select>
              </label>
            ) : (
              <DateRange value={interest} onChange={setInterest} />
            )}
          </ReportCard>
        </div>

        {isAdmin && (
          <>
            <div className="col-lg-6 col-xxl-4">
              <ReportCard name="audit-log" icon={<ShieldCheck size={19} />} title="Audit log" params={audit}
                description="Who did what, and when: the same entries as the Audit Log screen."
                note="Admins and super admins only">
                <DateRange value={audit} onChange={setAudit} />
                <label className="form-label mb-0" style={{ fontSize: 12 }}>
                  User
                  <input className="form-control form-control-sm" placeholder="Name or email" value={audit.user ?? ""}
                    onChange={(e) => setAudit({ ...audit, user: e.target.value || undefined })} />
                </label>
              </ReportCard>
            </div>
            <div className="col-lg-6 col-xxl-4">
              <ReportCard name="email-log" icon={<Mail size={19} />} title="Email log" params={emails}
                description="Every email: investor, type, subject, status (sent, suppressed, awaiting confirmation, failed) and dates."
                note="Admins and super admins only">
                <DateRange value={emails} onChange={setEmails} />
                <StatusSelect value={emails.status}
                  options={[["pending", "Awaiting confirmation"], ["queued", "Queued"], ["sent", "Sent"], ["failed", "Failed"], ["cancelled", "Suppressed / cancelled"]]}
                  onChange={(status) => setEmails({ ...emails, status })} />
              </ReportCard>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
