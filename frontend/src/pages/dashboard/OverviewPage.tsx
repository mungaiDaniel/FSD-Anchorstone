import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, ArrowDownToLine, ArrowUpFromLine, CalendarCheck, CheckCircle2, ChevronRight, Landmark, Mail, Percent, Users } from "lucide-react";
import { KPICard } from "@/components/data/KPICard";
import { ChartCard } from "@/components/charts/ChartCard";
import { DepositsWithdrawalsBarChart } from "@/components/charts/DepositsWithdrawalsBarChart";
import { Card, PageHeader } from "@/components/ui/Page";
import { RecordDepositModal, RequestWithdrawalModal } from "@/components/transactions/TransactionModals";
import { statsService } from "@/services";
import type { OverviewStats } from "@/lib/types";
import { ROUTES } from "@/lib/constants";
import { apiErrorMessage, formatDate, formatKES, formatKESCompact, formatRate } from "@/lib/utils";

export default function OverviewPage() {
  const [stats, setStats] = useState<OverviewStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [modal, setModal] = useState<"deposit" | "withdrawal" | null>(null);

  const load = () =>
    statsService
      .overview()
      .then((s) => {
        setStats(s);
        setError(null);
      })
      .catch((err) => setError(apiErrorMessage(err, "Couldn't load the dashboard.")));

  useEffect(() => {
    load();
  }, []);

  // Display-only arithmetic on the API's decimal strings; nothing here is stored or sent back.
  const sixMonths = (stats?.monthly_flows ?? []).reduce(
    (t, f) => ({ deposits: t.deposits + Number(f.deposits), withdrawals: t.withdrawals + Number(f.withdrawals) }),
    { deposits: 0, withdrawals: 0 },
  );
  const netThisMonth = stats ? Number(stats.deposits_this_month) - Number(stats.withdrawals_this_month) : 0;

  const attention: { text: string; to: string }[] = [];
  if (stats) {
    if (stats.pending_withdrawals.count > 0)
      attention.push({
        text: `${stats.pending_withdrawals.count} withdrawal request(s) awaiting approval (${formatKES(stats.pending_withdrawals.total)})`,
        to: ROUTES.WITHDRAWALS,
      });
    if (stats.draft_period)
      attention.push({ text: `Interest for ${stats.draft_period.label} is calculated and awaiting approval`, to: ROUTES.INTEREST_PERIOD(stats.draft_period.id) });
    if (Number(stats.interest_outstanding) > 0)
      attention.push({ text: `${formatKES(stats.interest_outstanding)} of approved interest not yet marked paid`, to: ROUTES.INTEREST });
    if (stats.emails.pending > 0)
      attention.push({ text: `${stats.emails.pending} statement(s) waiting for an admin to confirm or suppress`, to: `${ROUTES.EMAILS}?status=pending` });
    if (stats.emails.failed > 0) attention.push({ text: `${stats.emails.failed} email(s) failed to send`, to: ROUTES.EMAILS });
    if (!stats.current_rate) attention.push({ text: "No interest rate is set yet", to: ROUTES.INTEREST });
  }

  return (
    <div className="app-page">
      <PageHeader
        title="Overview"
        subtitle={stats ? `As of ${formatDate(stats.as_of)}` : "Deposits, withdrawals and interest at a glance"}
        actions={
          <>
            <button className="btn btn-primary btn-sm d-flex align-items-center gap-1" onClick={() => setModal("deposit")}>
              <ArrowDownToLine size={14} /> Record deposit
            </button>
            <button className="btn btn-outline-secondary btn-sm d-flex align-items-center gap-1" onClick={() => setModal("withdrawal")}>
              <ArrowUpFromLine size={14} /> Record withdrawal
            </button>
          </>
        }
      />

      {error && <div className="alert alert-danger py-2" style={{ fontSize: 13 }}>{error}</div>}

      <div className="row g-2 g-sm-3 mb-3">
        <div className="col-6 col-xl-3">
          <KPICard variant="featured" icon={<Landmark size={17} />} label="Total deposits held" value={stats ? formatKESCompact(stats.total_balance) : "—"}
            subtitle={stats ? formatKES(stats.total_balance) : undefined} />
        </div>
        <div className="col-6 col-xl-3">
          <KPICard icon={<Users size={17} />} label="Investors" value={stats ? String(stats.active_investors) : "—"}
            subtitle={stats ? `${stats.funded_investors} with a balance` : undefined} />
        </div>
        <div className="col-6 col-xl-3">
          <KPICard icon={<Percent size={17} />} label="Interest rate" value={stats?.current_rate ? formatRate(stats.current_rate.rate_percent) : "Not set"}
            subtitle={stats?.current_rate ? `Since ${formatDate(stats.current_rate.effective_from)}` : undefined} />
        </div>
        <div className="col-6 col-xl-3">
          <KPICard icon={<CalendarCheck size={17} />} label="Last interest run" value={stats?.last_period ? formatKESCompact(stats.last_period.total_net) : "—"}
            subtitle={stats?.last_period ? `${stats.last_period.label} · ${stats.last_period.investor_count} investors` : "No approved months yet"}
            />
        </div>
      </div>

      <div className="row g-3">
        <div className="col-lg-8">
          <ChartCard
            title="Deposits and withdrawals"
            subtitle="Last six months"
            actions={stats && (
              <div className="d-flex gap-4 tw:sm:text-right">
                <div>
                  <div className="tw:text-[11px] tw:uppercase tw:tracking-wider tw:font-semibold tw:text-text-tertiary">In</div>
                  <div className="font-tabular tw:font-semibold tw:text-brand-400">{formatKESCompact(sixMonths.deposits)}</div>
                </div>
                <div>
                  <div className="tw:text-[11px] tw:uppercase tw:tracking-wider tw:font-semibold tw:text-text-tertiary">Out</div>
                  <div className="font-tabular tw:font-semibold tw:text-text-secondary">{formatKESCompact(sixMonths.withdrawals)}</div>
                </div>
              </div>
            )}
            legend={[
              { label: "Deposits", color: "var(--color-chart-deposit)" },
              { label: "Withdrawals", color: "var(--color-chart-withdrawal)" },
            ]}
          >
            {stats && (
              <DepositsWithdrawalsBarChart
                labels={stats.monthly_flows.map((f) => f.month)}
                deposits={stats.monthly_flows.map((f) => Number(f.deposits))}
                withdrawals={stats.monthly_flows.map((f) => Number(f.withdrawals))}
              />
            )}
          </ChartCard>
        </div>
        <div className="col-lg-4 d-flex flex-column gap-3">
          <Card title="This month">
            <ul className="list-unstyled mb-0 tw:space-y-3">
              <MonthRow icon={<ArrowDownToLine size={15} />} label="Deposits" value={stats ? formatKES(stats.deposits_this_month) : "—"} />
              <MonthRow icon={<ArrowUpFromLine size={15} />} label="Withdrawals" value={stats ? formatKES(stats.withdrawals_this_month) : "—"} muted />
              <MonthRow icon={<Mail size={15} />} label="Emails waiting to send" value={stats ? String(stats.emails.queued) : "—"} muted />
            </ul>
            {stats && (
              <div className="d-flex justify-content-between align-items-baseline tw:mt-4 tw:pt-3 tw:border-t tw:border-border-subtle">
                <span className="tw:text-[13px] tw:font-semibold tw:text-text-secondary">Net flow</span>
                <span className={`font-tabular tw:font-bold tw:text-[15px] ${netThisMonth < 0 ? "tw:text-destructive" : "tw:text-brand-400"}`}>
                  {netThisMonth < 0 ? "−" : "+"}{formatKES(Math.abs(netThisMonth))}
                </span>
              </div>
            )}
          </Card>
          <Card
            title="Needs attention"
            actions={attention.length > 0 && (
              <span className="tw:inline-flex tw:items-center tw:justify-center tw:min-w-6 tw:h-6 tw:px-2 tw:rounded-full tw:bg-warning-bg tw:text-warning tw:text-xs tw:font-bold">
                {attention.length}
              </span>
            )}
          >
            {stats && attention.length === 0 && (
              <div className="d-flex align-items-center gap-2 tw:text-[13px] tw:text-success">
                <CheckCircle2 size={18} /> All clear. Nothing is waiting on you.
              </div>
            )}
            <ul className="list-unstyled mb-0 tw:-mx-2 tw:space-y-1">
              {attention.map((a) => (
                <li key={a.text}>
                  <Link
                    to={a.to}
                    className="d-flex align-items-start gap-2 text-decoration-none tw:rounded-lg tw:px-2 tw:py-2 tw:text-[13px] tw:text-text-primary tw:transition-colors tw:hover:bg-warning-bg/60 tw:group"
                  >
                    <AlertTriangle size={15} className="flex-shrink-0 tw:mt-0.5 tw:text-warning" />
                    <span className="flex-grow-1">{a.text}</span>
                    <ChevronRight size={15} className="flex-shrink-0 tw:mt-0.5 tw:text-text-disabled tw:transition-transform tw:group-hover:translate-x-0.5 tw:group-hover:text-warning" />
                  </Link>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>

      <RecordDepositModal open={modal === "deposit"} onClose={() => setModal(null)} onDone={load} />
      <RequestWithdrawalModal open={modal === "withdrawal"} onClose={() => setModal(null)} onDone={load} />
    </div>
  );
}

function MonthRow({ icon, label, value, muted }: { icon: React.ReactNode; label: string; value: string; muted?: boolean }) {
  return (
    <li className="d-flex align-items-center gap-3">
      <span
        className={`tw:inline-flex tw:items-center tw:justify-center tw:size-8 tw:rounded-lg tw:shrink-0 ${
          muted ? "tw:bg-bg-surface-alt tw:text-text-tertiary" : "tw:bg-bg-tint tw:text-brand-400"
        }`}
      >
        {icon}
      </span>
      <span className="flex-grow-1 tw:text-[13px] tw:text-text-secondary">{label}</span>
      <span className="font-tabular tw:text-[13px] tw:font-semibold tw:text-text-primary">{value}</span>
    </li>
  );
}
