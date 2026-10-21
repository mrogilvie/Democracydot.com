import difflib
import html
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse

import streamlit as st
from openai import OpenAIError

from comment_store import get_comments
from demodot import (
    HANSARD_CHAMBERS,
    LEGISLATION_HOST,
    MODEL,
    PARLIAMENT_URL,
    extract_uploaded_text,
    fetch_hansard_bill_debate,
    fetch_official_pdf,
    find_act_pdf_url,
    find_parliament_bill_page,
    find_parliament_bill_pdf_url,
    get_openai_client,
    parliament_bill_act_title,
    report_openai_error,
    publish_session_bill,
    sync_session_bill,
)
from follow_dialog import show_follow_dialog


LEVELS = [
    ("Low", 0, 16),
    ("Moderate", 17, 33),
    ("High", 34, 50),
    ("Very High", 51, 67),
    ("Exceptional", 68, 84),
    ("Aligned", 85, 100),
]
PARLIAMENT_HOST = urlparse(PARLIAMENT_URL).hostname


def find_bill_record(bill_name: str) -> tuple[str, str]:
    bill_page, bill_record_title = find_parliament_bill_page(bill_name)
    bill_pdf_url = find_parliament_bill_pdf_url(bill_page)
    return bill_pdf_url, parliament_bill_act_title(bill_record_title)


def extract_comparison_text(name: str, contents: bytes) -> str:
    pdf_name = name if name.casefold().endswith(".pdf") else f"{name}.pdf"
    return extract_uploaded_text(pdf_name, contents)


def create_marked_up_html(original_text: str, act_text: str, title: str) -> str:
    original_tokens = re.findall(r"\s+|[^\s]+", original_text)
    act_tokens = re.findall(r"\s+|[^\s]+", act_text)
    matcher = difflib.SequenceMatcher(None, original_tokens, act_tokens)
    marked_text = []

    for operation, original_start, original_end, act_start, act_end in matcher.get_opcodes():
        original_part = html.escape("".join(original_tokens[original_start:original_end]))
        act_part = html.escape("".join(act_tokens[act_start:act_end]))
        if operation == "equal":
            marked_text.append(original_part)
        elif operation == "delete":
            marked_text.append(f"<del>{original_part}</del>")
        elif operation == "insert":
            marked_text.append(f"<ins>{act_part}</ins>")
        else:
            marked_text.append(f"<del>{original_part}</del><ins>{act_part}</ins>")

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Marked-up comparison: {html.escape(title)}</title>
  <style>
    body {{ color: #172033; font: 16px/1.65 system-ui, sans-serif; margin: 2rem auto; max-width: 1000px; padding: 0 1.25rem; }}
    h1 {{ font-size: 1.6rem; line-height: 1.25; }}
    .legend {{ display: flex; flex-wrap: wrap; gap: 1rem; margin: 1rem 0; }}
    del {{ background: #fee2e2; color: #991b1b; text-decoration-thickness: 2px; }}
    ins {{ background: #dcfce7; color: #166534; text-decoration: none; }}
    pre {{ background: #f8fafc; border: 1px solid #dbe2ea; border-radius: 8px; font: inherit; overflow-wrap: anywhere; padding: 1rem; white-space: pre-wrap; }}
    @media print {{ body {{ margin: 0; max-width: none; }} pre {{ border: 0; padding: 0; }} }}
  </style>
</head>
<body>
  <h1>Marked-up comparison: {html.escape(title)}</h1>
  <p>Changes from the introduced Bill to the Act as passed.</p>
  <div class="legend"><span><del>Removed from the introduced Bill</del></span><span><ins>Added in the Act as passed</ins></span></div>
  <pre>{''.join(marked_text)}</pre>
</body>
</html>
"""


REPORT_TEXT_LIMIT = 30_000
ESTIMATED_SECONDS = 120


def countdown_html(seconds: int) -> str:
    return f"""<div style="font:16px system-ui,sans-serif;color:#172033">
  <strong>Estimated time remaining:</strong> <span id="t"></span>
  <div style="background:#e2e8f0;border-radius:6px;height:8px;margin-top:8px">
    <div id="bar" style="background:#ec4899;border-radius:6px;height:8px;width:100%"></div></div>
</div>
<script>
  const total = {seconds};
  const end = Date.now() + total * 1000;
  const t = document.getElementById("t"), bar = document.getElementById("bar");
  function tick() {{
    const left = Math.max(0, Math.ceil((end - Date.now()) / 1000));
    t.textContent = left > 0
      ? Math.floor(left / 60) + ":" + String(left % 60).padStart(2, "0")
      : "finishing up, almost done...";
    bar.style.width = (left / total * 100) + "%";
  }}
  tick(); setInterval(tick, 250);
</script>"""


def generate_process_report(
    client, bill_name: str, original: str, final: str
) -> dict:
    has_act = bool(final.strip())
    with st.spinner("Searching public discussion..."):
        discussion = client.responses.create(
            model=MODEL,
            tools=[{"type": "web_search_preview"}],
            instructions=(
                "Search news media and publicly visible social media for "
                "discussion of the named Tasmanian Parliament Bill. Write ONE "
                "nonpartisan paragraph summarising public sentiment: tone, main "
                "arguments for and against, and key stakeholders. State clearly "
                "if little or no discussion is found. Do not invent sources or "
                "quotes, and do not present sentiment as a poll."
            ),
            input=f"Bill: {bill_name}",
            max_output_tokens=600,
        ).output_text.strip()

    with st.spinner("Reading Hansard..."):
        debates = {}
        for chamber in HANSARD_CHAMBERS:
            try:
                sittings = fetch_hansard_bill_debate(bill_name, chamber)
            except (HTTPError, URLError, TimeoutError, ValueError):
                sittings = []
            debates[chamber] = sittings
    debate_text = "\n\n".join(
        f"=== {chamber} ===\n"
        + (
            "\n\n".join(f"[{day}]\n{text}" for day, text in sittings)[
                :REPORT_TEXT_LIMIT
            ]
            or "(No Hansard text found.)"
        )
        for chamber, sittings in debates.items()
    )
    sitting_count = sum(len(sittings) for sittings in debates.values())
    comment_count = sum(
        1
        for item in get_comments()
        if bill_name.casefold() in (item.get("bill_title") or "").casefold()
    )

    schema = {
        "type": "object",
        "properties": {
            "parliamentary_debates": {"type": "string"},
            "bill_to_act_delta": {"type": "string"},
            "process_analysis": {"type": "string"},
        },
        "required": ["parliamentary_debates", "bill_to_act_delta", "process_analysis"],
        "additionalProperties": False,
    }
    with st.spinner("Analysing the legislative process..."):
        response = client.responses.create(
            model=MODEL,
            instructions=(
                "You analyse a Tasmanian Parliament Bill. Return three fields, "
                "each ONE neutral plain-English paragraph. "
                "'parliamentary_debates': summarise the Hansard debate in both "
                "houses using only the supplied Hansard text; say so if none was "
                "found. 'bill_to_act_delta': "
                + (
                    "summarise the key differences between the original Bill "
                    "and the Act as passed, or say there are no material "
                    "changes. "
                    if has_act
                    else "return an empty string; no Act has been passed yet. "
                )
                + "'process_analysis': assess whether the democratic process "
                "is working, how much engagement happened (public discussion, "
                "Hansard sittings, constituent comments received)"
                + (
                    " and any key changes made during the legislative process. "
                    if has_act
                    else ". The Bill has not yet become an Act, so say the "
                    "process is still under way and make no claim about the "
                    "final outcome. "
                )
                + "Do not overstate; note evidence limits."
            ),
            input=(
                f"Bill: {bill_name}\n"
                f"Hansard sittings found: {sitting_count}\n"
                f"Constituent comments received on Democracydot: {comment_count}\n\n"
                f"PUBLIC DISCUSSION SUMMARY:\n{discussion}\n\n"
                f"HANSARD:\n{debate_text}\n\n"
                f"ORIGINAL BILL:\n{original.strip()[:REPORT_TEXT_LIMIT]}\n\n"
                + (
                    f"ACT AS PASSED:\n{final.strip()[:REPORT_TEXT_LIMIT]}"
                    if has_act
                    else "ACT AS PASSED: none (the Bill has not yet passed)."
                )
            ),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "process_report",
                    "strict": True,
                    "schema": schema,
                }
            },
            max_output_tokens=1500,
        )
    report = json.loads(response.output_text)
    report["public_discussion"] = discussion
    report["bill_name"] = bill_name
    return report


def create_index_report_html(
    result: dict | None, report: dict | None, title: str
) -> str:
    title = " ".join(w[:1].upper() + w[1:] for w in title.split())
    sections = []
    if report:
        for heading, key in (
            ("Public discussion", "public_discussion"),
            ("Parliamentary debates", "parliamentary_debates"),
            ("Bill compared with the Act as passed", "bill_to_act_delta"),
            ("Did the democratic process work?", "process_analysis"),
        ):
            if report.get(key):
                sections.append(
                    f"<h2>{heading}</h2><p>{html.escape(report[key])}</p>"
                )
    if result:
        score = result["alignment_index"]
        changes = "".join(
            f"<li>{html.escape(a)}</li>" for a in result["changed_areas"]
        )
        index_block = f"""{meter_html(score, alignment_level(score))}
<p><strong>What the Democracy Index measures:</strong> how closely the Act as passed
matches the Bill as introduced, scored from 0 to 100 on whether the Act preserves the
Bill's purpose and material provisions. A higher score means fewer substantive changes
during the legislative process. It does not measure whether the law is good or whether
the process was legitimate.</p>"""
        comparison_block = f"""<h2>Comparison report</h2><p>{html.escape(result["summary"])}</p>
{f"<h3>Notable changes</h3><ul>{changes}</ul>" if changes else ""}
<p><em>{html.escape(result["evidence_note"])}</em></p>"""
    else:
        index_block = (
            "<p><strong>Status:</strong> this Bill has not yet passed into an Act, so "
            "no comparison between the Bill and an Act is included. The sections "
            "below cover engagement so far.</p>"
        )
        comparison_block = ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Democracy Index: {html.escape(title)}</title>
<style>body{{font:16px/1.6 system-ui,sans-serif;color:#172033;margin:2rem auto;max-width:800px;padding:0 1rem}}
.score{{font-size:1.4rem;font-weight:700}}</style></head>
<body>
<h1>Democracy Index: {html.escape(title)}</h1>
{index_block}
{''.join(sections)}
{comparison_block}
<p><small>This document was produced via Democracydot (www.democracydot.com) and its use is subject to the Democracydot Terms and Conditions.</small></p>
<p><small>AI-assisted estimate; not an official parliamentary rating or a measure of democratic legitimacy.</small></p>
</body></html>
"""


def alignment_level(score: int) -> str:
    for label, minimum, maximum in LEVELS:
        if minimum <= score <= maximum:
            return label
    raise ValueError("Alignment score must be between 0 and 100.")


def meter_html(score: int, level: str) -> str:
    colors = ["#bd4b42", "#e58b3c", "#e4c34c", "#9dbb55", "#4b9470", "#176b5b"]
    stops = []
    for index, color in enumerate(colors):
        start = index * 100 / len(colors)
        end = (index + 1) * 100 / len(colors)
        stops.append(f"{color} {start:.2f}% {end:.2f}%")
    gradient = ", ".join(stops)
    return f"""
        <div class="demodot-meter">
          <div class="meter-heading">Demodot Meter</div>
          <div class="meter-index">Democratic Measure
            &nbsp;·&nbsp; Democracy Index:
            <strong>{score}/100</strong> &nbsp;·&nbsp; {level}</div>
          <div class="meter-track" role="img"
               aria-label="Democracy Index {score} out of 100, {level}">
            <div class="meter-gradient" style="background:linear-gradient(to right,{gradient})"></div>
            <div class="meter-marker" style="left:{score}%"></div>
          </div>
          <div class="meter-labels">
            <span>Low</span><span>Moderate</span><span>High</span>
            <span>Very High</span><span>Exceptional</span>
            <span>Aligned</span>
          </div>
        </div>
        <style>
          .demodot-meter {{
            background: #fff;
            border: 1px solid #d8dee5;
            border-radius: 14px;
            padding: 1.25rem 1.4rem 1rem;
            margin: .75rem 0 1.25rem;
          }}
          .meter-heading {{
            color: #334155;
            font-size: .9rem;
            font-weight: 700;
            letter-spacing: .08em;
            text-transform: uppercase;
          }}
          .meter-index {{
            color: #172033;
            font-size: 1.2rem;
            margin: .25rem 0 1.25rem;
          }}
          .meter-track {{
            height: 34px;
            position: relative;
          }}
          .meter-gradient {{
            border: 1px solid #26344333;
            border-radius: 5px;
            height: 20px;
            position: absolute;
            top: 7px;
            width: 100%;
          }}
          .meter-marker {{
            background: #142033;
            border: 3px solid #fff;
            border-radius: 50%;
            box-shadow: 0 1px 5px #17203388;
            height: 28px;
            position: absolute;
            top: 3px;
            transform: translateX(-50%);
            width: 28px;
          }}
          .meter-labels {{
            color: #475569;
            display: grid;
            font-size: .72rem;
            gap: .3rem;
            grid-template-columns: repeat(6, minmax(0, 1fr));
            line-height: 1.2;
            text-align: center;
          }}
          .meter-labels span:first-child {{ text-align: left; }}
          .meter-labels span:last-child {{ text-align: right; }}
          @media (max-width: 600px) {{
            .demodot-meter {{ padding: 1rem .75rem .8rem; }}
            .meter-labels {{ font-size: .58rem; }}
          }}
        </style>
        """


def render_meter(score: int, level: str) -> None:
    st.markdown(meter_html(score, level), unsafe_allow_html=True)


st.title("Democracy Index")
st.write(
    "Democracydot will prepare a Democracy Index that allows you to compare "
    "changes between the original Bill and any final Act. The Democracy Index "
    "incorporates democratic engagement through media, social media and "
    "parliamentary debates."
)
st.caption(
    "Both Bill texts, Hansard text and the Bill name are sent to OpenAI only when you request a comparison. "
    "Add only material you are authorized to share."
)
st.subheader("Find the Bill in Parliament records")
st.caption(
    "Search the official Parliament of Tasmania website to display the "
    "introduced Bill and its Act as passed. Enter the Bill name; no web address "
    "is needed."
)
def request_parliament_search() -> None:
    st.session_state["parliament_search_requested"] = True


if sync_session_bill("parliament_bill_search_input", "page3_synced_bill"):
    st.session_state["parliament_search_requested"] = True

bill_name = st.text_input(
    "Bill name",
    placeholder="For example, Conversion Practices Prohibition Bill 2026",
    help="Type the Bill name and press Enter to search Parliament records.",
    key="parliament_bill_search_input",
    on_change=request_parliament_search,
)
publish_session_bill("parliament_bill_search_input", "page3_synced_bill")
search_bill = st.session_state.pop("parliament_search_requested", False)

if search_bill:
    st.session_state.pop("parliament_bill_tabled_url", None)
    st.session_state.pop("parliament_bill_pdf", None)
    st.session_state.pop("parliament_act_pdf_url", None)
    st.session_state.pop("parliament_act_pdf", None)
    st.session_state.pop("parliament_bill_search_name", None)
    st.session_state.pop("marked_up_html", None)
    st.session_state.pop("marked_up_filename", None)
    st.session_state["original_bill_text"] = ""
    st.session_state["original_bill_text_input"] = ""
    st.session_state["final_bill_text"] = ""
    st.session_state["final_bill_text_input"] = ""
    if bill_name.strip():
        try:
            with st.spinner("Searching Parliament records..."):
                bill_pdf_url, act_title = find_bill_record(bill_name.strip())
                bill_pdf = fetch_official_pdf(bill_pdf_url, PARLIAMENT_HOST)
            st.session_state["parliament_bill_tabled_url"] = bill_pdf_url
            st.session_state["parliament_bill_pdf"] = bill_pdf
            st.session_state["parliament_bill_search_name"] = bill_name.strip()
            try:
                original_text = extract_comparison_text(
                    bill_pdf_url.rsplit("/", 1)[-1], bill_pdf
                )
                st.session_state["original_bill_text"] = original_text
                st.session_state["original_bill_text_input"] = st.session_state[
                    "original_bill_text"
                ]
            except ValueError as error:
                st.warning(f"The original Bill PDF is available, but {error}")

            try:
                with st.spinner("Finding the Act as passed..."):
                    act_pdf_url = find_act_pdf_url(act_title)
                    act_pdf = fetch_official_pdf(act_pdf_url, LEGISLATION_HOST)
            except (
                HTTPError,
                URLError,
                TimeoutError,
                UnicodeDecodeError,
                json.JSONDecodeError,
                ValueError,
            ) as error:
                st.warning(f"Could not retrieve the Act as passed PDF: {error}")
            else:
                st.session_state["parliament_act_pdf_url"] = act_pdf_url
                st.session_state["parliament_act_pdf"] = act_pdf
                try:
                    final_text = extract_comparison_text(
                        act_pdf_url.rsplit("/", 1)[-1], act_pdf
                    )
                    st.session_state["final_bill_text"] = final_text
                    st.session_state["final_bill_text_input"] = st.session_state[
                        "final_bill_text"
                    ]
                except ValueError as error:
                    st.warning(f"The Act as passed PDF is available, but {error}")
        except (HTTPError, URLError, TimeoutError, UnicodeDecodeError) as error:
            st.error(f"Could not retrieve the introduced Bill PDF: {error}")
        except ValueError as error:
            st.warning(str(error))
    else:
        st.warning("Enter a Bill name to search Parliament records.")

bill_as_tabled_url = st.session_state.get("parliament_bill_tabled_url")
with st.container(border=True):
    st.subheader("Original Bill as introduced")
    if st.session_state.get("parliament_bill_pdf"):
        st.pdf(
            st.session_state["parliament_bill_pdf"],
            height=640,
            key="original_bill_pdf_viewer",
        )
        if bill_as_tabled_url:
            st.link_button("Open Bill as Tabled PDF", bill_as_tabled_url)
    else:
        st.info("Search Parliament records above to display the introduced Bill PDF.")

with st.container(border=True):
    st.subheader("Act as passed")
    if st.session_state.get("parliament_act_pdf"):
        st.pdf(
            st.session_state["parliament_act_pdf"],
            height=640,
            key="act_as_passed_pdf_viewer",
        )
    else:
        st.info(
            "Search Parliament records above to find and display the Act as passed PDF."
        )

act_pdf = st.session_state.get("parliament_act_pdf")
saved_act_text = st.session_state.get("final_bill_text", "")
if (
    isinstance(act_pdf, bytes)
    and isinstance(saved_act_text, str)
    and saved_act_text.startswith("%PDF-")
):
    try:
        act_pdf_url = st.session_state.get("parliament_act_pdf_url", "Act-as-passed.pdf")
        corrected_act_text = extract_comparison_text(
            act_pdf_url.rsplit("/", 1)[-1], act_pdf
        )
    except ValueError as error:
        st.error(f"Could not reload the Act text from its PDF: {error}")
    else:
        st.session_state["final_bill_text"] = corrected_act_text

st.caption(
    "The Democracy Index is an AI-assisted estimate of substantive similarity, "
    "not an official parliamentary rating or a measure of democratic legitimacy."
)

compare_documents = st.button(
    "Create Democracy Index",
    key="compare_documents_and_show_markup",
)
st.caption("Please do not close the browser while the request is processing.")
timer_placeholder = st.empty()

if compare_documents:
    with timer_placeholder:
        st.iframe(countdown_html(ESTIMATED_SECONDS), height=90)
    original_bill = st.session_state.get("original_bill_text", "")
    final_bill = st.session_state.get("final_bill_text", "")
    st.session_state.pop("last_alignment", None)
    st.session_state.pop("process_report", None)
    st.session_state.pop("marked_up_html", None)
    st.session_state.pop("marked_up_filename", None)

    if not isinstance(original_bill, str) or not original_bill.strip():
        st.warning("Search Parliament records to retrieve the introduced Bill first.")
    elif not isinstance(final_bill, str) or not final_bill.strip():
        st.warning("The Act as passed text is not available for comparison.")
    else:
        title = st.session_state.get("parliament_bill_search_name", "Bill")
        st.session_state["marked_up_html"] = create_marked_up_html(
            original_bill,
            final_bill,
            title,
        )
        safe_title = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-").lower()
        st.session_state["marked_up_filename"] = (
            f"{safe_title or 'Bill'}-marked-up.html"
        )

        client = get_openai_client()
        if client:
            schema = {
                "type": "object",
                "properties": {
                    "alignment_index": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 100,
                    },
                    "summary": {"type": "string"},
                    "changed_areas": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "evidence_note": {"type": "string"},
                },
                "required": [
                    "alignment_index",
                    "summary",
                    "changed_areas",
                    "evidence_note",
                ],
                "additionalProperties": False,
            }
            try:
                with st.spinner("Comparing the documents..."):
                    response = client.responses.create(
                        model=MODEL,
                        instructions=(
                            "Compare the original Bill and the Act as passed. "
                            "Estimate substantive alignment from 0 to 100 based "
                            "on whether the Act preserves the original Bill's "
                            "purpose and material provisions. Do not let "
                            "formatting, renumbering, or minor wording changes "
                            "dominate the score. Identify notable changed areas "
                            "and briefly explain the basis and limitations of "
                            "the estimate. Be neutral and do not infer debate "
                            "positions from Bill text alone."
                        ),
                        input=(
                            "ORIGINAL BILL:\n"
                            f"{original_bill.strip()}\n\n"
                            "ACT AS PASSED:\n"
                            f"{final_bill.strip()}"
                        ),
                        text={
                            "format": {
                                "type": "json_schema",
                                "name": "bill_alignment",
                                "strict": True,
                                "schema": schema,
                            }
                        },
                        max_output_tokens=1000,
                    )
                result = json.loads(response.output_text)
                score = result["alignment_index"]
                if (
                    not isinstance(score, int)
                    or isinstance(score, bool)
                    or not 0 <= score <= 100
                    or not isinstance(result["summary"], str)
                    or not isinstance(result["changed_areas"], list)
                    or not all(
                        isinstance(area, str) for area in result["changed_areas"]
                    )
                    or not isinstance(result["evidence_note"], str)
                ):
                    raise ValueError("The comparison response has an invalid structure.")
            except OpenAIError as error:
                report_openai_error(error)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
                st.error(f"Could not interpret the comparison result: {error}")
            else:
                st.session_state["last_alignment"] = result
                try:
                    st.session_state["process_report"] = generate_process_report(
                        client, title, original_bill, final_bill
                    )
                except OpenAIError as error:
                    report_openai_error(error)
                except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
                    st.error(f"Could not build the process report: {error}")

timer_placeholder.empty()

if st.session_state.get("marked_up_html"):
    with st.container(border=True):
        st.subheader("Compared document")
        st.caption(
            "Red text was removed from the introduced Bill; green text was added "
            "in the Act as passed."
        )
        st.iframe(st.session_state["marked_up_html"], height=640)

    if st.button(
        "Visit Madeleine Ogilvie MP and follow to access downloads",
        key="open_follow_dialog",
    ):
        show_follow_dialog()
    st.caption(
        "Downloads are available after you confirm that you follow Madeleine "
        "Ogilvie MP on Facebook. This confirmation is not verified by Facebook."
    )
    follows_madeleine = st.checkbox(
        "I follow Madeleine Ogilvie MP on Facebook",
        key="follows_madeleine_ogilvie_mp",
    )
    if follows_madeleine:
        st.download_button(
            "Download marked-up comparison",
            data=st.session_state["marked_up_html"],
            file_name=st.session_state["marked_up_filename"],
            mime="text/html",
            key="download_marked_up_comparison",
        )
    else:
        st.info("Confirm that you follow the Facebook page to enable this download.")

previous = st.session_state.get("last_alignment")
if isinstance(previous, dict):
    previous_score = previous["alignment_index"]
    level = alignment_level(previous_score)
    report = st.session_state.get("process_report")
    if isinstance(report, dict):
        st.subheader(report["bill_name"])
        st.markdown("**Public discussion**")
        st.write(report["public_discussion"])
        st.markdown("**Parliamentary debates**")
        st.write(report["parliamentary_debates"])
        st.markdown("**Bill compared with the Act as passed**")
        st.write(report["bill_to_act_delta"])
        st.markdown("**Did the democratic process work?**")
        st.write(report["process_analysis"])
        st.caption(
            "AI-generated from web search, Hansard and the Bill and Act texts. "
            "Check the sources; this is not an official assessment."
        )
    render_meter(previous_score, level)
    st.subheader("Comparison report")
    st.write(previous["summary"])
    if previous["changed_areas"]:
        st.markdown("**Notable changes**")
        for area in previous["changed_areas"]:
            st.markdown(f"- {area}")
    st.caption(previous["evidence_note"])

    st.markdown("**Download the Democracy Index**")
    follows_for_index = st.checkbox(
        "I follow Madeleine Ogilvie MP on Facebook",
        key="follows_madeleine_ogilvie_mp_index",
    )
    if follows_for_index:
        index_title = st.session_state.get("parliament_bill_search_name", "Bill")
        index_slug = re.sub(r"[^A-Za-z0-9]+", "-", index_title).strip("-").lower()
        st.download_button(
            "Download Democracy Index",
            data=create_index_report_html(previous, report, index_title),
            file_name=f"{index_slug or 'bill'}-democracy-index.html",
            mime="text/html",
            key="download_democracy_index",
        )
    else:
        st.info("Confirm that you follow the Facebook page to enable this download.")
