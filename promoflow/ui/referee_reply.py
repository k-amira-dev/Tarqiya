"""The page a referee reaches from the Accept / Decline link in an email. No login: the link itself is the proof (see workflow/referee_links.py).
Nothing is recorded until the referee presses Confirm. After accepting, the same page shows the papers to grade; the applicant is never named."""
import streamlit as st

from promoflow.workflow import outreach

MESSAGES = {
    "invalid": "This link is not valid. Please use the link exactly as it appears in the email, or contact the Office of the Chancellor.",
    "expired": "This link has expired. Please contact the Office of the Chancellor if you still wish to answer.",
    "closed": "This request is closed and no answer is needed. Thank you for your time.",
    "reported": "Your report has been received. Thank you for your time.",
}


def render(token: str) -> None:
    st.markdown("<style>[data-testid='stSidebar'],[data-testid='stSidebarCollapsedControl']{display:none}</style>", unsafe_allow_html=True)
    left, middle, right = st.columns([1, 3, 1])
    with middle:
        st.markdown("### Tarqiya  |  Promotion review request")
        if "referee_report_sent" in st.session_state:
            st.success("Your report has been received. Thank you for your time.")
            return
        view = _view(token)
        if view.state in MESSAGES:
            st.warning(MESSAGES[view.state])
            return
        st.write(f"**Reference:** {view.case_ref}")
        st.write(f"**Application for promotion to** {view.target_rank} in {view.field}")
        if view.state == "answered":
            if view.answer == "accepted":
                st.success("Your answer has been recorded: you accepted this request. Thank you.")
                _grading_form(token)
            else:
                st.success("Your answer has been recorded: you declined this request. Thank you.")
            return
        accepting = view.action == "accept"
        st.write("You are about to **accept** this request to review the applicant's publications and send a short report"
                 + (f" by {view.deadline:%d %B %Y}." if view.deadline else ".") if accepting else
                 "You are about to **decline** this request. We will invite another referee.")
        if st.button("Confirm" if accepting else "Confirm decline", type="primary", key="referee_confirm"):
            st.session_state["referee_answered"] = outreach.answer_link(token)
            st.rerun()


def _grading_form(token: str) -> None:
    review = outreach.review_view(token)
    if review is None:
        return
    st.markdown("#### Papers to review")
    st.write("Please read each paper and give it a grade from 0 to 100. The applicant is not named here; please judge the papers on their "
             "merit. Then write a short recommendation.")
    with st.form("referee_report"):
        grades = {}
        for i, paper in enumerate(review.papers, start=1):
            where = f"{paper['journal']}" + (f", {paper['year']}" if paper["year"] else "")
            st.markdown(f"**{i}. {paper['title']}**  \n{where}" + (f"  \nhttps://doi.org/{paper['doi']}" if paper["doi"] else ""))
            grades[paper["id"]] = st.number_input("Grade (0 to 100)", min_value=0.0, max_value=100.0, value=None, step=1.0,
                                                  key=f"referee_grade_{paper['id']}")
        recommendation = st.text_area("Your recommendation (a few sentences)", max_chars=2000, key="referee_recommendation")
        final = st.checkbox("I confirm that these grades are final.", key="referee_final")
        sent = st.form_submit_button("Send my report", type="primary")
    if sent:
        problems = [] if final else ["Please tick the box to confirm the grades are final."]
        problems += outreach.validate_report({p["id"] for p in review.papers}, grades, recommendation)
        if not problems:
            problems = outreach.submit_report(token, grades, recommendation)
        if problems:
            for problem in problems:
                st.error(problem)
        else:
            st.session_state["referee_report_sent"] = True
            st.rerun()


def _view(token: str):
    """The answer just recorded (shown once after Confirm), else a fresh look at the link."""
    done = st.session_state.pop("referee_answered", None)
    if done is not None:
        return done
    return outreach.inspect_link(token)
