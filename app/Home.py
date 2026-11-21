"""Tarqiya entry point:  streamlit run app/Home.py"""
import streamlit as st

st.set_page_config(page_title="Tarqiya", page_icon=":material/school:", layout="wide",
                   initial_sidebar_state="expanded")

from promoflow.ui import assistant_box, shell, theme  # noqa: E402  (set_page_config must run first)
from promoflow.ui.auth import require_login  # noqa: E402

theme.inject()
referee_token = st.query_params.get("referee")           # a referee opened the Accept / Decline link in an email: no login
if referee_token:
    from promoflow.ui import referee_reply
    referee_reply.render(referee_token)
    st.stop()
user = require_login()
st.session_state["current_user"] = user

pages = shell.pages_for(user)
st.session_state["pf_pages"] = pages
navigation = st.navigation(list(pages.values()), position="hidden")
shell.sidebar(user, pages)
assistant_box.render(user)
navigation.run()
