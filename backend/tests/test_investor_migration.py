"""
Phase 2b item 2: existing investors move onto parties and investment accounts
with nothing visible changing (02-domain-model §6, phase plan 2b criteria 1–3, 6).

The golden test loads the demo book captured by the pre-2b code
(tests/golden/capture.py) into the pre-2b schema, runs the migrations, and
requires every investor screen, statement and Excel report to be identical.
"""
import pytest
from flask_jwt_extended import create_access_token
from flask_migrate import downgrade, upgrade
from sqlalchemy import text

from app.database.database import db
from app.Investors.model import Investor
from app.Parties.model import Account, Party, PartyBankAccount, PartyContact, PartyIdentifier, PartyPerson, PartyRole
from golden.capture import DATA_FILE, OUTPUTS_FILE, PRE_2B_REVISION, capture, load_data, read

PARTIES_REVISION = "b8c9d0e1f2a3"  # parties exist, investors not yet moved


def _alembic(fn, revision=None):
    db.session.commit()
    db.session.remove()
    fn(revision=revision) if revision else fn()


@pytest.fixture
def migrated_demo_book(app):
    """The pre-2b demo book, migrated by the real migrations; the schema is back at head afterwards."""
    _alembic(downgrade, PRE_2B_REVISION)
    try:
        load_data(db, read(DATA_FILE), [t.name for t in db.metadata.sorted_tables])
        _alembic(upgrade)
    except Exception:
        db.session.rollback()
        _alembic(upgrade)
        raise
    return read(DATA_FILE)


def _sign(email):
    return {"Authorization": f"Bearer {create_access_token(identity=email)}"}


def test_migration_golden_outputs_identical(migrated_demo_book, client):
    golden = read(OUTPUTS_FILE)
    now = capture(client, _sign)
    assert set(now) == set(golden)
    different = [k for k in sorted(golden) if now[k] != golden[k]]
    assert not different, f"{len(different)} outputs changed, first: {different[0]}\n" \
                          f"before: {str(golden[different[0]])[:600]}\nafter:  {str(now[different[0]])[:600]}"
    # The checks above cover the 7 Excel reports, the statements and the investor screens.
    assert sum(k.startswith("report:") for k in golden) == 7
    assert sum(k.startswith("pdf:account-statement/") for k in golden) == 14


def test_migration_one_party_and_account_per_investor(migrated_demo_book):
    investors = Investor.query.order_by(Investor.id).all()
    assert len(investors) == 14
    assert Party.query.count() == 14 == Account.query.count()
    assert PartyRole.query.filter_by(role="investor", status="active").count() == 14
    for inv in investors:
        party, account = db.session.get(Party, inv.party_id), db.session.get(Account, inv.account_id)
        assert account.account_no == inv.client_code and account.party_id == party.id
        assert account.account_type == "investment" and account.branch_id == inv.branch_id == party.home_branch_id
        assert account.status == inv.status
        assert party.display_name == inv.full_name and party.party_type == "person"
        assert party.kyc_status == "incomplete"
        email = PartyContact.query.filter_by(party_id=party.id, kind="email").one()
        assert email.value == inv.email and email.is_primary
    # Party numbers follow the investor order; the ACL- sequence carries on where it was.
    assert [p.party_no for p in Party.query.order_by(Party.id)] == [f"P-{n:07d}" for n in range(1, 15)]
    assert db.session.execute(text("SELECT last_value FROM investor_client_code_seq")).scalar() == 14

    by_code = {i.client_code: i for i in investors}
    grace = by_code["ACL-000001"]
    idents = {i.id_type: i for i in PartyIdentifier.query.filter_by(party_id=grace.party_id)}
    assert idents["national_id"].value_display == "28456712" and idents["kra_pin"].value_normalised == "A012345678K"
    person = db.session.get(PartyPerson, grace.party_id)
    assert (person.first_name, person.middle_name, person.last_name, person.name_needs_review) == \
        ("Grace", "Wanjiku", "Mwangi", True)
    mobile = PartyContact.query.filter_by(party_id=grace.party_id, kind="mobile").one()
    assert (mobile.value, mobile.value_normalised) == ("0712 345 678", "+254712345678")
    bank = PartyBankAccount.query.filter_by(party_id=grace.party_id).one()
    assert (bank.kind, bank.account_no, bank.is_default_payout) == ("mpesa", "0712345678", True)

    edge = {i.full_name: i for i in investors}
    hassan = edge["Hassan Omar Juma"]
    assert PartyIdentifier.query.filter_by(party_id=hassan.party_id, id_type="kra_pin").one().value_normalised == "A012938475H"
    kamau = edge["Kamau"]
    assert PartyIdentifier.query.filter_by(party_id=kamau.party_id).count() == 0
    assert db.session.get(PartyPerson, kamau.party_id).last_name == "Kamau"
    assert PartyBankAccount.query.filter_by(party_id=kamau.party_id).count() == 0
    closed = edge["Wambui Closed-Account"]
    assert PartyIdentifier.query.filter_by(party_id=closed.party_id).one().id_type == "passport"
    assert PartyContact.query.filter_by(party_id=closed.party_id, kind="mobile").one().value_normalised is None
    account = db.session.get(Account, closed.account_id)
    assert account.status == "closed" and account.closed_on is not None


def _insert_old_investor(code, name, email, id_number=None, kra_pin=None):
    db.session.execute(text(
        "INSERT INTO investors (client_code, full_name, email, id_number, kra_pin, created_at, created_by, "
        "date_created, date_updated) "
        "VALUES (:c, :n, :e, :i, :k, now(), 'staff@anchorstone.test', now(), now())"),
        {"c": code, "n": name, "e": email, "i": id_number, "k": kra_pin})


@pytest.mark.parametrize("field,first,second", [("id_number", "22 981 045", "22981045"),
                                                 ("kra_pin", "a009876543p", "A009876543P")])
def test_migration_refuses_duplicates_and_prints_list(app, field, first, second):
    _alembic(downgrade, PARTIES_REVISION)
    try:
        _insert_old_investor("ACL-000001", "Peter Kamau", "p1@example.com", **{field: first})
        _insert_old_investor("ACL-000002", "Peter K. Njoroge", "p2@example.com", **{field: second})
        _insert_old_investor("ACL-000003", "Grace Mwangi", "g@example.com", id_number="28456712")
        db.session.commit()

        # The read-only pre-flight lists them and exits non-zero …
        result = app.test_cli_runner().invoke(args=["kyc-preflight"])
        assert result.exit_code == 1, result.output
        assert "ACL-000001 Peter Kamau" in result.output and "ACL-000002 Peter K. Njoroge" in result.output
        assert "Fix the duplicates" in result.output

        # … and the migration refuses, naming both, without changing anything.
        label = "ID number" if field == "id_number" else "KRA PIN"
        from alembic import command
        from flask import current_app

        db.session.commit()
        db.session.remove()
        with pytest.raises(RuntimeError) as err:  # Alembic itself, so the migration's error surfaces
            command.upgrade(current_app.extensions["migrate"].migrate.get_config(), "head")
        message = str(err.value)
        assert "Can't move investors onto parties" in message and label in message
        assert "ACL-000001 Peter Kamau, ACL-000002 Peter K. Njoroge" in message
        db.session.rollback()
        assert db.session.execute(text("SELECT version_num FROM alembic_version")).scalar() == PARTIES_REVISION
        assert db.session.execute(text("SELECT count(*) FROM parties")).scalar() == 0

        # Once investor relations fixes it, the migration runs.
        db.session.execute(text(f"UPDATE investors SET {field} = NULL WHERE client_code = 'ACL-000002'"))
        db.session.commit()
        assert app.test_cli_runner().invoke(args=["kyc-preflight"]).exit_code == 0
        _alembic(upgrade)
        assert Party.query.count() == 3 and Account.query.count() == 3
    finally:
        db.session.rollback()
        if db.session.execute(text("SELECT version_num FROM alembic_version")).scalar() == PARTIES_REVISION:
            db.session.execute(text("DELETE FROM investors"))
            _alembic(upgrade)


def test_new_investor_creates_party_and_account(make_investor, staff):
    inv = make_investor(full_name="Jane Wanjiru Doe", id_number="12345678", kra_pin="a012345678k",
                        payout_method="bank", bank_name="KCB Bank", payout_account="1145829364")
    row = db.session.get(Investor, inv["id"])
    party = db.session.get(Party, row.party_id)
    account = db.session.get(Account, row.account_id)
    assert account.account_no == inv["client_code"] == "ACL-000001" and account.status == "active"
    assert party.party_no == "P-0000001" and party.display_name == "Jane Wanjiru Doe"
    assert [r.role for r in PartyRole.query.filter_by(party_id=party.id)] == ["investor"]
    detail = staff.get(f"/api/v1/parties/{party.id}").get_json()["data"]
    assert {(i["id_type"], i["value"]) for i in detail["identifiers"]} == {("national_id", "12345678"),
                                                                          ("kra_pin", "A012345678K")}
    assert detail["bank_accounts"][0]["bank_name"] == "KCB Bank"
    # The investor API response is unchanged in shape.
    assert set(inv) >= {"client_code", "full_name", "email", "phone", "id_number", "kra_pin", "payout_method"}
    assert "party_id" not in inv and "account_id" not in inv


def test_investor_with_an_existing_id_is_refused_naming_the_client(make_investor, staff):
    res = staff.post("/api/v1/parties", {"party_type": "person", "person": {"first_name": "Mary", "last_name": "Owino"},
                                         "identifiers": [{"id_type": "national_id", "value": "33456789"}],
                                         "roles": ["guarantor"]})
    assert res.status_code == 201
    res = staff.post("/api/v1/investors", {"full_name": "Mary A Owino", "email": "mary@example.com", "id_number": "33 456 789"})
    assert res.status_code == 409
    assert "ID number already registered to P-0000001 (Mary Owino)" in res.get_json()["message"]
    assert Investor.query.count() == 0 and Party.query.count() == 1


def test_attach_investor_role_to_existing_party_keeps_acl_sequence(make_investor, staff):
    make_investor()  # ACL-000001
    res = staff.post("/api/v1/parties", {
        "party_type": "person", "person": {"first_name": "Mary", "last_name": "Owino"}, "roles": ["guarantor"],
        "identifiers": [{"id_type": "national_id", "value": "33456789"}, {"id_type": "kra_pin", "value": "A018765432Q"}],
        "contacts": [{"kind": "mobile", "value": "0745667889"}, {"kind": "email", "value": "mary@example.com"}],
        "bank_accounts": [{"kind": "mpesa", "account_no": "0745667889"}]})
    mary = res.get_json()["data"]
    res = staff.post(f"/api/v1/parties/{mary['id']}/investor", {})
    assert res.status_code == 201, res.get_json()
    inv = res.get_json()["data"]
    assert inv["client_code"] == "ACL-000002"
    assert (inv["full_name"], inv["email"], inv["phone"], inv["id_number"], inv["kra_pin"]) == \
        ("Mary Owino", "mary@example.com", "0745667889", "33456789", "A018765432Q")
    assert (inv["payout_method"], inv["payout_account"]) == ("mpesa", "0745667889")
    assert Party.query.count() == 2  # no second record for Mary
    roles = {r["role"] for r in staff.get(f"/api/v1/parties/{mary['id']}").get_json()["data"]["roles"]}
    assert roles == {"guarantor", "investor"}
    assert staff.post(f"/api/v1/parties/{mary['id']}/investor", {}).status_code == 409
    # Permission: attaching is creating an investor.
    assert staff.post("/api/v1/parties/999/investor", {}).status_code == 404


def test_one_email_per_investor_still_enforced(make_investor, staff):
    make_investor(email="same@example.com")
    res = staff.post("/api/v1/investors", {"full_name": "Other", "email": "SAME@example.com"})
    assert res.status_code == 409 and "already uses this email" in res.get_json()["message"]
    other = staff.post("/api/v1/parties", {"party_type": "person", "person": {"first_name": "O", "last_name": "P"},
                                           "contacts": [{"kind": "email", "value": "same@example.com"}]}).get_json()["data"]
    res = staff.post(f"/api/v1/parties/{other['id']}/investor", {})
    assert res.status_code == 409 and "already uses this email" in res.get_json()["message"]
    assert staff.post(f"/api/v1/parties/{other['id']}/investor", {"email": "own@example.com"}).status_code == 201


def test_investor_edits_and_closing_reach_the_party(make_investor, staff, admin1):
    inv = make_investor(full_name="Jane Doe", phone="0712345678")
    row = db.session.get(Investor, inv["id"])
    res = staff.patch(f"/api/v1/investors/{inv['id']}", {"phone": "0722 000 111", "email": "jane.new@example.com"})
    assert res.status_code == 200
    contacts = {c.kind: c for c in PartyContact.query.filter_by(party_id=row.party_id)}
    assert contacts["mobile"].value_normalised == "+254722000111" and contacts["email"].value == "jane.new@example.com"
    assert admin1.patch(f"/api/v1/investors/{inv['id']}/status", {"status": "closed"}).status_code == 200
    account = db.session.get(Account, row.account_id)
    db.session.refresh(account)
    assert account.status == "closed" and account.closed_on is not None
