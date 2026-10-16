"""Phase 2a item 2: versioned business-rule settings changed under maker-checker."""
import pathlib
import re
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.database.database import db
from app.Interest.model import InterestPayout, InterestPeriod
from app.Settings import business
from app.Settings.model import SettingVersion
from app.Settings.registry import BINDINGS, DEFINITIONS, REGISTRY, normalise
from app.utils.dates import utcnow
from app.utils.http import ValidationError
from conftest import Api, _make_user


def _propose(api, key, value, expect=201, **extra):
    body = {"value": value, "source": "client_confirmed", "evidence": "Questionnaire I6", **extra}
    res = api.post(f"/api/v1/settings/business/{key}", body)
    assert res.status_code == expect, res.get_json()
    return res.get_json().get("data")


def _approve(api, cr_id, expect=200):
    res = api.post(f"/api/v1/change-requests/{cr_id}/approve")
    assert res.status_code == expect, res.get_json()
    return res.get_json().get("data")


# ── Registry and seed ──


def test_every_key_has_a_default_validator_binding_and_seeded_version_1():
    for d in DEFINITIONS:
        assert d.binding in BINDINGS and callable(d.validator) and d.description
        assert normalise(d.key, d.default) == d.default, f"{d.key} default fails its own validator"
        seed = SettingVersion.query.filter_by(key=d.key, version_no=1).one()
        assert seed.value == d.default and seed.source == "working_assumption" and seed.evidence
    assert {r.key for r in SettingVersion.query} == set(REGISTRY)


def test_values_in_use_today_are_unchanged():
    assert business.get("security.password_min_length") == 10
    assert business.get("security.login_max_failures") == 5
    assert business.get("investments.wht_rate_percent") == Decimal("0")
    assert business.get("email.max_attempts") == 3


def test_unknown_key_and_invalid_values_are_refused(admin1):
    with pytest.raises(ValidationError):
        business.get("no.such.key")
    _propose(admin1, "no.such.key", 1, expect=400)
    res = admin1.post("/api/v1/settings/business/security.password_min_length",
                      {"value": 6, "source": "client_confirmed", "evidence": "x"})
    assert res.status_code == 400 and "between 8 and 128" in res.get_json()["message"]
    _propose(admin1, "investments.wht_rate_percent", "101", expect=400)
    _propose(admin1, "investments.wht_rate_percent", "5.12345", expect=400)
    _propose(admin1, "access.out_of_portfolio_mode", "ignore", expect=400)
    _propose(admin1, "email.max_attempts", 4, expect=400, source="client_confirmed", evidence="")  # needs evidence


def test_staff_cannot_view_or_propose(staff):
    assert staff.get("/api/v1/settings/business").status_code == 403
    assert staff.post("/api/v1/settings/business/email.max_attempts", {"value": 4}).status_code == 403


# ── Maker-checker ──


def test_change_needs_a_second_person_and_applies_as_a_new_version(admin1, admin2):
    cr = _propose(admin1, "email.max_attempts", 5)
    assert cr["request_type"] == "settings.change" and business.get("email.max_attempts") == 3
    _approve(admin1, cr["id"], expect=403)
    applied = _approve(admin2, cr["id"])
    assert applied["status"] == "applied"
    db.session.expire_all()
    assert business.get("email.max_attempts") == 5
    v2 = SettingVersion.query.filter_by(key="email.max_attempts", version_no=2).one()
    assert (v2.created_by, v2.approved_by, v2.source, v2.change_request_id) == (
        "admin1@anchorstone.test", "admin2@anchorstone.test", "client_confirmed", cr["id"])
    assert v2.effective_from == date(2026, 10, 5)


def test_security_keys_need_two_different_approvers(admin1, admin2, superadmin):
    cr = _propose(admin1, "security.login_max_failures", 3)
    assert cr["request_type"] == "settings.change_security"
    assert _approve(admin2, cr["id"])["status"] == "pending"
    _approve(admin2, cr["id"], expect=403)  # same person twice
    assert _approve(superadmin, cr["id"])["status"] == "applied"


def test_login_limit_change_takes_effect_on_the_next_sign_in(client, admin1, admin2, superadmin):
    cr = _propose(admin1, "security.login_max_failures", 3)
    _approve(admin2, cr["id"])
    _approve(superadmin, cr["id"])
    _make_user("target@anchorstone.test", "user")
    codes = [client.post("/api/v1/login", json={"email": "target@anchorstone.test", "password": "wrong"}).status_code
             for _ in range(3)]
    assert codes == [401, 401, 429]


def test_password_minimum_comes_from_the_setting(admin1, admin2, superadmin, staff):
    cr = _propose(admin1, "security.password_min_length", 12)
    _approve(admin2, cr["id"])
    _approve(superadmin, cr["id"])
    res = staff.post("/api/v1/me/password", {"current_password": "password123", "new_password": "abcdefgh1234"[:11]})
    assert res.status_code == 400 and "at least 12" in res.get_json()["message"]


def test_database_refuses_maker_as_approver_and_any_edit():
    with pytest.raises(IntegrityError, match="ck_setting_versions_maker_not_checker"):
        db.session.add(SettingVersion(key="email.max_attempts", value=4, effective_from=date(2026, 11, 1),
                                      version_no=9, source="internal_decision", created_by="A@x",
                                      approved_by="a@x", approved_at=utcnow()))
        db.session.flush()
    db.session.rollback()
    for sql in ("UPDATE setting_versions SET value = '99'", "DELETE FROM setting_versions"):
        with pytest.raises(DBAPIError, match="insert-only"):
            db.session.execute(text(sql))
            db.session.flush()
        db.session.rollback()


# ── Effective dating ──


def test_no_backdating_and_no_effective_date_in_an_approved_month(admin1, make_investor, deposit, rate, admin2):
    _propose(admin1, "email.max_attempts", 4, expect=400, effective_from="2026-10-04")
    inv = make_investor()
    rate("12", "2026-01-01")
    deposit(inv["id"], "100000", "2026-08-01")
    pid = admin1.post("/api/v1/interest/periods/calculate", {"year": 2026, "month": 8}).get_json()["data"]["id"]
    assert admin2.post(f"/api/v1/interest/periods/{pid}/approve").status_code == 200
    res = admin1.post("/api/v1/settings/business/investments.wht_rate_percent",
                      {"value": "10", "effective_from": "2026-08-15", "source": "client_confirmed", "evidence": "B5"})
    assert res.status_code == 400


def test_future_dated_change_applies_only_from_its_date(admin1, admin2):
    cr = _propose(admin1, "email.max_attempts", 6, effective_from="2026-11-01")
    _approve(admin2, cr["id"])
    db.session.expire_all()
    assert business.get("email.max_attempts") == 3
    assert business.get("email.max_attempts", as_of=date(2026, 10, 31)) == 3
    assert business.get("email.max_attempts", as_of=date(2026, 11, 1)) == 6


def test_interest_uses_the_wht_rate_in_force_at_month_end(make_investor, deposit, rate, admin1):
    inv = make_investor()
    rate("12", "2026-01-01")
    deposit(inv["id"], "100000", "2026-07-01")
    # A version effective 1 September (inserted directly: the API refuses past dates).
    db.session.add(SettingVersion(key="investments.wht_rate_percent", value="10.0000", effective_from=date(2026, 9, 1),
                                  version_no=2, source="client_confirmed", evidence="test", created_by="a@x",
                                  approved_by="b@x", approved_at=utcnow()))
    db.session.commit()
    aug = admin1.post("/api/v1/interest/periods/calculate", {"year": 2026, "month": 8}).get_json()["data"]
    assert aug["tax_rate_percent"] == "0.0000" and aug["total_tax"] == "0.00"
    assert admin1.delete(f"/api/v1/interest/periods/{aug['id']}").status_code == 200
    aug = admin1.post("/api/v1/interest/periods/calculate", {"year": 2026, "month": 8}).get_json()["data"]
    assert aug["tax_rate_percent"] == "0.0000"  # recalculating August still uses August's rate


def test_september_payout_withholds_at_the_new_rate(make_investor, deposit, rate, admin1, admin2):
    inv = make_investor()
    rate("12", "2026-01-01")
    deposit(inv["id"], "100000", "2026-07-01")
    for month in (7, 8):
        pid = admin1.post("/api/v1/interest/periods/calculate", {"year": 2026, "month": month}).get_json()["data"]["id"]
        assert admin2.post(f"/api/v1/interest/periods/{pid}/approve").status_code == 200
    db.session.add(SettingVersion(key="investments.wht_rate_percent", value="10.0000", effective_from=date(2026, 9, 1),
                                  version_no=2, source="client_confirmed", evidence="test", created_by="a@x",
                                  approved_by="b@x", approved_at=utcnow()))
    db.session.commit()
    sep = admin1.post("/api/v1/interest/periods/calculate", {"year": 2026, "month": 9}).get_json()["data"]
    payout = InterestPayout.query.filter_by(period_id=sep["id"]).one()
    assert payout.tax_rate_percent == Decimal("10.0000")
    assert payout.tax_amount == (payout.gross_interest * Decimal("0.10")).quantize(Decimal("0.01"))
    assert {p.tax_rate_percent for p in InterestPeriod.query.filter(InterestPeriod.id != sep["id"])} == {Decimal("0")}


def test_stale_change_is_refused(admin1, admin2, superadmin):
    first = _propose(admin1, "email.max_attempts", 4)
    second = _propose(superadmin, "email.max_attempts", 5, effective_from="2026-12-01")
    _approve(admin2, first["id"])
    res = admin2.post(f"/api/v1/change-requests/{second['id']}/approve")
    assert res.status_code == 409 and "changed after this request" in res.get_json()["message"]


# ── Go-live report ──


def test_go_live_report_lists_the_values_still_on_working_assumptions(admin1, admin2):
    rows = admin1.get("/api/v1/settings/business?source=working_assumption").get_json()["data"]
    assert {r["key"] for r in rows} == set(REGISTRY)
    cr = _propose(admin1, "investments.wht_rate_percent", "0", evidence="Questionnaire B5: confirmed 0%")
    _approve(admin2, cr["id"])
    rows = admin1.get("/api/v1/settings/business?source=working_assumption").get_json()["data"]
    assert "investments.wht_rate_percent" not in {r["key"] for r in rows}
    all_rows = {r["key"]: r for r in admin1.get("/api/v1/settings/business").get_json()["data"]}
    wht = all_rows["investments.wht_rate_percent"]
    assert wht["source"] == "client_confirmed" and len(wht["history"]) == 2 and wht["wa_ref"] == "WA-03"


# ── No hard-coded rules left behind ──


def test_replaced_constants_are_gone():
    root = pathlib.Path(__file__).resolve().parents[1] / "app"
    pattern = re.compile(r"^\s*(MIN_PASSWORD_LENGTH|DEFAULT_TAX_RATE_PERCENT|MAX_ATTEMPTS)\s*=", re.M)
    offenders = [str(p) for p in root.rglob("*.py") if pattern.search(p.read_text(encoding="utf-8"))]
    assert offenders == []
