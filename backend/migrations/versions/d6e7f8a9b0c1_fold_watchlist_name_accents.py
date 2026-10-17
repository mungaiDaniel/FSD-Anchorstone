"""fold watchlist name accents

Name matching now folds accents ("Qaïda" = "Qaida"; app/Parties/normalise.py
normalise_name). Watchlist entries store their normalised name and aliases, so
they are recomputed here. Both rules are frozen copies, so this migration
keeps working if normalise_name changes again.

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-10-17 09:00:00.000000

"""
import json
import re
import unicodedata

from alembic import op
import sqlalchemy as sa


revision = 'd6e7f8a9b0c1'
down_revision = 'c5d6e7f8a9b0'
branch_labels = None
depends_on = None


def _old(value):
    return " ".join(sorted(re.sub(r"[^A-Z0-9 ]", " ", (value or "").upper()).split()))


def _folded(value):
    text = "".join(c for c in unicodedata.normalize("NFKD", value or "") if not unicodedata.combining(c))
    return " ".join(sorted(re.sub(r"[^A-Z0-9 ]", " ", text.upper()).split()))


def _recompute(rule):
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, full_name, aliases FROM watchlist_entries")).all()
    for entry_id, full_name, aliases in rows:
        aliases = [{**a, "name_normalised": rule(a.get("name"))} for a in (aliases or [])]
        conn.execute(sa.text("UPDATE watchlist_entries SET name_normalised = :n, aliases = CAST(:a AS jsonb) "
                             "WHERE id = :i"),
                     {"n": rule(full_name)[:200], "a": json.dumps(aliases), "i": entry_id})


def upgrade():
    _recompute(_folded)


def downgrade():
    _recompute(_old)
