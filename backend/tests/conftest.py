"""
Tests run against a real Postgres database (TEST_DATABASE_URI, default
postgresql://localhost/anchorstone_test). The schema is built by running the
actual Alembic migrations once per session, so the migrations are tested too;
every test then starts from empty tables.

WARNING: the test database is wiped. Never point TEST_DATABASE_URI at real data.
"""
import os
from datetime import date

os.environ["APP_ENV"] = "testing"

import pytest
from flask_jwt_extended import create_access_token
from flask_migrate import upgrade
from sqlalchemy import text

from app.Admin.model import User
from app.database.database import db
from main import create_app

TODAY = date(2026, 10, 5)

_DATED_MODULES = (
    "app.Transactions.service",
    "app.Interest.service",
    "app.Stats.route",
    "app.Reports.reports",
    "app.Reports.scheduled",
    "app.Emails.statements",
    "app.Interest.statement",
)


@pytest.fixture(scope="session")
def app():
    app = create_app("testing")
    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    assert "test" in uri.rsplit("/", 1)[-1], f"Refusing to wipe a non-test database: {uri}"
    with app.app_context():
        db.session.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
        db.session.commit()
        upgrade()
    yield app


@pytest.fixture(autouse=True)
def clean_db(app):
    with app.app_context():
        tables = ", ".join(f'"{t.name}"' for t in db.metadata.sorted_tables)
        db.session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        db.session.execute(text("ALTER SEQUENCE investor_client_code_seq RESTART WITH 1"))
        db.session.commit()
        yield
        db.session.rollback()
        db.session.remove()


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    """Pin 'today' (Nairobi) so date rules are deterministic."""
    import importlib

    for name in _DATED_MODULES:
        monkeypatch.setattr(importlib.import_module(name), "today_eat", lambda: TODAY)
    return TODAY


@pytest.fixture
def client(app):
    return app.test_client()


def _make_user(email, role, status="active"):
    user = User(name=email.split("@")[0].title(), email=email,
                password=User.generate_password_hash("password123"), role=role, status=status,
                must_change_password=False)
    db.session.add(user)
    db.session.commit()
    return user


class Api:
    """Thin JSON client that signs requests as a given user."""

    def __init__(self, client, email):
        self.client = client
        self.headers = {"Authorization": f"Bearer {create_access_token(identity=email)}"}

    def get(self, url, **kw):
        return self.client.get(url, headers=self.headers, **kw)

    def post(self, url, json=None):
        return self.client.post(url, json=json or {}, headers=self.headers)

    def patch(self, url, json=None):
        return self.client.patch(url, json=json or {}, headers=self.headers)

    def delete(self, url):
        return self.client.delete(url, headers=self.headers)


@pytest.fixture
def users(app):
    return {
        "staff": _make_user("staff@anchorstone.test", "user"),
        "admin1": _make_user("admin1@anchorstone.test", "admin"),
        "admin2": _make_user("admin2@anchorstone.test", "admin"),
        "super": _make_user("super@anchorstone.test", "super_admin"),
    }


@pytest.fixture
def staff(client, users):
    return Api(client, users["staff"].email)


@pytest.fixture
def admin1(client, users):
    return Api(client, users["admin1"].email)


@pytest.fixture
def admin2(client, users):
    return Api(client, users["admin2"].email)


@pytest.fixture
def superadmin(client, users):
    return Api(client, users["super"].email)


@pytest.fixture
def make_investor(staff):
    counter = {"n": 0}

    def _make(**overrides):
        counter["n"] += 1
        payload = {"full_name": f"Investor {counter['n']}", "email": f"investor{counter['n']}@example.com",
                   "phone": "0700000000", "payout_method": "mpesa", "payout_account": "0700000000"}
        payload.update(overrides)
        res = staff.post("/api/v1/investors", payload)
        assert res.status_code == 201, res.get_json()
        return res.get_json()["data"]

    return _make


@pytest.fixture
def deposit(staff):
    counter = {"n": 0}

    def _deposit(investor_id, amount, value_date, expect=201):
        counter["n"] += 1
        res = staff.post("/api/v1/deposits", {"investor_id": investor_id, "amount": str(amount),
                                              "value_date": value_date, "method": "bank_transfer",
                                              "reference": f"REF{counter['n']:05d}"})
        assert res.status_code == expect, res.get_json()
        return res.get_json().get("data")

    return _deposit


@pytest.fixture
def withdraw(staff, admin1):
    """Request as staff, approve as admin1 (maker ≠ checker)."""

    def _withdraw(investor_id, amount, value_date):
        res = staff.post("/api/v1/withdrawals", {"investor_id": investor_id, "amount": str(amount),
                                                 "requested_date": value_date, "method": "mpesa"})
        assert res.status_code == 201, res.get_json()
        wid = res.get_json()["data"]["id"]
        res = admin1.post(f"/api/v1/withdrawals/{wid}/approve", {"value_date": value_date})
        assert res.status_code == 200, res.get_json()
        return res.get_json()["data"]

    return _withdraw


@pytest.fixture
def rate(admin1):
    def _rate(percent, effective_from):
        res = admin1.post("/api/v1/interest/rates", {"rate_percent": str(percent), "effective_from": effective_from})
        assert res.status_code == 201, res.get_json()
        return res.get_json()["data"]

    return _rate
