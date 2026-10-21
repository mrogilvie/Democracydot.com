from json import JSONDecodeError, loads
from urllib.error import HTTPError, URLError

import streamlit as st
from openai import OpenAIError

from demodot import (
    MODEL,
    PARLIAMENT_HOST,
    PARLIAMENT_URL,
    extract_uploaded_text,
    fetch_official_pdf,
    find_hansard_debate_links,
    find_parliament_bill_page,
    find_parliament_bill_pdf_url,
    get_openai_client,
    get_source_material,
    report_openai_error,
)


MAX_AUTOCOMPLETE_CHARS = 60000
AUTOCOMPLETE_FIELDS = ("summary", "background", "policy")


def autocomplete_bill_information(bill_name: str) -> dict[str, str] | None:
    """Draft summary, background and policy context from the official Bill text."""
    try:
        with st.spinner("Retrieving the Bill from Parliament records..."):
            bill_page, record_title = find_parliament_bill_page(bill_name)
            pdf_url = find_parliament_bill_pdf_url(bill_page)
            pdf = fetch_official_pdf(pdf_url, PARLIAMENT_HOST)
            bill_text = extract_uploaded_text(
                pdf_url.rsplit("/", 1)[-1].removesuffix(".pdf") + ".pdf", pdf
            )
    except (HTTPError, URLError, TimeoutError, UnicodeDecodeError, ValueError) as error:
        st.warning(f"Could not retrieve the Bill from Parliament records: {error}")
        return None

    client = get_openai_client()
    if not client:
        return None

    schema = {
        "type": "object",
        "properties": {name: {"type": "string"} for name in AUTOCOMPLETE_FIELDS},
        "required": list(AUTOCOMPLETE_FIELDS),
        "additionalProperties": False,
    }
    try:
        with st.spinner("Drafting the Bill information with AI..."):
            response = client.responses.create(
                model=MODEL,
                instructions=(
                    "Using only the supplied Bill text, write nonpartisan "
                    "plain-language information for the public. 'summary': a "
                    "concise overview of what the Bill does. 'background': why "
                    "the Bill was introduced and its context, only as far as "
                    "the text supports. 'policy': the policy purpose, the main "
                    "changes it makes and who is affected. Do not infer debate "
                    "positions, invent facts, or give legal advice. If the text "
                    "does not support something, say so briefly."
                ),
                input=f"BILL: {record_title}\n\n{bill_text[:MAX_AUTOCOMPLETE_CHARS]}",
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "bill_information",
                        "strict": True,
                        "schema": schema,
                    }
                },
                max_output_tokens=1500,
            )
        result = loads(response.output_text)
        if not all(isinstance(result.get(name), str) for name in AUTOCOMPLETE_FIELDS):
            raise ValueError("The AI response has an invalid structure.")
    except OpenAIError as error:
        report_openai_error(error)
        return None
    except (JSONDecodeError, ValueError, TypeError) as error:
        st.error(f"Could not interpret the AI result: {error}")
        return None
    return {name: result[name].strip() for name in AUTOCOMPLETE_FIELDS}


st.title("Bill Information")
st.write(
    "Build a clear information page for the Bill: its summary, background, "
    "policy context, and essential reading."
)
st.caption(
    "Text is sent to OpenAI only when you request an AI feature, such as a summary "
    "or when you enter a Bill name. Add only material you are authorized to share."
)

st.caption(
    "Add the Bill-specific Parliament and Hansard links under Essential reading."
)

def request_autocomplete():
    st.session_state["bill_autocomplete_requested"] = True


st.text_input(
    "Bill name or number",
    value=st.session_state.get("bill_title", ""),
    key="bill_title_input",
    on_change=request_autocomplete,
    help="Press Enter and the fields below are drafted by AI from the Bill text.",
)

if st.session_state.pop("bill_autocomplete_requested", False):
    new_title = st.session_state.get("bill_title_input", "").strip()
    st.session_state["bill_title"] = new_title
    if new_title:
        drafted = autocomplete_bill_information(new_title)
        if drafted:
            for field, key in (
                ("summary", "bill_summary"),
                ("background", "bill_background"),
                ("policy", "bill_policy"),
            ):
                st.session_state[key] = (
                    st.session_state.get(key, "").strip() or drafted[field]
                )
            st.session_state["bill_autocompleted"] = True
            st.rerun()

if st.session_state.pop("bill_autocompleted", False):
    st.success(
        "Empty fields were drafted by AI from the Bill text and saved for this "
        "session. Review and edit them before relying on them."
    )

with st.form("bill_information_form"):
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
    st.session_state["bill_title"] = st.session_state.get("bill_title_input", "").strip()
    st.session_state["bill_summary"] = summary.strip()
    st.session_state["bill_background"] = background.strip()
    st.session_state["bill_policy"] = policy.strip()
    st.success("Bill information saved for this app session.")

@st.cache_data(ttl=3600, show_spinner=False)
def lookup_full_bill_title(bill_name: str) -> tuple[str, str] | None:
    try:
        page_url, full_title = find_parliament_bill_page(bill_name)
    except (HTTPError, URLError, TimeoutError, UnicodeDecodeError, ValueError):
        return None
    return full_title, page_url


st.subheader("Essential reading")
entered_bill = (
    st.session_state.get("bill_title_input") or st.session_state.get("bill_title", "")
).strip()
bill_record = lookup_full_bill_title(entered_bill) if entered_bill else None
st.text_input(
    "Full Bill title and number",
    value=bill_record[0] if bill_record else "",
    placeholder="Enter a Bill name or number above",
    disabled=True,
)
if entered_bill and not bill_record:
    st.caption("No matching Bill was found in Tasmanian Parliament records.")

hansard_links = find_hansard_debate_links(entered_bill) if entered_bill else []
for label, url in hansard_links:
    st.link_button(label, url)
if entered_bill and hansard_links:
    st.caption(
        "Hansard links are added automatically from the Parliament of Tasmania "
        "Hansard search for this Bill name."
    )
elif entered_bill:
    st.caption("No Hansard debates were found for this Bill name yet.")

essential_links = []
if bill_record:
    essential_links.append({"label": bill_record[0], "url": bill_record[1]})
essential_links.extend({"label": l, "url": u} for l, u in hansard_links)
st.session_state["essential_links"] = essential_links

with st.expander("Draft a plain-language summary with AI"):
    if st.button("Draft summary from saved material", key="draft_bill_summary"):
        source = get_source_material()
        if not source:
            st.warning("Add summary, background, or policy text first.")
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
    discussion_bill = entered_bill
    if not discussion_bill:
        st.warning("Enter a Bill name or number above first.")
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

st.divider()
st.link_button("Tasmanian Parliament website", PARLIAMENT_URL)
