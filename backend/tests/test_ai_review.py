"""Phase 3b, AI-07 (staff confirmation): reviewers accept or correct every value, a different
person approves, and only then do confirmed values reach the client record."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.Applications.model import ExtractionReview, FieldReview
from app.database.database import db
from app.DocAI.model import ExtractedField, StatementTransaction
from app.Parties.model import PartyIdentifier, PartyPerson
from docai_fakes import document, recorded, response
from test_docai import ai, client_with, consent, make_party, read, upload  # noqa: F401 (ai is a fixture)

BANK = ("bank_statement_3_pages.pdf", "application/pdf")


def fields_by_path(api, ex_id):
    body = api.get(f"/api/v1/extractions/{ex_id}/review").get_json()["data"]
    return body, {f["path"]: f for f in body["fields"]}


def accept_all(api, ex_id, skip=()):
    body, got = fields_by_path(api, ex_id)
    for path, f in got.items():
        if path in skip or f["review"]:
            continue
        action = "accept" if f["value"] is not None and f["validation"] != "failed" else "not_present"
        res = api.post(f"/api/v1/extractions/{ex_id}/review/fields/{f['id']}", {"action": action})
        assert res.status_code == 200, (path, res.get_json())


def submit(api, ex_id, expect=201):
    res = api.post(f"/api/v1/extractions/{ex_id}/review/submit")
    assert res.status_code == expect, res.get_json()
    return res.get_json()


def test_ai_07_low_confidence_values_are_flagged_and_failed_checks_come_first(ai, staff, users, admin1):
    answer = recorded("national_id_clean")["answer"]
    answer["fields"]["sex"]["confidence"] = 0.6
    answer["fields"]["id_number"]["value"] = "1234"  # fails the ID format check
    p, doc = client_with(staff)
    ex = read(users, p, doc, ai, response("national_id_clean", answer=answer))
    body, got = fields_by_path(admin1, ex.id)
    assert body["confidence_threshold"] == "0.85"
    assert got["sex"]["low_confidence"] is True and got["full_name"]["low_confidence"] is False
    assert body["fields"][0]["path"] == "id_number"  # failed check first
    assert body["state"] == "draft" and body["missing_actions"] == len(got)


def test_ai_07_a_correction_sits_beside_the_ai_value_and_needs_a_reason(ai, staff, users, admin1):
    p, doc = client_with(staff)
    ex = read(users, p, doc, ai, response("national_id_clean"))
    _, got = fields_by_path(admin1, ex.id)
    url = f"/api/v1/extractions/{ex.id}/review/fields/{got['full_name']['id']}"
    assert admin1.post(url, {"action": "correct", "value": "TESTA S. MOCKERSON"}).status_code == 400  # no reason
    res = admin1.post(url, {"action": "correct", "value": "TESTA SAMPLE MOCKERSON-ONE", "reason": "Hyphen missed"})
    assert res.status_code == 200
    field = db.session.get(ExtractedField, got["full_name"]["id"])
    assert field.value == "TESTA SAMPLE MOCKERSON"  # the AI value is never replaced
    stored = FieldReview.query.filter_by(field_id=field.id).one()
    assert (stored.action, stored.corrected_value, stored.reason) == ("correct", "TESTA SAMPLE MOCKERSON-ONE",
                                                                      "Hyphen missed")
    bad = admin1.post(f"/api/v1/extractions/{ex.id}/review/fields/{got['id_number']['id']}",
                      {"action": "correct", "value": "12AB", "reason": "x"})
    assert bad.status_code == 400 and "7 or 8 digits" in bad.get_json()["message"]
    missing = admin1.post(f"/api/v1/extractions/{ex.id}/review/fields/{got['place_of_birth']['id']}",
                          {"action": "accept"})
    assert missing.status_code == 400 and "can't be accepted" in missing.get_json()["message"]


def test_ai_07_wrong_role_and_incomplete_reviews_are_refused(ai, staff, users, admin1):
    p, doc = client_with(staff)
    ex = read(users, p, doc, ai, response("national_id_clean"))
    _, got = fields_by_path(admin1, ex.id)
    assert staff.post(f"/api/v1/extractions/{ex.id}/review/fields/{got['sex']['id']}",
                      {"action": "accept"}).status_code == 403
    res = admin1.post(f"/api/v1/extractions/{ex.id}/review/submit")
    assert res.status_code == 400 and "still need accept, correct or not present" in res.get_json()["message"]


def test_ai_07_maker_cannot_approve_and_a_second_person_saves_blanks_only(ai, staff, users, admin1, admin2):
    p = make_party(staff, id_number="00000009")  # the record already has a different ID number
    consent(staff, p["id"])
    doc = upload(staff, p["id"], document("national_id_clean.png"), "national_id", "image/png", "id.png")
    ex = read(users, p, doc, ai, response("national_id_clean"))
    accept_all(admin1, ex.id)
    cr_id = submit(admin1, ex.id)["data"]["change_request_id"]
    assert admin1.get(f"/api/v1/extractions/{ex.id}/review").get_json()["data"]["state"] == "submitted"
    # Locked while waiting for approval.
    _, got = fields_by_path(admin1, ex.id)
    assert admin1.post(f"/api/v1/extractions/{ex.id}/review/fields/{got['sex']['id']}",
                       {"action": "accept"}).status_code == 409
    assert admin1.post(f"/api/v1/change-requests/{cr_id}/approve").status_code == 403  # maker = checker
    assert staff.post(f"/api/v1/change-requests/{cr_id}/approve").status_code == 403   # no ai.review.approve
    assert db.session.get(PartyPerson, p["id"]).date_of_birth is None
    res = admin2.post(f"/api/v1/change-requests/{cr_id}/approve")
    assert res.status_code == 200, res.get_json()
    db.session.expire_all()
    review = ExtractionReview.query.filter_by(extraction_id=ex.id).one()
    assert (review.reviewed_by, review.approved_by) == ("admin1@anchorstone.test", "admin2@anchorstone.test")
    assert db.session.get(PartyPerson, p["id"]).date_of_birth == date(1990, 1, 1)  # blank → filled
    ids = PartyIdentifier.query.filter_by(party_id=p["id"], id_type="national_id").all()
    assert [i.value_normalised for i in ids] == ["00000009"]  # never overwritten
    assert review.party_updates["kept_existing"] == ["ID number: the record has 00000009, the document 00000001"]
    # Approved: frozen in the database; maker = checker refused by a CHECK even in raw SQL.
    with pytest.raises(Exception, match="can't be changed"):
        db.session.execute(text("UPDATE field_reviews SET action = 'not_present'"))
    db.session.rollback()
    with pytest.raises(Exception, match="can't be changed"):
        db.session.execute(text("UPDATE extraction_reviews SET approved_by = reviewed_by"))
    db.session.rollback()


def test_ai_07_reviewer_cannot_be_approver_in_the_database(ai, staff, users):
    p, doc = client_with(staff)
    ex = read(users, p, doc, ai, response("national_id_clean"))
    review = ExtractionReview(extraction_id=ex.id, reviewed_by="admin1@anchorstone.test")
    db.session.add(review)
    db.session.commit()
    with pytest.raises(Exception, match="ck_extraction_reviews_maker_checker"):
        db.session.execute(text("UPDATE extraction_reviews SET approved_by = 'Admin1@anchorstone.test', "
                                "approved_at = now() WHERE id = :i"), {"i": review.id})
    db.session.rollback()


def test_ai_07_misread_statement_row_is_fixed_by_a_correction_then_measured(ai, staff, users, admin1, admin2):
    p, doc = client_with(staff, "bank_statement", BANK)
    ex = read(users, p, doc, ai, response("bank_statement_page1"), response("bank_statement_page2_misread"),
              response("bank_statement_page3"))
    body, _ = fields_by_path(admin1, ex.id)
    assert body["statement"] and body["pages"][0]["page_number"] == 2  # the page that fails comes first
    assert body["pages"][0]["reviewed_status"] == "needs_review"
    accept_all(admin1, ex.id)
    res = admin1.post(f"/api/v1/extractions/{ex.id}/review/submit")
    assert res.status_code == 400 and "Page(s) 2 still don't add up" in res.get_json()["message"]
    row = StatementTransaction.query.filter_by(extraction_id=ex.id, page_number=2, row_no=4).one()
    fix = {"debit": "7250.50", "balance": "154749.50", "reason": "Misread 7 as 6"}
    assert admin1.post(f"/api/v1/extractions/{ex.id}/review/transactions/{row.id}",
                       {"balance": "1", "debit": "x", "reason": "r"}).status_code == 400
    assert admin1.post(f"/api/v1/extractions/{ex.id}/review/transactions/{row.id}", fix).status_code == 200
    body, _ = fields_by_path(admin1, ex.id)
    assert all(pg["reviewed_status"] == "balanced" for pg in body["pages"])
    assert db.session.get(StatementTransaction, row.id).debit == Decimal("6250.50")  # AI row untouched
    cr_id = submit(admin1, ex.id)["data"]["change_request_id"]
    assert admin2.post(f"/api/v1/change-requests/{cr_id}/approve").status_code == 200
    db.session.expire_all()
    review = ExtractionReview.query.filter_by(extraction_id=ex.id).one()
    assert review.confirmed_metrics["metrics"]["avg_monthly_inflow"] == "81666.67"
    assert review.confirmed_metrics["period_from"] == "2026-07-01"


def test_ai_07_unreliable_statement_and_a_returned_review(ai, staff, users, admin1, admin2):
    p, doc = client_with(staff, "bank_statement", BANK)
    ex = read(users, p, doc, ai, response("bank_statement_page1"), response("bank_statement_page2_misread"),
              response("bank_statement_page3"))
    accept_all(admin1, ex.id)
    assert admin1.post(f"/api/v1/extractions/{ex.id}/review/unreliable", {}).status_code == 400  # reason
    assert admin1.post(f"/api/v1/extractions/{ex.id}/review/unreliable",
                       {"reason": "Stamped over; bank won't reissue"}).status_code == 200
    cr_id = submit(admin1, ex.id)["data"]["change_request_id"]
    assert admin2.post(f"/api/v1/change-requests/{cr_id}/return", {"reason": "Check page 2 again"}).status_code == 200
    assert admin1.get(f"/api/v1/extractions/{ex.id}/review").get_json()["data"]["state"] == "returned"
    _, got = fields_by_path(admin1, ex.id)
    url = f"/api/v1/extractions/{ex.id}/review/fields/{got['header.branch']['id']}"
    assert admin1.post(url, {"action": "not_present"}).status_code == 200  # editable again
    assert submit(admin1, ex.id)["data"]["change_request_id"] == cr_id   # resubmitted, same request
    assert admin2.post(f"/api/v1/change-requests/{cr_id}/approve").status_code == 200
    db.session.expire_all()
    review = ExtractionReview.query.filter_by(extraction_id=ex.id).one()
    assert review.statement_unreliable and review.confirmed_metrics is None
