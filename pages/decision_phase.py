import sqlite3
from urllib.error import URLError
from urllib.parse import unquote, urlparse

import streamlit as st
from openai import OpenAIError

from comment_store import save_comment
from demodot import (
    BillStatus,
    ChamberStatus,
    MAX_SOURCE_CHARS,
    LEGISLATION_HOST,
    MODEL,
    PARLIAMENT_URL,
    extract_uploaded_text,
    fetch_official_pdf,
    find_act_pdf_url,
    find_parliament_bill_page,
    find_parliament_bill_document_urls,
    get_parliament_bill_status,
    get_openai_client,
    get_source_material,
    parliament_bill_act_title,
    report_openai_error,
    publish_session_bill,
    sync_session_bill,
)

DOCUMENT_ORDER = (
    "Bill as introduced",
    "Second reading speech",
    "Fact sheet",
    "Clause notes",
)


def format_chamber_status(status: ChamberStatus) -> str:
    if status["negatived_date"]:
        return f"Negatived on {status['negatived_date']}."
    if status["passed_date"]:
        return f"Passed on {status['passed_date']}."
    latest_stage = status["latest_stage"]
    latest_date = status["latest_date"]
    if latest_stage and latest_date:
        return (
            f"Not recorded as passed; latest recorded stage: "
            f"{latest_stage} ({latest_date})."
        )
    return "No passage stage is recorded."


def summarize_bill_status(status: BillStatus) -> str:
    house_passed = bool(status["house_of_assembly"]["passed_date"])
    council_passed = bool(status["legislative_council"]["passed_date"])
    if house_passed and council_passed:
        summary = "The Bill is recorded as having passed both houses."
    elif house_passed:
        summary = (
            "The Bill is recorded as having passed the House of Assembly; "
            "passage in the Legislative Council is not recorded."
        )
    elif council_passed:
        summary = (
            "The Bill is recorded as having passed the Legislative Council; "
            "passage in the House of Assembly is not recorded."
        )
    else:
        summary = "The Bill is not recorded as having passed both houses."

    royal_assent_date = status["royal_assent_date"]
    if royal_assent_date:
        return f"{summary} Royal Assent was received on {royal_assent_date}."
    return f"{summary} Royal Assent is not recorded."


st.title("Democratic Engagement")
st.write("Ask questions with Billbow Q&A and send constituent feedback.")
st.caption(
    "Questions and Bill source text are sent to OpenAI when you request an answer. "
    "Add only material you are authorized to share."
)

def request_interaction_search() -> None:
    st.session_state["interaction_search_requested"] = True


auto_search = sync_session_bill("parliament_bill_name", "page2_synced_bill")
searched_bill_name = st.text_input(
    "Enter Bill name",
    key="parliament_bill_name",
    on_change=request_interaction_search,
    help="Press Enter to search Parliament records. Filled in from the Bill you "
    "entered on Bill Information.",
)
publish_session_bill("parliament_bill_name", "page2_synced_bill")
if st.session_state.pop("interaction_search_requested", False) or auto_search:
    if not searched_bill_name.strip():
        st.warning("Enter a Bill name to search Parliament records.")
    else:
        st.session_state.pop("interaction_bill_status", None)
        st.session_state.pop("interaction_final_act_pdf_url", None)
        st.session_state.pop("interaction_final_act_pdf", None)
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
            st.session_state.pop("interaction_bill_status", None)
            st.session_state.pop("interaction_final_act_pdf_url", None)
            st.session_state.pop("interaction_final_act_pdf", None)
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
            try:
                bill_status = get_parliament_bill_status(bill_page_url)
            except (OSError, URLError, UnicodeDecodeError, ValueError) as error:
                st.warning(f"Could not retrieve the Bill's official passage status: {error}")
                st.session_state.pop("interaction_bill_status", None)
            else:
                st.session_state["interaction_bill_status"] = bill_status
                if bill_status["royal_assent_date"]:
                    try:
                        act_title = parliament_bill_act_title(bill_record_title)
                        act_url = find_act_pdf_url(act_title)
                        act_pdf = fetch_official_pdf(act_url, LEGISLATION_HOST)
                    except (OSError, URLError, UnicodeDecodeError, ValueError) as error:
                        st.warning(f"Could not retrieve the Act as passed: {error}")
                        st.session_state.pop("interaction_final_act_pdf_url", None)
                        st.session_state.pop("interaction_final_act_pdf", None)
                    else:
                        st.session_state["interaction_final_act_pdf_url"] = act_url
                        st.session_state["interaction_final_act_pdf"] = act_pdf

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
        ordered_documents = sorted(
            enumerate(official_documents),
            key=lambda item: (
                DOCUMENT_ORDER.index(item[1].get("category"))
                if isinstance(item[1], dict)
                and item[1].get("category") in DOCUMENT_ORDER
                else len(DOCUMENT_ORDER),
                item[0],
            ),
        )
        for index, document in ordered_documents:
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

    with st.container(border=True):
        st.subheader("5. Final Act and passage status")
        st.link_button("Open official Bill status record", bill_page_url)
        st.caption(
            "Status is taken from the official Parliament Bill record. An asterisk "
            "on a second-reading stage marks the speech date."
        )
        bill_status = st.session_state.get("interaction_bill_status")
        if isinstance(bill_status, dict):
            st.write(f"**Summary:** {summarize_bill_status(bill_status)}")
            st.write(
                "**House of Assembly:** "
                + format_chamber_status(bill_status["house_of_assembly"])
            )
            st.write(
                "**Legislative Council:** "
                + format_chamber_status(bill_status["legislative_council"])
            )
            royal_assent_date = bill_status["royal_assent_date"]
            if royal_assent_date:
                st.write(f"**Royal Assent:** Received on {royal_assent_date}.")
            else:
                st.write(
                    "**Royal Assent:** No Royal Assent date is recorded on the "
                    "official Bill record."
                )
        else:
            st.info("The official passage status could not be retrieved.")

        final_act_pdf = st.session_state.get("interaction_final_act_pdf")
        final_act_url = st.session_state.get("interaction_final_act_pdf_url")
        if isinstance(final_act_pdf, bytes) and isinstance(final_act_url, str):
            st.link_button("Open Final Act (as passed) PDF", final_act_url)
            st.pdf(
                final_act_pdf,
                height=640,
                key="interaction_final_act_pdf_viewer",
            )
        elif (
            isinstance(bill_status, dict)
            and not bill_status["royal_assent_date"]
        ):
            st.info("A Final Act is not available because Royal Assent is not recorded.")
        elif not isinstance(bill_status, dict):
            st.info("Final Act availability could not be checked.")
        else:
            st.info("No matching Final Act PDF is available.")

links = st.session_state.get("essential_links", [])
if isinstance(links, list):
    for link in links:
        if isinstance(link, dict) and link.get("label") and link.get("url"):
            st.link_button(link["label"], link["url"])

st.session_state["parliament_documents"] = []

st.subheader("Billbow Q&A")
st.caption(
    "Billbow allows you to ask specific questions about the Bill. Billbow will load "
    "the relevant parliamentary documents and use them to generate AI supported answers."
)
def request_question() -> None:
    st.session_state["question_requested"] = True


question = st.text_input(
    "Ask a question about the Bill",
    key="bill_question_input",
    on_change=request_question,
    help="Press Enter to ask.",
)

if st.session_state.pop("question_requested", False):
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
                st.session_state["billbow_answer"] = (
                    question.strip(),
                    response.output_text,
                )
            except OpenAIError as error:
                report_openai_error(error)

billbow_answer = st.session_state.get("billbow_answer")
if billbow_answer and billbow_answer[0] == question.strip():
    st.markdown(billbow_answer[1])

st.subheader("Proposed amendment")
st.caption(
    "Describe the change you would like to propose. Your request and relevant "
    "Bill or Act text will be sent to OpenAI to draft suggested amendment wording. "
    "Review the draft against official sources; it is not legal advice."
)
amendment_request = st.text_area(
    "What change would you like to propose to the Bill or Act?",
    key="amendment_request",
)
if st.button("Generate Amendment", key="generate_amendment"):
    st.session_state.pop("proposed_amendment", None)
    amendment_source = get_source_material()
    act_text = st.session_state.get("final_bill_text", "")
    if (
        isinstance(act_text, str)
        and act_text.strip()
        and not act_text.startswith("%PDF-")
    ):
        act_section = f"\n\n## Act as passed\n{act_text.strip()}"
        amendment_source = (
            amendment_source[: max(0, MAX_SOURCE_CHARS - len(act_section))]
            + act_section[:MAX_SOURCE_CHARS]
        )
    if not amendment_request.strip():
        st.warning("Describe the change you would like to propose.")
    elif not amendment_source.strip():
        st.warning(
            "Search for a Bill above or add Bill information and source documents "
            "on the Bill Information page before generating an amendment."
        )
    else:
        client = get_openai_client()
        if client:
            try:
                with st.spinner("Drafting a proposed amendment..."):
                    response = client.responses.create(
                        model=MODEL,
                        instructions=(
                            "Draft a proposed legislative amendment in response to "
                            "the user's requested change, using only the supplied "
                            "legislative material. Provide a concise title, identify "
                            "the provision to amend where the material supports it, "
                            "and present the amendment wording clearly. Do not "
                            "invent section numbers, existing wording, legal effects, "
                            "or facts. If the material is insufficient to draft "
                            "precise wording, explain what is missing and provide "
                            "only a clearly labelled indicative draft. State that "
                            "the draft is a suggestion for review, not legal advice."
                        ),
                        input=(
                            f"Legislative material:\n{amendment_source}\n\n"
                            f"Requested change:\n{amendment_request.strip()}"
                        ),
                        max_output_tokens=1800,
                    )
                st.session_state["proposed_amendment"] = (
                    amendment_request.strip(),
                    response.output_text,
                )
            except OpenAIError as error:
                report_openai_error(error)

proposed_amendment = st.session_state.get("proposed_amendment")
if (
    proposed_amendment
    and proposed_amendment[0] == amendment_request.strip()
):
    st.markdown(proposed_amendment[1])

st.subheader("Constituent feedback")
st.caption(
    "Comments are anonymous and saved so the app owner can review them. They are "
    "not sent to Parliament. You can choose to include your generated proposed "
    "amendment. Avoid including personal or sensitive information."
)
comment_bill = (
    st.session_state.get("bill_title", "").strip()
    or st.session_state.get("parliament_bill_name", "").strip()
)
if comment_bill:
    st.caption(f"Your comment will be saved against: **{comment_bill}**")

generated_amendment = st.session_state.get("proposed_amendment")
current_amendment = ""
if (
    isinstance(generated_amendment, tuple)
    and len(generated_amendment) == 2
    and generated_amendment[0] == st.session_state.get("amendment_request", "").strip()
    and isinstance(generated_amendment[1], str)
):
    current_amendment = generated_amendment[1].strip()
if current_amendment:
    st.checkbox(
        "Include my generated proposed amendment in this feedback",
        key="include_amendment_feedback",
    )


def request_comment() -> None:
    st.session_state["pending_comment"] = st.session_state.get(
        "constituent_comment_input", ""
    )
    st.session_state["pending_amendment"] = (
        current_amendment
        if st.session_state.get("include_amendment_feedback", False)
        else ""
    )
    st.session_state["constituent_comment_input"] = ""


st.text_input(
    "What would you like decision-makers to understand about this Bill?",
    key="constituent_comment_input",
    on_change=request_comment,
    help="Press Enter to send your comment.",
)
comment = st.session_state.pop("pending_comment", "")
pending_amendment = st.session_state.pop("pending_amendment", "")

if comment:
    if not comment_bill:
        st.warning(
            "Enter a Bill name above or on the Bill Information page, then send "
            "your comment again."
        )
    elif not comment.strip():
        st.warning("Enter a comment before sending.")
    else:
        submitted_comment = comment.strip()
        if pending_amendment:
            submitted_comment += (
                "\n\nProposed amendment:\n"
                f"{pending_amendment}"
            )
        try:
            save_comment(submitted_comment, comment_bill)
        except (OSError, sqlite3.Error) as error:
            st.error(f"Could not save your comment: {error}")
        else:
            st.success("Your comment was submitted for the app owner's review.")
