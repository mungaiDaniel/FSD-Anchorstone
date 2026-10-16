"""
PDF interest statements (ReportLab).

Kept from OFDS's PDFStatementGenerator: the class shape, key/value and history
table styles, header/footer pattern. Retargeted from NAV/share statements to
the Anchorstone interest statement. Colours come from app/utils/brand.py.
"""
import io
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List
from xml.sax.saxutils import escape

from flask import current_app
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.utils import brand

CONTENT_WIDTH = 7.0 * inch


def _hex(value: str):
    return colors.HexColor(value)


def _kes(amount) -> str:
    return f"KES {Decimal(amount or 0):,.2f}"


def _date(d) -> str:
    return d.strftime("%d %b %Y") if d else "—"


class PDFStatementGenerator:
    STATEMENT_TYPE_INTEREST = "interest"
    STATEMENT_TYPE_ACCOUNT = "account"  # on demand, "as of" a date

    def __init__(self, statement_data: Dict[str, Any]):
        self.data = statement_data
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        base = self.styles
        self.title_style = ParagraphStyle("Title", parent=base["Heading1"], fontSize=17,
                                          textColor=_hex(brand.PRIMARY), spaceAfter=4, alignment=TA_LEFT,
                                          fontName="Helvetica-Bold")
        self.subtitle_style = ParagraphStyle("Subtitle", parent=base["Normal"], fontSize=10,
                                             textColor=_hex(brand.TEXT_MUTED), spaceAfter=10)
        self.heading_style = ParagraphStyle("Heading", parent=base["Heading2"], fontSize=11.5,
                                            textColor=_hex(brand.PRIMARY), spaceBefore=6, spaceAfter=6,
                                            fontName="Helvetica-Bold")
        self.normal_style = ParagraphStyle("Body", parent=base["Normal"], fontSize=9.5,
                                           textColor=_hex(brand.TEXT), leading=13)
        self.small_right = ParagraphStyle("SmallRight", parent=base["Normal"], fontSize=8,
                                          textColor=_hex(brand.TEXT_MUTED), alignment=TA_RIGHT, leading=10)
        self.footer_style = ParagraphStyle("Footer", parent=base["Normal"], fontSize=8,
                                           textColor=_hex(brand.TEXT_MUTED), leading=11)
        self.wordmark_style = ParagraphStyle("Wordmark", parent=base["Normal"], fontSize=19,
                                             textColor=_hex(brand.PRIMARY), fontName=brand.PDF_WORDMARK_FONT, leading=23)

    def _kv_table_style(self) -> TableStyle:
        return TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), _hex(brand.SURFACE_ALT)),
            ("TEXTCOLOR", (0, 0), (0, -1), _hex(brand.PRIMARY)),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9.5),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("GRID", (0, 0), (-1, -1), 0.5, _hex(brand.BORDER)),
        ])

    def _history_table_style(self, n_rows: int) -> TableStyle:
        return TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), _hex(brand.PRIMARY)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, -1), 0.4, _hex(brand.BORDER)),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _hex(brand.SURFACE_ALT)]),
            ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
            ("FONTNAME", (0, n_rows - 1), (-1, n_rows - 1), "Helvetica-Bold"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ])

    def generate(self) -> bytes:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=0.65 * inch, rightMargin=0.65 * inch,
                                topMargin=0.55 * inch, bottomMargin=0.55 * inch,
                                title=self._title(), author=brand.COMPANY_NAME)
        if self.data.get("statement_type") == self.STATEMENT_TYPE_ACCOUNT:
            story = self._build_account_statement()
        else:
            story = self._build_interest_statement()
        doc.build(story)
        return buffer.getvalue()

    def _title(self) -> str:
        if self.data.get("statement_type") == self.STATEMENT_TYPE_ACCOUNT:
            return f"Account Statement {_date(self.data['as_of'])}"
        return f"Interest Statement {self.data['period']['label']}"

    def _build_header_section(self, title: str | None = None, subtitle: str | None = None) -> List[Any]:
        logo = brand.logo_path()
        left = Image(str(logo), width=150, height=45, kind="proportional") if logo else Paragraph(
            escape(brand.COMPANY_NAME), self.wordmark_style)
        address = current_app.config.get("COMPANY_ADDRESS") or ""
        contact = current_app.config.get("COMPANY_CONTACT") or ""
        right = Paragraph("<br/>".join(escape(x) for x in (address, contact) if x) or "&nbsp;", self.small_right)
        header = Table([[left, right]], colWidths=[3.6 * inch, 3.4 * inch])
        header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                    ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
        divider = Table([[""]], colWidths=[CONTENT_WIDTH],
                        style=[("LINEBELOW", (0, 0), (-1, -1), 1.2, _hex(brand.PRIMARY))])
        if title is None:
            period = self.data["period"]
            title = f"Interest Statement — {escape(period['label'])}"
            subtitle = f"Period {_date(period['start'])} to {_date(period['end'])}"
        return [
            header, Spacer(1, 4), divider, Spacer(1, 12),
            Paragraph(title, self.title_style),
            Paragraph(subtitle or "", self.subtitle_style),
        ]

    @staticmethod
    def _payout_to(inv: Dict[str, Any]) -> str:
        if inv.get("payout_method") == "mpesa":
            return f"M-Pesa {inv.get('payout_account') or ''}".strip()
        if inv.get("payout_method") == "bank":
            return " ".join(x for x in (inv.get("bank_name"), inv.get("payout_account")) if x) or "Bank"
        return "—"

    def _footer(self) -> Any:
        divider = Table([[""]], colWidths=[CONTENT_WIDTH],
                        style=[("LINEBELOW", (0, 0), (-1, -1), 0.5, _hex(brand.BORDER))])
        footer = Paragraph(
            "Interest is simple interest, calculated daily on your closing balance at the stated annual "
            "rate on a 365-day basis, and paid out monthly. It is not added to your balance. Please report "
            "any discrepancy to us promptly.<br/>"
            f"Generated {datetime.now(timezone.utc).strftime('%d %B %Y %H:%M UTC')} · {escape(brand.COMPANY_NAME)}",
            self.footer_style)
        return KeepTogether([divider, Spacer(1, 4), footer])

    def _build_account_statement(self) -> List[Any]:
        d = self.data
        inv, totals, ledger, payouts = d["investor"], d["totals"], d["ledger"], d["payouts"]
        as_of = d["as_of"]
        story = self._build_header_section(
            "Account Statement", f"As of {_date(as_of)} · all transactions since the account opened")

        t = Table([
            ["Investor", Paragraph(escape(inv["full_name"]), self.normal_style)],
            ["Account", inv["client_code"]],
            ["Statement date", _date(as_of)],
            ["Interest paid to", Paragraph(escape(self._payout_to(inv)), self.normal_style)],
        ], colWidths=[2.2 * inch, 4.8 * inch])
        t.setStyle(self._kv_table_style())
        story += [Paragraph("Account details", self.heading_style), t, Spacer(1, 10)]

        summary = [
            ["Current balance", _kes(totals["balance"])],
            ["Total deposited", _kes(totals["total_deposited"])],
            ["Total withdrawn", _kes(totals["total_withdrawn"])],
        ]
        if totals["pending_withdrawals"] > 0:
            summary.append(["Withdrawals awaiting approval", _kes(totals["pending_withdrawals"])])
        summary += [
            ["Interest paid to date", _kes(totals["interest_paid"])],
            ["Interest due (approved, not yet paid)", _kes(totals["interest_payable"])],
            ["Current interest rate",
             f"{d['rate_percent']:.2f}% p.a." if d.get("rate_percent") is not None else "—"],
        ]
        t = Table(summary, colWidths=[2.8 * inch, 4.2 * inch])
        style = self._kv_table_style()
        style.add("FONTNAME", (1, 0), (1, 0), "Helvetica-Bold")
        t.setStyle(style)
        story += [Paragraph("Summary", self.heading_style), t, Spacer(1, 10)]

        rows = [["Date", "Description", "Reference", "Deposit", "Withdrawal", "Balance"]]
        for e in ledger["entries"]:
            is_dep = e["kind"] == "deposit"
            rows.append([
                _date(e["date"]),
                "Deposit" if is_dep else "Withdrawal",
                Paragraph(escape(e["reference"] or ""), self.normal_style),
                _kes(e["amount"]) if is_dep else "",
                "" if is_dep else _kes(-e["amount"]),
                _kes(e["balance"]),
            ])
        rows.append([_date(as_of), "Balance today", "", "", "", _kes(ledger["closing_balance"])])
        t = Table(rows, colWidths=[0.85 * inch, 1.05 * inch, 1.5 * inch, 1.2 * inch, 1.2 * inch, 1.2 * inch],
                  repeatRows=1)
        style = self._history_table_style(len(rows))
        if len(rows) > 2:
            style.add("FONTNAME", (0, 1), (-1, 1), "Helvetica")  # first row is a transaction, not a total
        t.setStyle(style)
        story += [Paragraph("Deposits and withdrawals", self.heading_style), t, Spacer(1, 10)]

        if payouts:
            prow = [["Month", "Average balance", "Rate", "Interest", "Status"]]
            for p in payouts:
                status = f"Paid {_date(p['paid_at'])}" if p["status"] == "paid" else "Due"
                prow.append([p["label"], _kes(p["average_daily_balance"]), f"{p['rate_percent']:.2f}%",
                             _kes(p["net_interest"]), status])
            t = Table(prow, colWidths=[1.4 * inch, 1.7 * inch, 0.9 * inch, 1.5 * inch, 1.5 * inch], repeatRows=1)
            style = self._history_table_style(len(prow))
            style.add("FONTNAME", (0, 1), (-1, -1), "Helvetica")  # no total rows in this table
            style.add("ALIGN", (1, 0), (3, -1), "RIGHT")
            t.setStyle(style)
            story += [Paragraph("Interest history", self.heading_style), t, Spacer(1, 10)]

        story.append(self._footer())
        return story

    def _build_interest_statement(self) -> List[Any]:
        d = self.data
        inv, payout, ledger, to_date = d["investor"], d["payout"], d["ledger"], d["to_date"]
        story = self._build_header_section()

        payout_to = self._payout_to(inv)

        account_rows = [
            ["Investor", Paragraph(escape(inv["full_name"]), self.normal_style)],
            ["Account", inv["client_code"]],
            ["Statement date", datetime.now(timezone.utc).strftime("%d %b %Y")],
            ["Interest paid to", Paragraph(escape(payout_to), self.normal_style)],
        ]
        t = Table(account_rows, colWidths=[2.2 * inch, 4.8 * inch])
        t.setStyle(self._kv_table_style())
        story += [Paragraph("Account details", self.heading_style), t, Spacer(1, 10)]

        if payout["status"] == "paid":
            status = f"Paid on {_date(payout['paid_at'])} (ref {payout['payment_reference']})"
        else:
            status = "Approved — payment pending"
        interest_rows = [
            ["Opening balance", _kes(payout["opening_balance"])],
            ["Closing balance", _kes(payout["closing_balance"])],
            ["Average daily balance", _kes(payout["average_daily_balance"])],
            ["Days in period", str(payout["days"])],
            ["Interest rate", f"{payout['rate_percent']:.2f}% p.a."],
            ["Interest for the period", _kes(payout["net_interest"])],
            ["Payment status", status],
        ]
        # Withholding tax rows appear only once a tax rate is actually applied.
        if payout["tax_rate_percent"] > 0:
            interest_rows[5:6] = [
                ["Gross interest", _kes(payout["gross_interest"])],
                [f"Withholding tax ({payout['tax_rate_percent']:.2f}%)", f"-{_kes(payout['tax_amount'])}"],
                ["Net interest", _kes(payout["net_interest"])],
            ]
        t = Table(interest_rows, colWidths=[2.2 * inch, 4.8 * inch])
        style = self._kv_table_style()
        net_row = next(i for i, r in enumerate(interest_rows) if r[0] in ("Interest for the period", "Net interest"))
        style.add("FONTNAME", (1, net_row), (1, net_row), "Helvetica-Bold")
        t.setStyle(style)
        story += [Paragraph("Interest summary", self.heading_style), t, Spacer(1, 10)]

        rows = [["Date", "Description", "Reference", "Deposit", "Withdrawal", "Balance"],
                [_date(d["period"]["start"]), "Opening balance", "", "", "", _kes(ledger["opening_balance"])]]
        for e in ledger["entries"]:
            is_dep = e["kind"] == "deposit"
            rows.append([
                _date(e["date"]),
                "Deposit" if is_dep else "Withdrawal",
                Paragraph(escape(e["reference"] or ""), self.normal_style),
                _kes(e["amount"]) if is_dep else "",
                "" if is_dep else _kes(-e["amount"]),
                _kes(e["balance"]),
            ])
        rows.append([_date(d["period"]["end"]), "Closing balance", "", "", "", _kes(ledger["closing_balance"])])
        t = Table(rows, colWidths=[0.85 * inch, 1.05 * inch, 1.5 * inch, 1.2 * inch, 1.2 * inch, 1.2 * inch],
                  repeatRows=1)
        t.setStyle(self._history_table_style(len(rows)))
        story += [Paragraph("Deposits and withdrawals in this period", self.heading_style), t, Spacer(1, 10)]

        totals_rows = [
            ["Total deposited", _kes(to_date["total_deposited"])],
            ["Total withdrawn", _kes(to_date["total_withdrawn"])],
            ["Interest paid out to date", _kes(to_date["interest_paid_to_date"])],
        ]
        t = Table(totals_rows, colWidths=[2.2 * inch, 4.8 * inch])
        t.setStyle(self._kv_table_style())
        story += [Paragraph(f"Account to {_date(d['period']['end'])}", self.heading_style), t, Spacer(1, 8)]

        story.append(self._footer())
        return story


def generate_interest_statement_pdf(payout_id: int) -> bytes:
    from app.Interest.statement import build_interest_statement_data
    return PDFStatementGenerator(build_interest_statement_data(payout_id)).generate()


def generate_account_statement_pdf(investor_id: int) -> bytes:
    """Statement of the account as of today (on demand, not tied to a month)."""
    from app.Interest.statement import build_account_statement_data
    return PDFStatementGenerator(build_account_statement_data(investor_id)).generate()
