from urllib.parse import urlparse

import streamlit as st
from openai import OpenAIError

from demodot import (
    MODEL,
    PARLIAMENT_URL,
    extract_uploaded_text,
    get_openai_client,
    get_source_material,
    report_openai_error,
)


st.title("Bill Information")
st.write(
    "Build a clear information page for the Bill: its summary, background, "
    "policy context, and essential reading."
)
st.caption(
    "Text is sent to OpenAI only when you request an AI summary. Add only material "
    "you are authorized to share."
)

st.link_button("Tasmanian Parliament website", PARLIAMENT_URL)
st.caption(
    "Add the Bill-specific Parliament and Hansard links under Essential reading."
)

with st.form("bill_information_form"):
    bill_title = st.text_input(
        "Bill name or number",
        value=st.session_state.get("bill_title", ""),
    )
    summary = st.text_area(
        "Bill summary",
        value=st.session_state.get("bill_summary", ""),
        height=130,
        help="Enter an existing summary, or draft one from your source material below.",
    )
    background = st.text_area(
        "Background information",
        value=st.session_state.get("bill_background", ""),
        height=160,
    )
    policy = st.text_area(
        "Policy context",
        value=st.session_state.get("bill_policy", ""),
        height=160,
    )
    saved = st.form_submit_button("Save Bill information")

if saved:
    st.session_state["bill_title"] = bill_title.strip()
    st.session_state["bill_summary"] = summary.strip()
    st.session_state["bill_background"] = background.strip()
    st.session_state["bill_policy"] = policy.strip()
    st.success("Bill information saved for this app session.")

st.subheader("Source documents")
st.caption("Upload selectable-text PDFs, plain text, or Markdown documents.")
policy_files = st.file_uploader(
    "Policy documents",
    type=["pdf", "txt", "md"],
    accept_multiple_files=True,
    max_upload_size=10,
    key="policy_documents",
)
information_files = st.file_uploader(
    "Background and information documents",
    type=["pdf", "txt", "md"],
    accept_multiple_files=True,
    max_upload_size=10,
    key="information_documents",
)

documents = []
for category, files in (
    ("Policy", policy_files),
    ("Information", information_files),
):
    for uploaded_file in files:
        try:
            text = extract_uploaded_text(uploaded_file.name, uploaded_file.getvalue())
        except ValueError as error:
            st.error(str(error))
            continue
        documents.append(
            {"category": category, "name": uploaded_file.name, "text": text}
        )
st.session_state["source_documents"] = documents

if documents:
    st.write(f"{len(documents)} source document(s) ready for the other stages.")
else:
    st.info("No source documents uploaded yet.")

st.subheader("Essential reading")
with st.form("essential_link_form", clear_on_submit=True):
    link_label = st.text_input("Link title", placeholder="Bill page or Hansard")
    link_url = st.text_input(
        "Web address",
        placeholder="https://www.parliament.tas.gov.au/...",
    )
    add_link = st.form_submit_button("Add link")

if add_link:
    parsed_url = urlparse(link_url.strip())
    if not link_label.strip() or parsed_url.scheme != "https" or not parsed_url.netloc:
        st.error("Provide a title and a valid HTTPS web address.")
    else:
        links = st.session_state.get("essential_links", [])
        if not isinstance(links, list):
            links = []
        links.append({"label": link_label.strip(), "url": link_url.strip()})
        st.session_state["essential_links"] = links
        st.success("Essential reading link added.")

links = st.session_state.get("essential_links", [])
if isinstance(links, list):
    for index, link in enumerate(links):
        if isinstance(link, dict) and link.get("label") and link.get("url"):
            label = link["label"]
            if index == 0 and label == "Bill as passed":
                label = "Bill as passed (if avail)"
            st.link_button(label, link["url"])

with st.expander("Draft a plain-language summary with AI"):
    if st.button("Draft summary from saved material", key="draft_bill_summary"):
        source = get_source_material()
        if not source:
            st.warning("Add summary, background, policy text, or source documents first.")
        else:
            client = get_openai_client()
            if client:
                try:
                    with st.spinner("Drafting a summary..."):
                        response = client.responses.create(
                            model=MODEL,
                            instructions=(
                                "Write a concise, nonpartisan plain-language summary "
                                "of the supplied legislative material. State only "
                                "what the material supports, identify uncertainty, "
                                "and do not provide legal advice."
                            ),
                            input=source,
                            max_output_tokens=700,
                        )
                    st.markdown(response.output_text)
                except OpenAIError as error:
                    report_openai_error(error)

st.subheader("The public discussion")
st.caption(
    "AI searches the web for news coverage and public posts about this Bill and "
    "summarises the sentiment it finds. Only the Bill name is sent to OpenAI."
)
if st.button("The public discussion", key="public_discussion"):
    discussion_bill = st.session_state.get("bill_title", "").strip()
    if not discussion_bill:
        st.warning("Save a Bill name or number above first.")
    else:
        client = get_openai_client()
        if client:
            try:
                with st.spinner("Searching media and social media..."):
                    response = client.responses.create(
                        model=MODEL,
                        tools=[{"type": "web_search_preview"}],
                        instructions=(
                            "Search news media and publicly visible social media "
                            "for discussion of the named Tasmanian Parliament Bill. "
                            "Write a nonpartisan summary of public sentiment: "
                            "overall tone, main arguments for and against, key "
                            "stakeholders, and recurring concerns. Cite the "
                            "sources used. State clearly when little or no "
                            "discussion is found or when social media content "
                            "could not be accessed. Do not invent sources or "
                            "quotes, and do not present sentiment as a poll."
                        ),
                        input=f"Bill: {discussion_bill}",
                        max_output_tokens=900,
                    )
                st.session_state["public_discussion_result"] = (
                    discussion_bill,
                    response.output_text,
                )
            except OpenAIError as error:
                report_openai_error(error)

result = st.session_state.get("public_discussion_result")
if result:
    st.markdown(f"**Public sentiment on {result[0]}**")
    st.markdown(result[1])
    st.caption(
        "AI-generated from web search results. Coverage of social media is "
        "partial and not representative of all constituents. Check the cited "
        "sources."
    )
