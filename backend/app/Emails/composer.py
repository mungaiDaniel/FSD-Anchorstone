"""
Builds the transaction and statement emails and adds them to the outbox.

The queue_* functions add the OutboxEmail to the current session WITHOUT
committing — callers commit it together with the deposit / withdrawal /
period approval that triggered it, so an email can never exist for a
transaction that was rolled back (or vice versa).

Bodies are plain text; app/utils/email_template.py renders them into the
branded HTML layout at send time ("•" lines become bullet lists, short
ALL-CAPS lines become section headings).
"""
from flask import current_app

from app.database.database import db
from app.Emails.model import (
    EMAIL_DEPOSIT_CONFIRMATION,
    EMAIL_DEPOSIT_REVERSAL,
    EMAIL_INTEREST_STATEMENT,
    EMAIL_WITHDRAWAL_CONFIRMATION,
    EmailAttachment,
    OutboxEmail,
)
from app.Transactions.ledger import balance_as_of
from app.utils.money import fmt_kes

METHOD_LABELS = {
    "bank_transfer": "Bank transfer",
    "mpesa": "M-Pesa",
    "cheque": "Cheque",
    "cash": "Cash",
}


def _company() -> str:
    return current_app.config.get("COMPANY_NAME", "Anchorstone Capital Ltd")


def _sign_off() -> str:
    return (
        "If anything in this email doesn't match your records, please contact us right away.\n\n"
        f"Kind regards,\n{_company()}"
    )


def _fmt_date(d) -> str:
    return d.strftime("%d %B %Y")


def queue_deposit_confirmation(deposit, actor: str | None) -> OutboxEmail:
    investor = deposit.investor
    balance = balance_as_of(investor.id)
    body = (
        f"Dear {investor.full_name},\n\n"
        f"We confirm receipt of your deposit into your {_company()} account.\n\n"
        "DEPOSIT DETAILS\n\n"
        f"• Amount: {fmt_kes(deposit.amount)}\n"
        f"• Date received: {_fmt_date(deposit.value_date)}\n"
        f"• Method: {METHOD_LABELS.get(deposit.method, deposit.method)}\n"
        f"• Reference: {deposit.reference}\n"
        f"• Account: {investor.client_code}\n\n"
        f"Your account balance is now {fmt_kes(balance)}. "
        "Interest is calculated daily on your balance and paid out monthly.\n\n"
        f"{_sign_off()}"
    )
    email = OutboxEmail(
        email_type=EMAIL_DEPOSIT_CONFIRMATION,
        investor_id=investor.id,
        deposit_id=deposit.id,
        recipient_email=investor.email,
        recipient_name=investor.full_name,
        subject=f"Deposit confirmation — {fmt_kes(deposit.amount)} received",
        body=body,
        created_by=actor,
    )
    db.session.add(email)
    return email


def queue_deposit_reversal_notice(deposit, actor: str | None) -> OutboxEmail:
    """Tells the investor that a deposit they were already sent a confirmation
    for has been reversed. The internal reversal reason is not included."""
    investor = deposit.investor
    balance = balance_as_of(investor.id)
    body = (
        f"Dear {investor.full_name},\n\n"
        f"A deposit recorded on your {_company()} account has been reversed, so the confirmation "
        "we sent you for it no longer applies.\n\n"
        "REVERSED DEPOSIT\n\n"
        f"• Amount: {fmt_kes(deposit.amount)}\n"
        f"• Date received: {_fmt_date(deposit.value_date)}\n"
        f"• Method: {METHOD_LABELS.get(deposit.method, deposit.method)}\n"
        f"• Reference: {deposit.reference}\n"
        f"• Account: {investor.client_code}\n\n"
        f"Your account balance is now {fmt_kes(balance)}.\n\n"
        f"{_sign_off()}"
    )
    email = OutboxEmail(
        email_type=EMAIL_DEPOSIT_REVERSAL,
        investor_id=investor.id,
        deposit_id=deposit.id,
        recipient_email=investor.email,
        recipient_name=investor.full_name,
        subject=f"Deposit reversed — {fmt_kes(deposit.amount)} ({deposit.reference})",
        body=body,
        created_by=actor,
    )
    db.session.add(email)
    return email


def queue_withdrawal_confirmation(withdrawal, actor: str | None) -> OutboxEmail:
    investor = withdrawal.investor
    balance = balance_as_of(investor.id)
    lines = [
        f"• Amount: {fmt_kes(withdrawal.amount)}",
        f"• Effective date: {_fmt_date(withdrawal.value_date)}",
        f"• Method: {METHOD_LABELS.get(withdrawal.method, withdrawal.method)}",
    ]
    if withdrawal.payment_reference:
        lines.append(f"• Payment reference: {withdrawal.payment_reference}")
    lines.append(f"• Account: {investor.client_code}")
    body = (
        f"Dear {investor.full_name},\n\n"
        f"Your withdrawal from your {_company()} account has been approved and processed.\n\n"
        "WITHDRAWAL DETAILS\n\n"
        + "\n".join(lines)
        + "\n\n"
        f"Your account balance is now {fmt_kes(balance)}.\n\n"
        f"{_sign_off()}"
    )
    email = OutboxEmail(
        email_type=EMAIL_WITHDRAWAL_CONFIRMATION,
        investor_id=investor.id,
        withdrawal_id=withdrawal.id,
        recipient_email=investor.email,
        recipient_name=investor.full_name,
        subject=f"Withdrawal confirmation — {fmt_kes(withdrawal.amount)}",
        body=body,
        created_by=actor,
    )
    db.session.add(email)
    return email


def queue_interest_statement(payout, actor: str | None) -> OutboxEmail:
    """The statement PDF is generated now, when the month is approved, and
    stored with the email: later edits (an investor's name or payout account,
    say) can't change a statement that has already been issued. The caller
    must have flushed the period's approval first."""
    from app.utils.pdf_generator import generate_interest_statement_pdf, interest_statement_filename

    investor = payout.investor
    period = payout.period
    body = (
        f"Dear {investor.full_name},\n\n"
        f"Please find attached your {_company()} interest statement for {period.label}.\n\n"
        "SUMMARY\n\n"
        f"• Interest period: {_fmt_date(period.period_start)} – {_fmt_date(period.period_end)}\n"
        f"• Balance at period end: {fmt_kes(payout.closing_balance)}\n"
        f"• Average daily balance: {fmt_kes(payout.average_daily_balance)}\n"
        f"• Interest rate: {payout.rate_percent:.2f}% p.a.\n"
        f"• Interest for the period: {fmt_kes(payout.net_interest)}\n\n"
        "Interest is paid out to your nominated account and is not added to your balance. "
        "The attached statement lists every deposit and withdrawal in the period.\n\n"
        f"{_sign_off()}"
    )
    email = OutboxEmail(
        email_type=EMAIL_INTEREST_STATEMENT,
        investor_id=investor.id,
        payout_id=payout.id,
        recipient_email=investor.email,
        recipient_name=investor.full_name,
        subject=f"Your interest statement — {period.label}",
        body=body,
        created_by=actor,
    )
    email.attachment = EmailAttachment(
        filename=interest_statement_filename(payout),
        content_type="application/pdf",
        data=generate_interest_statement_pdf(payout.id),
    )
    db.session.add(email)
    return email
