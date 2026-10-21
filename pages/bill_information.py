import difflib
import html
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

import streamlit as st
from openai import OpenAIError

from demodot import (
    MODEL,
    PARLIAMENT_URL,
    extract_uploaded_text,
    fetch_official_pdf,
    find_parliament_bill_page,
    find_parliament_bill_pdf_url,
    get_openai_client,
    report_openai_error,
    sync_session_bill,
)
from follow_dialog import show_follow_dialog


LEVELS = [
    ("Low", 0, 16),
    ("Moderate", 17, 33),
    ("High", 34, 50),
    ("Very High", 51, 67),
    ("Exceptional", 68, 84),
    ("Perfect Alignment", 85, 100),
]
PARLIAMENT_HOST = urlparse(PARLIAMENT_URL).hostname
LEGISLATION_URL = "https://www.legislation.tas.gov.au"
LEGISLATION_HOST = urlparse(LEGISLATION_URL).hostname
LEGISLATION_SEARCH_URL = f"{LEGISLATION_URL}/projectdata"


def find_bill_record(bill_name: str) -> tuple[str, str]:
    bill_page, bill_record_title = find_parliament_bill_page(bill_name)
    bill_pdf_url = find_parliament_bill_pdf_url(bill_page)

    clean_bill_title = re.sub(r"\s+\(\d+\s+of\s+\d{4}\)$", "", bill_record_title)
    act_title, replacements = re.subn(
        r"\bBill(?=(?:\s+\d{4})?$)",
        "Act",
        clean_bill_title,
        count=1,
        flags=re.IGNORECASE,
    )
    if replacements == 0:
        raise ValueError("The Parliament record does not identify a matching Bill title.")
    return bill_pdf_url, act_title


def find_act_pdf_url(act_title: str) -> str:
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
            "User-Agent": "Democracydot/1.0",
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    with urlopen(request, timeout=15) as response:
        final_url = urlparse(response.geturl())
        if final_url.scheme != "https" or final_url.hostname != LEGISLATION_HOST:
            raise ValueError("The legislation website redirected to an unexpected address.")
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


def alignment_level(score: int) -> str:
    for label, minimum, maximum in LEVELS:
        if minimum <= score <= maximum:
            return label
    raise ValueError("Alignment score must be between 0 and 100.")


def render_meter(score: int, level: str) -> None:
    colors = ["#bd4b42", "#e58b3c", "#e4c34c", "#9dbb55", "#4b9470", "#176b5b"]
    stops = []
    for index, color in enumerate(colors):
        start = index * 100 / len(colors)
        end = (index + 1) * 100 / len(colors)
        stops.append(f"{color} {start:.2f}% {end:.2f}%")
    gradient = ", ".join(stops)
    st.markdown(
        f"""
        <div class="demodot-meter">
          <div class="meter-heading">Demodot Meter</div>
          <div class="meter-index">Democratic Measure
            &nbsp;·&nbsp; Democracy Index:
            <strong>{score}/100</strong> &nbsp;·&nbsp; {level}</div>
          <div class="meter-track" role="img"
               aria-label="Democracy Index {score} out of 100, {level} alignment">
            <div class="meter-gradient" style="background:linear-gradient(to right,{gradient})"></div>
            <div class="meter-marker" style="left:{score}%"></div>
          </div>
          <div class="meter-labels">
            <span>Low</span><span>Moderate</span><span>High</span>
            <span>Very High</span><span>Exceptional</span>
            <span>Perfect Alignment</span>
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
        """,
        unsafe_allow_html=True,
    )


st.title("Democracy Index")
st.write(
    "View the introduced Bill and Act as passed, then compare both versions."
)
st.caption(
    "Both Bill texts are sent to OpenAI only when you request a comparison. "
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
    "Compare document - Democracy Index",
    key="compare_documents_and_show_markup",
)

if compare_documents:
    original_bill = st.session_state.get("original_bill_text", "")
    final_bill = st.session_state.get("final_bill_text", "")
    st.session_state.pop("last_alignment", None)
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
    render_meter(previous_score, level)
    st.subheader("Comparison report")
    st.write(previous["summary"])
    if previous["changed_areas"]:
        st.markdown("**Notable changes**")
        for area in previous["changed_areas"]:
            st.markdown(f"- {area}")
    st.caption(previous["evidence_note"])
