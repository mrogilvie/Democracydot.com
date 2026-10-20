import streamlit as st

from design_system import apply_design_system


st.set_page_config(
    page_title="Democracydot",
    page_icon="🏛️",
    layout="wide",
)
apply_design_system()

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
            "pages/bill_information.py",
            title="Bill information",
            icon=":material/article:",
        ),
        st.Page(
            "pages/bill_interaction.py",
            title="Democratic interaction",
            icon=":material/forum:",
        ),
        st.Page(
            "pages/decision_phase.py",
            title="Democracy Index",
            icon=":material/how_to_vote:",
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
