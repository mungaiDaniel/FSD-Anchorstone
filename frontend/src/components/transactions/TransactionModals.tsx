import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Modal } from "@/components/ui/Modal";
import { Field } from "@/components/ui/Page";
import { InvestorPicker } from "@/components/forms/InvestorPicker";
import { transactionService } from "@/services";
import type { Deposit, InvestorListItem, PaymentMethod, Withdrawal } from "@/lib/types";
import { PAYMENT_METHOD_LABELS } from "@/lib/constants";
import { apiErrorMessage, formatDate, formatKES, todayISO } from "@/lib/utils";

const AMOUNT_RE = /^\d+(\.\d{1,2})?$/;

function MethodSelect({ value, onChange }: { value: PaymentMethod; onChange: (m: PaymentMethod) => void }) {
  return (
    <select className="form-select" value={value} onChange={(e) => onChange(e.target.value as PaymentMethod)}>
      {(Object.keys(PAYMENT_METHOD_LABELS) as PaymentMethod[]).map((m) => (
        <option key={m} value={m}>{PAYMENT_METHOD_LABELS[m]}</option>
      ))}
    </select>
  );
}

function cleanAmount(raw: string) {
  return raw.replace(/,/g, "").trim();
}

// ── Record deposit ──

export function RecordDepositModal({
  open,
  onClose,
  onDone,
  investor,
}: {
  open: boolean;
  onClose: () => void;
  onDone: () => void;
  investor?: InvestorListItem | null;
}) {
  const [picked, setPicked] = useState<InvestorListItem | null>(investor ?? null);
  const [amount, setAmount] = useState("");
  const [valueDate, setValueDate] = useState(todayISO());
  const [method, setMethod] = useState<PaymentMethod>("bank_transfer");
  const [reference, setReference] = useState("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) {
      setPicked(investor ?? null);
      setAmount("");
      setValueDate(todayISO());
      setMethod("bank_transfer");
      setReference("");
      setNotes("");
    }
  }, [open, investor]);

  const amountValid = AMOUNT_RE.test(cleanAmount(amount)) && Number(cleanAmount(amount)) > 0;
  const canSubmit = !!picked && amountValid && !!valueDate && reference.trim().length > 0;

  const submit = async () => {
    if (!picked) return;
    setSubmitting(true);
    try {
      const res = await transactionService.recordDeposit({
        investor_id: picked.id,
        amount: cleanAmount(amount),
        value_date: valueDate,
        method,
        reference: reference.trim(),
        notes: notes.trim() || undefined,
      });
      toast.success(res.message);
      onDone();
      onClose();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal title="Record deposit" open={open} onClose={onClose} onSubmit={submit} submitLabel="Record deposit"
      submitting={submitting} submitDisabled={!canSubmit}>
      {!investor && (
        <Field label="Investor">
          <InvestorPicker value={picked} onChange={setPicked} />
        </Field>
      )}
      <div className="row g-2">
        <div className="col-sm-6">
          <Field label="Amount (KES)" error={amount && !amountValid ? "Enter an amount with up to 2 decimals." : undefined}>
            <input className="form-control font-tabular" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0.00" />
          </Field>
        </div>
        <div className="col-sm-6">
          <Field label="Date received">
            <input type="date" className="form-control" value={valueDate} max={todayISO()} onChange={(e) => setValueDate(e.target.value)} />
          </Field>
        </div>
        <div className="col-sm-6">
          <Field label="Method">
            <MethodSelect value={method} onChange={setMethod} />
          </Field>
        </div>
        <div className="col-sm-6">
          <Field label="Reference" hint="Bank, M-Pesa or cheque reference — must be unique.">
            <input className="form-control" value={reference} onChange={(e) => setReference(e.target.value)} maxLength={100} />
          </Field>
        </div>
      </div>
      <Field label="Notes (optional)">
        <textarea className="form-control" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </Field>
      <p className="mb-0" style={{ fontSize: 12, color: "var(--color-text-tertiary)" }}>
        The investor is emailed a deposit confirmation automatically.
      </p>
    </Modal>
  );
}

// ── Request withdrawal ──

export function RequestWithdrawalModal({
  open,
  onClose,
  onDone,
  investor,
}: {
  open: boolean;
  onClose: () => void;
  onDone: () => void;
  investor?: InvestorListItem | null;
}) {
  const [picked, setPicked] = useState<InvestorListItem | null>(investor ?? null);
  const [amount, setAmount] = useState("");
  const [requestedDate, setRequestedDate] = useState(todayISO());
  const [method, setMethod] = useState<PaymentMethod>("mpesa");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) {
      setPicked(investor ?? null);
      setAmount("");
      setRequestedDate(todayISO());
      setMethod(investor?.payout_method === "bank" ? "bank_transfer" : "mpesa");
      setNotes("");
    }
  }, [open, investor]);

  const available = picked ? Number(picked.balance) - Number(picked.pending_withdrawals) : 0;
  const value = Number(cleanAmount(amount));
  const amountValid = AMOUNT_RE.test(cleanAmount(amount)) && value > 0;
  const tooMuch = amountValid && value > available;

  const submit = async () => {
    if (!picked) return;
    setSubmitting(true);
    try {
      const res = await transactionService.requestWithdrawal({
        investor_id: picked.id,
        amount: cleanAmount(amount),
        requested_date: requestedDate,
        method,
        notes: notes.trim() || undefined,
      });
      toast.success(res.message);
      onDone();
      onClose();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal title="Record withdrawal request" open={open} onClose={onClose} onSubmit={submit} submitLabel="Submit for approval"
      submitting={submitting} submitDisabled={!picked || !amountValid || tooMuch}>
      {!investor && (
        <Field label="Investor">
          <InvestorPicker value={picked} onChange={setPicked} />
        </Field>
      )}
      {picked && (
        <p style={{ fontSize: 12, color: "var(--color-text-secondary)" }}>
          Available to withdraw: <strong className="font-tabular">{formatKES(available)}</strong>
          {Number(picked.pending_withdrawals) > 0 && <> (after {formatKES(picked.pending_withdrawals)} already pending)</>}
        </p>
      )}
      <div className="row g-2">
        <div className="col-sm-6">
          <Field label="Amount (KES)" error={tooMuch ? "More than the available balance." : amount && !amountValid ? "Enter an amount with up to 2 decimals." : undefined}>
            <input className="form-control font-tabular" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0.00" />
          </Field>
        </div>
        <div className="col-sm-6">
          <Field label="Date requested">
            <input type="date" className="form-control" value={requestedDate} max={todayISO()} onChange={(e) => setRequestedDate(e.target.value)} />
          </Field>
        </div>
      </div>
      <Field label="Pay out by">
        <MethodSelect value={method} onChange={setMethod} />
      </Field>
      <Field label="Notes (optional)">
        <textarea className="form-control" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </Field>
      <p className="mb-0" style={{ fontSize: 12, color: "var(--color-text-tertiary)" }}>
        The balance isn't reduced until a different admin approves this request. The investor is emailed once it's approved.
      </p>
    </Modal>
  );
}

// ── Approve / reject withdrawal (checker) ──

export function ApproveWithdrawalModal({ withdrawal, onClose, onDone }: { withdrawal: Withdrawal | null; onClose: () => void; onDone: () => void }) {
  const [valueDate, setValueDate] = useState(todayISO());
  const [reference, setReference] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (withdrawal) {
      setValueDate(todayISO());
      setReference("");
    }
  }, [withdrawal]);

  if (!withdrawal) return null;

  const submit = async () => {
    setSubmitting(true);
    try {
      const res = await transactionService.approveWithdrawal(withdrawal.id, {
        value_date: valueDate,
        payment_reference: reference.trim() || undefined,
      });
      toast.success(res.message);
      onDone();
      onClose();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal title="Approve withdrawal" open onClose={onClose} onSubmit={submit} submitLabel={`Approve ${formatKES(withdrawal.amount)}`}
      submitVariant="primary" submitting={submitting}>
      <p style={{ fontSize: 13 }}>
        <strong>{withdrawal.investor_name}</strong> ({withdrawal.client_code}) requested{" "}
        <strong className="font-tabular">{formatKES(withdrawal.amount)}</strong> on {formatDate(withdrawal.requested_date)}, recorded by{" "}
        {withdrawal.requested_by}.
      </p>
      <Field label="Effective date" hint="The balance is reduced from this date. Defaults to today.">
        <input type="date" className="form-control" value={valueDate} min={withdrawal.requested_date} max={todayISO()}
          onChange={(e) => setValueDate(e.target.value)} />
      </Field>
      <Field label="Payment reference (optional)" hint="Included in the investor's confirmation email.">
        <input className="form-control" value={reference} onChange={(e) => setReference(e.target.value)} maxLength={100} />
      </Field>
    </Modal>
  );
}

export function ReasonModal({
  title,
  description,
  submitLabel,
  open,
  onClose,
  onConfirm,
}: {
  title: string;
  description: React.ReactNode;
  submitLabel: string;
  open: boolean;
  onClose: () => void;
  onConfirm: (reason: string) => Promise<void>;
}) {
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) setReason("");
  }, [open]);

  const submit = async () => {
    setSubmitting(true);
    try {
      await onConfirm(reason.trim());
      onClose();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal title={title} open={open} onClose={onClose} onSubmit={submit} submitLabel={submitLabel} submitVariant="danger"
      submitting={submitting} submitDisabled={!reason.trim()}>
      <div style={{ fontSize: 13 }} className="mb-3">{description}</div>
      <Field label="Reason (recorded in the audit log)">
        <textarea className="form-control" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
    </Modal>
  );
}

export function ReverseDepositModal({ deposit, onClose, onDone }: { deposit: Deposit | null; onClose: () => void; onDone: () => void }) {
  return (
    <ReasonModal
      title="Reverse deposit"
      open={!!deposit}
      onClose={onClose}
      submitLabel="Reverse deposit"
      description={
        deposit && (
          <>
            Reverse <strong className="font-tabular">{formatKES(deposit.amount)}</strong> for {deposit.investor_name} (
            {deposit.reference}, {formatDate(deposit.value_date)})? It stops counting toward the balance. The record is kept.
          </>
        )
      }
      onConfirm={async (reason) => {
        if (!deposit) return;
        const res = await transactionService.reverseDeposit(deposit.id, reason);
        toast.success(res.message);
        onDone();
      }}
    />
  );
}

export function RejectWithdrawalModal({ withdrawal, onClose, onDone }: { withdrawal: Withdrawal | null; onClose: () => void; onDone: () => void }) {
  return (
    <ReasonModal
      title="Reject withdrawal"
      open={!!withdrawal}
      onClose={onClose}
      submitLabel="Reject"
      description={
        withdrawal && (
          <>
            Reject the request for <strong className="font-tabular">{formatKES(withdrawal.amount)}</strong> from {withdrawal.investor_name}?
            No email is sent to the investor.
          </>
        )
      }
      onConfirm={async (reason) => {
        if (!withdrawal) return;
        const res = await transactionService.rejectWithdrawal(withdrawal.id, reason);
        toast.success(res.message);
        onDone();
      }}
    />
  );
}
