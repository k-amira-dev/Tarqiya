"""The first page: "How PromoFlow works". A plain-language guide for anyone new to the promotion process or the system
(an applicant, a Head of Department or a Dean who has just joined). No technical detail on purpose."""
import streamlit as st

from promoflow.db.enums import RoleName
from promoflow.ui import theme

# (step title, who does it, what happens)
STEPS = [
    ("Prepare", "Applicant", "Fills in the dossier, Sections 0 to 10, and attaches the evidence for each claim."),
    ("Submit", "Applicant", "Applications are accepted only in the first week of January, April and October."),
    ("Evaluate", "PromoFlow", "Checks eligibility and prepares an evaluation of research, teaching and service "
                              "against the policy."),
    ("Head of Department", "Reviewer", "Reads the report, then approves the case or returns it with comments."),
    ("Dean", "Reviewer", "Reads the report and the Head's decision, then approves or returns the case."),
    ("Referees", "Chancellor", "Chooses external referees from a shortlist. Their reports complete the case."),
]

EVALUATIONS = [
    ("Eligibility check", "Are the basic conditions met?",
     "Time in the current rank, years at the university, the submission window, a doctorate, and the required "
     "documents. A condition that is not met stops the application here."),
    ("Research evaluation", "Is there enough qualifying research?",
     "Counts papers by author role, publication status and journal class. Being built."),
    ("Teaching evaluation", "How strong is the teaching and advising record?",
     "Scored out of 30 using Appendix E of the policy. Pass mark: 24."),
    ("Service evaluation", "How strong is the university and community service?",
     "Scored out of 10 using Appendix F of the policy. Pass mark: 8."),
]

ROLE_INTRO = {
    RoleName.APPLICANT: "You are an applicant. Start with Section 0 and work down to Section 11. Everything you "
                        "enter is saved, and you can come back at any time before you submit.",
    RoleName.HOD: "You review applicants from your department. When a case reaches you, open Reviews, read the "
                  "report, and approve it or return it with a comment.",
    RoleName.DEAN: "You review applicants from your college after the Head of Department. Open Reviews to see the "
                   "report and the Head's decision, then approve or return the case.",
}


def _card(key: str, number: str, title: str, subtitle: str, body: str) -> None:
    with st.container(key=f"card_{key}"):
        theme.card_header(number, title, subtitle)
        theme.html(body)


def render() -> None:
    user = st.session_state["current_user"]
    theme.html("""
    <div class="pf-hero"><div class="crumb">START HERE</div>
    <h1>How PromoFlow works</h1>
    <p>A short guide to the academic promotion process and to the system you will use. PromoFlow helps people
    prepare, check and review a promotion. It never decides one.</p></div>""")

    intro = next((text for role, text in ROLE_INTRO.items() if user.has(role)), None)
    if intro:
        theme.html(f'<div class="pf-tile hi" style="min-height:0;margin-bottom:18px"><h4>Your role</h4>'
                   f"<p>{theme.esc(intro)}</p></div>")

    steps = "".join(f'<div class="pf-step"><div class="n">{i}</div><h4>{theme.esc(t)}</h4>'
                    f'<div class="who">{theme.esc(who)}</div><p>{theme.esc(text)}</p></div>'
                    for i, (t, who, text) in enumerate(STEPS, 1))
    _card("about_flow", "1", "The promotion in six steps", "From preparing a dossier to the external referees.",
          f'<div class="pf-flow">{steps}</div>'
          '<div class="pf-note">A case can be sent back to the applicant by the Head of Department or the Dean. '
          "The applicant corrects it and submits again, and the checks run once more.</div>")

    st.write("")
    ev = "".join(f"<tr><td><b>{theme.esc(n)}</b></td><td>{theme.esc(q)}</td><td>{theme.esc(d)}</td></tr>"
                 for n, q, d in EVALUATIONS)
    _card("about_evals", "2", "The four evaluations", "What the report for each case is made of.",
          f'<table class="pf-tbl"><thead><tr><th>Evaluation</th><th>Question it answers</th><th>How it works</th></tr>'
          f"</thead><tbody>{ev}</tbody></table>")

    st.write("")
    pages = st.session_state.get("pf_pages", {})
    cols = st.columns([2, 2, 3])
    if user.has(RoleName.APPLICANT) and "section0" in pages and cols[0].button(
            "Start with Section 0  →", type="primary", key="about_start"):
        st.switch_page(pages["section0"])
    if user.has(RoleName.HOD, RoleName.DEAN) and "reviews" in pages and cols[0].button(
            "Open my reviews  →", type="primary", key="about_reviews"):
        st.switch_page(pages["reviews"])
    if cols[1].button("Go to the dashboard", key="about_dash"):
        st.switch_page(pages["home"])
