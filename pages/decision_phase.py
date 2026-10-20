import sqlite3
from urllib.error import URLError
from urllib.parse import unquote, urlparse

import streamlit as st
from openai import OpenAIError

from comment_store import save_comment
from demodot import (
    MODEL,
    PARLIAMENT_URL,
    extract_uploaded_text,
    fetch_official_pdf,
    find_parliament_bill_page,
    find_parliament_bill_document_urls,
    get_openai_client,
    get_source_material,
    report_openai_error,
)


st.title("Democratic interaction")
st.write("Ask questions with Billbow Q&A and send constituent feedback.")
st.caption(
    "Questions and Bill source text are sent to OpenAI when you request an answer. "
    "Add only material you are authorized to share."
)

searched_bill_name = st.text_input(
    "Enter Bill name",
    key="parliament_bill_name",
)
if st.button("Search Parliament Bills", key="search_interaction_bill"):
    if not searched_bill_name.strip():
        st.warning("Enter a Bill name to search Parliament records.")
    else:
        try:
            bill_page_url, bill_record_title = find_parliament_bill_page(
                searched_bill_name.strip()
            )
            bill_document_urls = find_parliament_bill_document_urls(bill_page_url)
            bill_pdf_url = bill_document_urls["Bill as introduced"][0]
            bill_pdf_bytes = fetch_official_pdf(
                bill_pdf_url, urlparse(PARLIAMENT_URL).hostname
            )
        except (OSError, URLError, ValueError) as error:
            st.error(f"Could not retrieve that Bill from Parliament: {error}")
            st.session_state.pop("interaction_bill_page_url", None)
            st.session_state.pop("interaction_bill_record_title", None)
            st.session_state.pop("interaction_bill_pdf_url", None)
            st.session_state.pop("interaction_bill_pdf_bytes", None)
            st.session_state.pop("official_parliament_documents", None)
        else:
            st.session_state["interaction_bill_page_url"] = bill_page_url
            st.session_state["interaction_bill_record_title"] = bill_record_title
            st.session_state["interaction_bill_pdf_url"] = bill_pdf_url
            st.session_state["interaction_bill_pdf_bytes"] = bill_pdf_bytes
            official_documents = []
            for category, document_urls in bill_document_urls.items():
                if not document_urls and category != "Bill as introduced":
                    st.info(
                        f"No {category.lower()} PDF is linked from this Bill record."
                    )
                    continue
                for index, document_url in enumerate(document_urls):
                    try:
                        pdf_bytes = (
                            bill_pdf_bytes
                            if category == "Bill as introduced" and index == 0
                            else fetch_official_pdf(
                                document_url,
                                urlparse(PARLIAMENT_URL).hostname,
                            )
                        )
                    except (OSError, URLError, ValueError) as error:
                        st.warning(
                            f"Could not retrieve the {category} PDF "
                            f"({document_url.rsplit('/', 1)[-1]}): {error}"
                        )
                        continue
                    document_name = unquote(document_url.rsplit("/", 1)[-1])
                    try:
                        text = extract_uploaded_text(document_name, pdf_bytes)
                    except ValueError as error:
                        st.warning(
                            f"The {category} PDF is available, but its text "
                            f"could not be extracted: {error}"
                        )
                        text = ""
                    official_documents.append(
                        {
                            "category": category,
                            "name": document_name,
                            "url": document_url,
                            "pdf": pdf_bytes,
                            "text": text,
                        }
                    )
            st.session_state["official_parliament_documents"] = official_documents

bill_page_url = st.session_state.get("interaction_bill_page_url")
bill_record_title = st.session_state.get("interaction_bill_record_title")
bill_pdf_url = st.session_state.get("interaction_bill_pdf_url")
bill_pdf_bytes = st.session_state.get("interaction_bill_pdf_bytes")
if (
    isinstance(bill_page_url, str)
    and isinstance(bill_record_title, str)
    and isinstance(bill_pdf_url, str)
    and isinstance(bill_pdf_bytes, bytes)
):
    with st.container(border=True):
        st.subheader(f"{bill_record_title} — Bill as introduced")
        st.pdf(bill_pdf_bytes, height=640, key="interaction_bill_pdf_viewer")
        st.link_button("Open Bill as Tabled PDF", bill_pdf_url)
    official_documents = st.session_state.get("official_parliament_documents", [])
    if isinstance(official_documents, list):
        for index, document in enumerate(official_documents):
            if (
                not isinstance(document, dict)
                or document.get("category") == "Bill as introduced"
            ):
                continue
            category = document.get("category", "Bill document")
            pdf_bytes = document.get("pdf")
            document_url = document.get("url")
            if not isinstance(pdf_bytes, bytes):
                continue
            with st.container(border=True):
                st.subheader(f"{bill_record_title} — {category}")
                st.pdf(
                    pdf_bytes,
                    height=520,
                    key=f"interaction_official_document_{index}",
                )
                if isinstance(document_url, str):
                    st.link_button(f"Open {category} PDF", document_url)

links = st.session_state.get("essential_links", [])
if isinstance(links, list):
    for link in links:
        if isinstance(link, dict) and link.get("label") and link.get("url"):
            st.link_button(link["label"], link["url"])

st.session_state["parliament_documents"] = []

st.subheader("Billbow Q&A")
st.caption(
    "Billbow uses AI to answer questions about Bills before the Tasmanian "
    "Parliament, grounded in retrieved Parliament documents and material added on the "
    "Bill information page. Source materials can include the Bill as introduced, "
    "the second reading speech, the fact sheet, and clause notes."
)
with st.form("bill_question_form"):
    question = st.text_area("Ask a question about the Bill", height=100)
    ask_question = st.form_submit_button("Ask about this Bill")

if ask_question:
    source = get_source_material()
    if not question.strip():
        st.warning("Enter a question first.")
    elif not source:
        st.warning(
            "Search for a Bill above or add Bill information and source documents "
            "on the Bill information page first."
        )
    else:
        client = get_openai_client()
        if client:
            try:
                with st.spinner("Preparing an answer..."):
                    response = client.responses.create(
                        model=MODEL,
                        instructions=(
                            "Answer the user's question using only the supplied "
                            "legislative material. If the material does not answer "
                            "the question, say so clearly. Quote or identify relevant "
                            "parts where possible. Keep a neutral tone and do not "
                            "give legal advice."
                        ),
                        input=f"Legislative material:\n{source}\n\nQuestion:\n{question.strip()}",
                        max_output_tokens=900,
                    )
                st.markdown(response.output_text)
            except OpenAIError as error:
                report_openai_error(error)

st.subheader("Constituent feedback")
st.caption(
    "Comments are anonymous and saved so the app owner can review them. They are "
    "not sent to Parliament. Avoid including personal or sensitive information."
)
with st.form("billbow_form", clear_on_submit=True):
    bill_title = st.text_input(
        "Bill name or number",
        value=st.session_state.get("bill_title", ""),
        help="Comments are grouped by this Bill in the owner review page.",
    )
    comment = st.text_area(
        "What would you like decision-makers to understand about this Bill?",
        height=130,
    )
    submit_comment = st.form_submit_button("Submit comment")

if submit_comment:
    if not bill_title.strip():
        st.warning("Enter the name or number of the Bill this comment is about.")
    elif not comment.strip():
        st.warning("Enter a comment before submitting.")
    else:
        try:
            save_comment(comment, bill_title)
        except (OSError, sqlite3.Error) as error:
            st.error(f"Could not save your comment: {error}")
        else:
            st.success("Your comment was submitted for the app owner's review.")
