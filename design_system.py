import streamlit as st


def apply_design_system() -> None:
    st.markdown(
        """
        <style>
        :root {
            --marine: #102a43;
            --cornflower: #6495ed;
            --cornflower-deep: #4778d0;
            --pink: #ff38d1;
            --paper: #f7f9ff;
            --white: #ffffff;
            --muted: #5e7085;
            --line: #e0e8f3;
        }

        .stApp {
            background:
                radial-gradient(ellipse at 92% 2%, #dfe9ff 0, transparent 27rem),
                var(--paper);
            color: var(--marine);
        }
        [data-testid="stHeader"] {
            background: rgba(247, 249, 255, .84);
        }
        [data-testid="stMainBlockContainer"] {
            max-width: 1240px;
            padding-top: 2.5rem;
            padding-bottom: 4rem;
        }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #fff 0%, #f1f5ff 100%);
            border-right: 1px solid var(--line);
        }
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
            color: var(--muted);
        }
        h1, h2, h3, h4, p, label, [data-testid="stWidgetLabel"] p {
            color: var(--marine);
        }
        h1 {
            font-size: clamp(2.15rem, 4vw, 3.35rem) !important;
            font-weight: 760 !important;
            letter-spacing: -.045em !important;
        }
        h2, h3 {
            letter-spacing: -.025em;
        }
        p, [data-testid="stCaptionContainer"] {
            line-height: 1.65;
        }
        [data-testid="stCaptionContainer"] {
            color: var(--muted);
        }
        [data-testid="stVerticalBlockBorderWrapper"] {
            background: rgba(255, 255, 255, .92);
            border-color: var(--line) !important;
            border-radius: 20px !important;
            box-shadow: 0 12px 32px rgba(16, 42, 67, .045);
        }
        [data-testid="stTextInput"] input,
        [data-testid="stTextArea"] textarea {
            background: var(--white);
            border-color: #cfdaea;
            border-radius: 12px;
            color: var(--marine);
        }
        [data-testid="stTextArea"] textarea {
            font-family: inherit;
            font-size: 1rem;
            line-height: 1.5;
        }
        [data-testid="stTextInput"] input:focus,
        [data-testid="stTextArea"] textarea:focus {
            border-color: var(--cornflower);
            box-shadow: 0 0 0 2px rgba(100, 149, 237, .18);
        }
        [data-testid="stTextInput"] [data-baseweb="input"]:focus-within,
        [data-testid="stTextInput"] [data-baseweb="base-input"]:focus-within,
        [data-testid="stTextArea"] [data-baseweb="textarea"]:focus-within {
            border-color: var(--pink) !important;
            box-shadow: 0 0 0 1px var(--pink) !important;
        }
        [data-testid="stTextInput"] input:focus,
        [data-testid="stTextArea"] textarea:focus {
            border-color: var(--pink) !important;
            box-shadow: none !important;
            caret-color: var(--pink);
        }
        [data-testid="stTextInput"] input:disabled {
            -webkit-text-fill-color: var(--marine) !important;
            color: var(--marine) !important;
            font-weight: 600;
            opacity: 1 !important;
            background: #eef3fb !important;
        }
        [data-testid="stTextInput"]:has(input:disabled) {
            opacity: 1 !important;
        }
        [data-testid="stForm"] {
            background: rgba(255, 255, 255, .75);
            border: 1px solid var(--line);
            border-radius: 20px;
            padding: 1.25rem 1.4rem;
        }
        .stButton button, .stFormSubmitButton button, .stPageLink a {
            border-radius: 999px;
            font-weight: 650;
            transition: transform .16s ease, box-shadow .16s ease;
        }
        .stButton button:hover, .stFormSubmitButton button:hover,
        .stPageLink a:hover {
            box-shadow: 0 8px 22px rgba(71, 120, 208, .2);
            transform: translateY(-1px);
        }
        .stButton button[kind="primary"],
        .stFormSubmitButton button[kind="primary"] {
            background: var(--marine);
            border-color: var(--marine);
            color: var(--white);
        }
        .stButton button[kind="primary"]:hover,
        .stFormSubmitButton button[kind="primary"]:hover {
            background: var(--cornflower-deep);
            border-color: var(--cornflower-deep);
        }
        [class*="st-key-"][class*="follow_dialog"] button {
            background: var(--pink) !important;
            border-color: var(--pink) !important;
            color: #fff !important;
        }
        [class*="st-key-"][class*="follow_dialog"] button p {
            color: #fff !important;
        }
        [class*="st-key-"][class*="follow_dialog"] button:hover {
            background: #e01fb9 !important;
            border-color: #e01fb9 !important;
            box-shadow: 0 8px 22px rgba(255, 56, 209, .35);
        }
        .st-key-free_signup button {
            background: var(--pink) !important;
            border-color: var(--pink) !important;
            box-shadow: 0 0 18px rgba(255, 56, 209, .4);
            color: var(--marine) !important;
            font-size: 1.1rem;
            font-weight: 750;
            min-height: 3.5rem;
            min-width: 15rem;
            padding: .85rem 2rem;
        }
        .st-key-free_signup button:hover {
            background: #ff72df !important;
            border-color: #ff72df !important;
            box-shadow: 0 0 24px rgba(255, 56, 209, .6);
        }
        .st-key-run_guided_analysis button,
        .st-key-run_full_analysis button,
        .st-key-signup_continue button,
        .st-key-download_democracy_index button,
        .st-key-download_marked_up_comparison button,
        .st-key-download_documents button,
        .st-key-download_bill_information button,
        .st-key-download_guided_analysis button,
        .st-key-download_hansard_summary button,
        .st-key-download_public_discussion button {
            background: var(--pink) !important;
            border-color: var(--pink) !important;
            color: #fff !important;
        }
        .st-key-download_documents button:disabled {
            opacity: .55;
        }
        .st-key-run_guided_analysis button p,
        .st-key-run_full_analysis button p,
        .st-key-signup_continue button p,
        .st-key-download_democracy_index button p,
        .st-key-download_marked_up_comparison button p,
        .st-key-download_documents button p,
        .st-key-download_bill_information button p,
        .st-key-download_guided_analysis button p,
        .st-key-download_hansard_summary button p,
        .st-key-download_public_discussion button p {
            color: #fff !important;
        }
        .st-key-run_guided_analysis button:hover,
        .st-key-run_full_analysis button:hover,
        .st-key-signup_continue button:hover,
        .st-key-download_democracy_index button:hover,
        .st-key-download_marked_up_comparison button:hover,
        .st-key-download_documents button:hover,
        .st-key-download_bill_information button:hover,
        .st-key-download_guided_analysis button:hover,
        .st-key-download_hansard_summary button:hover,
        .st-key-download_public_discussion button:hover {
            background: #e01fb9 !important;
            border-color: #e01fb9 !important;
            box-shadow: 0 8px 22px rgba(255, 56, 209, .35);
        }
        .st-key-run_guided_analysis button:focus,
        .st-key-run_guided_analysis button:active,
        .st-key-run_guided_analysis button:focus:not(:active),
        .st-key-run_full_analysis button:focus,
        .st-key-run_full_analysis button:active,
        .st-key-run_full_analysis button:focus:not(:active),
        .st-key-signup_continue button:focus,
        .st-key-signup_continue button:active,
        .st-key-signup_continue button:focus:not(:active),
        .st-key-download_democracy_index button:focus,
        .st-key-download_democracy_index button:active,
        .st-key-download_democracy_index button:focus:not(:active),
        .st-key-download_marked_up_comparison button:focus,
        .st-key-download_marked_up_comparison button:active,
        .st-key-download_marked_up_comparison button:focus:not(:active),
        .st-key-download_documents button:focus,
        .st-key-download_documents button:active,
        .st-key-download_documents button:focus:not(:active),
        .st-key-download_bill_information button:focus,
        .st-key-download_bill_information button:active,
        .st-key-download_bill_information button:focus:not(:active),
        .st-key-download_guided_analysis button:focus,
        .st-key-download_guided_analysis button:active,
        .st-key-download_guided_analysis button:focus:not(:active),
        .st-key-download_hansard_summary button:focus,
        .st-key-download_hansard_summary button:active,
        .st-key-download_hansard_summary button:focus:not(:active),
        .st-key-download_public_discussion button:focus,
        .st-key-download_public_discussion button:active,
        .st-key-download_public_discussion button:focus:not(:active) {
            background: #e01fb9 !important;
            border-color: #e01fb9 !important;
            color: #fff !important;
            box-shadow: none;
        }
        .dd-hero-copy a.dd-follow-btn {
            display: inline-block;
            margin-top: 1.1rem;
            padding: .6rem 1.4rem;
            background: var(--pink);
            border: 1px solid var(--pink);
            border-radius: 999px;
            color: #fff !important;
            font-weight: 650;
            text-decoration: none !important;
            transition: transform .16s ease, box-shadow .16s ease;
        }
        .dd-hero-copy a.dd-follow-btn:hover {
            background: #e01fb9;
            border-color: #e01fb9;
            box-shadow: 0 8px 22px rgba(255, 56, 209, .35);
            transform: translateY(-1px);
        }
        .stPageLink a {
            background: #dbeafe !important;
            border: 1px solid #93c5fd !important;
            color: var(--marine) !important;
        }
        .stPageLink a * {
            color: var(--marine) !important;
        }
        .stPageLink a:hover {
            background: #bfdbfe !important;
            border-color: #60a5fa !important;
        }
        [data-testid="stFileUploader"] section {
            background: #f5f8ff;
            border-color: #b9cbed;
            border-radius: 16px;
        }
        [data-testid="stAlert"] {
            border-radius: 14px;
        }
        hr {
            border-color: var(--line);
        }
        .dd-hero {
            position: relative;
            overflow: hidden;
            padding: clamp(2.2rem, 6vw, 4rem) clamp(2rem, 6vw, 4.8rem);
            border: 1px solid #dce7fb;
            border-radius: 32px;
            background:
                radial-gradient(circle at 90% 18%, rgba(255, 56, 209, .22), transparent 15rem),
                linear-gradient(125deg, #fff 10%, #eef4ff 68%, #e1ebff 100%);
            box-shadow: 0 24px 70px rgba(16, 42, 67, .09);
        }
        .dd-hero-copy {
            margin-top: 2rem;
            padding: clamp(1.5rem, 4vw, 2.5rem) clamp(1.5rem, 5vw, 3.5rem);
            border: 1px solid #dce7fb;
            border-radius: 24px;
            background:
                radial-gradient(ellipse at 100% 0, rgba(219, 234, 254, .65), transparent 55%),
                rgba(255, 255, 255, .88);
            box-shadow: 0 14px 38px rgba(16, 42, 67, .055);
        }
        .dd-hero-copy p + p {
            border-top: 1px solid var(--line);
            margin-top: 1.25rem;
            padding-top: 1.1rem;
        }
        .dd-eyebrow {
            display: inline-flex;
            align-items: center;
            gap: .55rem;
            margin-bottom: 1.2rem;
            padding: .45rem .85rem;
            border: 1px solid #f5b0e8;
            border-radius: 999px;
            background: #fff;
            color: var(--marine);
            font-size: .76rem;
            font-weight: 750;
            letter-spacing: .12em;
            text-transform: uppercase;
        }
        .dd-eyebrow span {
            width: .55rem;
            height: .55rem;
            border-radius: 50%;
            background: var(--pink);
            box-shadow: 0 0 12px rgba(255, 56, 209, .7);
        }
        .dd-hero h1 {
            max-width: 850px;
            margin: 0 0 1rem;
            color: var(--marine);
            font-size: clamp(2.8rem, 6vw, 5.3rem) !important;
            line-height: .99;
            letter-spacing: -.065em !important;
        }
        .dd-hero h1 em {
            color: var(--cornflower-deep);
            font-style: normal;
        }
        .dd-hero p {
            max-width: 760px;
            margin: 0;
            color: #496177;
            font-size: clamp(1.05rem, 1.8vw, 1.25rem);
            line-height: 1.7;
        }
        .dd-hero-copy .dd-site-link {
            margin-top: 1rem;
            font-size: .95rem;
            font-weight: 700;
        }
        .dd-site-link a {
            color: var(--cornflower-deep);
            text-decoration-color: var(--pink);
            text-decoration-thickness: 2px;
            text-underline-offset: 4px;
        }
        .dd-site-link a:hover {
            color: var(--marine);
        }
        .dd-section-label {
            margin: 2.5rem 0 .65rem;
            padding-left: .85rem;
            border-left: 3px solid var(--pink);
            color: var(--cornflower-deep);
            font-size: .76rem;
            font-weight: 750;
            letter-spacing: .14em;
            text-transform: uppercase;
        }
        .dd-card-number {
            display: inline-grid;
            width: 2.6rem;
            height: 2.6rem;
            place-items: center;
            margin-bottom: .7rem;
            border-radius: 13px;
            background: #e9f0ff;
            color: var(--cornflower-deep);
            font-weight: 800;
        }
        .dd-index-note {
            padding: 1.1rem 1.35rem;
            border-left: 4px solid var(--pink);
            border-radius: 0 14px 14px 0;
            background: #fff;
            color: #496177;
            line-height: 1.6;
        }
        .dd-footer {
            display: flex;
            justify-content: space-between;
            gap: 1rem;
            margin-top: 2.5rem;
            padding-top: 1.1rem;
            border-top: 1px solid var(--line);
            color: var(--muted);
            font-size: .82rem;
        }
        .dd-footer span:first-child {
            color: var(--marine);
            font-weight: 750;
        }
        .dd-social-links {
            display: flex;
            gap: 1rem;
        }
        .dd-social-links a {
            color: var(--cornflower-deep);
            font-weight: 650;
            text-decoration-color: var(--pink);
            text-underline-offset: 4px;
        }
        .dd-social-links a:hover {
            color: var(--marine);
        }
        @media (max-width: 700px) {
            [data-testid="stMainBlockContainer"] {
                padding: 1.2rem 1rem 2.5rem;
            }
            .dd-hero { border-radius: 23px; }
            .dd-hero-copy { border-radius: 19px; }
            [data-testid="stForm"] { padding: 1rem; }
            .dd-footer { flex-direction: column; gap: .35rem; }
        }
        [data-testid="stStatusWidgetRunningManIcon"],
        [data-testid="stStatusWidgetNewYearsIcon"] { display: none !important; }
        [data-testid="stStatusWidgetRunningIcon"] {
            border: 2px solid currentColor;
            border-radius: 50%;
            box-sizing: border-box;
            height: 1.5rem;
            position: relative;
            width: 1.5rem;
        }
        [data-testid="stStatusWidgetRunningIcon"]::before,
        [data-testid="stStatusWidgetRunningIcon"]::after {
            background: currentColor;
            border-radius: 1px;
            content: "";
            left: calc(50% - 1px);
            position: absolute;
            transform-origin: 50% 100%;
            width: 2px;
        }
        [data-testid="stStatusWidgetRunningIcon"]::before {
            animation: dd-tick 1s steps(2, jump-none) infinite;
            bottom: 50%;
            height: 38%;
        }
        [data-testid="stStatusWidgetRunningIcon"]::after {
            animation: dd-tick 12s steps(12, jump-none) infinite;
            bottom: 50%;
            height: 28%;
        }
        @keyframes dd-tick { to { transform: rotate(360deg); } }
        </style>
        """,
        unsafe_allow_html=True,
    )
