"""Referee selection: the Chancellor's page. Pick referees from the shortlist the Chancellor's Office evaluation prepared.

Two steps. First a person VERIFIES each referee: the rank (ORCID job titles are typed by the researcher and can be out of date) and the
email, checked against the university page. Only verified Professors without a conflict can be ticked. Then the Chancellor selects, and
Tarqiya queues an invitation email for each one. A selection, not an approval. With no mail server configured the emails stay queued.
"""
import re

import streamlit as st

from promoflow.db.enums import Rank, RoleName
from promoflow.db.models import Referee
from promoflow.db.session import session_scope
from promoflow.dossier import audit
from promoflow.rules import referees as referee_rules
from promoflow.ui import cache, theme
from promoflow.workflow import outreach, referee_result, referee_view, review_service

K = "ref_"
CASE_KEY = K + "case"
RANK_LABEL = {Rank.LECTURER: "Lecturer", Rank.ASSISTANT_PROFESSOR: "Assistant Professor", Rank.ASSOCIATE_PROFESSOR: "Associate Professor",
              Rank.PROFESSOR: "Professor"}
RANK_OPTIONS = {r.value: label for r, label in RANK_LABEL.items()}
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
AUDITED = ["email", "rank", "rank_verified"]


def render() -> None:
    user = st.session_state["current_user"]
    theme.html("""
    <div class="pf-hero"><div class="crumb">REFEREE SELECTION</div>
    <h1>Choose the external referees</h1>
    <p>The Chancellor's Office evaluation prepared a shortlist of external referees with conflict-of-interest checks.
    A person first verifies each referee's rank and email; then the Chancellor chooses who to invite. This is a selection, not an approval.
    Referee identities are confidential and are never shown to the applicant.</p></div>""")
    if not user.has(RoleName.CHANCELLOR):
        st.info("Only the Chancellor selects referees.", icon=":material/info:")
        return
    if flash := st.session_state.pop(K + "flash", None):
        st.success(flash, icon=":material/check_circle:")
    case_id = st.session_state.get(CASE_KEY)
    if case_id is None:
        _list()
    else:
        _detail(user, case_id)


def _list() -> None:
    if st.button("Refresh", icon=":material/refresh:", key=K + "refresh"):
        cache.clear()
        st.rerun()
    with session_scope() as s:
        cases = referee_view.cases(s)
    if not cases:
        st.info("No cases are at the referee-selection step.", icon=":material/inbox:")
        return
    for c in cases:
        with st.container(key=f"card_refcase_{c.case_id}"):
            left, mid, right = st.columns([3.2, 2.2, 1.3], vertical_alignment="center")
            left.markdown(f"**{c.applicant_name}**  \n{c.department}")
            status = "Waiting for your selection" if c.waiting else "Referees selected: invitations sent or queued"
            mid.markdown(f"{c.track.replace('_', ' ').title()}  \n{status}")
            if right.button("Open" if c.waiting else "View", key=f"{K}open_{c.case_id}", type="primary" if c.waiting else "secondary",
                            use_container_width=True):
                st.session_state[CASE_KEY] = c.case_id
                st.rerun()


def _detail(user, case_id: int) -> None:
    if st.button("← Back to the list", key=K + "back"):
        st.session_state.pop(CASE_KEY, None)
        st.rerun()
    with session_scope() as s:
        status = review_service.get_status(case_id)
        rows = referee_view.shortlist(s, case_id)
        mails = referee_view.messages(s, case_id)
    waiting = status.waiting_for == "chancellor"
    if not rows and waiting:
        st.warning("There is no shortlist for this case.", icon=":material/warning:")
        return
    if waiting:
        verified = sum(1 for r in rows if r.rank_verified)
        st.caption(f"{len(rows)} candidates, best match first; {verified} verified. Open **Verify rank and email** on a card, check it, "
                   "and confirm. Only verified Professors can be ticked.")
    picks = {}
    for r in rows:
        picks[r.candidate_id] = _candidate(user, case_id, r, waiting)
    if waiting:
        _select_button(user, case_id, rows, picks)
    else:
        _responses(case_id)
        _result_panel(user, case_id)
        _invitations(mails)


def _responses(case_id: int) -> None:
    """What each contacted referee answered: their status and, once their report is in, each paper's grade and the recommendation."""
    with session_scope() as s:
        rows = referee_view.responses(s, case_id)
    st.markdown("#### Referee responses")
    if not rows:
        st.info("No referee has been contacted yet.", icon=":material/mail:")
        return
    st.caption("Referee names and grades are confidential: the applicant never sees them.")
    for r in rows:
        with st.container(key=f"card_resp_{r.assignment_id}"):
            head, grade = st.columns([4, 1], vertical_alignment="center")
            head.markdown(f"**{r.referee_name}**  \n{r.university}")
            grade.markdown(f"**{r.average:.1f}%** average" if r.average is not None else "No grades yet")
            dates = [f"Invited {r.invited_at:%d %b %Y}"] if r.invited_at else []
            if r.last_reminder_at:
                dates.append(f"last reminder {r.last_reminder_at:%d %b %Y}")
            if r.responded_at:
                dates.append(f"answered {r.responded_at:%d %b %Y}")
            if r.submitted_at:
                dates.append(f"report received {r.submitted_at:%d %b %Y}")
            st.caption(f"{r.status}  ·  " + ", ".join(dates))
            if r.grades:
                for g in r.grades:
                    st.write(f"- {g.title}: **{g.grade:.0f}%**")
                if r.recommendation:
                    st.markdown(f"**Recommendation:** {r.recommendation}")


def _result_panel(user, case_id: int) -> None:
    """The referee result: how many reports are in, the average against the pass mark, and the button that tells the applicant."""
    try:
        with session_scope() as s:
            result = referee_result.view(s, case_id)
    except referee_result.ResultError as err:
        st.warning(str(err), icon=":material/warning:")
        return
    st.markdown("#### Referee result")
    st.write(f"**{result.reports}** of **{result.minimum}** reports needed have arrived.")
    if result.average is not None:
        st.write(f"Average grade so far: **{result.average:.1f}%** (pass mark {result.pass_mark:.0f}%).")
    if result.passed is None:
        st.caption("The result can be released once the minimum number of reports is in.")
        return
    outcome = "reaches" if result.passed else "does not reach"
    st.info(f"The average {outcome} the pass mark. Releasing tells the applicant "
            f"{'that they have been promoted' if result.passed else 'that the application was not successful'}.", icon=":material/gavel:")
    sure = st.checkbox("I have checked the reports and want to tell the applicant.", key=K + "release_sure")
    if st.button("Release the result to the applicant", type="primary", key=K + "release", disabled=not sure, icon=":material/send:"):
        try:
            referee_result.release(case_id, user.id)
        except referee_result.ResultError as err:
            st.error(str(err), icon=":material/error:")
            return
        cache.clear()
        st.session_state.pop(CASE_KEY, None)
        st.session_state[K + "flash"] = "The result was released. The applicant will see it on their dashboard."
        st.rerun()


def _candidate(user, case_id: int, r: "referee_view.CandidateRow", waiting: bool) -> bool:
    """One candidate card. Returns True when the Chancellor ticked it."""
    with st.container(key=f"card_cand_{r.candidate_id}"):
        head, score = st.columns([4, 1], vertical_alignment="center")
        with head:
            picked = False
            if waiting:
                picked = st.checkbox(r.name, key=f"{K}pick_{r.candidate_id}", disabled=bool(r.blocked), help=r.blocked)
            else:
                theme.html(f'<div class="pf-card-h"><h3>{theme.esc(r.name)}</h3></div>')
            theme.html(f'<div class="pf-card-sub" style="margin-left:0">{theme.esc(r.university)} · {theme.esc(r.country)}'
                       f' · h-index {r.h_index if r.h_index is not None else "–"} '
                       f'(applicant entered {r.applicant_h_index if r.applicant_h_index is not None else "–"})</div>')
        unranked = r.match_score is None or (r.match_score == 0 and (r.rationale or "").startswith("Not ranked"))
        score.markdown("Not ranked" if unranked else f"**{r.match_score:.0%}** match")
        if r.topics:
            st.caption("Topics: " + ", ".join(r.topics))
        if r.rationale:
            st.caption(r.rationale)
        tags = ""
        if r.conflicts:
            tags += "".join(f'<span class="pf-tag low">Conflict: {theme.esc(c)}</span> ' for c in r.conflicts)
        elif r.eligible:
            tags += '<span class="pf-tag">No conflict of interest</span> '
        if not r.eligible:
            tags += '<span class="pf-tag low">Not eligible</span> '
        if r.rank_verified:
            rank = RANK_OPTIONS.get(r.rank, "unknown rank")
            tags += f'<span class="pf-tag">Verified: {theme.esc(rank)}</span> '
        else:
            tags += '<span class="pf-tag low">Not verified</span> '
        if r.selected:
            tags += '<span class="pf-tag">Selected</span> ' + ('<span class="pf-tag">Invitation queued</span>' if r.invited else
                                                                  '<span class="pf-tag low">Waiting for email / rank</span>')
        theme.html(tags)
        if waiting:
            _verify_box(user, case_id, r)
    return picked


def _verify_box(user, case_id: int, r: "referee_view.CandidateRow") -> None:
    """The human check: look at the current rank and email on the university page, correct them if needed, and confirm."""
    with st.expander("Verify rank and email", expanded=not r.rank_verified, icon=":material/verified_user:"):
        st.caption("ORCID job titles are typed by the researcher and can be out of date, and most ORCID emails are private. "
                   "Check the current rank and a working email on the university page, then confirm.")
        links = referee_rules.contact_search_links(r.name, r.university)
        cols = st.columns(4)
        if r.orcid:
            cols[0].link_button("ORCID record", f"https://orcid.org/{r.orcid}", use_container_width=True)
        cols[1].link_button("Google Scholar", links["google_scholar"], use_container_width=True)
        cols[2].link_button("LinkedIn", links["linkedin"], use_container_width=True)
        cols[3].link_button("Web search", links["web"], use_container_width=True)

        suggestion_key = f"{K}orcid_{r.candidate_id}"
        if r.orcid and st.button("What does ORCID say?", key=f"{K}ask_{r.candidate_id}", icon=":material/search:"):
            st.session_state[suggestion_key] = outreach.suggest_contact(r.referee_id) or "none"
        if (sug := st.session_state.get(suggestion_key)) is not None:
            if sug == "none":
                st.caption("ORCID gave no current job title or public email.")
            else:
                st.caption(f"ORCID: current job title **{sug.role_title or 'none'}**; public email **{sug.email or 'none'}**.")

        a, b = st.columns(2)
        email = a.text_input("Email", value=r.email or "", key=f"{K}vemail_{r.candidate_id}", placeholder="name@university.edu").strip()
        current = r.rank if r.rank in RANK_OPTIONS else None
        rank = b.selectbox("Current academic rank", list(RANK_OPTIONS), format_func=RANK_OPTIONS.get,
                           index=list(RANK_OPTIONS).index(current) if current else None, placeholder="Choose the rank",
                           key=f"{K}vrank_{r.candidate_id}")
        if st.button("Update verification" if r.rank_verified else "Verify", key=f"{K}verify_{r.candidate_id}", type="primary",
                     icon=":material/check:"):
            if not rank:
                st.error("Choose the rank you found.", icon=":material/error:")
            elif not EMAIL.match(email):
                st.error("Enter an email that looks right.", icon=":material/error:")
            else:
                _verify(user, case_id, r, email, Rank(rank))


def _verify(user, case_id: int, r: "referee_view.CandidateRow", email: str, rank: Rank) -> None:
    with session_scope() as s:
        before = audit.snapshot(s.get(Referee, r.referee_id), AUDITED)
    try:
        outreach.confirm_referee(r.referee_id, email=email, rank=rank)      # also marks the rank verified
    except Exception as err:                                                # for example an email already used by another referee
        st.error(f"It could not be saved: {type(err).__name__}. Check that the email is not used by another referee.", icon=":material/error:")
        return
    with session_scope() as s:
        audit.log(s, user_id=user.id, case_id=case_id, action="referee_verified", entity_table="referee", entity_id=r.referee_id,
                  before=before, after=audit.snapshot(s.get(Referee, r.referee_id), AUDITED))
    cache.clear()
    st.session_state[K + "flash"] = f"{r.name}: rank and email verified."
    st.rerun()


def _select_button(user, case_id: int, rows, picks: dict) -> None:
    chosen = [r for r in rows if picks[r.candidate_id]]
    if st.button(f"Select {len(chosen)} referee{'s' if len(chosen) != 1 else ''}", type="primary", icon=":material/how_to_reg:",
                 key=K + "select", disabled=not chosen):
        try:
            with st.spinner("Selecting the referees and preparing the invitations…"):
                review_service.select_referees(case_id, user.id, [r.candidate_id for r in chosen], wait=True)    # wait, so the list shows the new state
        except review_service.ReviewError as err:
            st.error(str(err), icon=":material/error:")
            return
        except Exception as err:
            st.error(f"The selection could not be saved: {type(err).__name__}.", icon=":material/error:")
            return
        cache.clear()
        failure = review_service.get_status(case_id).error
        if failure:
            st.error(f"The selection was saved but the next step stopped: {failure}", icon=":material/error:")
            return
        st.session_state.pop(CASE_KEY, None)
        st.session_state[K + "flash"] = (f"{len(chosen)} referee(s) selected. Invitations are being prepared; the emails stay queued "
                                         "until a mail server is configured.")
        st.rerun()


def _invitations(mails: list) -> None:
    st.subheader("Invitation emails", divider="gray")
    if not mails:
        st.info("No invitation was queued yet. A referee needs a verified rank and a confirmed email before an invitation is prepared.", icon=":material/mail:")
        return
    for m in mails:
        with st.expander(f"{m.referee_name} · {m.subject} · {m.status}"):
            st.text(m.body)
