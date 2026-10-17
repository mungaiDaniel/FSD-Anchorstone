"""
The versioned JSON Schemas (one file per document type and version).

    build(doc_type)        the schema the spec in types.py describes (used by
                           scripts/build_docai_schemas.py to write the file once)
    load(doc_type)         the committed file, its version name and SHA-256
    load_prompt(doc_type)  the prompt file (prompts/<type>.v<n>.md), its version and SHA-256
    for_api(schema)        the copy sent to the API: keywords structured output
                           doesn't support (min/max, lengths) are removed; Python
                           still checks them on the answer (validate())
    validate(schema, obj)  list of readable errors, empty when valid

Every value the model returns has the same envelope (05 §5): value, confidence,
source page, a short source snippet, legibility and notes. Money is a string.
Statements are read one page at a time; their schema describes one page.
"""
import copy
import hashlib
import json
from functools import lru_cache

from jsonschema import Draft202012Validator

from app.DocAI.types import DETECTABLE, DocType

_UNSUPPORTED = {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "minLength",
                "maxLength", "minItems", "maxItems", "uniqueItems", "pattern", "$schema", "$id"}
NULLABLE_STRING = {"anyOf": [{"type": "string"}, {"type": "null"}]}


def _describe(hint: str, kind: str) -> str:
    fmt = {"date": "Date as YYYY-MM-DD.", "past_date": "Date as YYYY-MM-DD.",
           "money": "Amount as a plain number with 2 decimals, no commas or currency, e.g. 12500.00.",
           "signed_money": "Amount as a plain number with 2 decimals, no commas or currency; negative with a "
                           "leading minus, e.g. -1250.00.",
           "integer": "Whole number, digits only.", "year": "Four-digit year.", "sex": "M or F.",
           "kenyan_id": "Digits only.", "kra_pin": "11 characters, e.g. A000000000Z."}.get(kind, "")
    return " ".join(p for p in (hint and hint.rstrip(".") + ".", fmt) if p) or "As printed."


def _object(properties: dict) -> dict:
    return {"type": "object", "additionalProperties": False, "required": list(properties), "properties": properties}


def _fields(items) -> dict:
    return _object({f.name: {"$ref": "#/$defs/field", "description": _describe(f.hint, f.kind)} for f in items})


def build(t: DocType) -> dict:
    defs = {
        "field": _object({
            "value": {**NULLABLE_STRING, "description": "Exactly what is printed (normalised as described), "
                                                        "or null if it is absent or can't be read."},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1,
                           "description": "0 to 1: how sure you are the value is read correctly."},
            "source_page": {"type": "integer", "minimum": 1, "description": "1-based page the value is on."},
            "source_text": {**NULLABLE_STRING, "maxLength": 120,
                            "description": "Up to 80 characters copied from around the value."},
            "legibility": {"type": "string", "enum": ["good", "partial", "unreadable"]},
            "notes": {**NULLABLE_STRING, "description": "Anything the reviewer should know, or null."},
        }),
    }
    top = {
        "detected_document_type": {"type": "string", "enum": list(DETECTABLE),
                                   "description": "What this document actually is, whatever it was declared as."},
        "readable": {"type": "boolean", "description": "False if the page or document can't be read reliably."},
        "unreadable_reason": {**NULLABLE_STRING, "description": "Why it can't be read (blur, glare, cropped, "
                                                               "too dark ...), or null."},
    }
    if t.statement:
        defs["row"] = _object({
            "row": {"type": "integer", "minimum": 1, "description": "Row number as listed on the page, from 1."},
            "date": {**NULLABLE_STRING, "description": "Transaction or completion date as YYYY-MM-DD."},
            "description": {**NULLABLE_STRING, "description": "Narrative / details, as printed."},
            "reference": {**NULLABLE_STRING, "description": "Reference, cheque or receipt number, if any."},
            "debit": {**NULLABLE_STRING, "description": "Money out (withdrawn / paid out), plain number with 2 "
                                                        "decimals, or null."},
            "credit": {**NULLABLE_STRING, "description": "Money in (paid in / deposited), plain number with 2 "
                                                         "decimals, or null."},
            "balance": {**NULLABLE_STRING, "description": "Running balance printed on the row, or null."},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        })
        props = {
            **top,
            "page_number": {"type": "integer", "minimum": 1},
            "rows_order": {"type": "string", "enum": ["oldest_first", "newest_first"],
                           "description": "The order the rows are printed in on this page."},
            "header": {**_fields(t.fields), "description": "Statement details printed on this page (null values "
                                                           "for anything not on this page)."},
            "page_opening_balance": {"$ref": "#/$defs/field",
                                     "description": "Balance brought forward / opening balance printed on this "
                                                    "page, or null value if none is printed."},
            "page_closing_balance": {"$ref": "#/$defs/field",
                                     "description": "Balance carried forward / closing balance printed on this "
                                                    "page, or null value if none is printed."},
            "transactions": {"type": "array", "items": {"$ref": "#/$defs/row"}},
            "warnings": {"type": "array", "items": {"type": "string"}},
        }
    else:
        fields = _fields(t.fields)
        for group, items in t.lists.items():
            fields["properties"][group] = {"type": "array", "items": _fields(items)}
            fields["required"].append(group)
        props = {
            **top,
            "page_count_seen": {"type": "integer", "minimum": 1},
            "fields": fields,
            "warnings": {"type": "array", "items": {"type": "string"}},
        }
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": t.schema_name,
            "title": f"{t.label} ({t.schema_name})", **_object(props), "$defs": defs}


def dumps(schema: dict) -> str:
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"


@lru_cache(maxsize=None)
def _read(path: str) -> tuple[dict, str]:
    raw = open(path, "rb").read()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def load(t: DocType) -> tuple[dict, str, str]:
    """(schema, version name, SHA-256 of the file)."""
    schema, sha = _read(str(t.schema_path))
    return copy.deepcopy(schema), t.schema_name, sha


def load_prompt(t: DocType) -> tuple[str, str, str]:
    """(prompt text, version name, SHA-256 of the file)."""
    raw = _read_bytes(str(t.prompt_path))
    return raw.decode("utf-8"), t.prompt_name, hashlib.sha256(raw).hexdigest()


@lru_cache(maxsize=None)
def _read_bytes(path: str) -> bytes:
    return open(path, "rb").read()


def for_api(schema: dict) -> dict:
    """Unsupported keywords removed, and local $refs inlined (a $ref keeps its sibling description)."""
    defs = schema.get("$defs", {})

    def walk(node):
        if isinstance(node, dict):
            ref = node.get("$ref", "")
            if ref.startswith("#/$defs/"):
                merged = {**defs[ref.split("/")[-1]], **{k: v for k, v in node.items() if k != "$ref"}}
                return walk(merged)
            return {k: walk(v) for k, v in node.items() if k not in _UNSUPPORTED and k != "$defs"}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


def validate(schema: dict, obj) -> list[str]:
    errors = sorted(Draft202012Validator(schema).iter_errors(obj), key=lambda e: list(e.absolute_path))
    out = []
    for e in errors[:20]:
        where = "/".join(str(p) for p in e.absolute_path) or "(top)"
        out.append(f"{where}: {e.message}"[:300])
    return out
