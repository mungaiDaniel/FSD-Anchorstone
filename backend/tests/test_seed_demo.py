"""
scripts/seed_demo.py --reset: refuses without the flag or on the wrong database,
deletes the demo's document files through the store, rebuilds the schema with
the migrations, and can run twice in a row with new clients still getting a
fresh client code and account number.
"""
import importlib.util
import pathlib
import uuid

import pytest

from app.database.database import db
from app.Documents.model import Document
from app.Documents.store import get_store
from app.Investors.model import Investor
from app.Parties.model import Account, AccountHold
from conftest import Api
from test_documents import _upload

_SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "seed_demo.py"


@pytest.fixture(scope="module")
def seed_demo():
    spec = importlib.util.spec_from_file_location("seed_demo", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name, confirmed", [
    ("statement_demo", False),       # right name, no flag
    ("statement", True),             # live-looking name
    ("statement_demo_copy", True),   # must END in _demo / _test
    ("demo", True),
])
def test_reset_guard_refuses(seed_demo, name, confirmed):
    with pytest.raises(SystemExit, match="Refusing to reset"):
        seed_demo.check_reset_allowed(name, confirmed)


def test_reset_guard_allows_demo_and_test_databases_with_the_flag(seed_demo):
    seed_demo.check_reset_allowed("statement_demo", True)
    seed_demo.check_reset_allowed("anchorstone_test", True)


def test_reset_without_the_flag_touches_nothing(app, seed_demo, make_investor, capsys):
    make_investor()
    db.session.commit()
    with pytest.raises(SystemExit, match="i-understand-this-deletes-data"):
        seed_demo.seed(app, reset=True, confirmed=False)
    assert "Database: " in capsys.readouterr().out  # named before anything happens
    assert Investor.query.count() == 1


def test_reset_twice_then_a_new_client_gets_fresh_numbers(app, client, seed_demo, admin1, capsys):
    doc = _upload(admin1)
    key = db.session.get(Document, uuid.UUID(doc["id"])).storage_key
    assert get_store().exists(key)
    db.session.commit()  # end this session's transaction so the schema can be dropped

    app.config["MAIL_SUPPRESS_SEND"] = False  # the reset must force it on regardless
    try:
        seen = []
        orig = seed_demo.reset_database

        def spy():
            seen.append((app.config["MAIL_SUPPRESS_SEND"], app.extensions["mail"].suppress))
            return orig()

        seed_demo.reset_database = spy
        try:
            seed_demo.seed(app, reset=True, confirmed=True)
        finally:
            seed_demo.reset_database = orig
        assert seen == [(True, True)]
        assert app.config["MAIL_SUPPRESS_SEND"] is False  # restored afterwards
    finally:
        app.config["MAIL_SUPPRESS_SEND"] = True

    assert not get_store().exists(key)  # no orphaned encrypted file
    assert "1 document file(s) deleted" in capsys.readouterr().out

    seed_demo.seed(app, reset=True, confirmed=True)
    out = capsys.readouterr().out
    assert "Database: " in out and "0 document file(s) deleted" in out

    db.session.remove()
    assert Investor.query.count() == len(seed_demo.INVESTORS)
    assert AccountHold.query.filter_by(reason="pending_withdrawal", released_at=None).count() == 1

    maker = Api(client, seed_demo.MAKER)
    res = maker.post("/api/v1/investors", {"full_name": "New Client After Reset", "email": "new.client@example.com",
                                           "phone": "0700000000", "payout_method": "mpesa",
                                           "payout_account": "0700000000"})
    assert res.status_code == 201, res.get_json()
    code = res.get_json()["data"]["client_code"]
    assert code == f"ACL-{len(seed_demo.INVESTORS) + 1:06d}"
    account = db.session.get(Account, db.session.get(Investor, res.get_json()["data"]["id"]).account_id)
    assert account.account_no == code
    assert db.session.query(Account.account_no).distinct().count() == Account.query.count()
