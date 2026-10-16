"""
Brand tokens for server-rendered output (HTML emails and PDF statements).
The web app's equivalents live in ../frontend/src/styles/globals.css — keep
the two in step.

Palette: navy on white, with a pale lavender for sparing section backgrounds.
Typography: a bold serif for the "Anchorstone Capital Ltd" wordmark only;
clean sans-serif for everything else.
"""
from pathlib import Path

COMPANY_NAME = "Anchorstone Capital Ltd"

PRIMARY = "#1A2060"        # navy: headings, wordmark, buttons, rules
ACCENT = "#1A2060"
TEXT = "#23263A"           # near-black charcoal for body text
TEXT_MUTED = "#5E6278"
SURFACE_ALT = "#ECEDFB"    # pale lavender, used sparingly (label columns, table headers)
BORDER = "#DCDEF0"

# Email clients don't load web fonts reliably, so these are system fallbacks
# that approximate Inter (body) and the serif wordmark.
EMAIL_FONT_STACK = "Inter, 'Segoe UI', Helvetica, Arial, sans-serif"
EMAIL_WORDMARK_FONT_STACK = "'Playfair Display', Georgia, 'Times New Roman', serif"

# ReportLab built-in fonts: Times-Bold for the wordmark, Helvetica for text.
PDF_WORDMARK_FONT = "Times-Bold"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# Drop a logo here later and both emails and PDFs pick it up automatically;
# until then the styled text wordmark is used.
LOGO_PATH = PROJECT_ROOT / "assets" / "logo" / "anchorstone-logo.png"


def logo_path() -> Path | None:
    return LOGO_PATH if LOGO_PATH.exists() else None
