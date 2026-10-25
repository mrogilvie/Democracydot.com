"""Read-only access to the saved Parliament Bill records in ./snapshot.

The snapshot is built by build_snapshot.py and lets the app work when the live
Parliament website refuses requests from the hosting provider.
"""

import json
from functools import lru_cache
from pathlib import Path


SNAPSHOT_DIR = Path(__file__).resolve().with_name("snapshot")
INDEX_PATH = SNAPSHOT_DIR / "index.json"


@lru_cache(maxsize=1)
def _index() -> dict:
    try:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"generated": None, "bills": {}, "pdfs": {}, "acts": {}}


def generated_date() -> str | None:
    return _index().get("generated")


def bill_links() -> list[tuple[str, str]]:
    return [(url, bill["title"]) for url, bill in _index()["bills"].items()]


def bill_documents(bill_url: str) -> dict[str, list[str]] | None:
    bill = _index()["bills"].get(bill_url)
    return bill.get("documents") if bill else None


def bill_status(bill_url: str) -> dict | None:
    bill = _index()["bills"].get(bill_url)
    return bill.get("status") if bill else None


def act_pdf_url(act_title: str) -> str | None:
    return _index()["acts"].get(act_title)


def pdf_bytes(document_url: str) -> bytes | None:
    filename = _index()["pdfs"].get(document_url)
    if not filename:
        return None
    try:
        return (SNAPSHOT_DIR / "pdfs" / filename).read_bytes()
    except OSError:
        return None
