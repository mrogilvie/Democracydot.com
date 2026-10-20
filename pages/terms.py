from pathlib import Path

import streamlit as st


st.markdown(Path(__file__).resolve().parent.parent.joinpath("TERMS.md").read_text(encoding="utf-8"))
