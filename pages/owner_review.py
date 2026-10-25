import hmac
from datetime import datetime

import streamlit as st

from comment_store import (
    STORE_ERRORS,
    get_comments,
    get_owner_password,
    get_signups,
)


st.title("Owner review")
st.write("Review Billbow comments and contact details submitted for updates.")

owner_password = get_owner_password()
if not owner_password:
    st.error(
        "Owner review is not configured. Set DEMOCRACYDOT_OWNER_PASSWORD in the "
        "project .env file or Streamlit secrets, then restart the app."
    )
    st.stop()

if not st.session_state.get("owner_authenticated", False):
    with st.form("owner_login_form"):
        password = st.text_input("Owner password", type="password")
        login = st.form_submit_button("Sign in")
    if login:
        if hmac.compare_digest(
            password.encode("utf-8"), owner_password.encode("utf-8")
        ):
            st.session_state["owner_authenticated"] = True
            st.rerun()
        st.error("Incorrect password.")
    st.stop()

if st.button("Sign out"):
    st.session_state.pop("owner_authenticated", None)
    st.rerun()

try:
    comments = get_comments()
    signups = get_signups()
except STORE_ERRORS as error:
    st.error(f"Could not load saved review data: {error}")
    st.stop()

st.subheader("Update sign-ups")
if not signups:
    st.info("There are no update sign-ups yet.")
else:
    st.caption(
        f"{len(signups)} person/people have opted in to updates and announcements."
    )
    st.dataframe(signups, hide_index=True, use_container_width=True)

st.subheader("Billbow comments")
if not comments:
    st.info("There are no comments to review yet.")
else:
    st.caption(f"{len(comments)} comment(s), newest first")
    comments_by_bill = {}
    for item in comments:
        title = item["bill_title"] or "Bill not specified"
        bill_key = " ".join(title.split()).casefold()
        comments_by_bill.setdefault(bill_key, (title, []))[1].append(item)

    for title, bill_comments in comments_by_bill.values():
        st.subheader(title)
        for item in bill_comments:
            submitted_at = datetime.fromisoformat(item["submitted_at"]).strftime(
                "%Y-%m-%d %H:%M UTC"
            )
            with st.container(border=True):
                st.caption(submitted_at)
                st.write(item["comment"])
