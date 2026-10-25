import html
import re
import uuid
from json import JSONDecodeError, loads
from urllib.error import HTTPError, URLError

import markdown
import streamlit as st
import streamlit.components.v1 as components
from openai import OpenAIError

from demodot import (
    MODEL,
    PARLIAMENT_HOST,
    PARLIAMENT_URL,
    extract_uploaded_text,
    fetch_official_pdf,
    HANSARD_CHAMBERS,
    PETITIONS_INFO_URL,
    fetch_hansard_bill_debate,
    find_hansard_debate_links,
    find_parliament_bill_page,
    find_parliament_bill_pdf_url,
    find_parliament_petitions,
    get_openai_client,
    report_openai_error,
)
from comment_store import STORE_ERRORS, save_signup
from follow_dialog import DEVICE_COOKIE, show_follow_dialog


MAX_AUTOCOMPLETE_CHARS = 60000
AUTOCOMPLETE_FIELDS = ("summary", "background", "policy")
MAX_GUIDED_ANALYSIS_CHARS = 60000
GUIDED_ANALYSES = {
    "Summary": "Summarise what the Bill does in plain language.",
    "Key changes": "List the main changes the Bill makes to existing law.",
    "Affected groups": "Identify who is affected by the Bill and how.",
    "Risks and concerns": (
        "Identify legal, practical or rights-related risks and ambiguities "
        "in the Bill text."
    ),
    "Plain-English explanation": (
        "Explain the Bill to a high-school student in a short paragraph."
    ),
}
GUIDED_ANALYSIS_SYSTEM = (
    "You assist with legal research. Use only the supplied Bill text. Be "
    "nonpartisan, concise and do not give legal advice. If the text does not "
    "support something, say so."
)


def ask_guided_analysis(client, task: str, text: str, max_tokens: int = 700) -> str:
    response = client.responses.create(
        model=MODEL,
        instructions=f"{GUIDED_ANALYSIS_SYSTEM}\n\nTask: {task}",
        input=text,
        max_output_tokens=max_tokens,
    )
    return response.output_text.strip()


def create_guided_report_html(
    report: str, title: str, label: str = "Bill analysis"
) -> str:
    body = markdown.markdown(html.escape(report, quote=False), extensions=["extra"])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(label)}: {html.escape(title)}</title>
  <style>
    body {{ background: #f7f9ff; color: #102a43; font: 16px/1.65 system-ui, sans-serif; margin: 0; padding: 2rem 1.25rem; }}
    main {{ background: #fff; border: 1px solid #e0e8f3; border-radius: 20px; box-shadow: 0 12px 32px rgba(16, 42, 67, .06); margin: 0 auto; max-width: 860px; padding: 2rem 2.5rem; }}
    h1 {{ border-bottom: 3px solid #ff38d1; font-size: 1.9rem; letter-spacing: -.03em; line-height: 1.25; margin-top: 0; padding-bottom: .6rem; }}
    h2 {{ color: #4778d0; font-size: 1.3rem; letter-spacing: -.02em; margin: 1.8rem 0 .4rem; }}
    ul, ol {{ padding-left: 1.4rem; }}
    li {{ margin: .3rem 0; }}
    em {{ color: #5e7085; }}
    footer {{ color: #5e7085; font-size: .85rem; margin: 1.5rem auto 0; max-width: 860px; text-align: center; }}
    @media print {{ body {{ background: #fff; padding: 0; }} main {{ border: 0; box-shadow: none; }} }}
  </style>
</head>
<body>
  <main>
{body}
  </main>
  <footer>Prepared with Democracydot. Information only, not legal advice.</footer>
</body>
</html>
"""


def create_guided_analysis(bill_name: str, selected_analyses: list[str]) -> None:
    if not selected_analyses:
        st.warning("Select at least one analysis to continue.")
        return

    client = get_openai_client()
    if not client:
        return

    try:
        with st.spinner("Step 1: loading the Bill..."):
            if not bill_name:
                st.warning("Enter a Bill name or number above first.")
                return
            bill_page, title = find_parliament_bill_page(bill_name)
            pdf_url = find_parliament_bill_pdf_url(bill_page)
            pdf = fetch_official_pdf(pdf_url, PARLIAMENT_HOST)
            bill_text = extract_uploaded_text("bill.pdf", pdf)
    except (HTTPError, URLError, TimeoutError, UnicodeDecodeError, ValueError, OSError) as error:
        st.error(f"Could not load the Bill: {error}")
        return

    bill_text = bill_text[:MAX_GUIDED_ANALYSIS_CHARS]
    results: dict[str, str] = {}
    try:
        progress = st.progress(0.0, text="Running selected analyses...")
        selected_tasks = [
            (name, GUIDED_ANALYSES[name])
            for name in selected_analyses
            if name in GUIDED_ANALYSES
        ]
        for index, (name, task) in enumerate(selected_tasks, start=1):
            results[name] = ask_guided_analysis(
                client, task, f"BILL: {title}\n\n{bill_text}"
            )
            progress.progress(index / len(selected_tasks), text=f"Completed: {name}")

        body = "\n\n".join(
            f"## {name}\n{results[name]}" for name, _ in selected_tasks
        )
        with st.spinner("Step 3: compiling the report..."):
            conclusion = ask_guided_analysis(
                client,
                "Write a two-sentence overall conclusion for a report based on "
                "these analyses.",
                body or "\n\n".join(results.values()),
                max_tokens=200,
            )
    except OpenAIError as error:
        report_openai_error(error)
        return

    st.session_state["guided_report"] = (
        f"# Bill analysis: {title}\n\n{body}\n\n## Overall conclusion\n"
        f"{conclusion}\n\n_AI-generated; not legal advice._\n"
    )
    st.session_state["guided_report_title"] = title


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
    "This function is AI supported. A search of relevant information is "
    "performed once you enter the Bill name."
)
download_area = st.container()

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

st.subheader("Guided Bill Analysis")
st.write("Select the analyses to include in your report:")
selected_guided_analyses = [
    name
    for index, name in enumerate(GUIDED_ANALYSES)
    if st.checkbox(
        name,
        value=True,
        key=f"guided_analysis_option_{index}",
    )
]
if st.button("Compile a Report", type="primary", key="run_guided_analysis"):
    create_guided_analysis(
        st.session_state.get("bill_title_input", "").strip(),
        selected_guided_analyses,
    )

guided_report = st.session_state.get("guided_report")
if guided_report:
    st.subheader(f"Report: {st.session_state.get('guided_report_title', 'Bill')}")
    st.markdown(guided_report)
    report_slug = re.sub(
        r"[^A-Za-z0-9]+",
        "-",
        st.session_state.get("guided_report_title", "bill"),
    ).strip("-") or "bill"
    st.download_button(
        "Download analysis report",
        create_guided_report_html(
            guided_report, st.session_state.get("guided_report_title", "Bill")
        ),
        file_name=f"{report_slug}-analysis.html",
        mime="text/html",
        key="download_guided_analysis",
    )

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

petition_links = []
if entered_bill:
    try:
        with st.spinner("Searching Parliament e-petitions..."):
            petition_links = find_parliament_petitions(hansard_name)
    except (OSError, ValueError):
        petition_links = []
for label, url in petition_links:
    st.link_button(label, url)
if petition_links:
    st.caption(
        "Petitions are matched automatically from the House of Assembly and "
        "Legislative Council e-petition sites using the Bill name and its "
        "subject matter. Check each petition to confirm it is relevant."
    )
elif entered_bill:
    st.caption(
        "No e-petitions on this Bill or its subject matter were found. "
        "Paper petitions are not searched."
    )
    st.link_button("Browse Parliament petitions", PETITIONS_INFO_URL)

essential_links = []
if bill_record:
    essential_links.append({"label": bill_record[0], "url": bill_record[1]})
essential_links.extend({"label": l, "url": u} for l, u in hansard_links)
essential_links.extend({"label": l, "url": u} for l, u in petition_links)
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
    summary_unlocked = bool(
        st.session_state.get("bill_info_follows_madeleine")
        and st.session_state.get("signup_saved")
    )
    summary_slug = re.sub(r"[^A-Za-z0-9]+", "-", hansard_name).strip("-") or "bill"
    st.download_button(
        "Download Summary",
        data=create_guided_report_html(
            f"# Hansard summary: {hansard_name}\n\n{hansard_summary[1]}",
            hansard_name,
            "Hansard summary",
        ),
        file_name=f"{summary_slug}-hansard-summary.html",
        mime="text/html",
        key="download_hansard_summary",
        disabled=not summary_unlocked,
    )
    if not summary_unlocked:
        st.caption(
            "Tick the Facebook box and enter your name and mobile number near the "
            "top of this page to enable the download."
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
    discussion_unlocked = bool(
        st.session_state.get("bill_info_follows_madeleine")
        and st.session_state.get("signup_saved")
    )
    discussion_slug = re.sub(r"[^A-Za-z0-9]+", "-", result[0]).strip("-") or "bill"
    st.download_button(
        "Download summary",
        data=create_guided_report_html(
            f"# Public sentiment: {result[0]}\n\n{result[1]}\n\n"
            "_AI-generated from web search results. Coverage of social media is "
            "partial and not representative of all constituents. Check the cited "
            "sources._",
            result[0],
            "Public discussion",
        ),
        file_name=f"{discussion_slug}-public-discussion.html",
        mime="text/html",
        key="download_public_discussion",
        disabled=not discussion_unlocked,
    )
    if not discussion_unlocked:
        st.caption(
            "Tick the Facebook box and enter your name and mobile number near the "
            "top of this page to enable the download."
        )

st.divider()


def nest_headings(text: str) -> str:
    """Keep embedded report headings below the full report's section headings."""
    lines = []
    for line in text.strip().splitlines():
        match = re.match(r"(#{1,6})\s+(.*)", line)
        if match:
            line = f"{'#' * max(len(match.group(1)), 3)} {match.group(2)}"
        lines.append(line)
    return "\n".join(lines)


def build_full_report_markdown() -> str:
    title = bill_record[0] if bill_record else entered_bill
    lines = [f"# Full report: {title}", ""]

    information = []
    for heading, key in (
        ("Bill summary", "bill_summary"),
        ("Background information", "bill_background"),
        ("Policy context", "bill_policy"),
    ):
        text = st.session_state.get(key, "").strip()
        if text:
            information += [f"### {heading}", "", text, ""]
    if information:
        lines += ["## Bill information", ""] + information
    if essential_links:
        lines += ["## Essential reading", ""]
        lines += [f"- [{link['label']}]({link['url']})" for link in essential_links]
        lines.append("")

    analysis = st.session_state.get("guided_report")
    if analysis:
        body = "\n".join(
            line
            for line in analysis.splitlines()
            if not re.match(r"#\s", line)
        )
        lines += ["## Guided Bill Analysis", "", nest_headings(body), ""]

    for heading, key, note in (
        (
            "Hansard AI summary",
            "hansard_summary",
            "AI-generated from Parliament of Tasmania Hansard; may be incomplete.",
        ),
        (
            "Public discussion",
            "public_discussion_result",
            "AI-generated from web search results; not a poll.",
        ),
    ):
        saved_result = st.session_state.get(key)
        if saved_result and saved_result[0] in (entered_bill, hansard_name):
            lines += [
                f"## {heading}",
                "",
                f"_{note}_",
                "",
                nest_headings(saved_result[1]),
                "",
            ]
    lines += [
        "---",
        "_Prepared with Democracydot. Information only, not legal advice. "
        "Check the official Parliament of Tasmania records._",
    ]
    return "\n".join(lines)



with download_area:
    if st.button(
        "Please follow me on facebook for downloads access",
        key="open_follow_dialog_bill_info",
    ):
        show_follow_dialog()
    st.caption("It's an honour system")
    follows_madeleine = st.checkbox(
        "I follow Madeleine Ogilvie MP on Facebook",
        key="bill_info_follows_madeleine",
    )
    if st.session_state.get("signup_saved"):
        st.success("Your name and mobile number are saved on this device.")
    else:
        with st.form("download_signup_form"):
            signup_name = st.text_input("Name")
            signup_mobile = st.text_input("Mobile number")
            st.caption(
                "Your name and mobile number are collected and stored by "
                "Democracydot so you can be contacted about updates and "
                "announcements."
            )
            continue_clicked = st.form_submit_button("Continue", key="signup_continue")
        if continue_clicked:
            digits = re.sub(r"\D", "", signup_mobile)
            if not signup_name.strip():
                st.warning("Enter your name to continue.")
            elif len(digits) < 8 or len(digits) > 15:
                st.warning("Enter a valid mobile number to continue.")
            else:
                st.session_state.setdefault("signup_device_token", uuid.uuid4().hex)
                try:
                    save_signup(
                        signup_name,
                        signup_mobile,
                        st.session_state["signup_device_token"],
                    )
                except ValueError as error:
                    st.warning(str(error))
                except STORE_ERRORS as error:
                    st.error(f"Could not save your details: {error}")
                else:
                    st.session_state["signup_saved"] = True
                    components.html(
                        "<script>window.parent.document.cookie = "
                        f"'{DEVICE_COOKIE}="
                        f"{st.session_state['signup_device_token']}; "
                        "max-age=31536000; path=/; SameSite=Lax';</script>",
                        height=0,
                    )
                    st.success("Thanks, your details are saved on this device.")
    if entered_bill and not follows_madeleine:
        st.info("Confirm that you follow the Facebook page to enable the download.")

if entered_bill and follows_madeleine and st.session_state.get("signup_saved"):
    download_name = re.sub(r"[^A-Za-z0-9]+", "-", hansard_name).strip("-") or "bill"
    full_report_title = bill_record[0] if bill_record else entered_bill
    st.download_button(
        "Download full report",
        data=create_guided_report_html(
            build_full_report_markdown(), full_report_title, "Full report"
        ),
        file_name=f"{download_name}-full-report.html",
        mime="text/html",
        key="download_bill_information",
    )

st.divider()
st.link_button("Tasmanian Parliament website", PARLIAMENT_URL)
