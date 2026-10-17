"""
Write the JSON Schema file for each AI document type from app/DocAI/types.py.

    venv/Scripts/python scripts/build_docai_schemas.py          write any missing file
    venv/Scripts/python scripts/build_docai_schemas.py --check  exit 1 if a file differs from the spec

A schema file is never overwritten: past extractions name it and store its SHA-256.
To change what a type reads, bump its schema_version in types.py and run this again.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.DocAI import schema_registry as schemas  # noqa: E402
from app.DocAI.types import SCHEMA_DIR, TYPES  # noqa: E402


def main(check: bool) -> int:
    SCHEMA_DIR.mkdir(exist_ok=True)
    bad = 0
    for t in TYPES:
        text = schemas.dumps(schemas.build(t))
        path = t.schema_path
        if not path.exists():
            if check:
                print(f"missing: {path.name}")
                bad += 1
            else:
                path.write_text(text, encoding="utf-8", newline="\n")
                print(f"wrote:   {path.name}")
        elif path.read_text(encoding="utf-8") != text:
            print(f"differs: {path.name} (bump schema_version in types.py instead of editing it)")
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main("--check" in sys.argv))
