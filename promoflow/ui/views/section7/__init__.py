"""Section 7 – University & Community Service (spec chapter 11): one tab per Appendix F evidence sub-section."""
import streamlit as st

from promoflow.db.session import session_scope
from promoflow.dossier import section7 as s7
from promoflow.dossier.section0 import EDITABLE
from promoflow.ui import cache, theme
from promoflow.ui.views.section7 import (
    admin_positions_tab, committees_tab, community_tab, policy_tab, trainings_tab, workshops_tab,
)


def render() -> None:
    user = st.session_state["current_user"]
    ctx = cache.load_cached(f"pfc:s7:{user.id}", lambda s: s7.load(s, user.id))

    theme.html("""
    <div class="pf-hero"><div class="crumb">MY PROMOTION · SECTION 7 OF 11</div>
    <h1>University &amp; Community Service</h1>
    <p>Evidence for the five Appendix F rubric items. Community activities have no dedicated line on the
    form — the reviewer maps them to the closest item.</p></div>""")

    if ctx.case_id is None:
        st.info("Save Section 0 (Applicant Details & Promotion Track) first — it creates your draft application.",
                icon=":material/info:")
        return

    editable = ctx.status in EDITABLE
    if flash := st.session_state.pop("s7_flash", None):
        st.success(flash, icon=":material/check_circle:")
    if not editable:
        st.info("This application has been submitted, so Section 7 is read-only.", icon=":material/lock:")

    tabs = st.tabs(["7A-1 · Committees", "7A-2 · Admin positions", "7A-3 · Workshops", "7A-4 · Trainings",
                   "7A-5 · Policy contributions", "7B · Community service"])
    with tabs[0]:
        committees_tab.render(ctx.committees, editable)
    with tabs[1]:
        admin_positions_tab.render(ctx.admin_positions, editable)
    with tabs[2]:
        workshops_tab.render(ctx.workshops, editable)
    with tabs[3]:
        trainings_tab.render(ctx.trainings, editable)
    with tabs[4]:
        policy_tab.render(ctx.policy_contributions, editable)
    with tabs[5]:
        community_tab.render(ctx.community, ctx.case_id, editable)
