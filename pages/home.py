import streamlit as st

DEMOCRACYDOT_FACEBOOK_URL = "https://www.facebook.com/profile.php?id=61595771103973"
MADELEINE_FACEBOOK_URL = "https://www.facebook.com/madeleineogilvie.com.au/"


st.markdown(
    """
    <section class="dd-hero">
      <div class="dd-eyebrow"><span></span> Clarity for every citizen</div>
      <h1>Democracy, made <em>understandable.</em></h1>
    </section>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="dd-section-label">A clearer connection between your public voice and our laws</div>',
    unsafe_allow_html=True,
)

st.markdown(
    """
    <section class="dd-hero-copy">
      <p>
        Follow a Tasmanian Bill from first exposure draft to final Act.
        Democracydot helps you understand the issues and take part in the whole
        conversation. Quickly find relevant information, ask questions and
        receive plain-English answers with Billbow, and compare a Bill with the
        Act passed by the Tasmanian Parliament. Download a comparison document
        showing the differences between the Bill and the Act.
      </p>
      <p>
        The Democracy Index estimates how closely the Act reflects the Bill and
        helps you explore how the Bill changed during the democratic process.
      </p>
      <p>
        To access downloads and functions in Democracydot please join my
        facebook page.
      </p>
      <a class="dd-follow-btn" href="{FACEBOOK_PAGE_URL}" target="_blank"
         rel="noopener noreferrer">Follow Madeleine Ogilvie MP on Facebook</a>
    </section>
    """.replace("{FACEBOOK_PAGE_URL}", MADELEINE_FACEBOOK_URL),
    unsafe_allow_html=True,
)

st.markdown(
    """
    <style>
      [data-testid="stHorizontalBlock"]:has([class*="st-key-dd-home-card-"]) {
        align-items: stretch;
      }
      [data-testid="stColumn"]:has([class*="st-key-dd-home-card-"]) {
        display: flex;
        flex-direction: column;
      }
      [data-testid="stColumn"]:has([class*="st-key-dd-home-card-"]) > [data-testid="stVerticalBlock"],
      [data-testid="stColumn"]:has([class*="st-key-dd-home-card-"]) [data-testid="stLayoutWrapper"] {
        display: flex;
        flex: 1 1 auto;
        flex-direction: column;
      }
      [class*="st-key-dd-home-card-"] { flex: 1 1 auto; }
      [class*="st-key-dd-home-card-"] > [data-testid="stElementContainer"]:last-child {
        margin-top: auto;
      }
    </style>
    """,
    unsafe_allow_html=True,
)
bill_info, interaction, decisions = st.columns(3)

with bill_info:
    with st.container(border=True, key="dd-home-card-1"):
        st.markdown('<div class="dd-card-number">01</div>', unsafe_allow_html=True)
        st.subheader("Bill Information")
        st.write(
            "Get the essentials in one place: a plain-language overview, policy "
            "context, source documents, and further reading."
        )
        st.page_link("pages/bill_interaction.py", label="Explore the Bill", icon=":material/arrow_forward:")

with interaction:
    with st.container(border=True, key="dd-home-card-2"):
        st.markdown('<div class="dd-card-number">02</div>', unsafe_allow_html=True)
        st.subheader("Democratic Engagement")
        st.write(
            "Ask questions grounded in Bill material and submit an anonymous "
            "comment for the app owner to review."
        )
        st.page_link("pages/decision_phase.py", label="Join the conversation", icon=":material/arrow_forward:")

with decisions:
    with st.container(border=True, key="dd-home-card-3"):
        st.markdown('<div class="dd-card-number">03</div>', unsafe_allow_html=True)
        st.subheader("Democracy Index")
        st.write(
            "Compare the Bill with the final Act, generate a Democracy Index "
            "report, and download a helpful comparison document."
        )
        st.page_link("pages/bill_information.py", label="Generate report", icon=":material/arrow_forward:")
st.markdown(
    """
    <div class="dd-index-note">
      <strong>AI disclosure</strong><br>
      Democracydot uses AI to generate summaries, answer questions, and estimate
      alignment between original Bill and final Act text. AI outputs may be
      incomplete or inaccurate and should be checked against official sources.
      They are for general information only, not legal advice or an official
      parliamentary assessment. The Democracy Index is an estimate, not a
      definitive measure of democratic legitimacy.
    </div>
    """,
    unsafe_allow_html=True,
)
st.markdown(
    """
    <p class="dd-site-link">
      <a href="https://www.democracydot.com" target="_blank" rel="noopener noreferrer">
        www.democracydot.com
      </a>
    </p>
    """,
    unsafe_allow_html=True,
)
st.markdown(
    """
    <footer class="dd-footer">
      <span>Democracydot</span>
      <a href="/privacy" target="_self">Privacy Policy</a>
      <nav class="dd-social-links" aria-label="Social media">
        <a href="https://www.facebook.com/profile.php?id=61595771103973" target="_blank"
           rel="noopener noreferrer">Facebook</a>
        <a href="https://www.linkedin.com/in/hon-madeleine-ogilvie-mp-a23076b4"
           target="_blank" rel="noopener noreferrer">LinkedIn</a>
      </nav>
      <span>© 2026 Madeleine Ogilvie. All rights reserved.</span>
    </footer>
    """.replace("{DEMOCRACYDOT_FACEBOOK_URL}", DEMOCRACYDOT_FACEBOOK_URL),
    unsafe_allow_html=True,
)
