import os
from io import BytesIO
from pathlib import Path
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
