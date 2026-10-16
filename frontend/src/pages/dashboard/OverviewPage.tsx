import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, ArrowDownToLine, ArrowUpFromLine, CalendarCheck, Landmark, Percent, Users } from "lucide-react";
import { KPICard } from "@/components/data/KPICard";
import { ChartCard } from "@/components/charts/ChartCard";
import { DepositsWithdrawalsBarChart } from "@/components/charts/DepositsWithdrawalsBarChart";
import { Card, PageHeader } from "@/components/ui/Page";
import { StatusBadge } from "@/components/data/StatusBadge";
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

      <div className="row g-3 mb-3">
        <div className="col-sm-6 col-xl-3">
          <KPICard icon={<Landmark size={17} />} label="Total deposits held" value={stats ? formatKESCompact(stats.total_balance) : "—"}
            subtitle={stats ? formatKES(stats.total_balance) : undefined} />
        </div>
        <div className="col-sm-6 col-xl-3">
          <KPICard icon={<Users size={17} />} label="Investors" value={stats ? String(stats.active_investors) : "—"}
            subtitle={stats ? `${stats.funded_investors} with a balance` : undefined} />
        </div>
        <div className="col-sm-6 col-xl-3">
          <KPICard icon={<Percent size={17} />} label="Interest rate" value={stats?.current_rate ? formatRate(stats.current_rate.rate_percent) : "Not set"}
            subtitle={stats?.current_rate ? `Since ${formatDate(stats.current_rate.effective_from)}` : undefined} />
        </div>
        <div className="col-sm-6 col-xl-3">
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
            <dl className="mb-0" style={{ fontSize: 13 }}>
              <div className="d-flex justify-content-between py-1">
                <dt className="fw-normal" style={{ color: "var(--color-text-secondary)" }}>Deposits</dt>
                <dd className="mb-0 font-tabular">{stats ? formatKES(stats.deposits_this_month) : "—"}</dd>
              </div>
              <div className="d-flex justify-content-between py-1">
                <dt className="fw-normal" style={{ color: "var(--color-text-secondary)" }}>Withdrawals</dt>
                <dd className="mb-0 font-tabular">{stats ? formatKES(stats.withdrawals_this_month) : "—"}</dd>
              </div>
              <div className="d-flex justify-content-between py-1">
                <dt className="fw-normal" style={{ color: "var(--color-text-secondary)" }}>Emails waiting to send</dt>
                <dd className="mb-0 font-tabular">{stats ? stats.emails.queued : "—"}</dd>
              </div>
            </dl>
          </Card>
          <Card title="Needs attention">
            {stats && attention.length === 0 && (
              <p className="mb-0 d-flex align-items-center gap-2" style={{ fontSize: 13, color: "var(--color-text-secondary)" }}>
                <StatusBadge status="active" label="All clear" /> Nothing waiting on you.
              </p>
            )}
            <ul className="list-unstyled mb-0">
              {attention.map((a) => (
                <li key={a.text} className="mb-2">
                  <Link to={a.to} className="d-flex gap-2 text-decoration-none" style={{ fontSize: 13, color: "var(--color-text-primary)" }}>
                    <AlertTriangle size={15} className="flex-shrink-0 mt-1" style={{ color: "var(--color-warning)" }} />
                    <span>{a.text}</span>
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
