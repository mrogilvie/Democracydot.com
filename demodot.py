import os
import re
import zipfile
from io import BytesIO
from pathlib import Path
from html import unescape as html_unescape
from html.parser import HTMLParser
from urllib.parse import unquote, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

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


MODEL = "gpt-4o-mini"
MAX_SOURCE_CHARS = 60_000
PARLIAMENT_URL = "https://www.parliament.tas.gov.au/"
PARLIAMENT_HOST = urlparse(PARLIAMENT_URL).hostname
PARLIAMENT_SEARCH_URL = f"{PARLIAMENT_URL.rstrip('/')}/search-results"
HANSARD_SEARCH_URL = "https://search.parliament.tas.gov.au/search/search/"
HANSARD_CHAMBERS = ("House of Assembly", "Legislative Council")


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


def get_openai_client() -> OpenAI | None:
    load_dotenv(Path(__file__).resolve().with_name(".env"))
    try:
        api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    except StreamlitSecretNotFoundError:
        api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        st.error(
            "OpenAI API key not found. Add OPENAI_API_KEY to the project .env "
            "file or Streamlit secrets."
        )
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


def find_parliament_bill_page(bill_name: str) -> tuple[str, str]:
    search_url = (
        f"{PARLIAMENT_SEARCH_URL}?"
        f"{urlencode({'queries_all_query': bill_name})}"
    )
    request = Request(search_url, headers={"User-Agent": "Democracydot/1.0"})
    with urlopen(request, timeout=15) as response:
        final_url = urlparse(response.geturl())
        if final_url.scheme != "https" or final_url.hostname != PARLIAMENT_HOST:
            raise ValueError(
                "The Parliament website redirected to an unexpected address."
            )
        page = response.read().decode("utf-8")

    parser = _ParliamentLinkParser()
    parser.feed(page)
    for href, label in parser.links:
        bill_url = urljoin(search_url, href)
        parsed_bill_url = urlparse(bill_url)
        if (
            label.casefold().startswith(bill_name.casefold())
            and parsed_bill_url.scheme == "https"
            and parsed_bill_url.hostname == PARLIAMENT_HOST
            and parsed_bill_url.path.startswith("/bills/")
        ):
            return bill_url, label
    raise ValueError(f"No Parliament Bill record was found for {bill_name!r}.")


def find_parliament_bill_document_urls(
    bill_page_url: str,
) -> dict[str, list[str]]:
    parsed_bill_url = urlparse(bill_page_url)
    if (
        parsed_bill_url.scheme != "https"
        or parsed_bill_url.hostname != PARLIAMENT_HOST
        or not parsed_bill_url.path.startswith("/bills/")
    ):
        raise ValueError("The Bill record is not on the official Parliament website.")

    request = Request(bill_page_url, headers={"User-Agent": "Democracydot/1.0"})
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
    parsed_url = urlparse(document_url)
    if parsed_url.scheme != "https" or parsed_url.hostname != allowed_host:
        raise ValueError("The PDF is not hosted on the expected official website.")

    request = Request(document_url, headers={"User-Agent": "Democracydot/1.0"})
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
            request = Request(url, headers={"User-Agent": "Democracydot/1.0"})
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
        f"{HANSARD_SEARCH_URL}?{query}", headers={"User-Agent": "Democracydot/1.0"}
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
            f"https://{search_host}{path}", headers={"User-Agent": "Democracydot/1.0"}
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


def sync_session_bill(widget_key: str, marker_key: str) -> bool:
    """Copy the Bill entered on page 1 into a page's own Bill box.

    Returns True when a new Bill arrived since this page last synced, so the
    page can run its search automatically.
    """
    bill = st.session_state.get("bill_title", "").strip()
    if not bill or st.session_state.get(marker_key) == bill:
        return False
    st.session_state[widget_key] = bill
    st.session_state[marker_key] = bill
    return True
