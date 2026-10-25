import streamlit as st

from design_system import apply_design_system


st.set_page_config(
    page_title="Democracydot",
    page_icon="🏛️",
    layout="wide",
)
apply_design_system()

with st.sidebar:
    st.header("OpenAI credentials")
    st.text_input(
        "OpenAI API key",
        type="password",
        key="openai_api_key",
        placeholder="sk-...",
        help="Used only for this session to call the OpenAI API.",
    )

home_page = st.Page(
    "pages/home.py",
    title="Home",
    icon=":material/home:",
    default=True,
)

pages = {
    "Democracydot": [
        home_page,
        st.Page(
            "pages/bill_interaction.py",
            title="Bill Information",
            icon=":material/article:",
        ),
        st.Page(
            "pages/decision_phase.py",
            title="Democratic Engagement",
            icon=":material/forum:",
        ),
        st.Page(
            "pages/bill_information.py",
            title="Democracy Index",
            icon=":material/how_to_vote:",
        ),
    ],
    "About": [
        st.Page(
            "pages/privacy.py",
            title="Privacy Policy",
            icon=":material/policy:",
            url_path="privacy",
        ),
        st.Page(
            "pages/terms.py",
            title="Terms and Conditions",
            icon=":material/gavel:",
            url_path="terms",
        ),
    ],
    "App owner": [
        st.Page(
            "pages/owner_review.py",
            title="Review comments",
            icon=":material/rate_review:",
        )
    ],
}

st.navigation(pages).run()

st.divider()
st.caption(
    "By browsing or using Democracydot you accept the "
    "[Terms and Conditions](/terms). The app does not provide legal advice and "
    "is used entirely at your own risk. See the [Privacy Policy](/privacy)."
)
