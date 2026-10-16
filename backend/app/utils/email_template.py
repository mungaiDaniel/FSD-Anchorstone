"""
Branded HTML layout for every investor email.

The body is composed as plain text (app/Emails/composer.py) and rendered here:
paragraphs become <p>, "•"/"*" lines become <ul><li>, and a short ALL-CAPS line
on its own becomes a section sub-heading. The plain text is also sent as the
text/plain alternative.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape as _escape

from flask import current_app

from app.utils import brand

LOGO_CONTENT_ID = "anchorstone_logo"

EMAIL_TITLES = {
    "DEPOSIT_CONFIRMATION": "Deposit Confirmation",
    "DEPOSIT_REVERSAL": "Deposit Reversed",
    "WITHDRAWAL_CONFIRMATION": "Withdrawal Confirmation",
    "INTEREST_STATEMENT": "Interest Statement",
    "ACCOUNT_STATEMENT": "Account Statement",
    "AUM_REPORT": "Monthly AUM Summary",
    "TEST": "Test Email",
}


def get_email_title(email_type: str | None, fallback: str = "Notification") -> str:
    if not email_type:
        return fallback
    return EMAIL_TITLES.get(email_type, email_type.replace("_", " ").title())


def _render_body_html(text: str) -> str:
    safe = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = [p.strip() for p in safe.split("\n\n") if p.strip()]

    parts = []
    for para in paragraphs:
        lines = [line.strip() for line in para.split("\n") if line.strip()]
        if not lines:
            continue

        if len(lines) == 1 and lines[0].isupper() and len(lines[0]) <= 60:
            parts.append(
                f'<p style="margin:24px 0 8px 0;color:{brand.PRIMARY};font-size:12px;'
                f'font-weight:700;letter-spacing:0.8px;text-transform:uppercase;'
                f'border-bottom:1px solid {brand.BORDER};padding-bottom:6px;">{_escape(lines[0])}</p>'
            )
            continue

        if any(line.startswith(("•", "*")) for line in lines):
            items = []
            for line in lines:
                clean = line[1:].strip() if line.startswith(("•", "*")) else line
                if clean:
                    items.append(f'<li style="margin:4px 0;font-size:14px;line-height:1.5;">{_escape(clean)}</li>')
            parts.append(f'<ul style="margin:8px 0;padding-left:22px;color:{brand.TEXT};">{"".join(items)}</ul>')
            continue

        para_html = "<br/>".join(_escape(line) for line in lines)
        parts.append(f'<p style="margin:12px 0;font-size:14px;line-height:1.6;color:{brand.TEXT};">{para_html}</p>')

    return "".join(parts)


def _header_html(has_logo: bool) -> str:
    if has_logo:
        return (
            f'<img src="cid:{LOGO_CONTENT_ID}" alt="{_escape(brand.COMPANY_NAME)}" width="170" '
            'style="display:block;margin:0 auto;height:auto;border:0;">'
        )
    return (
        f'<p style="margin:0;color:{brand.PRIMARY};font-family:{brand.EMAIL_WORDMARK_FONT_STACK};font-size:24px;font-weight:700;letter-spacing:0.3px;">'
        f"{_escape(brand.COMPANY_NAME)}</p>"
    )


def render_branded_email_html(title: str, body_text: str, *, has_logo: bool = False) -> str:
    year = datetime.now(timezone.utc).year
    address = current_app.config.get("COMPANY_ADDRESS") or ""
    contact = current_app.config.get("COMPANY_CONTACT") or ""
    footer_lines = "".join(
        f'<p style="margin:6px 0 0 0;color:{brand.TEXT_MUTED};font-size:11px;">{_escape(line)}</p>'
        for line in (address, contact) if line
    )

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_escape(title)}</title>
</head>
<body style="margin:0;padding:0;background-color:{brand.SURFACE_ALT};font-family:{brand.EMAIL_FONT_STACK};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:{brand.SURFACE_ALT};">
<tr><td align="center" style="padding:32px 16px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:12px;overflow:hidden;">
<tr><td style="height:4px;background-color:{brand.PRIMARY};line-height:4px;font-size:0;">&nbsp;</td></tr>
<tr><td style="padding:32px 40px 12px 40px;text-align:center;">{_header_html(has_logo)}</td></tr>
<tr><td style="padding:0 40px 24px 40px;text-align:center;">
<p style="margin:0;color:{brand.ACCENT};font-size:13px;font-weight:700;letter-spacing:1.2px;text-transform:uppercase;">{_escape(title)}</p>
</td></tr>
<tr><td style="padding:0 40px 8px 40px;">
{_render_body_html(body_text)}
</td></tr>
<tr><td style="padding:28px 40px 24px 40px;border-top:1px solid {brand.BORDER};text-align:center;">
<p style="margin:0;color:{brand.TEXT_MUTED};font-size:11px;">&copy; {year} {_escape(brand.COMPANY_NAME)}. All rights reserved.</p>
{footer_lines}
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""


def attach_brand_logo(msg) -> bool:
    """Attach the logo as an inline CID image if one is configured."""
    path = brand.logo_path()
    if path is None:
        return False
    msg.attach(
        filename=path.name,
        content_type="image/png",
        data=path.read_bytes(),
        disposition="inline",
        headers={"Content-ID": f"<{LOGO_CONTENT_ID}>"},
    )
    return True
