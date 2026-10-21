import re
from json import JSONDecodeError, loads
from urllib.error import HTTPError, URLError

import streamlit as st
from openai import OpenAIError

from follow_dialog import show_follow_dialog

from demodot import (
    MODEL,
    PARLIAMENT_HOST,
    PARLIAMENT_URL,
    extract_uploaded_text,
    fetch_official_pdf,
    HANSARD_CHAMBERS,
    fetch_hansard_bill_debate,
    find_hansard_debate_links,
    find_parliament_bill_page,
    find_parliament_bill_pdf_url,
    get_openai_client,
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
                    st.session_state.get(f"{key}_input", "").strip()
                    or st.session_state.get(key, "").strip()
                    or drafted[field]
                )
            st.session_state["bill_autocompleted"] = True
            st.session_state["bill_autocompleted_now"] = True
            st.rerun()

if st.session_state.pop("bill_autocompleted", False):
    st.success(
        "Empty fields were drafted by AI from the Bill text and saved for this "
        "session. Review and edit them before relying on them."
    )

FIELD_KEYS = {
    "bill_summary": "bill_summary_input",
    "bill_background": "bill_background_input",
    "bill_policy": "bill_policy_input",
}
for stored_key, widget_key in FIELD_KEYS.items():
    if widget_key not in st.session_state or st.session_state.get("bill_autocompleted_now"):
        st.session_state[widget_key] = st.session_state.get(stored_key, "")
st.session_state.pop("bill_autocompleted_now", None)

st.text_area(
    "Bill summary",
    key="bill_summary_input",
    height=130,
    help="Enter an existing summary, or let AI draft it when you enter the Bill name.",
)
st.text_area("Background information", key="bill_background_input", height=160)
st.text_area("Policy context", key="bill_policy_input", height=160)
for stored_key, widget_key in FIELD_KEYS.items():
    st.session_state[stored_key] = st.session_state[widget_key].strip()
st.session_state["bill_title"] = st.session_state.get("bill_title_input", "").strip()

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

hansard_name = bill_record[0] if bill_record else entered_bill
hansard_links = find_hansard_debate_links(hansard_name) if entered_bill else []
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

st.subheader("Create Hansard AI summary")
st.caption(
    "Summarises the House of Assembly debate, then the Legislative Council "
    "debate, then draws a conclusion, using only the Parliament of Tasmania "
    "Hansard text for this Bill."
)
if st.button("Create Hansard AI summary", key="summarise_hansard"):
    if not entered_bill:
        st.warning("Enter a Bill name or number above first.")
    else:
        try:
            with st.spinner("Reading Hansard..."):
                debates = {
                    chamber: fetch_hansard_bill_debate(hansard_name, chamber)
                    for chamber in HANSARD_CHAMBERS
                }
        except (HTTPError, URLError, TimeoutError, ValueError, OSError) as error:
            st.warning(f"Could not retrieve Hansard: {error}")
            debates = None
        if debates is not None and not any(debates.values()):
            st.info("No Hansard text was found for this Bill yet.")
        elif debates is not None:
            parts = []
            for chamber, sittings in debates.items():
                if sittings:
                    body = "\n\n".join(
                        f"[{sitting}]\n{text}" for sitting, text in sittings
                    )
                else:
                    body = "(No Hansard text found for this chamber.)"
                parts.append(f"=== {chamber} ===\n{body}")
            client = get_openai_client()
            if client:
                try:
                    with st.spinner("Summarising the debates..."):
                        response = client.responses.create(
                            model=MODEL,
                            instructions=(
                                "You summarise Tasmanian Parliament Hansard for "
                                "the public in neutral plain English, using ONLY "
                                "the supplied Hansard text. Write three markdown "
                                "sections: '### House of Assembly debate', "
                                "'### Legislative Council debate' and "
                                "'### Conclusion'. In each debate section cover "
                                "the main arguments for and against, key "
                                "amendments and the outcome of any vote, naming "
                                "speakers only when the text does. If a "
                                "chamber's text shows only the first reading, or "
                                "none, say the Bill has not yet been debated "
                                "there and do not speculate. The Conclusion "
                                "should draw together the debates and where the "
                                "Bill stands, only as far as the text supports. "
                                "Text marked 'trimmed' is excerpted. Do not "
                                "provide legal advice or invent facts."
                            ),
                            input=f"Bill: {hansard_name}\n\n" + "\n\n".join(parts),
                            max_output_tokens=1500,
                        )
                    st.session_state["hansard_summary"] = (
                        hansard_name,
                        response.output_text,
                    )
                except OpenAIError as error:
                    report_openai_error(error)

hansard_summary = st.session_state.get("hansard_summary")
if hansard_summary and hansard_summary[0] == hansard_name:
    st.markdown(hansard_summary[1])
    st.caption(
        "AI-generated from Parliament of Tasmania Hansard and may be incomplete "
        "or wrong; long debates are trimmed. Read the Hansard links above for "
        "the full record."
    )

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
st.subheader("Download this Bill information")


def build_bill_information_markdown() -> str:
    lines = [f"# {bill_record[0] if bill_record else entered_bill}", ""]
    for heading, key in (
        ("Bill summary", "bill_summary"),
        ("Background information", "bill_background"),
        ("Policy context", "bill_policy"),
    ):
        text = st.session_state.get(key, "").strip()
        if text:
            lines += [f"## {heading}", "", text, ""]
    if essential_links:
        lines += ["## Essential reading", ""]
        lines += [f"- [{link['label']}]({link['url']})" for link in essential_links]
        lines.append("")
    for heading, key, note in (
        (
            "Hansard AI summary",
            "hansard_summary",
            "AI-generated from Parliament of Tasmania Hansard; may be incomplete.",
        ),
        (
            "The public discussion",
            "public_discussion_result",
            "AI-generated from web search results; not a poll.",
        ),
    ):
        saved_result = st.session_state.get(key)
        if saved_result and saved_result[0] in (entered_bill, hansard_name):
            lines += [f"## {heading}", "", f"_{note}_", "", saved_result[1], ""]
    lines += [
        "---",
        "Prepared with Democracydot. Information only, not legal advice. "
        "Check the official Parliament of Tasmania records.",
    ]
    return "\n".join(lines)


if st.button(
    "Follow Madeleine Ogilvie MP on Facebook to download this information",
    key="open_follow_dialog_bill_info",
):
    show_follow_dialog()
st.caption(
    "Downloads are available after you confirm that you follow Madeleine Ogilvie "
    "MP on Facebook. This confirmation is not verified by Facebook."
)
follows_madeleine = st.checkbox(
    "I follow Madeleine Ogilvie MP on Facebook",
    key="bill_info_follows_madeleine",
)
if not entered_bill:
    st.info("Enter a Bill name or number above to prepare a download.")
elif follows_madeleine:
    download_name = re.sub(r"[^A-Za-z0-9]+", "-", hansard_name).strip("-") or "bill"
    st.download_button(
        "Download Bill information",
        data=build_bill_information_markdown(),
        file_name=f"{download_name}-information.md",
        mime="text/markdown",
        key="download_bill_information",
    )
else:
    st.info("Confirm that you follow the Facebook page to enable the download.")

st.divider()
st.link_button("Tasmanian Parliament website", PARLIAMENT_URL)
