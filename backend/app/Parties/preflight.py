"""
Pre-flight report for moving investors onto parties (02-domain-model §6.1 step 1).

    flask --app main kyc-preflight

Read-only. Lists what would stop identifiers being unique, and what investor
relations should look at. The migration parties_from_investors runs the same
duplicate checks (frozen copy) and refuses to run while any remain.
"""
import re
from collections import defaultdict

from app.Parties.normalise import normalise_identifier, normalise_phone

_NATIONAL_ID = re.compile(r"^\d{6,9}$")


def classify_id(value: str | None) -> str | None:
    """national_id for 6–9 digits; anything else is taken as a passport and flagged."""
    normalised = normalise_identifier("national_id", value)
    if not normalised:
        return None
    return "national_id" if _NATIONAL_ID.match(normalised) else "passport"


def investor_preflight(rows) -> dict:
    """rows: (id, client_code, full_name, id_number, kra_pin, phone)."""
    by_id, by_pin = defaultdict(list), defaultdict(list)
    report = {"duplicate_id_numbers": [], "duplicate_kra_pins": [], "passport_like_ids": [], "missing_id_and_pin": [],
              "unreadable_phones": []}
    for inv_id, code, name, id_number, kra_pin, phone in rows:
        who = {"id": inv_id, "client_code": code, "full_name": name}
        n_id = normalise_identifier("national_id", id_number)
        n_pin = normalise_identifier("kra_pin", kra_pin)
        if n_id:
            by_id[n_id].append({**who, "value": id_number})
            if classify_id(id_number) != "national_id":
                report["passport_like_ids"].append({**who, "value": id_number})
        if n_pin:
            by_pin[n_pin].append({**who, "value": kra_pin})
        if not n_id and not n_pin:
            report["missing_id_and_pin"].append(who)
        if phone and not normalise_phone(phone):
            report["unreadable_phones"].append({**who, "value": phone})
    report["duplicate_id_numbers"] = [{"value": k, "investors": v} for k, v in sorted(by_id.items()) if len(v) > 1]
    report["duplicate_kra_pins"] = [{"value": k, "investors": v} for k, v in sorted(by_pin.items()) if len(v) > 1]
    report["blocking"] = bool(report["duplicate_id_numbers"] or report["duplicate_kra_pins"])
    return report


def format_report(report: dict) -> str:
    lines = []
    for key, title in (("duplicate_id_numbers", "Investors sharing an ID number (BLOCKS the migration)"),
                       ("duplicate_kra_pins", "Investors sharing a KRA PIN (BLOCKS the migration)")):
        lines.append(f"{title}: {len(report[key])}")
        for group in report[key]:
            lines.append(f"  {group['value']}: " + ", ".join(f"{i['client_code']} {i['full_name']} ({i['value']})"
                                                         for i in group["investors"]))
    for key, title in (("passport_like_ids", "ID numbers that look like passports (migrated as passports)"),
                       ("missing_id_and_pin", "Investors with neither an ID number nor a KRA PIN"),
                       ("unreadable_phones", "Phone numbers that can't be read (kept as typed, flagged)")):
        lines.append(f"{title}: {len(report[key])}")
        for i in report[key]:
            lines.append(f"  {i['client_code']} {i['full_name']}" + (f" ({i['value']})" if i.get("value") else ""))
    lines.append("Migration can run." if not report["blocking"] else "Fix the duplicates above before migrating.")
    return "\n".join(lines)
