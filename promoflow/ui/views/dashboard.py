"""Landing page after login: role-based overview."""
from datetime import date

import streamlit as st

from promoflow.db.enums import RoleName
from promoflow.dossier import section0 as s0
from promoflow.rules.eligibility import next_submission_window
from promoflow.ui import cache, theme
from promoflow.workflow import referee_result


def _case_status(s, user_id: int) -> str | None:
    case = s0.active_case(s, user_id)
    return case.status.value if case else None


def render() -> None:
    user = st.session_state["current_user"]
    first = (user.full_name or "").replace("Dr.", "").replace("Prof.", "").split()
    today = date.today()
    w = next_submission_window(today)
    theme.html(f"""
    <div class="pf-hero"><div class="crumb">DASHBOARD</div>
    <h1>Welcome back{', ' + theme.esc(first[0]) if first else ''}</h1>
    <p>Tarqiya prepares and checks your promotion dossier against the SCHESR policy. Nothing moves forward
    without a person approving it.</p></div>""")

    if user.has(RoleName.APPLICANT):
        result = cache.load_cached(f"pfc:result:{user.id}", lambda s: referee_result.for_applicant(s, user.id))
        if result is not None:                                     # the Chancellor's Office released the referee result
            title, text = referee_result.message(result)
            (st.success if result.passed else st.warning)(f"**{title}**\n\n{text}", icon=":material/celebration:" if result.passed
                                                          else ":material/info:")
        case_status = cache.load_cached(f"pfc:status:{user.id}", lambda s: _case_status(s, user.id))
        status = case_status.replace("_", " ").capitalize() if case_status else "Not started"
        window = (f"Open now until {w.end:%d %b}" if w.open_now else f"{w.start:%d}–{w.end:%d %b %Y}")
        theme.html(f"""
        <div class="pf-tiles">
          <div class="pf-tile hi"><h4>Your application</h4><p>Status: <b>{theme.esc(status)}</b>.<br/>
            Start with Section 0: your details and promotion track.</p></div>
          <div class="pf-tile"><h4>Next submission window</h4><p><b style="color:var(--ink);font-size:20px">{window}</b><br/>
            Submissions are accepted only in the first week of January, April and October.</p></div>
          <div class="pf-tile"><h4>How it works</h4><p>Enter each claim once and attach its evidence. Tarqiya
            checks it, prepares the official forms and flags anything a reviewer should look at.</p></div>
        </div>""")
        st.write("")
        if st.button("Open Section 0 · Applicant details  →", type="primary"):
            st.switch_page(st.session_state["pf_pages"]["section0"])
    else:
        theme.html("""
        <div class="pf-tiles">
          <div class="pf-tile hi"><h4>Reviews</h4><p>Cases waiting for your decision appear under Reviews. Tarqiya
            prepares a report for each one; you approve it or return it to the applicant.</p></div>
          <div class="pf-tile"><h4>Referee selection</h4><p>After the Dean approves, the Chancellor chooses the external referees
            from a shortlist with conflict-of-interest checks.</p></div>
        </div>""")
        if "reviews" in st.session_state["pf_pages"]:
            st.write("")
            if st.button("Open cases awaiting my decision  →", type="primary"):
                st.switch_page(st.session_state["pf_pages"]["reviews"])
        if "referees" in st.session_state["pf_pages"]:
            st.write("")
            if st.button("Open referee selection  →", type="primary"):
                st.switch_page(st.session_state["pf_pages"]["referees"])
