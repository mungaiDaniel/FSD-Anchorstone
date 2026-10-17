"""
Builds the synthetic AI-extraction fixtures (phase 3a). Run from backend/:

    venv/Scripts/python tests/fixtures/make_fixtures.py

documents/      sample files, every one stamped "SAMPLE — NOT A REAL DOCUMENT", with
                obviously fake names and numbers. Never put a real client document here.
ai_responses/   recorded API responses for those samples, written by hand (not from a
                real call). The answers match the samples; the token counts are realistic
                estimates for claude-opus-5-5, used for the cost-per-type figures.

The output is deterministic, so re-running it doesn't change committed files.
"""
import io
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

HERE = Path(__file__).parent
DOCS = HERE / "documents"
RESPONSES = HERE / "ai_responses"
STAMP = "SAMPLE — NOT A REAL DOCUMENT"
NAME = "TESTA SAMPLE MOCKERSON"
NOTE = ("SYNTHETIC recorded response for tests: written by hand for the matching file in "
        "tests/fixtures/documents (not a real client, not from a real API call). Token counts are "
        "realistic estimates for claude-opus-5-5.")


# ── Documents ──


def _font(size):
    for name in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def id_card(blurred=False) -> bytes:
    img = Image.new("RGB", (1000, 630), (226, 236, 228))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, 999, 90), fill=(30, 90, 50))
    d.text((30, 25), "REPUBLIC OF SAMPLELAND — NATIONAL IDENTITY CARD (SPECIMEN)", fill="white", font=_font(28))
    d.rectangle((40, 130, 300, 450), outline=(80, 80, 80), width=3)
    d.text((95, 270), "NO PHOTO", fill=(120, 120, 120), font=_font(30))
    lines = [("SERIAL NUMBER", "000000001"), ("ID NUMBER", "00000001"), ("FULL NAMES", NAME),
             ("DATE OF BIRTH", "01.01.1990"), ("SEX", "FEMALE"), ("DISTRICT OF BIRTH", "SAMPLE DISTRICT"),
             ("PLACE OF ISSUE", "SAMPLEVILLE"), ("DATE OF ISSUE", "15.06.2015")]
    y = 105
    for label, value in lines:
        d.text((340, y), label, fill=(60, 60, 60), font=_font(20))
        d.text((340, y + 22), value, fill=(0, 0, 0), font=_font(30))
        y += 58
    d.text((40, 596), STAMP, fill=(200, 0, 0), font=_font(26))
    if blurred:
        rnd = random.Random(7)
        img = img.filter(ImageFilter.GaussianBlur(14))
        px = img.load()
        for _ in range(60000):
            x, y = rnd.randrange(1000), rnd.randrange(630)
            v = rnd.randrange(256)
            px[x, y] = (v, v, v)
        img = img.filter(ImageFilter.GaussianBlur(3))
        ImageDraw.Draw(img).text((40, 596), STAMP, fill=(200, 0, 0), font=_font(26))
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


def _pdf(pages) -> bytes:
    """pages: list of (title, [lines]). Every page carries the SAMPLE stamp."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4, invariant=1)
    w, h = A4
    for n, (title, lines) in enumerate(pages, 1):
        c.setFont("Helvetica-Bold", 14)
        c.drawString(40, h - 50, title)
        c.setFont("Helvetica", 9)
        y = h - 80
        for line in lines:
            c.drawString(40, y, line)
            y -= 14
        c.setFont("Helvetica", 8)
        c.drawString(40, 30, f"Page {n} of {len(pages)}")
        c.saveState()
        c.setFillColorRGB(0.85, 0, 0)
        c.setFont("Helvetica-Bold", 30)
        c.translate(w / 2, h / 2)
        c.rotate(35)
        c.drawCentredString(0, 0, STAMP)
        c.restoreState()
        c.showPage()
    c.save()
    return buf.getvalue()


BANK_HEADER = ["SAMPLE BANK (NOT A REAL BANK) — SAMPLE BRANCH", f"Account name: {NAME}",
               "Account number: XXXXXX0000      Currency: KES", "Statement period: 01/07/2026 to 30/09/2026", "",
               f"{'Date':<12}{'Description':<40}{'Debit':>12}{'Credit':>12}{'Balance':>14}"]
BANK_PAGES = [
    ("50,000.00", [("01/07/2026", "SALARY SAMPLE EMPLOYER LTD", "", "80,000.00", "130,000.00"),
                   ("05/07/2026", "ATM WITHDRAWAL SAMPLE ATM", "10,000.00", "", "120,000.00"),
                   ("10/07/2026", "FULIZA REPAYMENT", "2,500.00", "", "117,500.00"),
                   ("14/07/2026", "CHEQUE DEPOSIT 000123", "", "5,000.00", "122,500.00"),
                   ("16/07/2026", "CHQ 000123 RTD INSUFF FUNDS", "5,000.00", "", "117,500.00"),
                   ("25/07/2026", "SAMPLE POWER PREPAID", "1,500.00", "", "116,000.00")], "116,000.00"),
    ("116,000.00", [("01/08/2026", "SALARY SAMPLE EMPLOYER LTD", "", "80,000.00", "196,000.00"),
                    ("03/08/2026", "TALA LOAN REPAYMENT", "4,000.00", "", "192,000.00"),
                    ("12/08/2026", "MPESA TRANSFER 0700000001", "30,000.00", "", "162,000.00"),
                    ("20/08/2026", "SAMPLE SUPERMARKET", "7,250.50", "", "154,749.50")], "154,749.50"),
    ("154,749.50", [("01/09/2026", "SALARY SAMPLE EMPLOYER LTD", "", "80,000.00", "234,749.50"),
                    ("04/09/2026", "FULIZA M-PESA REPAYMENT", "3,000.00", "", "231,749.50"),
                    ("28/09/2026", "RENT SAMPLE LANDLORD", "25,000.00", "", "206,749.50")], "206,749.50"),
]


def bank_statement() -> bytes:
    pages = []
    for opening, rows, closing in BANK_PAGES:
        lines = list(BANK_HEADER) + [f"{'':<12}{'BALANCE BROUGHT FORWARD':<40}{'':>12}{'':>12}{opening:>14}"]
        lines += [f"{d:<12}{desc:<40}{dr:>12}{cr:>12}{bal:>14}" for d, desc, dr, cr, bal in rows]
        lines += [f"{'':<12}{'BALANCE CARRIED FORWARD':<40}{'':>12}{'':>12}{closing:>14}"]
        pages.append((f"BANK STATEMENT — {STAMP}", lines))
    return _pdf(pages)


MPESA_PAGES = [  # newest first, as Safaricom prints them
    [("UAS0000008", "2026-09-27 14:02:11", "Funds received from SAMPLE EMPLOYER LTD", "8,500.00", "", "25,800.00"),
     ("UAS0000007", "2026-09-15 10:44:01", "Customer Withdrawal At Agent Till 000000", "", "5,000.00", "17,300.00"),
     ("UAS0000006", "2026-09-10 08:15:40", "M-Shwari Loan Repayment", "", "3,500.00", "22,300.00"),
     ("UAS0000005", "2026-09-03 18:20:05", "Funds received from SAMPLE PAYER 0700000001", "12,000.00", "",
      "25,800.00")],
    [("UAS0000004", "2026-08-21 09:01:33", "Pay Bill to 888880 - SAMPLE POWER Acc. 00000000", "", "1,000.00",
      "13,800.00"),
     ("UAS0000003", "2026-08-09 12:30:00", "Fuliza M-Pesa Repayment", "", "1,200.00", "14,800.00"),
     ("UAS0000002", "2026-08-05 16:45:12", "Customer Transfer to SAMPLE SHOP 0700000002", "", "2,000.00",
      "16,000.00"),
     ("UAS0000001", "2026-08-02 07:55:59", "Funds received from SAMPLE PAYER 0700000001", "15,000.00", "",
      "18,000.00")],
]


def mpesa_statement() -> bytes:
    pages = []
    for n, rows in enumerate(MPESA_PAGES, 1):
        lines = []
        if n == 1:
            lines += [f"Customer Name: {NAME}", "Mobile Number: 0700 XXX 000",
                      "Statement Period: 01 Aug 2026 - 30 Sep 2026", "", "DETAILED STATEMENT"]
        lines.append(f"{'Receipt No':<12}{'Completion Time':<21}{'Details':<50}{'Status':<11}{'Paid In':>11}"
                     f"{'Withdrawn':>11}{'Balance':>11}")
        lines += [f"{r:<12}{t:<21}{d:<50}{'Completed':<11}{pi:>11}{wd:>11}{bal:>11}" for r, t, d, pi, wd, bal in rows]
        pages.append((f"M-PESA STATEMENT (SPECIMEN) — {STAMP}", lines))
    return _pdf(pages)


SIMPLE_DOCS = {
    "kra_pin_certificate.pdf": ("KRA PIN CERTIFICATE (SPECIMEN)", [
        "Personal Identification Number: A000000000Z", f"Taxpayer Name: {NAME}", "Taxpayer Type: Individual",
        "Registration Date: 20/02/2016", "Tax Obligation(s): Income Tax - Resident Individual"]),
    "passport_bio_page.pdf": ("PASSPORT (SPECIMEN) — REPUBLIC OF SAMPLELAND", [
        "Passport No: AK0000000", "Surname: MOCKERSON", "Given names: TESTA SAMPLE", "Nationality: KENYAN",
        "Date of birth: 01 JAN 1990", "Sex: F", "Date of issue: 10 MAR 2022", "Date of expiry: 09 MAR 2032",
        "P<KENMOCKERSON<<TESTA<SAMPLE<<<<<<<<<<<<<<<<<",
        "AK00000000KEN9001014F3203095<<<<<<<<<<<<<<00"]),
    "cr12.pdf": ("CR12 (SPECIMEN) — REGISTRAR OF COMPANIES", [
        "Company: SAMPLE TRADING LIMITED", "Registration No: PVT-SAMPLE01", "Date: 01/09/2026",
        "Registered office: P.O. Box 00000-00100, Sampleville", "Directors:",
        "  TESTA SAMPLE MOCKERSON  ID 00000001  Kenyan  600 shares",
        "  EXEMPLA DUMMY PLACEHOLDER  ID 00000002  Kenyan  400 shares", "Shareholders:",
        "  TESTA SAMPLE MOCKERSON  Ordinary  600", "  EXEMPLA DUMMY PLACEHOLDER  Ordinary  400",
        "Secretary: SAMPLE SECRETARIES LLP"]),
    "certificate_of_incorporation.pdf": ("CERTIFICATE OF INCORPORATION (SPECIMEN)", [
        "This is to certify that SAMPLE TRADING LIMITED", "is incorporated as a private company limited by shares",
        "Registration No: PVT-SAMPLE01", "Dated: 14/03/2019"]),
    "audited_financial_statements.pdf": ("AUDITED FINANCIAL STATEMENTS (SPECIMEN) — SAMPLE TRADING LIMITED", [
        "Auditor: SAMPLE & CO. CERTIFIED PUBLIC ACCOUNTANTS", "Year ended 31 December 2025",
        "Opinion: unqualified", "Amounts in KES '000", "Revenue 12,500", "Cost of sales (7,800)",
        "Operating profit 2,100", "Finance costs (350)", "Profit after tax 1,240", "Total assets 9,800",
        "Current assets 4,300", "Current liabilities 2,900", "Total liabilities 4,100", "Equity 5,700",
        "Cash and cash equivalents 860"]),
    "title_deed.pdf": ("TITLE DEED (SPECIMEN)", [
        "Title Number: SAMPLE/BLOCK1/000", "Registration section: SAMPLE SECTION", "Parcel No: 000",
        "Area: 0.050 Ha", f"Registered proprietor: {NAME}", "Tenure: Freehold", "Encumbrances: none registered",
        "Registered: 05/05/2018"]),
    "logbook.pdf": ("MOTOR VEHICLE REGISTRATION CERTIFICATE (SPECIMEN)", [
        "Registration No: KZZ 000Z", "Make: SAMPLEMOTORS", "Model: EXAMPLE 1.5", "Year of manufacture: 2019",
        "Chassis No: SMPL0000000000000", "Engine No: ENG000000", f"Owner: {NAME}", "Financier: none",
        "Colour: WHITE"]),
    "valuation_report.pdf": ("VALUATION REPORT (SPECIMEN)", [
        "Valuer: SAMPLE VALUERS LTD (Valuer: EXEMPLA DUMMY)", "Date of valuation: 15/08/2026",
        "Property: Title No. SAMPLE/BLOCK1/000", "Open market value: KES 6,500,000",
        "Forced sale value: KES 4,875,000", "Insurance value: KES 3,200,000", "Condition: good",
        "Valid for 12 months"]),
    "crb_report.pdf": ("CREDIT REPORT (SPECIMEN) — SAMPLE CREDIT BUREAU", [
        "Report date: 30/09/2026", f"Subject: {NAME}  ID 00000001", "Score: 650 (band: Medium risk)",
        "Accounts: 4 total, 2 open, 0 non-performing", "Total outstanding: KES 120,000.00",
        "Total in arrears: KES 0.00", "Defaults listed: none", "Enquiries in the last 90 days: 3"]),
}


# ── Recorded responses ──


def e(value, confidence=0.97, page=1, source=None, legibility="good", notes=None):
    return {"value": value, "confidence": confidence, "source_page": page,
            "source_text": source if source is not None else (None if value is None else str(value)[:80]),
            "legibility": legibility, "notes": notes}


ID_FIELDS = ("id_number", "full_name", "date_of_birth", "sex", "place_of_birth", "date_of_issue", "serial_number",
             "district")


def doc_answer(detected, fields, *, readable=True, reason=None, pages=1, warnings=()):
    return {"detected_document_type": detected, "readable": readable, "unreadable_reason": reason,
            "page_count_seen": pages, "fields": fields, "warnings": list(warnings)}


def response(name, answer, input_tokens, output_tokens, stop_reason="end_turn"):
    return name, {"_comment": NOTE, "id": f"msg_sample_{name}", "request_id": f"req_sample_{name}",
                  "model": "claude-opus-5-5", "stop_reason": stop_reason,
                  "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens,
                            "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
                  "answer": answer}


def national_id_clean():
    return doc_answer("national_id", {
        "id_number": e("00000001", 0.98, source="ID NUMBER 00000001"),
        "full_name": e(NAME, 0.97, source=f"FULL NAMES {NAME}"),
        "date_of_birth": e("1990-01-01", 0.96, source="DATE OF BIRTH 01.01.1990"),
        "sex": e("F", 0.97, source="SEX FEMALE"),
        "place_of_birth": e(None, 0.0, notes="Not printed on this card (only district of birth)."),
        "date_of_issue": e("2015-06-15", 0.95, source="DATE OF ISSUE 15.06.2015"),
        "serial_number": e("000000001", 0.94, source="SERIAL NUMBER 000000001"),
        "district": e("SAMPLE DISTRICT", 0.93, source="DISTRICT OF BIRTH SAMPLE DISTRICT"),
    }, warnings=["The card is marked SAMPLE — NOT A REAL DOCUMENT."])


def statement_page(page, rows, opening, closing, header, order="oldest_first"):
    return {"detected_document_type": header.pop("_type"), "readable": True, "unreadable_reason": None,
            "page_number": page, "rows_order": order, "header": header,
            "page_opening_balance": e(opening, 0.95, page) if opening else e(None, 0.0, page),
            "page_closing_balance": e(closing, 0.95, page) if closing else e(None, 0.0, page),
            "transactions": [{"row": i, "date": d, "description": desc, "reference": ref, "debit": dr, "credit": cr,
                              "balance": bal, "confidence": 0.95} for i, (d, desc, ref, dr, cr, bal) in
                             enumerate(rows, 1)],
            "warnings": []}


def _iso(d):
    day, month, year = d.split("/")
    return f"{year}-{month}-{day}"


def _amt(text):
    return text.replace(",", "") or None


def bank_page(n, misread=False):
    opening, rows, closing = BANK_PAGES[n - 1]
    header = {"_type": "bank_statement"}
    values = {"bank_name": "SAMPLE BANK (NOT A REAL BANK)", "branch": "SAMPLE BRANCH", "account_name": NAME,
              "account_number_last4": "0000", "currency": "KES", "period_from": "2026-07-01",
              "period_to": "2026-09-30"}
    for k, v in values.items():
        header[k] = e(v, 0.96, n)
    parsed = [(_iso(d), desc, None, _amt(dr), _amt(cr), _amt(bal)) for d, desc, dr, cr, bal in rows]
    if misread:  # the model reads 7,250.50 as 6,250.50 on page 2, row 4
        d, desc, ref, dr, cr, bal = parsed[3]
        parsed[3] = (d, desc, ref, "6250.50", cr, bal)
    return statement_page(n, parsed, _amt(opening), _amt(closing), header)


def mpesa_page(n):
    header = {"_type": "mpesa_statement"}
    if n == 1:
        header.update({"customer_name": e(NAME, 0.97), "mobile_number_last4": e("0000", 0.9),
                       "period_from": e("2026-08-01", 0.95), "period_to": e("2026-09-30", 0.95)})
    else:
        header.update({k: e(None, 0.0, n) for k in ("customer_name", "mobile_number_last4", "period_from",
                                                     "period_to")})
    rows = [(t[:10], d, r, _amt(wd), _amt(pi), _amt(bal)) for r, t, d, pi, wd, bal in MPESA_PAGES[n - 1]]
    return statement_page(n, rows, None, None, header, order="newest_first")


def simple(detected, values, pages=1):
    return doc_answer(detected, {k: (v if isinstance(v, (dict, list)) else e(v)) for k, v in values.items()},
                      pages=pages)


def responses():
    unreadable = doc_answer("national_id", {n: e(None, 0.0, legibility="unreadable") for n in ID_FIELDS},
                            readable=False, reason="The image is heavily blurred and noisy; no characters can be "
                                                   "made out.")
    wrong = doc_answer("kra_pin", {n: e(None, 0.0) for n in ID_FIELDS},
                       warnings=["This is a KRA PIN certificate, not a national ID card."])
    invalid = national_id_clean()
    del invalid["fields"]["id_number"]["source_page"]
    yield response("national_id_clean", national_id_clean(), 2950, 980)
    yield response("national_id_missing_source_page", invalid, 2950, 960)
    yield response("national_id_unreadable", unreadable, 2900, 310)
    yield response("national_id_wrong_type_kra_pin", wrong, 3400, 420)
    yield response("passport", simple("passport", {
        "passport_number": "AK0000000", "surname": "MOCKERSON", "given_names": "TESTA SAMPLE",
        "nationality": "KENYAN", "date_of_birth": "1990-01-01", "sex": "F", "date_of_issue": "2022-03-10",
        "date_of_expiry": "2032-03-09", "mrz_line_1": "P<KENMOCKERSON<<TESTA<SAMPLE<<<<<<<<<<<<<<<<<",
        "mrz_line_2": "AK00000000KEN9001014F3203095<<<<<<<<<<<<<<00"}), 3300, 1100)
    yield response("kra_pin", simple("kra_pin", {
        "kra_pin": "A000000000Z", "taxpayer_name": NAME, "taxpayer_type": "Individual",
        "registration_date": "2016-02-20", "tax_obligations": "Income Tax - Resident Individual"}), 3400, 700)
    yield response("cr12", simple("cr12", {
        "company_name": "SAMPLE TRADING LIMITED", "registration_number": "PVT-SAMPLE01", "cr12_date": "2026-09-01",
        "registered_office": "P.O. Box 00000-00100, Sampleville", "secretary": "SAMPLE SECRETARIES LLP",
        "directors": [{"name": e(NAME), "id_or_passport_number": e("00000001"), "nationality": e("Kenyan"),
                       "shares": e("600")},
                      {"name": e("EXEMPLA DUMMY PLACEHOLDER"), "id_or_passport_number": e("00000002"),
                       "nationality": e("Kenyan"), "shares": e("400")}],
        "shareholders": [{"name": e(NAME), "share_class": e("Ordinary"), "number_of_shares": e("600")},
                         {"name": e("EXEMPLA DUMMY PLACEHOLDER"), "share_class": e("Ordinary"),
                          "number_of_shares": e("400")}]}), 6200, 1600)
    yield response("certificate_of_incorporation", simple("certificate_of_incorporation", {
        "entity_name": "SAMPLE TRADING LIMITED", "registration_number": "PVT-SAMPLE01",
        "registration_date": "2019-03-14", "entity_type": "Private company limited by shares"}), 3100, 520)
    yield response("audited_financial_statements", simple("audited_financial_statements", {
        "entity_name": "SAMPLE TRADING LIMITED", "auditor": "SAMPLE & CO. CERTIFIED PUBLIC ACCOUNTANTS",
        "year_end": "2025-12-31", "opinion_type": "unqualified", "currency": "KES", "units": "KES '000",
        "revenue": "12500.00", "cost_of_sales": "-7800.00", "operating_profit": "2100.00",
        "finance_costs": "-350.00", "net_profit": "1240.00", "total_assets": "9800.00",
        "current_assets": "4300.00", "current_liabilities": "2900.00", "total_liabilities": "4100.00",
        "equity": "5700.00", "cash": "860.00"}), 4600, 1500)
    yield response("title_deed", simple("title_deed", {
        "title_number": "SAMPLE/BLOCK1/000", "registration_section": "SAMPLE SECTION", "parcel_number": "000",
        "area": "0.050 Ha", "registered_proprietors": NAME, "tenure": "freehold", "lease_term": None,
        "encumbrances": None, "registration_date": "2018-05-05"}), 3800, 1000)
    yield response("logbook", simple("logbook", {
        "registration_number": "KZZ 000Z", "make": "SAMPLEMOTORS", "model": "EXAMPLE 1.5",
        "year_of_manufacture": "2019", "chassis_number": "SMPL0000000000000", "engine_number": "ENG000000",
        "registered_owners": NAME, "financier_interest": None, "colour": "WHITE"}), 3500, 950)
    yield response("valuation_report", simple("valuation_report", {
        "valuer_firm": "SAMPLE VALUERS LTD", "valuer_name": "EXEMPLA DUMMY", "valuation_date": "2026-08-15",
        "asset_identifier": "SAMPLE/BLOCK1/000", "open_market_value": "6500000.00",
        "forced_sale_value": "4875000.00", "insurance_value": "3200000.00", "condition_notes": "good",
        "validity_period": "12 months"}), 5200, 1050)
    yield response("crb_report", simple("crb_report", {
        "bureau_name": "SAMPLE CREDIT BUREAU", "report_date": "2026-09-30", "subject_name": NAME,
        "subject_id_number": "00000001", "credit_score": "650", "score_band": "Medium risk", "total_accounts": "4",
        "open_accounts": "2", "non_performing_accounts": "0", "total_outstanding": "120000.00",
        "total_in_arrears": "0.00", "defaults_listed": None, "enquiries_last_90_days": "3"}), 4800, 1050)
    for n in (1, 2, 3):
        yield response(f"bank_statement_page{n}", bank_page(n), 4700, 2100)
    yield response("bank_statement_page2_misread", bank_page(2, misread=True), 4700, 2050)
    for n in (1, 2):
        yield response(f"mpesa_statement_page{n}", mpesa_page(n), 4900, 2300)


def main():
    DOCS.mkdir(exist_ok=True)
    RESPONSES.mkdir(exist_ok=True)
    files = {"national_id_clean.png": id_card(), "national_id_unreadable.png": id_card(blurred=True),
             "bank_statement_3_pages.pdf": bank_statement(), "mpesa_statement_2_pages.pdf": mpesa_statement()}
    for name, (title, lines) in SIMPLE_DOCS.items():
        files[name] = _pdf([(f"{title} — {STAMP}", lines)])
    for name, data in files.items():
        (DOCS / name).write_bytes(data)
    for name, body in responses():
        (RESPONSES / f"{name}.json").write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n",
                                                encoding="utf-8", newline="\n")
    (DOCS / "README.md").write_text(
        "# Synthetic sample documents — NOT REAL\n\n"
        "Every file here is generated by `../make_fixtures.py` and stamped **SAMPLE — NOT A REAL DOCUMENT**. "
        "Names (TESTA SAMPLE MOCKERSON, EXEMPLA DUMMY PLACEHOLDER), ID numbers (00000001), PINs, accounts and "
        "amounts are invented.\n\n**Never add a real client document to this folder or anywhere in the repo.**\n",
        encoding="utf-8", newline="\n")
    print(f"{len(files)} documents, {len(list(RESPONSES.glob('*.json')))} responses")


if __name__ == "__main__":
    main()
