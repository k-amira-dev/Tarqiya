"""Section 5 – Academic Research (spec chapter 9): one tab per entry type, since this is the largest section."""
from datetime import date

import streamlit as st

from promoflow.db.session import session_scope
from promoflow.dossier import section5 as s5
from promoflow.dossier.section0 import EDITABLE
from promoflow.ui import theme
from promoflow.ui.views.section5 import (
    awards_tab, books_tab, classification_tab, conference_tab, creative_tab, funded_tab, papers_tab, patents_tab,
    scopus_tab,
)


def render() -> None:
    user = st.session_state["current_user"]
    today = date.today()
    with session_scope() as s:
        ctx = s5.load(s, user.id, today)

    theme.html("""
    <div class="pf-hero"><div class="crumb">MY PROMOTION · SECTION 5 OF 11</div>
    <h1>Academic Research</h1>
    <p>Each research item is its own entry. Counts, caps and journal classification are computed from what
    you enter here.</p></div>""")

    if ctx.case_id is None:
        st.info("Save Section 0 (Applicant Details & Promotion Track) first — it creates your draft application.",
                icon=":material/info:")
        return

    editable = ctx.status in EDITABLE
    if flash := st.session_state.pop("s5_flash", None):
        st.success(flash, icon=":material/check_circle:")
    if not editable:
        st.info("This application has been submitted, so Section 5 is read-only.", icon=":material/lock:")

    tabs = st.tabs(["5A · Journal papers", "5A-2 · Creative works", "5B · Books", "5C · Conference papers",
                   "5D · Funded projects", "5E · Classification form", "5F · Scopus evidence", "5G · Patents",
                   "5H · Awards"])
    with tabs[0]:
        papers_tab.render(ctx.current_rank_date, ctx.previously_rejected, ctx.papers, editable)
    with tabs[1]:
        creative_tab.render(ctx.creative_works, editable)
    with tabs[2]:
        books_tab.render(ctx.books, editable)
    with tabs[3]:
        conference_tab.render(ctx.conference_papers, editable)
    with tabs[4]:
        funded_tab.render(ctx.funded_projects, editable)
    with tabs[5]:
        classification_tab.render(ctx.papers, ctx.case_id, editable)
    with tabs[6]:
        scopus_tab.render(ctx.scopus, editable)
    with tabs[7]:
        patents_tab.render(ctx.patents, editable)
    with tabs[8]:
        awards_tab.render(ctx.awards, editable)
