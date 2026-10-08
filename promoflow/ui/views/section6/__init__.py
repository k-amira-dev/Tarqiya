"""Section 6 – Teaching & Academic Advising (spec chapter 10): one tab per Appendix E evidence sub-section."""
import streamlit as st

from promoflow.dossier import section6 as s6
from promoflow.dossier.section0 import EDITABLE
from promoflow.dossier.section6.common import course_options_from
from promoflow.ui import cache, theme
from promoflow.ui.views.section6 import (
    advising_tab, course_files_tab, courses_tab, curriculum_tab, development_tab, innovation_tab,
    peer_observations_tab, satisfaction_tab, supervision_tab,
)


def render() -> None:
    user = st.session_state["current_user"]
    ctx = cache.load_cached(f"pfc:s6:{user.id}", lambda s: s6.load(s, user.id))
    courses_for_links = course_options_from(ctx.courses)

    theme.html("""
    <div class="pf-hero"><div class="crumb">MY PROMOTION · SECTION 6 OF 11</div>
    <h1>Teaching &amp; Academic Advising</h1>
    <p>Evidence for the ten Appendix E rubric items. Each tab below feeds one or more items.</p></div>""")

    if ctx.case_id is None:
        st.info("Save Section 0 (Applicant Details & Promotion Track) first — it creates your draft application.",
                icon=":material/info:")
        return

    editable = ctx.status in EDITABLE
    if flash := st.session_state.pop("s6_flash", None):
        st.success(flash, icon=":material/check_circle:")
    if not editable:
        st.info("This application has been submitted, so Section 6 is read-only.", icon=":material/lock:")

    tabs = st.tabs(["6A · Courses taught", "6B · Peer observations", "6C · Student satisfaction",
                   "6D · Curriculum development", "6E · Academic advising", "6F · Course files",
                   "6G · Teaching innovation", "6H · Graduate supervision", "6I · Development activities"])
    with tabs[0]:
        courses_tab.render(ctx.courses, ctx.registrar_report, ctx.case_id, editable)
    with tabs[1]:
        peer_observations_tab.render(ctx.peer_observations, courses_for_links, editable)
    with tabs[2]:
        satisfaction_tab.render(ctx.satisfaction, ctx.courses, courses_for_links, editable)
    with tabs[3]:
        curriculum_tab.render(ctx.curriculum, editable)
    with tabs[4]:
        advising_tab.render(ctx.advising, editable)
    with tabs[5]:
        course_files_tab.render(ctx.course_files, courses_for_links, editable)
    with tabs[6]:
        innovation_tab.render(ctx.innovation, courses_for_links, editable)
    with tabs[7]:
        supervision_tab.render(ctx.supervision, editable)
    with tabs[8]:
        development_tab.render(ctx.development, editable)
