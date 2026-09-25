"""PromoFlow entry point:  streamlit run app/Home.py"""
import streamlit as st

from promoflow.db.enums import RoleName
from promoflow.ui.auth import require_login

st.set_page_config(page_title="PromoFlow", page_icon=":material/school:", layout="wide")

user = require_login()

st.title(f"Welcome, {user.full_name}")

# Placeholder dashboard: each role gets its own zone once the pages are built.
cols = st.columns(3)
if user.has(RoleName.APPLICANT):
    cols[0].subheader("My Promotion")
    cols[0].write("Start or continue your promotion dossier.")
if user.has(RoleName.HOD, RoleName.DEAN, RoleName.CHANCELLOR):
    cols[1].subheader("Reviews")
    cols[1].write("Cases waiting for your decision.")
if user.has(RoleName.ADMIN):
    cols[2].subheader("Admin")
    cols[2].write("Criteria, journal rankings, users & roles, audit log.")
