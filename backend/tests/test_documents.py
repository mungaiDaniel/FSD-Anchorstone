"""Phase 2a item 6: encrypted document storage."""
import hashlib
import io
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.database.database import db
from app.Documents import crypto
from app.Documents.model import DataAccessLog, Document
from app.Documents.store import get_store
from app.utils.audit_log import AuditLog
from conftest import Api, _make_user

PDF = b"%PDF-1.4\n" + b"Jane Wanjiru, ID 12345678, KRA A123456789Z\n" * 200 + b"%%EOF\n"
MARKER = b"Jane Wanjiru, ID 12345678"


def _upload(api, data=PDF, content_type="application/pdf", sensitive=True, expect=201, **form):
    fields = {"document_type": "national_id", "sensitive": "true" if sensitive else "false", **form,
              "file": (io.BytesIO(data), "id-front.pdf", content_type)}
    res = api.client.post("/api/v1/documents", data=fields, headers=api.headers, content_type="multipart/form-data")
    assert res.status_code == expect, res.get_json()
    return res.get_json().get("data")


def _blob(doc_id) -> bytes:
    return get_store().get(db.session.get(Document, uuid.UUID(doc_id)).storage_key)


def test_stored_bytes_are_encrypted_and_the_download_matches(admin1):
    doc = _upload(admin1, entity_type="investor", entity_id="7")
    blob = _blob(doc["id"])
    assert MARKER not in blob and b"%PDF" not in blob
    assert len(blob) == len(PDF) + 16  # GCM tag
    row = db.session.get(Document, uuid.UUID(doc["id"]))
    assert row.key_id == "test-1" and row.storage_key.startswith("documents/") and "Jane" not in row.storage_key
    assert doc["links"] == [{"entity_type": "investor", "entity_id": "7", "purpose": "kyc"}]

    res = admin1.get(f"/api/v1/documents/{doc['id']}/content")
    assert res.status_code == 200 and res.data == PDF
    assert hashlib.sha256(res.data).hexdigest() == doc["sha256"]
    assert res.headers["Cache-Control"] == "no-store"


def test_every_read_is_logged(admin1, users):
    doc = _upload(admin1)
    admin1.get(f"/api/v1/documents/{doc['id']}")
    admin1.get(f"/api/v1/documents/{doc['id']}/content")
    admin1.get(f"/api/v1/documents/{doc['id']}/content")
    logs = DataAccessLog.query.filter_by(document_id=uuid.UUID(doc["id"])).order_by(DataAccessLog.id).all()
    assert [l.action for l in logs] == ["upload", "view", "download", "download"]
    assert {l.user_email for l in logs} == {users["admin1"].email}
    with pytest.raises(DBAPIError, match="insert-only"):
        db.session.execute(text("DELETE FROM data_access_logs"))
        db.session.flush()
    db.session.rollback()


def test_download_needs_the_permission(client, admin1, staff):
    sensitive = _upload(admin1)
    ordinary = _upload(admin1, sensitive=False)
    assert staff.get(f"/api/v1/documents/{sensitive['id']}/content").status_code == 403  # no view.sensitive
    assert staff.get(f"/api/v1/documents/{ordinary['id']}/content").status_code == 200
    nobody = _make_user("nobody@anchorstone.test", "user")
    from app.Access.model import Role
    Role.query.filter_by(legacy_role="user").update({"active": False})
    db.session.commit()
    assert Api(client, nobody.email).get(f"/api/v1/documents/{ordinary['id']}/content").status_code == 403
    assert DataAccessLog.query.filter_by(action="download").count() == 1  # refusals serve and log nothing


def test_upload_validation(admin1, staff):
    _upload(admin1, data=b"not a pdf at all", expect=400)
    _upload(admin1, content_type="application/zip", data=b"PK\x03\x04", expect=400)
    _upload(admin1, document_type="nonsense", expect=400)
    _upload(admin1, data=b"", expect=400)
    _upload(admin1, entity_type="investor", expect=400)  # entity_type without entity_id
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    assert _upload(staff, data=png, content_type="image/png", sensitive=False)["content_type"] == "image/png"


def test_upload_size_limit_comes_from_settings(app, admin1, monkeypatch):
    from app.Settings import business
    real = business.get
    monkeypatch.setattr(business, "get", lambda key, **kw: 1 if key == "documents.max_mb" else real(key, **kw))
    _upload(admin1, data=b"%PDF-" + b"x" * (1024 * 1024), expect=400)


def test_not_configured_without_a_kek(app, admin1, monkeypatch):
    monkeypatch.setitem(app.config, "DOCUMENT_KEK", None)
    res = admin1.client.post("/api/v1/documents", headers=admin1.headers, content_type="multipart/form-data",
                             data={"document_type": "national_id", "file": (io.BytesIO(PDF), "a.pdf", "application/pdf")})
    assert res.status_code == 503 and "not configured" in res.get_json()["message"]


def test_tampered_blob_is_refused_and_reported(admin1):
    doc = _upload(admin1)
    row = db.session.get(Document, uuid.UUID(doc["id"]))
    blob = bytearray(get_store().get(row.storage_key))
    blob[100] ^= 0x01
    get_store().put(row.storage_key, bytes(blob))
    res = admin1.get(f"/api/v1/documents/{doc['id']}/content")
    assert res.status_code == 500 and MARKER not in res.data
    assert AuditLog.query.filter_by(action="DOCUMENT_INTEGRITY_FAILURE").count() == 1


def test_a_blob_moved_onto_another_document_does_not_decrypt(admin1):
    a, b = _upload(admin1), _upload(admin1, data=PDF + b"other")
    store = get_store()
    row_a = db.session.get(Document, uuid.UUID(a["id"]))
    row_b = db.session.get(Document, uuid.UUID(b["id"]))
    store.put(row_b.storage_key, store.get(row_a.storage_key))
    assert admin1.get(f"/api/v1/documents/{b['id']}/content").status_code == 500


# ── Destruction (maker-checker, crypto-shredding) ──


def test_destroyed_document_is_unreadable_even_from_a_copy_of_its_bytes(admin1, superadmin, users):
    doc = _upload(admin1)
    doc_id = uuid.UUID(doc["id"])
    row = db.session.get(Document, doc_id)
    copy_of_blob = get_store().get(row.storage_key)   # e.g. an old backup of the bucket
    nonce, key_before = row.nonce, row.wrapped_data_key
    kek = crypto.kek_for(row.key_id)

    res = admin1.post(f"/api/v1/documents/{doc['id']}/destroy", {"reason": "Erasure request under the DPA"})
    assert res.status_code == 201
    cr_id = res.get_json()["data"]["id"]
    assert admin1.post(f"/api/v1/change-requests/{cr_id}/approve").status_code == 403  # maker
    assert superadmin.post(f"/api/v1/change-requests/{cr_id}/approve").status_code == 200

    db.session.expire_all()
    row = db.session.get(Document, doc_id)
    assert row.status == "destroyed" and row.wrapped_data_key is None and row.destroyed_by == users["super"].email
    assert not get_store().exists(row.storage_key)
    assert admin1.get(f"/api/v1/documents/{doc['id']}/content").status_code == 410

    # Nothing left in the database opens the copied bytes: the data key is gone, and
    # the KEK itself is not the data key.
    with pytest.raises(crypto.IntegrityFailure):
        crypto.open_sealed(copy_of_blob, nonce, kek.key, doc_id.bytes)
    leftovers = db.session.execute(text("SELECT wrapped_data_key FROM documents WHERE id = :i"), {"i": doc_id}).scalar()
    assert leftovers is None
    # Control: with the key that was destroyed, the same copy would have opened.
    data_key = crypto.unwrap(key_before, doc_id.bytes, kek)
    assert crypto.open_sealed(copy_of_blob, nonce, data_key, doc_id.bytes) == PDF


def test_database_refuses_deleting_or_altering_documents(admin1, superadmin):
    doc = _upload(admin1)
    for sql in ("DELETE FROM documents", "UPDATE documents SET sha256 = repeat('0', 64)"):
        with pytest.raises(DBAPIError):
            db.session.execute(text(sql))
            db.session.flush()
        db.session.rollback()
    cr = admin1.post(f"/api/v1/documents/{doc['id']}/destroy", {"reason": "duplicate"}).get_json()["data"]
    superadmin.post(f"/api/v1/change-requests/{cr['id']}/approve")
    with pytest.raises(DBAPIError, match="destroyed"):
        db.session.execute(text("UPDATE documents SET status = 'active', wrapped_data_key = '\\x00'"))
        db.session.flush()
    db.session.rollback()


def test_destruction_rules(admin1, staff, superadmin):
    doc = _upload(admin1)
    assert staff.post(f"/api/v1/documents/{doc['id']}/destroy", {"reason": "x"}).status_code == 403
    assert admin1.post(f"/api/v1/documents/{doc['id']}/destroy", {}).status_code == 400  # reason required
    db.session.execute(text("UPDATE documents SET legal_hold = true"))
    db.session.commit()
    assert admin1.post(f"/api/v1/documents/{doc['id']}/destroy", {"reason": "x"}).status_code == 400


def test_legal_hold_after_the_request_makes_it_stale(admin1, superadmin):
    doc = _upload(admin1)
    cr = admin1.post(f"/api/v1/documents/{doc['id']}/destroy", {"reason": "x"}).get_json()["data"]
    db.session.execute(text("UPDATE documents SET legal_hold = true"))
    db.session.commit()
    assert superadmin.post(f"/api/v1/change-requests/{cr['id']}/approve").status_code == 409
    assert db.session.get(Document, uuid.UUID(doc["id"])).status == "active"
