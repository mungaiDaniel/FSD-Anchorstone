import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { CheckCircle2, ChevronLeft, FileText, RefreshCw, Trash2 } from "lucide-react";
import { Card, EmptyState, PageHeader, Stat } from "@/components/ui/Page";
import { Modal } from "@/components/ui/Modal";
import { StatusBadge } from "@/components/data/StatusBadge";
import { interestService } from "@/services";
import { useAuth } from "@/context/AuthContext";
import type { InterestPayout, InterestPeriodDetail } from "@/lib/types";
import { ROUTES } from "@/lib/constants";
import { apiErrorMessage, formatDate, formatDateTime, formatKES, formatRate } from "@/lib/utils";

export default function InterestPeriodPage() {
  const id = Number(useParams().id);
  const navigate = useNavigate();
  const { isAdmin, userEmail } = useAuth();
  const [period, setPeriod] = useState<InterestPeriodDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<"approve" | "discard" | "recalculate" | null>(null);
  const [working, setWorking] = useState(false);
  const [refs, setRefs] = useState<Record<number, string>>({});
  const [search, setSearch] = useState("");

  const load = useCallback(async () => {
    try {
      setPeriod(await interestService.period(id));
      setError(null);
    } catch (err) {
      setError(apiErrorMessage(err, "Couldn't load this month."));
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const payouts = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!period) return [];
    return term
      ? period.payouts.filter((p) => p.investor_name.toLowerCase().includes(term) || p.client_code.toLowerCase().includes(term))
      : period.payouts;
  }, [period, search]);

  if (error && !period) return <div className="app-page"><div className="alert alert-danger">{error}</div></div>;
  if (!period) return <div className="app-page" style={{ color: "var(--color-text-tertiary)" }}>Loading…</div>;

  const isDraft = period.status === "draft";
  const isApproved = period.status === "approved";
  const calculatedBySelf = period.calculated_by.toLowerCase() === (userEmail ?? "").toLowerCase();
  const unpaid = period.payouts.filter((p) => p.status === "pending");
  const readyToMark = Object.entries(refs).filter(([, r]) => r.trim()).map(([pid, r]) => ({ payout_id: Number(pid), reference: r.trim() }));
  const taxApplied = Number(period.tax_rate_percent) > 0;

  const run = async (action: () => Promise<{ message: string }>, after?: () => void) => {
    setWorking(true);
    try {
      const res = await action();
      toast.success(res.message);
      setConfirm(null);
      after ? after() : load();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setWorking(false);
    }
  };

  const [year, month] = period.period_start.split("-").map(Number) as [number, number];

  return (
    <div className="app-page">
      <Link to={ROUTES.INTEREST} className="d-inline-flex align-items-center gap-1 mb-2 text-decoration-none" style={{ fontSize: 12, color: "var(--color-text-tertiary)" }}>
        <ChevronLeft size={14} /> Interest
      </Link>
      <PageHeader
        title={`Interest — ${period.label}`}
        subtitle={<span className="d-inline-flex align-items-center gap-2">{formatDate(period.period_start)} to {formatDate(period.period_end)} <StatusBadge status={period.status} /></span>}
        actions={
          isAdmin && isDraft && (
            <>
              <button className="btn btn-primary btn-sm d-flex align-items-center gap-1" disabled={calculatedBySelf}
                title={calculatedBySelf ? "You calculated this draft — a different admin must approve it." : undefined}
                onClick={() => setConfirm("approve")}>
                <CheckCircle2 size={14} /> Approve & send statements
              </button>
              <button className="btn btn-outline-secondary btn-sm d-flex align-items-center gap-1" onClick={() => setConfirm("recalculate")}>
                <RefreshCw size={14} /> Recalculate
              </button>
              <button className="btn btn-outline-danger btn-sm d-flex align-items-center gap-1" onClick={() => setConfirm("discard")}>
                <Trash2 size={14} /> Discard
              </button>
            </>
          )
        }
      />

      {isDraft && (
        <div className="alert alert-warning py-2" style={{ fontSize: 13 }}>
          Draft calculated by {period.calculated_by} on {formatDateTime(period.calculated_at)}. Check the figures, then a{" "}
          <strong>different admin</strong> approves it. Approval emails each investor their statement and locks {period.label}: nothing
          can be backdated into it afterwards.
        </div>
      )}
      {isApproved && unpaid.length > 0 && (
        <div className="alert alert-info py-2" style={{ fontSize: 13 }}>
          Approved by {period.approved_by}. Statements have been queued. When each payout is transferred, enter its payment reference
          below and mark it paid.
        </div>
      )}

      <div className="card shadow mb-3">
        <div className="card-body">
          <div className="row g-3">
            <div className="col-6 col-md-3"><Stat label="Investors" value={period.investor_count} /></div>
            <div className="col-6 col-md-3"><Stat label="Total interest" value={formatKES(period.total_net)} /></div>
            {taxApplied && <div className="col-6 col-md-3"><Stat label="Withholding tax" value={formatKES(period.total_tax)} /></div>}
            <div className="col-6 col-md-3"><Stat label="Unpaid" value={isDraft ? "—" : `${unpaid.length} of ${period.payouts.length}`} /></div>
            <div className="col-6 col-md-3"><Stat label="Approved" value={period.approved_by ?? "—"} sub={period.approved_at ? formatDateTime(period.approved_at) : undefined} /></div>
          </div>
        </div>
      </div>

      <Card
        title="Payouts"
        actions={
          <div className="d-flex gap-2 align-items-center">
            <input className="form-control form-control-sm" style={{ width: 220 }} placeholder="Filter investors" value={search}
              onChange={(e) => setSearch(e.target.value)} aria-label="Filter payouts" />
            {isAdmin && isApproved && (
              <button className="btn btn-sm btn-primary text-nowrap" disabled={readyToMark.length === 0 || working}
                onClick={() => run(() => interestService.markPaid(period.id, readyToMark), () => { setRefs({}); load(); })}>
                Mark {readyToMark.length || ""} paid
              </button>
            )}
          </div>
        }
      >
        {period.payouts.length === 0 ? (
          <EmptyState message="No investor earned interest this month." />
        ) : (
          <div className="app-table-scroll">
            <table className="table app-table align-middle mb-0">
              <thead>
                <tr>
                  <th>Investor</th>
                  <th className="text-end">Opening</th>
                  <th className="text-end">Closing</th>
                  <th className="text-end">Average daily</th>
                  <th>Rate</th>
                  <th className="text-end">Interest</th>
                  <th>Payment</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {payouts.map((p: InterestPayout) => (
                  <tr key={p.id}>
                    <td>
                      <Link to={ROUTES.INVESTOR_DETAIL(p.investor_id)}>{p.investor_name}</Link>
                      <div className="font-tabular" style={{ fontSize: 11, color: "var(--color-text-tertiary)" }}>{p.client_code}</div>
                    </td>
                    <td className="text-end font-tabular">{formatKES(p.opening_balance)}</td>
                    <td className="text-end font-tabular">{formatKES(p.closing_balance)}</td>
                    <td className="text-end font-tabular">{formatKES(p.average_daily_balance)}</td>
                    <td className="nowrap" style={{ fontSize: 12 }}>{formatRate(p.rate_percent)}</td>
                    <td className="text-end font-tabular fw-semibold">{formatKES(p.net_interest)}</td>
                    <td style={{ minWidth: 170 }}>
                      {isDraft && <span style={{ fontSize: 12, color: "var(--color-text-tertiary)" }}>After approval</span>}
                      {!isDraft && p.status === "paid" && (
                        <>
                          <StatusBadge status="paid" />
                          <div style={{ fontSize: 11, color: "var(--color-text-tertiary)" }}>{p.payment_reference} · {formatDate(p.paid_at)}</div>
                        </>
                      )}
                      {isApproved && p.status === "pending" && (isAdmin ? (
                        <input className="form-control form-control-sm" placeholder="Payment reference" value={refs[p.id] ?? ""}
                          onChange={(e) => setRefs((r) => ({ ...r, [p.id]: e.target.value }))} maxLength={100}
                          aria-label={`Payment reference for ${p.investor_name}`} />
                      ) : <StatusBadge status="pending" label="Unpaid" />)}
                    </td>
                    <td className="text-end">
                      <button className="btn btn-sm btn-outline-secondary d-inline-flex align-items-center gap-1"
                        onClick={() => interestService.openStatement(p).catch((err) => toast.error(apiErrorMessage(err)))}>
                        <FileText size={13} /> {isDraft ? "Preview" : "Statement"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Modal title={`Approve ${period.label}`} open={confirm === "approve"} onClose={() => setConfirm(null)}
        onSubmit={() => run(() => interestService.approve(period.id))} submitLabel="Approve & send" submitVariant="primary" submitting={working}>
        <p style={{ fontSize: 13 }}>
          Approve <strong className="font-tabular">{formatKES(period.total_net)}</strong> of interest for {period.investor_count} investor(s)?
        </p>
        <ul style={{ fontSize: 13 }}>
          <li>Each investor is emailed their statement (PDF attached).</li>
          <li>{period.label} becomes locked: no deposits, withdrawals or rate changes can be dated in it.</li>
          <li>If any transaction changed since this draft was calculated, approval is refused and you'll need to recalculate.</li>
        </ul>
      </Modal>
      <Modal title={`Recalculate ${period.label}`} open={confirm === "recalculate"} onClose={() => setConfirm(null)}
        onSubmit={() => run(() => interestService.calculate(year, month))} submitLabel="Recalculate" submitting={working}>
        <p className="mb-0" style={{ fontSize: 13 }}>Re-runs the calculation from the current deposits, withdrawals and rates. You become the calculating admin, so someone else must approve it.</p>
      </Modal>
      <Modal title={`Discard ${period.label} draft`} open={confirm === "discard"} onClose={() => setConfirm(null)}
        onSubmit={() => run(() => interestService.discard(period.id), () => navigate(ROUTES.INTEREST))} submitLabel="Discard draft"
        submitVariant="danger" submitting={working}>
        <p className="mb-0" style={{ fontSize: 13 }}>The draft figures are deleted. Nothing has been sent to investors.</p>
      </Modal>
    </div>
  );
}
