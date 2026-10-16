"""
Writes the golden files. Run it only at the last pre-2b commit (see capture.py):

    GOLDEN_WRITE=1 GOLDEN_OUT=<dir> venv/Scripts/python -m pytest tests/golden/test_make_golden.py
"""
import os
from pathlib import Path

import pytest
from flask_jwt_extended import create_access_token

from app.database.database import db
from conftest import REFERENCE_TABLES
from golden.capture import DATA_FILE, OUTPUTS_FILE, capture, dump_data, seed_demo_book, write


@pytest.mark.skipif(not os.environ.get("GOLDEN_WRITE"), reason="writes golden files; run at the pre-2b commit only")
def test_make_golden(app, client, users):
    seed_demo_book(db)
    data = dump_data(db, set(REFERENCE_TABLES))
    outputs = capture(client, lambda email: {"Authorization": f"Bearer {create_access_token(identity=email)}"})
    out = Path(os.environ.get("GOLDEN_OUT") or DATA_FILE.parent)
    write(out / DATA_FILE.name, data)
    write(out / OUTPUTS_FILE.name, outputs)
    assert len(data["tables"]["investors"].splitlines()) == 15  # header + 14
