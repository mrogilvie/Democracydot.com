import json
import os
import re
import zipfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from io import BytesIO
from pathlib import Path
from html import unescape as html_unescape
from html.parser import HTMLParser
from typing import TypedDict
from urllib.parse import unquote, urlencode, urljoin, urlparse
from urllib.error import HTTPError
from urllib.request import Request, urlopen as _urlopen

import bill_snapshot
import streamlit as st
from dotenv import load_dotenv
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    OpenAIError,
    RateLimitError,
)
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from streamlit.errors import StreamlitSecretNotFoundError
from streamlit.runtime.scriptrunner import get_script_run_ctx


MODEL = "gpt-4o-mini"
MAX_SOURCE_CHARS = 60_000
PARLIAMENT_URL = "https://www.parliament.tas.gov.au/"
PARLIAMENT_HOST = urlparse(PARLIAMENT_URL).hostname
PARLIAMENT_SEARCH_URL = f"{PARLIAMENT_URL.rstrip('/')}/search-results"
PARLIAMENT_BILLS_URL = f"{PARLIAMENT_URL.rstrip('/')}/bills"
LEGISLATION_URL = "https://www.legislation.tas.gov.au"
LEGISLATION_HOST = urlparse(LEGISLATION_URL).hostname
LEGISLATION_SEARCH_URL = f"{LEGISLATION_URL}/projectdata"
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
}
# Tried in order when a site answers 403 to the default BROWSER_HEADERS.
FALLBACK_HEADER_PROFILES = (
    {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/17.4 Safari/605.1.15"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-AU,en;q=0.9",
        "Referer": PARLIAMENT_URL,
        "Upgrade-Insecure-Requests": "1",
    },
    {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0"
        ),
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": PARLIAMENT_URL,
    },
    {
        "User-Agent": "curl/8.5.0",
        "Accept": "*/*",
    },
)
HANSARD_SEARCH_URL = "https://search.parliament.tas.gov.au/search/search/"
HANSARD_CHAMBERS = ("House of Assembly", "Legislative Council")


USE_SNAPSHOT = True
# After Parliament refuses this host, skip further live requests for a while.
LIVE_BLOCK_SECONDS = 300
_live_blocked_until = 0.0


def urlopen(request: Request, timeout: float):
    """Open a request, retrying with other header profiles if refused with 403."""
    global _live_blocked_until
    is_parliament = urlparse(request.full_url).hostname == PARLIAMENT_HOST
    if USE_SNAPSHOT and is_parliament and time.monotonic() < _live_blocked_until:
        raise HTTPError(
            request.full_url,
            403,
            f"Forbidden - refused by {PARLIAMENT_HOST} ({request.full_url})",
            {},
            None,
        )
    try:
        return _urlopen(request, timeout=timeout)
    except HTTPError as error:
        if error.code != 403:
            raise
        last_error = error

    custom_headers = {
        name: value
        for name, value in request.header_items()
        if name.casefold() == "x-requested-with"
    }
    for profile in FALLBACK_HEADER_PROFILES:
        retry = Request(request.full_url, headers={**profile, **custom_headers})
        try:
            return _urlopen(retry, timeout=timeout)
        except HTTPError as error:
            if error.code != 403:
                raise
            last_error = error
    # A short pause then one more attempt: some firewalls refuse bursts only briefly.
    time.sleep(2)
    try:
        return _urlopen(request, timeout=timeout)
    except HTTPError as error:
        if error.code != 403:
            raise
        last_error = error
    if is_parliament:
        _live_blocked_until = time.monotonic() + LIVE_BLOCK_SECONDS
    raise HTTPError(
        last_error.url,
        last_error.code,
        f"Forbidden - refused by {urlparse(last_error.url).hostname} "
        f"({last_error.url})",
        last_error.headers,
        None,
    )


class _ParliamentLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self.href: str | None = None
        self.label: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag == "a":
            self.href = dict(attrs).get("href")
            self.label = []

    def handle_data(self, data: str) -> None:
        if self.href:
            text = data.strip()
            if text:
                self.label.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.href:
            self.links.append((self.href, " ".join(self.label)))
            self.href = None
            self.label = []


class _BillStatusTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_table = False
        self.current_row: list[str] | None = None
        self.current_cell: list[str] | None = None
        self.rows: list[list[str]] = []
        self.status_rows: list[list[str]] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag == "table" and not self.in_table:
            self.in_table = True
            self.rows = []
        elif self.in_table and tag == "tr":
            self.current_row = []
        elif self.in_table and tag in ("th", "td"):
            self.current_cell = []

    def handle_data(self, data: str) -> None:
        if self.current_cell is not None:
            self.current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.in_table and tag in ("th", "td") and self.current_cell is not None:
            self.current_row.append(" ".join(" ".join(self.current_cell).split()))
            self.current_cell = None
        elif self.in_table and tag == "tr" and self.current_row is not None:
            self.rows.append(self.current_row)
            self.current_row = None
        elif self.in_table and tag == "table":
            headers = self.rows[0] if self.rows else []
            if (
                len(headers) >= 4
                and headers[0].casefold().startswith("house of assembly")
                and headers[2].casefold().startswith("legislative council")
            ):
                self.status_rows = self.rows
            self.in_table = False


class ChamberStatus(TypedDict):
    passed_date: str | None
    latest_stage: str | None
    latest_date: str | None
    negatived_date: str | None


class BillStatus(TypedDict):
    house_of_assembly: ChamberStatus
    legislative_council: ChamberStatus
    royal_assent_date: str | None


def _use_snapshot_notice() -> None:
    """Show that saved Parliament records are in use; never let it break a lookup."""
    try:
        # The context's coordinator is recreated each script run, so it marks the run.
        run_marker = get_script_run_ctx().parallel_coordinator
        if st.session_state.get("_snapshot_notice_run") is run_marker:
            return
        st.session_state["_snapshot_notice_run"] = run_marker
        st.warning(
            "If Parliament records cannot be reached live, saved 2025-2026 "
            "records are used.",
            icon=":material/info:",
        )
    except Exception:
        pass


def get_openai_client() -> OpenAI | None:
    load_dotenv(Path(__file__).resolve().with_name(".env"))
    api_key = (st.session_state.get("openai_api_key") or "").strip()
    if not api_key:
        try:
            api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
        except StreamlitSecretNotFoundError:
            api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        st.error("OpenAI API key not found. Enter your key in the sidebar.")
        return None
    return OpenAI(api_key=api_key, timeout=45)


def report_openai_error(error: OpenAIError) -> None:
    if isinstance(error, AuthenticationError):
        st.error("OpenAI rejected the API key. Check that it is valid and active.")
    elif isinstance(error, RateLimitError):
        st.error("OpenAI rate limit or quota reached. Check your account and try again.")
    elif isinstance(error, APITimeoutError):
        st.error("The OpenAI request timed out. Please try again.")
    elif isinstance(error, APIConnectionError):
        st.error("Could not connect to OpenAI. Check the connection and try again.")
    elif isinstance(error, APIStatusError):
        st.error(f"OpenAI returned an API error (HTTP {error.status_code}).")
    else:
        st.error("The OpenAI request failed. Please try again.")


def _fetch_parliament_bill_links(page_url: str) -> list[tuple[str, str]]:
    """Return (url, title) for every Bill record linked from a Parliament page."""
    request = Request(page_url, headers={**BROWSER_HEADERS})
    with urlopen(request, timeout=15) as response:
        final_url = urlparse(response.geturl())
        if final_url.scheme != "https" or final_url.hostname != PARLIAMENT_HOST:
            raise ValueError(
                "The Parliament website redirected to an unexpected address."
            )
        page = response.read().decode("utf-8")

    parser = _ParliamentLinkParser()
    parser.feed(page)
    bills = []
    for href, label in parser.links:
        bill_url = urljoin(page_url, href)
        parsed_bill_url = urlparse(bill_url)
        if (
            parsed_bill_url.scheme == "https"
            and parsed_bill_url.hostname == PARLIAMENT_HOST
            and parsed_bill_url.path.startswith("/bills/")
            and label
        ):
            bills.append((bill_url, label))
    return bills


def _match_parliament_bill(
    bill_name: str, bills: list[tuple[str, str]]
) -> tuple[str, str] | None:
    wanted = " ".join(bill_name.casefold().split())
    for bill_url, label in bills:
        if label.casefold().startswith(wanted):
            return bill_url, label

    number = re.fullmatch(
        r"(?:bill\s+)?(?:no\.?\s*)?(\d+)\s+of\s+(\d{4})", wanted
    )
    if number:
        for bill_url, label in bills:
            listed = re.search(r"\(\s*(\d+)\s+o[f0]\s+(\d{4})\s*\)", label)
            if listed and listed.groups() == number.groups():
                return bill_url, label

    # A name from within the title; prefer the most recent Bill.
    contained = [
        (bill_url, label)
        for bill_url, label in bills
        if wanted and wanted in label.casefold()
    ]
    if contained:
        return max(
            contained,
            key=lambda item: max(map(int, re.findall(r"\b(?:19|20)\d{2}\b", item[1])), default=0),
        )
    return None


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_parliament_bill_links(page_url: str) -> list[tuple[str, str]]:
    return _fetch_parliament_bill_links(page_url)


def _parliament_bill_list_pages() -> list[str]:
    this_year = datetime.now().year
    return [PARLIAMENT_BILLS_URL] + [
        f"{PARLIAMENT_BILLS_URL}/bills-introduced-into-parliament-{year}"
        for year in range(this_year, 2009, -1)
    ]


def find_parliament_bill_page(bill_name: str) -> tuple[str, str]:
    # The Bills lists are plain pages; the site search is more likely to be
    # refused (HTTP 403) for requests from cloud hosts, so it is only a fallback.
    # Pages are read one at a time, newest first, to avoid a burst of requests.
    for page_url in _parliament_bill_list_pages():
        try:
            match = _match_parliament_bill(
                bill_name, _cached_parliament_bill_links(page_url)
            )
        except (OSError, ValueError):
            continue
        if match:
            return match

    if USE_SNAPSHOT:
        match = _match_parliament_bill(bill_name, bill_snapshot.bill_links())
        if match:
            return match

    search_url = (
        f"{PARLIAMENT_SEARCH_URL}?"
        f"{urlencode({'queries_all_query': bill_name})}"
    )
    match = None
    try:
        match = _match_parliament_bill(
            bill_name, _fetch_parliament_bill_links(search_url)
        )
    except HTTPError as error:
        raise ValueError(
            f"No Parliament Bill record was found for {bill_name!r} on the "
            f"current Bills list, and the Parliament site search refused the "
            f"request (HTTP {error.code})."
        ) from error
    if match:
        return match
    raise ValueError(f"No Parliament Bill record was found for {bill_name!r}.")


def get_parliament_bill_status(bill_page_url: str) -> BillStatus:
    try:
        return _live_get_parliament_bill_status(bill_page_url)
    except OSError:
        saved = USE_SNAPSHOT and bill_snapshot.bill_status(bill_page_url)
        if not saved:
            raise
        _use_snapshot_notice()
        return saved


def _live_get_parliament_bill_status(bill_page_url: str) -> BillStatus:
    parsed_bill_url = urlparse(bill_page_url)
    if (
        parsed_bill_url.scheme != "https"
        or parsed_bill_url.hostname != PARLIAMENT_HOST
        or not parsed_bill_url.path.startswith("/bills/")
    ):
        raise ValueError("The Bill record is not on the official Parliament website.")

    request = Request(bill_page_url, headers={**BROWSER_HEADERS})
    with urlopen(request, timeout=15) as response:
        final_url = urlparse(response.geturl())
        if final_url.scheme != "https" or final_url.hostname != PARLIAMENT_HOST:
            raise ValueError(
                "The Parliament website redirected to an unexpected address."
            )
        page = response.read().decode("utf-8")

    parser = _BillStatusTableParser()
    parser.feed(page)
    if not parser.status_rows:
        raise ValueError("The Parliament Bill record does not include a status table.")

    houses: dict[str, ChamberStatus] = {}
    for key, stage_column, date_column in (
        ("house_of_assembly", 0, 1),
        ("legislative_council", 2, 3),
    ):
        latest_stage = None
        latest_date = None
        passed_date = None
        negatived_date = None
        for row in parser.status_rows[1:]:
            if len(row) <= date_column:
                continue
            stage = row[stage_column].strip()
            date = row[date_column].strip()
            if not stage or not date:
                continue
            if stage.casefold().startswith("third reading"):
                passed_date = date
            elif stage.casefold().startswith("negatived"):
                negatived_date = date
            if date not in ("-", "—", "–"):
                latest_stage = stage
                latest_date = date
        houses[key] = {
            "passed_date": passed_date,
            "latest_stage": latest_stage,
            "latest_date": latest_date,
            "negatived_date": negatived_date,
        }

    royal_assent_date = None
    for row in parser.status_rows[1:]:
        if row and row[0].casefold().startswith("royal assent") and len(row) > 1:
            date = row[1].strip()
            if date and date not in ("-", "—", "–"):
                royal_assent_date = date
            break

    return {
        "house_of_assembly": houses["house_of_assembly"],
        "legislative_council": houses["legislative_council"],
        "royal_assent_date": royal_assent_date,
    }


def parliament_bill_act_title(bill_record_title: str) -> str:
    # Drop the record's number suffix, e.g. "(45 of 2026)", "(Bill 41 of 2025)"
    # or the occasional "(21 0f 2026)" typo.
    clean_bill_title = re.sub(
        r"\s*\(\s*(?:Bill\s+)?\d+\s+o[f0]\s+\d{4}\s*\)\s*$",
        "",
        bill_record_title,
        flags=re.IGNORECASE,
    ).strip()
    # "Bill" is followed only by an optional "(No. n)" and an optional year.
    act_title, replacements = re.subn(
        r"\bBill(?=(?:\s+\(No\.?\s*\d+\))?(?:\s+\d{4})?$)",
        "Act",
        clean_bill_title,
        count=1,
        flags=re.IGNORECASE,
    )
    if replacements == 0:
        raise ValueError("The Parliament record does not identify a matching Bill title.")
    return act_title


def find_act_pdf_url(act_title: str) -> str:
    """Find the Act as passed. The legislation site titles an Act with the year it
    was passed, so a Bill introduced in one year may become an Act the next."""
    candidates = [act_title]
    year = re.search(r"\b(\d{4})$", act_title)
    if year:
        candidates.append(f"{act_title[: year.start()]}{int(year.group(1)) + 1}")

    first_error: Exception | None = None
    for candidate in candidates:
        try:
            return _find_act_pdf_url_for_title(candidate)
        except (OSError, ValueError) as error:
            first_error = first_error or error
    raise first_error


def _find_act_pdf_url_for_title(act_title: str) -> str:
    try:
        return _live_find_act_pdf_url(act_title)
    except OSError:
        saved = USE_SNAPSHOT and bill_snapshot.act_pdf_url(act_title)
        if not saved:
            raise
        _use_snapshot_notice()
        return saved


def _live_find_act_pdf_url(act_title: str) -> str:
    expression = f'(PrintType="act.new") AND Title="{act_title}"'
    query = urlencode(
        {
            "ds": "EnAct-FragTocRelationIdxDatasource",
            "start": 1,
            "count": 10,
            "expression": expression,
        }
    )
    request_url = f"{LEGISLATION_SEARCH_URL}?{query}"
    request = Request(
        request_url,
        headers={
            **BROWSER_HEADERS,
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    with urlopen(request, timeout=15) as response:
        final_url = urlparse(response.geturl())
        if final_url.scheme != "https" or final_url.hostname != LEGISLATION_HOST:
            raise ValueError(
                "The legislation website redirected to an unexpected address."
            )
        result = json.loads(response.read().decode("utf-8"))

    if not isinstance(result, dict):
        raise ValueError("The legislation search returned an invalid result.")
    records = result.get("data", [])
    if isinstance(records, dict):
        records = [records]
    if not isinstance(records, list):
        raise ValueError("The legislation search returned an invalid result.")
    for record in records:
        if not isinstance(record, dict):
            continue
        title_field = record.get("title")
        id_field = record.get("id")
        print_type_field = record.get("print.type")
        if not all(
            isinstance(field, dict)
            for field in (title_field, id_field, print_type_field)
        ):
            continue
        title = title_field.get("__value__")
        act_id = id_field.get("__value__")
        print_type = print_type_field.get("__value__")
        if (
            isinstance(title, str)
            and title.casefold() == act_title.casefold()
            and isinstance(act_id, str)
            and re.fullmatch(r"act-\d{4}-\d{3}", act_id)
            and print_type == "act.new"
        ):
            return f"{LEGISLATION_URL}/view/pdf/asmade/{act_id}"
    raise ValueError(f"No Act as passed PDF was found for {act_title!r}.")


def find_parliament_bill_document_urls(
    bill_page_url: str,
) -> dict[str, list[str]]:
    try:
        return _live_find_parliament_bill_document_urls(bill_page_url)
    except OSError:
        saved = USE_SNAPSHOT and bill_snapshot.bill_documents(bill_page_url)
        if not saved:
            raise
        _use_snapshot_notice()
        return saved


def _live_find_parliament_bill_document_urls(
    bill_page_url: str,
) -> dict[str, list[str]]:
    parsed_bill_url = urlparse(bill_page_url)
    if (
        parsed_bill_url.scheme != "https"
        or parsed_bill_url.hostname != PARLIAMENT_HOST
        or not parsed_bill_url.path.startswith("/bills/")
    ):
        raise ValueError("The Bill record is not on the official Parliament website.")

    request = Request(bill_page_url, headers={**BROWSER_HEADERS})
    with urlopen(request, timeout=15) as response:
        final_url = urlparse(response.geturl())
        if final_url.scheme != "https" or final_url.hostname != PARLIAMENT_HOST:
            raise ValueError(
                "The Parliament website redirected to an unexpected address."
            )
        page = response.read().decode("utf-8")

    parser = _ParliamentLinkParser()
    parser.feed(page)
    documents: dict[str, list[str]] = {
        "Bill as introduced": [],
        "Second reading speech": [],
        "Fact sheet": [],
        "Clause notes": [],
    }
    bill_priorities: dict[str, int] = {}
    for href, label in parser.links:
        document_url = urljoin(bill_page_url, href)
        parsed_document_url = urlparse(document_url)
        label_lower = f"{label} {unquote(parsed_document_url.path)}".casefold()
        if (
            parsed_document_url.scheme != "https"
            or parsed_document_url.hostname != PARLIAMENT_HOST
        ):
            continue
        if any(
            marker in label_lower
            for marker in (
                "bill as tabled",
                "bill as introduced",
                "text of bill as introduced",
            )
        ):
            priority = 0 if "tabled" in label_lower else 1
            previous_priority = bill_priorities.get(document_url)
            if previous_priority is None or priority < previous_priority:
                documents["Bill as introduced"].append(document_url)
                bill_priorities[document_url] = priority
        elif "second reading" in label_lower or "2nd reading" in label_lower:
            documents["Second reading speech"].append(document_url)
        elif "fact sheet" in label_lower or "factsheet" in label_lower:
            documents["Fact sheet"].append(document_url)
        elif any(
            marker in label_lower
            for marker in (
                "clause note",
                "clause-by-clause",
                "clause by clause",
                "clause analysis",
                "explanatory notes",
            )
        ):
            documents["Clause notes"].append(document_url)

    documents = {
        category: list(dict.fromkeys(urls))
        for category, urls in documents.items()
    }
    if not documents["Bill as introduced"]:
        raise ValueError("No Bill as Tabled document was found on the Bill record.")
    documents["Bill as introduced"].sort(
        key=lambda url: bill_priorities[url]
    )
    return documents


def find_parliament_bill_pdf_url(bill_page_url: str) -> str:
    return find_parliament_bill_document_urls(bill_page_url)[
        "Bill as introduced"
    ][0]


def fetch_official_pdf(document_url: str, allowed_host: str) -> bytes:
    try:
        return _live_fetch_official_pdf(document_url, allowed_host)
    except OSError:
        saved = USE_SNAPSHOT and bill_snapshot.pdf_bytes(document_url)
        if not saved:
            raise
        _use_snapshot_notice()
        return saved


def _live_fetch_official_pdf(document_url: str, allowed_host: str) -> bytes:
    parsed_url = urlparse(document_url)
    if parsed_url.scheme != "https" or parsed_url.hostname != allowed_host:
        raise ValueError("The PDF is not hosted on the expected official website.")

    request = Request(document_url, headers={**BROWSER_HEADERS})
    with urlopen(request, timeout=15) as response:
        final_url = urlparse(response.geturl())
        if final_url.scheme != "https" or final_url.hostname != allowed_host:
            raise ValueError("The official website redirected to an unexpected address.")
        contents = response.read()
    if not contents.startswith(b"%PDF-"):
        raise ValueError("The official document could not be read as a PDF.")
    return contents


def extract_uploaded_text(name: str, contents: bytes) -> str:
    suffix = Path(name).suffix.lower()
    if suffix == ".pdf":
        try:
            reader = PdfReader(BytesIO(contents))
        except PdfReadError as error:
            raise ValueError(f"Could not read PDF {name!r}.") from error
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        if not text.strip():
            raise ValueError(
                f"No selectable text was found in {name!r}; scanned PDFs need OCR."
            )
        return text
    return contents.decode("utf-8", errors="replace")


def get_bill_information() -> dict[str, str]:
    information = st.session_state.get("bill_information", {})
    return information if isinstance(information, dict) else {}


def get_source_material() -> str:
    information = get_bill_information()
    sections = [
        ("Bill summary", information.get("summary", "")),
        ("Background", information.get("background", "")),
        ("Policy", information.get("policy", "")),
    ]
    for state_key in (
        "source_documents",
        "parliament_documents",
        "official_parliament_documents",
    ):
        documents = st.session_state.get(state_key, [])
        if isinstance(documents, list):
            for document in documents:
                if isinstance(document, dict):
                    category = document.get("category", "Source")
                    name = document.get("name", "Uploaded file")
                    text = document.get("text", "")
                    if text:
                        sections.append((f"{category}: {name}", text))

    combined = "\n\n".join(
        f"## {title}\n{text}" for title, text in sections if text and text.strip()
    )
    if len(combined) > MAX_SOURCE_CHARS:
        combined = combined[:MAX_SOURCE_CHARS]
    return combined


@st.cache_data(ttl=3600, show_spinner=False)
def find_hansard_debate_links(bill_name: str) -> list[tuple[str, str]]:
    """Return official Hansard search links for each chamber that debated the Bill."""
    phrase = re.sub(r"\s*\(\s*\d+\s+of\s+\d{4}\s*\)\s*$", "", bill_name).strip()
    if not phrase:
        return []
    links = []
    for chamber in HANSARD_CHAMBERS:
        query = urlencode(
            {
                "IW_DATABASE": "Hansard",
                "IW_SORT": "-date",
                "IW_FIELD_IN_AUTHOR": chamber,
                "IW_FIELD_TEXT": f'"{phrase}"',
            }
        )
        url = f"{HANSARD_SEARCH_URL}?{query}"
        try:
            request = Request(url, headers={**BROWSER_HEADERS})
            with urlopen(request, timeout=15) as response:
                if urlparse(response.geturl()).hostname != urlparse(HANSARD_SEARCH_URL).hostname:
                    continue
                page = response.read().decode("utf-8", errors="replace")
        except (OSError, ValueError):
            continue
        found = re.search(r"isys_stats_docs'>(\d+)", page)
        if found and int(found.group(1)) > 0:
            links.append((f"Hansard debates: {chamber}", url))
    return links


HANSARD_MAX_DOCUMENTS = 6
HANSARD_MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024
HANSARD_MAX_CHAMBER_CHARS = 60000


def _hansard_search_phrase(bill_name: str) -> str:
    return re.sub(r"\s*\(\s*\d+\s+of\s+\d{4}\s*\)\s*$", "", bill_name).strip()


def _extract_bill_sections(docx_bytes: bytes, phrase: str) -> list[str]:
    """Return the Hansard text of each item whose heading names the Bill."""
    with zipfile.ZipFile(BytesIO(docx_bytes)) as archive:
        xml = archive.read("word/document.xml").decode("utf-8", errors="replace")
    sections: list[list[str]] = []
    inside = False
    wanted = phrase.casefold()
    for paragraph in re.findall(r"<w:p[ >].*?</w:p>", xml, re.S):
        text = re.sub(r"<[^>]+>", "", paragraph)
        text = html_unescape(text).strip()
        if not text:
            continue
        if 'w:val="Heading1"' in paragraph:
            inside = wanted in text.casefold()
            if inside:
                sections.append([text])
            continue
        if inside:
            sections[-1].append(text)
    return ["\n".join(lines) for lines in sections]


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_hansard_bill_debate(bill_name: str, chamber: str) -> list[tuple[str, str]]:
    """Fetch (sitting day, text) for Hansard items about the Bill in one chamber."""
    phrase = _hansard_search_phrase(bill_name)
    if not phrase or chamber not in HANSARD_CHAMBERS:
        return []
    search_host = urlparse(HANSARD_SEARCH_URL).hostname
    query = urlencode(
        {
            "IW_DATABASE": "Hansard",
            "IW_SORT": "date",
            "IW_FIELD_IN_AUTHOR": chamber,
            "IW_FIELD_TEXT": f'"{phrase}"',
        }
    )
    request = Request(
        f"{HANSARD_SEARCH_URL}?{query}", headers={**BROWSER_HEADERS}
    )
    with urlopen(request, timeout=20) as response:
        if urlparse(response.geturl()).hostname != search_host:
            raise ValueError("Unexpected redirect from the Hansard search.")
        page = response.read().decode("utf-8", errors="replace")

    document_paths = []
    for path in re.findall(
        r'href="(/search/isysquery/[0-9a-f-]+/\d+/doc/[^"/]+\.docx)"', page
    ):
        if path not in document_paths:
            document_paths.append(path)

    results = []
    for path in document_paths[:HANSARD_MAX_DOCUMENTS]:
        document_request = Request(
            f"https://{search_host}{path}", headers={**BROWSER_HEADERS}
        )
        with urlopen(document_request, timeout=60) as response:
            if urlparse(response.geturl()).hostname != search_host:
                raise ValueError("Unexpected redirect from the Hansard search.")
            data = response.read(HANSARD_MAX_DOWNLOAD_BYTES + 1)
        if len(data) > HANSARD_MAX_DOWNLOAD_BYTES:
            continue
        try:
            sections = _extract_bill_sections(data, phrase)
        except (zipfile.BadZipFile, KeyError):
            continue
        if sections:
            sitting = unquote(path.rsplit("/", 1)[-1]).removesuffix(".docx")
            text = "\n\n".join(sections)
            if all(text != existing for _, existing in results):
                results.append((sitting, text))
    return _fit_hansard_budget(results)


def _fit_hansard_budget(results: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Share the character budget between sitting days, trimming the middle."""
    total = sum(len(text) for _, text in results)
    if total <= HANSARD_MAX_CHAMBER_CHARS:
        return results
    fitted = []
    for sitting, text in results:
        allowance = max(500, HANSARD_MAX_CHAMBER_CHARS * len(text) // total)
        if len(text) > allowance:
            head = allowance * 6 // 10
            tail = allowance - head
            text = f"{text[:head]}\n[... debate text trimmed ...]\n{text[-tail:]}"
        fitted.append((sitting, text))
    return fitted


PETITION_SITES = {
    "House of Assembly": "https://haepetitions.parliament.tas.gov.au/haepet",
    "Legislative Council": "https://lcepetitions.parliament.tas.gov.au/lcepet",
}
PETITIONS_INFO_URL = f"{PARLIAMENT_URL.rstrip('/')}/petitions"
_PETITION_STOPWORDS = frozenset(
    "a an and as at bill bills by for from in into of on or the to with act acts "
    "amendment amendments miscellaneous related legislation consequential "
    "provisions repeal tasmania tasmanian state no".split()
)
_PETITION_ITEM = re.compile(
    r'PetitionDetails/(\d+)\?[^"]*">\s*(.*?)\s*</a>', re.DOTALL
)


def bill_subject_keywords(bill_name: str) -> tuple[str, list[str]]:
    """Return the Bill's subject phrase and its distinctive keywords."""
    phrase = re.sub(r"\s*\(\s*\d+\s+of\s+\d{4}\s*\)\s*$", "", bill_name)
    phrase = re.sub(r"\bBill\b.*$", "", phrase, flags=re.IGNORECASE)
    phrase = re.sub(r"\bAmendment\b", "", phrase, flags=re.IGNORECASE)
    phrase = " ".join(re.sub(r"[^\w\s]", " ", phrase).split()).casefold()
    words = [
        w for w in phrase.split() if w not in _PETITION_STOPWORDS and len(w) > 3
    ]
    return phrase, list(dict.fromkeys(words))


def _fetch_petition_page(url: str, allowed_host: str) -> str:
    request = Request(url, headers={**BROWSER_HEADERS})
    with urlopen(request, timeout=8) as response:
        if urlparse(response.geturl()).hostname != allowed_host:
            raise ValueError("Unexpected redirect from the e-petitions site.")
        return response.read().decode("utf-8", errors="replace")


def _petition_text(page: str) -> str:
    page = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", page, flags=re.DOTALL)
    return " ".join(html_unescape(re.sub(r"<[^>]+>", " ", page)).split())


PETITION_LOAD_SECONDS = 45


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def _load_petitions_cached() -> list[dict[str, str | int]]:
    entries = []
    for chamber, base in PETITION_SITES.items():
        host = urlparse(base).hostname
        for listing in (base, f"{base}/Home/ClosedPetitions"):
            try:
                page = _fetch_petition_page(listing, host)
            except (OSError, ValueError):
                continue
            for petition_id, title in _PETITION_ITEM.findall(page):
                entries.append(
                    {
                        "chamber": chamber,
                        "title": " ".join(html_unescape(title).split()),
                        "url": f"{base}/Home/PetitionDetails/{petition_id}",
                        "host": host,
                    }
                )
    if not entries:
        # Raising keeps a failed load out of the cache so it is retried.
        raise OSError("The e-petition sites could not be reached.")

    deadline = time.monotonic() + PETITION_LOAD_SECONDS

    def add_text(entry: dict[str, str]) -> dict[str, str | int]:
        body = ""
        if time.monotonic() < deadline:
            try:
                body = _petition_text(
                    _fetch_petition_page(entry["url"], entry["host"])
                )
            except (OSError, ValueError):
                pass
        counted = re.search(r"([\d,]+)\s+Signatures?\b", body)
        signatures = int(counted.group(1).replace(",", "")) if counted else 0
        return {**entry, "text": body, "signatures": signatures}

    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(add_text, entries))


def load_petitions() -> list[dict[str, str | int]]:
    """Load every open and closed e-petition from both chambers, with its text."""
    try:
        return _load_petitions_cached()
    except OSError:
        return []


def match_parliament_petitions(
    bill_name: str, limit: int = 6
) -> list[dict[str, str | int]]:
    """Return e-petitions on the Bill or its subject matter, best match first."""
    phrase, keywords = bill_subject_keywords(bill_name)
    petitions = load_petitions()
    if not keywords or not petitions:
        return []
    corpus = [(p["title"].casefold(), p["text"].casefold()) for p in petitions]
    # Words found in many petitions (for example "health") are too generic.
    rare = [
        word
        for word in keywords
        if sum(1 for title, body in corpus if word in title or word in body)
        <= max(3, len(corpus) // 12)
    ]
    scored = []
    for petition, (title, body) in zip(petitions, corpus):
        in_body = [word for word in rare if word in body or word in title]
        in_title = [word for word in rare if word in title]
        exact = bool(phrase) and phrase in body
        enough = (
            exact
            or (len(rare) == 1 and bool(in_title))
            or (len(in_body) >= 2 and bool(in_title))
            or (len(rare) >= 2 and len(in_body) == len(rare))
        )
        if enough:
            scored.append((10 * exact + 3 * len(in_title) + len(in_body), petition))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [petition for _, petition in scored[:limit]]


def find_parliament_petitions(
    bill_name: str, limit: int = 6
) -> list[tuple[str, str]]:
    """Return (label, url) e-petitions on the Bill or its subject matter."""
    return [
        (
            f"Petition ({p['chamber']}): {p['title']}"
            + (f" - {p['signatures']:,} signatures" if p["signatures"] else ""),
            str(p["url"]),
        )
        for p in match_parliament_petitions(bill_name, limit)
    ]


def sync_session_bill(widget_key: str, marker_key: str) -> bool:
    """Copy the Bill entered on page 1 into a page's own Bill box.

    Returns True when a new Bill arrived since this page last synced, so the
    page can run its search automatically.
    """
    bill = st.session_state.get("bill_title", "").strip()
    if not bill:
        return False
    # Streamlit discards a page's widget value when the user leaves the page, so
    # refill the box on return even if the search has already run.
    if widget_key not in st.session_state:
        st.session_state[widget_key] = bill
    if st.session_state.get(marker_key) == bill:
        return False
    st.session_state[widget_key] = bill
    st.session_state[marker_key] = bill
    return True


def publish_session_bill(widget_key: str, marker_key: str) -> None:
    """Share a Bill typed on this page with every other page for the session."""
    bill = st.session_state.get(widget_key, "").strip()
    if bill and bill != st.session_state.get("bill_title", "").strip():
        st.session_state["bill_title"] = bill
        st.session_state[marker_key] = bill
