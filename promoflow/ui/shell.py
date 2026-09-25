"""App shell: page registry (role-based) and the black sidebar with the dossier navigator."""
import streamlit as st

from promoflow.db.enums import RoleName
from promoflow.ui import theme
from promoflow.ui.auth import ROLE_LABELS, CurrentUser, logout
from promoflow.ui.views import dashboard, section0

# Dossier sections not built yet: shown in the navigator so applicants see the whole journey.
UPCOMING_SECTIONS = [
    ("1", "Application form"), ("2", "Curriculum vitae"), ("3", "Degrees & equivalency"),
    ("4", "Ranks & experience"), ("5", "Research"), ("6", "Teaching & advising"),
    ("7", "University & community service"), ("8", "Recommendation letters"), ("9", "Conditions form"),
    ("10", "Cover letter"), ("11", "Review & submit"),
]


def pages_for(user: CurrentUser) -> dict[str, st.Page]:
    pages = {"home": st.Page(dashboard.render, title="Dashboard", icon=":material/space_dashboard:",
                             url_path="home", default=True)}
    if user.has(RoleName.APPLICANT):
        pages["section0"] = st.Page(section0.render, title="Applicant details", icon=":material/badge:",
                                    url_path="applicant-details")
    return pages


def sidebar(user: CurrentUser, pages: dict[str, st.Page]) -> None:
    with st.sidebar:
        theme.html(f'<div class="pf-brand">{theme.logo(34)}<div><b>PromoFlow</b>'
                   '<small>FACULTY PROMOTION REVIEW</small></div></div>')
        st.page_link(pages["home"], label="Dashboard", icon=":material/space_dashboard:")

        if user.has(RoleName.APPLICANT):
            theme.html('<div class="pf-navlabel">My promotion</div>')
            st.page_link(pages["section0"], label="0 · Applicant details", icon=":material/badge:")
            theme.html("".join(
                f'<div class="pf-soon"><span>{n} · {theme.esc(t)}</span><em>soon</em></div>'
                for n, t in UPCOMING_SECTIONS))
        if user.has(RoleName.HOD, RoleName.DEAN, RoleName.CHANCELLOR):
            theme.html('<div class="pf-navlabel">Reviews</div>'
                       '<div class="pf-soon"><span>Cases awaiting my decision</span><em>soon</em></div>')
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
