"""PromoFlow entry point:  streamlit run app/Home.py"""
import streamlit as st

st.set_page_config(page_title="PromoFlow", page_icon=":material/school:", layout="wide",
                   initial_sidebar_state="expanded")

from promoflow.ui import shell, theme  # noqa: E402  (set_page_config must run first)
from promoflow.ui.auth import require_login  # noqa: E402

theme.inject()
user = require_login()
st.session_state["current_user"] = user

pages = shell.pages_for(user)
st.session_state["pf_pages"] = pages
navigation = st.navigation(list(pages.values()), position="hidden")
shell.sidebar(user, pages)
navigation.run()
