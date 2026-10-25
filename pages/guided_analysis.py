import streamlit as st
from openai import OpenAIError
from urllib.error import HTTPError, URLError

from demodot import (
    MODEL,
    PARLIAMENT_HOST,
    extract_uploaded_text,
    fetch_official_pdf,
    find_parliament_bill_page,
    find_parliament_bill_pdf_url,
    get_openai_client,
    report_openai_error,
)

MAX_CHARS = 60000

# Step 2 makes one AI call per analysis, so every run makes at least 5 calls
# (plus one for the final report in step 3).
ANALYSES = {
    "Summary": "Summarise what the Bill does in plain language.",
    "Key changes": "List the main changes the Bill makes to existing law.",
    "Affected groups": "Identify who is affected by the Bill and how.",
    "Risks and concerns": "Identify legal, practical or rights-related risks and "
    "ambiguities in the Bill text.",
    "Plain-English explanation": "Explain the Bill to a high-school student "
    "in a short paragraph.",
}
SYSTEM = (
    "You assist with legal research. Use only the supplied Bill text. Be "
    "nonpartisan, concise and do not give legal advice. If the text does not "
    "support something, say so."
)


def ask(client, task: str, text: str, max_tokens: int = 700) -> str:
    response = client.responses.create(
        model=MODEL,
        instructions=f"{SYSTEM}\n\nTask: {task}",
        input=text,
        max_output_tokens=max_tokens,
    )
    return response.output_text.strip()


st.title("Guided Bill Analysis")
st.write(
    "A three-step legal research workflow: **1. Load the Bill**, "
    "**2. Run AI analyses** (5 AI calls), **3. Review and download the report**."
)
st.caption(
    "Bill text is sent to OpenAI when you run the analysis. This is not legal advice."
)

st.subheader("Step 1: Load the Bill")
bill_name = st.text_input("Bill name or number")
upload = st.file_uploader("Or upload the Bill (PDF or text)", type=["pdf", "txt"])
selected = st.multiselect(
    "Analyses to include in the report",
    list(ANALYSES),
    default=list(ANALYSES),
    help="All five analyses are always run; unticked ones are left out of the report.",
)

if st.button("Run analysis", type="primary"):
    client = get_openai_client()
    if not client:
        st.stop()

    try:
        with st.spinner("Step 1: loading the Bill..."):
            if upload is not None:
                title = upload.name
                bill_text = extract_uploaded_text(upload.name, upload.getvalue())
            elif bill_name.strip():
                page, title = find_parliament_bill_page(bill_name.strip())
                pdf_url = find_parliament_bill_pdf_url(page)
                pdf = fetch_official_pdf(pdf_url, PARLIAMENT_HOST)
                bill_text = extract_uploaded_text("bill.pdf", pdf)
            else:
                st.warning("Enter a Bill name or upload a file.")
                st.stop()
    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        st.error(f"Could not load the Bill: {error}")
        st.stop()

    bill_text = bill_text[:MAX_CHARS]
    results: dict[str, str] = {}
    try:
        progress = st.progress(0.0, text="Step 2: running AI analyses...")
        for i, (name, task) in enumerate(ANALYSES.items(), start=1):
            results[name] = ask(client, task, f"BILL: {title}\n\n{bill_text}")
            progress.progress(i / len(ANALYSES), text=f"Completed: {name}")
        with st.spinner("Step 3: compiling the report..."):
            body = "\n\n".join(
                f"## {name}\n{results[name]}" for name in selected if name in results
            )
            overall = ask(
                client,
                "Write a two-sentence overall conclusion for a report based on "
                "these analyses.",
                body or "\n\n".join(results.values()),
                max_tokens=200,
            )
    except OpenAIError as error:
        report_openai_error(error)
        st.stop()

    st.session_state["guided_report"] = (
        f"# Bill analysis: {title}\n\n{body}\n\n## Overall conclusion\n{overall}\n\n"
        "_AI-generated; not legal advice._\n"
    )

report = st.session_state.get("guided_report")
if report:
    st.subheader("Step 3: Report")
    st.markdown(report)
    st.download_button(
        "Download report (Markdown)",
        report,
        file_name="bill_analysis.md",
        mime="text/markdown",
    )
