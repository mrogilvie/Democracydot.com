"""Save Parliament of Tasmania Bill records and PDFs into ./snapshot.

Run from a machine where the Parliament website is reachable:

    python build_snapshot.py            # Bills introduced in 2025 and 2026
    python build_snapshot.py 2026       # chosen years only

Existing PDFs are kept, so an interrupted run can simply be repeated.
"""

import hashlib
import json
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import demodot
from bill_snapshot import INDEX_PATH, SNAPSHOT_DIR

DEFAULT_YEARS = (2025, 2026)
PAUSE_SECONDS = 0.4


def bill_list(year: int) -> dict[str, str]:
    pages = (
        demodot.PARLIAMENT_BILLS_URL,
        f"{demodot.PARLIAMENT_BILLS_URL}/bills-introduced-into-parliament-{year}",
    )
    bills: dict[str, str] = {}
    for page in pages:
        for url, title in demodot._fetch_parliament_bill_links(page):
            if urlparse(url).path.startswith(f"/bills/bills{year}/"):
                bills.setdefault(url, title)
        time.sleep(PAUSE_SECONDS)
    return bills


def save_pdf(url: str, host: str, pdfs: dict[str, str]) -> None:
    if url in pdfs:
        return
    name = url.rsplit("/", 1)[-1] or "document.pdf"
    filename = f"{hashlib.sha1(url.encode()).hexdigest()[:10]}-{name}"
    path = SNAPSHOT_DIR / "pdfs" / filename
    if not path.exists():
        path.write_bytes(demodot.fetch_official_pdf(url, host))
        time.sleep(PAUSE_SECONDS)
    pdfs[url] = filename


def main() -> None:
    years = tuple(int(arg) for arg in sys.argv[1:]) or DEFAULT_YEARS
    (SNAPSHOT_DIR / "pdfs").mkdir(parents=True, exist_ok=True)
    demodot.USE_SNAPSHOT = False

    bills: dict[str, dict] = {}
    pdfs: dict[str, str] = {}
    acts: dict[str, str] = {}
    for year in years:
        listing = bill_list(year)
        print(f"{year}: {len(listing)} Bills")
        for number, (url, title) in enumerate(sorted(listing.items()), start=1):
            entry: dict = {"title": title, "documents": None, "status": None}
            try:
                entry["documents"] = demodot.find_parliament_bill_document_urls(url)
                for urls in entry["documents"].values():
                    for document_url in urls:
                        save_pdf(document_url, demodot.PARLIAMENT_HOST, pdfs)
            except (OSError, ValueError) as error:
                print(f"  [{number}] {title}: documents skipped ({error})")
            time.sleep(PAUSE_SECONDS)
            try:
                entry["status"] = demodot.get_parliament_bill_status(url)
            except (OSError, ValueError):
                pass
            time.sleep(PAUSE_SECONDS)
            try:
                act_title = demodot.parliament_bill_act_title(title)
                act_url = demodot.find_act_pdf_url(act_title)
                save_pdf(act_url, demodot.LEGISLATION_HOST, pdfs)
                acts[act_title] = act_url
            except (OSError, ValueError):
                pass
            time.sleep(PAUSE_SECONDS)
            bills[url] = entry
            print(f"  [{number}/{len(listing)}] {title}")

    index = {
        "generated": date.today().isoformat(),
        "years": list(years),
        "bills": bills,
        "pdfs": pdfs,
        "acts": acts,
    }
    INDEX_PATH.write_text(json.dumps(index, indent=1), encoding="utf-8")
    used = set(pdfs.values())
    for stale in (SNAPSHOT_DIR / "pdfs").iterdir():
        if stale.name not in used:
            stale.unlink()
    size = sum(path.stat().st_size for path in Path(SNAPSHOT_DIR).rglob("*") if path.is_file())
    print(f"Saved {len(bills)} Bills, {len(pdfs)} PDFs, {len(acts)} Acts ({size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
