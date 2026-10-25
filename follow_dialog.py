import sqlite3
from urllib.parse import urlencode

import streamlit as st

from comment_store import get_signup_for_device


DEVICE_COOKIE = "dd_device"
FACEBOOK_PAGE_URL = "https://www.facebook.com/madeleineogilvie.com.au/"
FACEBOOK_FOLLOW_WIDGET_URL = (
    "https://www.facebook.com/plugins/page.php?"
    + urlencode(
        {
            "href": FACEBOOK_PAGE_URL,
            "tabs": "",
            "width": 340,
            "height": 130,
            "small_header": "true",
            "adapt_container_width": "true",
            "hide_cover": "false",
            "show_facepile": "false",
        }
    )
)


@st.dialog("Follow Madeleine Ogilvie MP")
def show_follow_dialog() -> None:
    st.write(
        "Please follow Madeleine Ogilvie MP on Facebook, then tick the "
        "confirmation box on the Democracy Index page to unlock downloads."
    )
    st.iframe(FACEBOOK_FOLLOW_WIDGET_URL, height=140)
    st.link_button("Open the Facebook page", FACEBOOK_PAGE_URL)


def restore_signup_from_cookie() -> None:
    """Recognise a device that already gave its name and mobile number."""
    if st.session_state.get("signup_saved"):
        return
    device_cookie = st.context.cookies.get(DEVICE_COOKIE)
    if not isinstance(device_cookie, str) or not device_cookie:
        return
    try:
        signup = get_signup_for_device(device_cookie)
    except (OSError, sqlite3.Error):
        return
    if signup:
        st.session_state["signup_saved"] = True
        st.session_state["signup_device_token"] = device_cookie
