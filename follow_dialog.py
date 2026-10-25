from urllib.parse import urlencode

import streamlit as st


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
