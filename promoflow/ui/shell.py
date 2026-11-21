"""App shell: page registry (role-based) and the black sidebar with the dossier navigator."""
import streamlit as st

from promoflow.db.enums import RoleName
from promoflow.ui import theme
from promoflow.ui.auth import ROLE_LABELS, CurrentUser, logout
from promoflow.ui.views import (
    about, dashboard, referees, reviews, section0, section1, section2, section3, section4, section5, section6, section7, section8,
    section9, section10, section11,
)

# Every applicant-facing dossier section, in order. This is the whole dossier (§0-11).
SECTIONS = [
    ("0", "Applicant details", ":material/badge:", "applicant-details", section0.render),
    ("1", "Application form", ":material/description:", "application-form", section1.render),
    ("2", "Curriculum vitae", ":material/contact_page:", "curriculum-vitae", section2.render),
    ("3", "Degrees & equivalency", ":material/school:", "degrees", section3.render),
    ("4", "Ranks & experience", ":material/timeline:", "ranks", section4.render),
    ("5", "Research", ":material/science:", "research", section5.render),
    ("6", "Teaching & advising", ":material/menu_book:", "teaching", section6.render),
    ("7", "University & community service", ":material/volunteer_activism:", "service", section7.render),
    ("8", "Recommendation letters", ":material/mail:", "recommendation-letters", section8.render),
    ("9", "Conditions form", ":material/rule:", "conditions-form", section9.render),
    ("10", "Cover letter", ":material/draft:", "cover-letter", section10.render),
    ("11", "Review & submit", ":material/send:", "review-submit", section11.render),
]


def pages_for(user: CurrentUser) -> dict[str, st.Page]:
    # "How Tarqiya works" is the first page everyone lands on; the dashboard is one click away.
    pages = {"about": st.Page(about.render, title="How Tarqiya works", icon=":material/lightbulb:",
                              url_path="about", default=True),
             "home": st.Page(dashboard.render, title="Dashboard", icon=":material/space_dashboard:", url_path="home")}
    if user.has(RoleName.APPLICANT):
        for code, title, icon, url_path, render in SECTIONS:
            pages[f"section{code}"] = st.Page(render, title=title, icon=icon, url_path=url_path)
    if user.has(RoleName.HOD, RoleName.DEAN):
        pages["reviews"] = st.Page(reviews.render, title="Reviews", icon=":material/fact_check:", url_path="reviews")
    if user.has(RoleName.CHANCELLOR):
        pages["referees"] = st.Page(referees.render, title="Referee selection", icon=":material/how_to_reg:", url_path="referees")
    return pages


def sidebar(user: CurrentUser, pages: dict[str, st.Page]) -> None:
    with st.sidebar:
        theme.html(f'<div class="pf-uos" style="display:flex;justify-content:center;width:100%;margin:4px 0 14px">{theme.uos_logo(80, light=True)}</div>')   # inline, so it does not depend on the stylesheet being reloaded
        theme.html(f'<div class="pf-brand">{theme.logo(34)}<div><b>Tarqiya</b>'
                   '<small>FACULTY PROMOTION REVIEW</small></div></div>')
        st.page_link(pages["about"], label="How Tarqiya works", icon=":material/lightbulb:")
        st.page_link(pages["home"], label="Dashboard", icon=":material/space_dashboard:")

        if user.has(RoleName.APPLICANT):
            theme.html('<div class="pf-navlabel">My promotion</div>')
            for code, title, icon, _url_path, _render in SECTIONS:
                st.page_link(pages[f"section{code}"], label=f"{code} · {title}", icon=icon)
        if user.has(RoleName.HOD, RoleName.DEAN, RoleName.CHANCELLOR):
            theme.html('<div class="pf-navlabel">Reviews</div>')
            if "reviews" in pages:
                st.page_link(pages["reviews"], label="Awaiting my decision", icon=":material/fact_check:")
            if "referees" in pages:
                st.page_link(pages["referees"], label="Referee selection", icon=":material/how_to_reg:")
        if user.has(RoleName.ADMIN):
            theme.html('<div class="pf-navlabel">Admin</div>'
                       '<div class="pf-soon"><span>Criteria & journal rankings</span><em>soon</em></div>'
                       '<div class="pf-soon"><span>Users & roles</span><em>soon</em></div>'
                       '<div class="pf-soon"><span>Audit log</span><em>soon</em></div>')

        st.divider()
        roles = " · ".join(ROLE_LABELS[g.role] for g in user.roles) or "No role assigned"
        theme.html(f'<div class="pf-user"><div class="pf-av">{theme.esc(theme.initials(user.full_name))}</div>'
                   f'<div><b>{theme.esc(user.full_name)}</b><span>{theme.esc(roles)}</span></div></div>')
        if st.button("Log out", icon=":material/logout:", use_container_width=True, key="logout"):
            logout()
