import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { ArrowDownToLine, ArrowUpFromLine, ChevronLeft, FileText, Mail, Pencil } from "lucide-react";
import { Card, EmptyState, PageHeader, Stat } from "@/components/ui/Page";
import { Modal } from "@/components/ui/Modal";
import { StatusBadge } from "@/components/data/StatusBadge";
import { InvestorForm } from "@/components/forms/InvestorForm";
import {
  ApproveWithdrawalModal,
  RecordDepositModal,
  RejectWithdrawalModal,
  RequestWithdrawalModal,
  ReverseDepositModal,
} from "@/components/transactions/TransactionModals";
import { emailService, interestService, investorService } from "@/services";
import { useAuth } from "@/context/AuthContext";
import type { Deposit, InterestPayout, InvestorListItem, InvestorSummary, Ledger, OutboxEmail, Withdrawal } from "@/lib/types";
import { PAYMENT_METHOD_LABELS, ROUTES } from "@/lib/constants";
import { apiErrorMessage, formatDate, formatDateTime, formatKES, formatRate } from "@/lib/utils";

type Tab = "statement" | "deposits" | "withdrawals" | "interest" | "emails" | "details";

const TABS: { key: Tab; label: string }[] = [
  { key: "statement", label: "Statement" },
  { key: "deposits", label: "Deposits" },
  { key: "withdrawals", label: "Withdrawals" },
  { key: "interest", label: "Interest" },
  { key: "emails", label: "Emails" },
  { key: "details", label: "Details" },
];

export default function InvestorDetailPage() {
  const id = Number(useParams().id);
  const { isAdmin, userEmail } = useAuth();
  const navigate = useNavigate();
  const [investor, setInvestor] = useState<InvestorSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("statement");
  const [ledger, setLedger] = useState<Ledger | null>(null);
  const [deposits, setDeposits] = useState<Deposit[] | null>(null);
  const [withdrawals, setWithdrawals] = useState<Withdrawal[] | null>(null);
  const [payouts, setPayouts] = useState<InterestPayout[] | null>(null);
  const [emails, setEmails] = useState<OutboxEmail[] | null>(null);

  const [modal, setModal] = useState<"deposit" | "withdrawal" | "edit" | "close" | "email" | null>(null);
  const [reverseTarget, setReverseTarget] = useState<Deposit | null>(null);
  const [approveTarget, setApproveTarget] = useState<Withdrawal | null>(null);
  const [rejectTarget, setRejectTarget] = useState<Withdrawal | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const [inv, led, deps, wds, pays, ems] = await Promise.all([
        investorService.get(id),
        investorService.ledger(id),
        investorService.deposits(id),
        investorService.withdrawals(id),
        investorService.payouts(id),
        investorService.emails(id),
      ]);
      setInvestor(inv);
      setLedger(led);
      setDeposits(deps);
      setWithdrawals(wds);
      setPayouts(pays);
      setEmails(ems);
      setError(null);
    } catch (err) {
      setError(apiErrorMessage(err, "Couldn't load this investor."));
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  if (error && !investor) {
    return (
      <div className="app-page">
        <div className="alert alert-danger">{error}</div>
        <Link to={ROUTES.INVESTORS}>Back to investors</Link>
      </div>
    );
  }
  if (!investor) return <div className="app-page" style={{ color: "var(--color-text-tertiary)" }}>Loading…</div>;

  const asListItem: InvestorListItem = { ...investor, balance: investor.balance, pending_withdrawals: investor.pending_withdrawals };
  const active = investor.status === "active";
  const isOwn = (w: Withdrawal) => w.requested_by.toLowerCase() === (userEmail ?? "").toLowerCase();

  const toggleStatus = async () => {
    setSaving(true);
    try {
      const res = await investorService.setStatus(investor.id, active ? "closed" : "active");
      toast.success(res.message);
      setModal(null);
      load();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="app-page">
      <Link to={ROUTES.INVESTORS} className="d-inline-flex align-items-center gap-1 mb-2 text-decoration-none" style={{ fontSize: 12, color: "var(--color-text-tertiary)" }}>
        <ChevronLeft size={14} /> Investors
      </Link>
      <PageHeader
        title={investor.full_name}
        subtitle={
          <span className="d-inline-flex align-items-center gap-2">
            <span className="font-tabular">{investor.client_code}</span> · {investor.email} <StatusBadge status={investor.status} />
          </span>
        }
        actions={
          <>
            {active && (
              <>
                <button className="btn btn-primary btn-sm d-flex align-items-center gap-1" onClick={() => setModal("deposit")}>
                  <ArrowDownToLine size={14} /> Record deposit
                </button>
                <button className="btn btn-outline-secondary btn-sm d-flex align-items-center gap-1" onClick={() => setModal("withdrawal")}
                  disabled={Number(investor.balance) - Number(investor.pending_withdrawals) <= 0}>
                  <ArrowUpFromLine size={14} /> Record withdrawal
                </button>
              </>
            )}
            {isAdmin && (
              <button className="btn btn-outline-secondary btn-sm d-flex align-items-center gap-1" onClick={() => setModal("email")}>
                <Mail size={14} /> Send statement
              </button>
            )}
          </>
        }
      />

      <div className="card shadow mb-3">
        <div className="card-body">
          <div className="row g-3">
            <div className="col-6 col-md-4 col-xl-2"><Stat label="Balance" value={formatKES(investor.balance)} /></div>
            <div className="col-6 col-md-4 col-xl-2"><Stat label="Total deposited" value={formatKES(investor.total_deposited)} /></div>
            <div className="col-6 col-md-4 col-xl-2"><Stat label="Total withdrawn" value={formatKES(investor.total_withdrawn)} /></div>
            <div className="col-6 col-md-4 col-xl-2"><Stat label="Pending withdrawals" value={formatKES(investor.pending_withdrawals)} /></div>
            <div className="col-6 col-md-4 col-xl-2"><Stat label="Interest paid" value={formatKES(investor.interest_paid)} /></div>
            <div className="col-6 col-md-4 col-xl-2"><Stat label="Interest due" value={formatKES(investor.interest_payable)} sub="Approved, not yet paid" /></div>
          </div>
        </div>
      </div>

      <ul className="nav nav-tabs app-tabs mb-3" role="tablist">
        {TABS.map((t) => (
          <li className="nav-item" key={t.key}>
            <button className={`nav-link${tab === t.key ? " active" : ""}`} role="tab" aria-selected={tab === t.key} onClick={() => setTab(t.key)}>
              {t.label}
            </button>
          </li>
        ))}
      </ul>

      {tab === "statement" && ledger && (
        <Card title="Account statement" actions={<span style={{ fontSize: 12, color: "var(--color-text-tertiary)" }}>Posted deposits and approved withdrawals, newest first</span>}>
          {ledger.entries.length === 0 ? (
            <EmptyState message="No transactions yet." />
          ) : (
            <div className="app-table-scroll">
              <table className="table app-table align-middle mb-0">
                <thead>
                  <tr><th>Date</th><th>Type</th><th>Reference</th><th>Method</th><th className="text-end">Amount</th><th className="text-end">Balance</th></tr>
                </thead>
                <tbody>
                  {ledger.entries.map((e) => (
                    <tr key={`${e.kind}-${e.id}`}>
                      <td className="nowrap">{formatDate(e.date)}</td>
                      <td>{e.kind === "deposit" ? "Deposit" : "Withdrawal"}</td>
                      <td className="font-tabular">{e.reference || "—"}</td>
                      <td>{PAYMENT_METHOD_LABELS[e.method]}</td>
                      <td className="text-end font-tabular" style={{ color: Number(e.amount) < 0 ? "var(--color-destructive)" : "var(--color-success)" }}>
                        {Number(e.amount) < 0 ? "−" : "+"}{formatKES(Math.abs(Number(e.amount)))}
                      </td>
                      <td className="text-end font-tabular">{formatKES(e.balance)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {tab === "deposits" && deposits && (
        <Card title="Deposits">
          {deposits.length === 0 ? <EmptyState message="No deposits recorded." /> : (
            <div className="app-table-scroll">
              <table className="table app-table align-middle mb-0">
                <thead>
                  <tr><th>Date received</th><th>Reference</th><th>Method</th><th className="text-end">Amount</th><th>Status</th><th>Recorded by</th><th /></tr>
                </thead>
                <tbody>
                  {deposits.map((d) => (
                    <tr key={d.id}>
                      <td className="nowrap">{formatDate(d.value_date)}</td>
                      <td className="font-tabular">{d.reference}</td>
                      <td>{PAYMENT_METHOD_LABELS[d.method]}</td>
                      <td className="text-end font-tabular">{formatKES(d.amount)}</td>
                      <td>
                        <StatusBadge status={d.status} />
                        {d.reversal_reason && <div style={{ fontSize: 11, color: "var(--color-text-tertiary)" }}>{d.reversal_reason}</div>}
                      </td>
                      <td style={{ fontSize: 12 }}>{d.recorded_by}</td>
                      <td className="text-end">
                        {isAdmin && d.status === "posted" && (
                          <button className="btn btn-sm btn-outline-danger" onClick={() => setReverseTarget({ ...d, investor_name: investor.full_name })}>Reverse</button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {tab === "withdrawals" && withdrawals && (
        <Card title="Withdrawals">
          {withdrawals.length === 0 ? <EmptyState message="No withdrawals." /> : (
            <div className="app-table-scroll">
              <table className="table app-table align-middle mb-0">
                <thead>
                  <tr><th>Requested</th><th className="text-end">Amount</th><th>Method</th><th>Status</th><th>Effective</th><th>Recorded / decided by</th><th /></tr>
                </thead>
                <tbody>
                  {withdrawals.map((w) => (
                    <tr key={w.id}>
                      <td className="nowrap">{formatDate(w.requested_date)}</td>
                      <td className="text-end font-tabular">{formatKES(w.amount)}</td>
                      <td>{PAYMENT_METHOD_LABELS[w.method]}</td>
                      <td>
                        <StatusBadge status={w.status} />
                        {w.rejection_reason && <div style={{ fontSize: 11, color: "var(--color-text-tertiary)" }}>{w.rejection_reason}</div>}
                      </td>
                      <td className="nowrap">{formatDate(w.value_date)}</td>
                      <td style={{ fontSize: 12 }}>{w.requested_by}{w.decided_by && <> → {w.decided_by}</>}</td>
                      <td className="text-end text-nowrap">
                        {isAdmin && w.status === "pending" && (isOwn(w) ? (
                          <span style={{ fontSize: 11, color: "var(--color-text-tertiary)" }}>Needs another admin</span>
                        ) : (
                          <>
                            <button className="btn btn-sm btn-primary me-1" onClick={() => setApproveTarget(w)}>Approve</button>
                            <button className="btn btn-sm btn-outline-danger" onClick={() => setRejectTarget(w)}>Reject</button>
                          </>
                        ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {tab === "interest" && payouts && (
        <Card title="Interest payouts">
          {payouts.length === 0 ? <EmptyState message="No approved interest yet." /> : (
            <div className="app-table-scroll">
              <table className="table app-table align-middle mb-0">
                <thead>
                  <tr><th>Month</th><th className="text-end">Average balance</th><th>Rate</th><th className="text-end">Interest</th><th>Payment</th><th /></tr>
                </thead>
                <tbody>
                  {payouts.map((p) => (
                    <tr key={p.id}>
                      <td><Link to={ROUTES.INTEREST_PERIOD(p.period_id)}>{p.period_label}</Link></td>
                      <td className="text-end font-tabular">{formatKES(p.average_daily_balance)}</td>
                      <td className="nowrap">{formatRate(p.rate_percent)}</td>
                      <td className="text-end font-tabular fw-semibold">{formatKES(p.net_interest)}</td>
                      <td>
                        <StatusBadge status={p.status} />
                        {p.payment_reference && <div style={{ fontSize: 11, color: "var(--color-text-tertiary)" }}>{p.payment_reference} · {formatDate(p.paid_at)}</div>}
                      </td>
                      <td className="text-end">
                        <button className="btn btn-sm btn-outline-secondary d-inline-flex align-items-center gap-1"
                          onClick={() => interestService.openStatement(p).catch((err) => toast.error(apiErrorMessage(err)))}>
                          <FileText size={13} /> Statement
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {tab === "emails" && emails && (
        <Card title="Emails sent to this investor">
          {emails.length === 0 ? <EmptyState message="No emails yet." /> : (
            <div className="app-table-scroll">
              <table className="table app-table align-middle mb-0">
                <thead><tr><th>Queued</th><th>Subject</th><th>Status</th><th>Sent</th></tr></thead>
                <tbody>
                  {emails.map((e) => (
                    <tr key={e.id}>
                      <td style={{ fontSize: 12 }}>{formatDateTime(e.queued_at)}</td>
                      <td>{e.subject}</td>
                      <td>
                        <StatusBadge status={e.status} />
                        {e.last_error && <div style={{ fontSize: 11, color: "var(--color-text-tertiary)" }}>{e.last_error}</div>}
                      </td>
                      <td style={{ fontSize: 12 }}>{formatDateTime(e.sent_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {tab === "details" && (
        <Card
          title="Investor details"
          actions={
            <div className="d-flex gap-2">
              <button className="btn btn-sm btn-outline-secondary d-flex align-items-center gap-1" onClick={() => setModal("edit")}>
                <Pencil size={13} /> Edit
              </button>
              {isAdmin && (
                <button className={`btn btn-sm ${active ? "btn-outline-danger" : "btn-outline-secondary"}`} onClick={() => setModal("close")}>
                  {active ? "Close account" : "Reopen account"}
                </button>
              )}
            </div>
          }
        >
          <dl className="row mb-0" style={{ fontSize: 13 }}>
            {[
              ["Client code", investor.client_code],
              ["Email", investor.email],
              ["Phone", investor.phone],
              ["National ID / passport", investor.id_number],
              ["KRA PIN", investor.kra_pin],
              ["Pay out to", investor.payout_method === "bank"
                ? `${investor.bank_name ?? "Bank"} · ${investor.payout_account ?? "—"}`
                : investor.payout_method === "mpesa" ? `M-Pesa · ${investor.payout_account ?? "—"}` : null],
              ["Notes", investor.notes],
              ["Created", `${formatDateTime(investor.created_at)} by ${investor.created_by}`],
              ["Closed", investor.closed_at ? formatDateTime(investor.closed_at) : null],
            ].map(([label, value]) => (
              <div className="col-md-6 d-flex py-1" key={label}>
                <dt className="fw-normal me-2" style={{ width: 170, color: "var(--color-text-secondary)", flexShrink: 0 }}>{label}</dt>
                <dd className="mb-0">{value || "—"}</dd>
              </div>
            ))}
          </dl>
        </Card>
      )}

      <Modal title="Send statement" open={modal === "email"} onClose={() => setModal(null)} submitting={saving}
        submitLabel="Generate statement" onSubmit={async () => {
          setSaving(true);
          try {
            const res = await emailService.generateStatement(investor.id);
            toast.success(res.message, {
              action: { label: "Open Emails", onClick: () => navigate(`${ROUTES.EMAILS}?status=pending`) },
            });
            setModal(null);
            load();
          } catch (err) {
            toast.error(apiErrorMessage(err));
          } finally {
            setSaving(false);
          }
        }}>
        <p style={{ fontSize: 14 }}>
          This creates a PDF statement of {investor.full_name.split(" ")[0]}'s account <strong>as of today</strong>:
          balance, totals, interest paid and due, and every transaction.
        </p>
        <p className="mb-0" style={{ fontSize: 14 }}>
          It is <strong>not sent yet</strong>. It waits on the Emails page, where an admin checks the PDF and either
          confirms it (it goes to {investor.email}) or suppresses it.
        </p>
      </Modal>
      <RecordDepositModal open={modal === "deposit"} onClose={() => setModal(null)} onDone={load} investor={asListItem} />
      <RequestWithdrawalModal open={modal === "withdrawal"} onClose={() => setModal(null)} onDone={load} investor={asListItem} />
      <ReverseDepositModal deposit={reverseTarget} onClose={() => setReverseTarget(null)} onDone={load} />
      <ApproveWithdrawalModal withdrawal={approveTarget} onClose={() => setApproveTarget(null)} onDone={load} />
      <RejectWithdrawalModal withdrawal={rejectTarget} onClose={() => setRejectTarget(null)} onDone={load} />

      <Modal title="Edit investor" open={modal === "edit"} onClose={() => setModal(null)} wide>
        <InvestorForm
          initial={investor}
          submitLabel="Save changes"
          submitting={saving}
          onCancel={() => setModal(null)}
          onSubmit={async (data) => {
            setSaving(true);
            try {
              const res = await investorService.update(investor.id, data);
              toast.success(res.message);
              setModal(null);
              load();
            } catch (err) {
              toast.error(apiErrorMessage(err));
            } finally {
              setSaving(false);
            }
          }}
        />
      </Modal>

      <Modal title={active ? "Close account" : "Reopen account"} open={modal === "close"} onClose={() => setModal(null)}
        onSubmit={toggleStatus} submitLabel={active ? "Close account" : "Reopen"} submitVariant={active ? "danger" : "primary"} submitting={saving}>
        <p style={{ fontSize: 13 }} className="mb-0">
          {active
            ? "Closing is only possible when the balance is zero, nothing is pending and all interest has been paid out. A closed account can't take new deposits."
            : "Reopening lets the account take deposits again."}
        </p>
      </Modal>
    </div>
  );
}
