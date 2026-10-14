"""Reviews – the Head of Department's and the Dean's pages. Cases waiting at their gate, the Report Builder's report,
and the decision. Nothing here runs an agent: the decision button calls promoflow.workflow.service.resume()."""
import streamlit as st

from promoflow.db.enums import Gate, GateOutcome, RoleName
from promoflow.db.session import session_scope
from promoflow.ui import cache, theme
from promoflow.workflow import service

K = "rev_"
CASE_KEY = K + "case"
GATE_LABEL = {"hod": "Head of Department", "dean": "Dean"}
SECTION_TITLES = {
    "0": "Applicant details", "1": "Application form", "2": "Curriculum vitae", "3": "Degrees & equivalency",
    "4": "Ranks & experience", "5": "Research", "6": "Teaching & advising", "7": "University & community service",
    "8": "Recommendation letters", "9": "Conditions form", "10": "Cover letter",
}
AGENT_TITLE = {"eligibility": "Eligibility Checker", "research": "Research Agent", "teaching": "Teaching Agent",
               "service": "Service Agent"}
VERDICT = {"pass": ("green", "Pass"), "fail": ("red", "Does not pass"), "needs_human": ("amber", "Needs a person"),
           "incomplete": ("amber", "Incomplete")}
MARK = {True: ("ok", "✓"), False: ("fail", "✕"), None: ("warn", "!")}


def render() -> None:
    user = st.session_state["current_user"]
    theme.html("""
    <div class="pf-hero"><div class="crumb">REVIEWS</div>
    <h1>Cases awaiting my decision</h1>
    <p>The agents prepare a report; you decide. Nothing moves to the next step until you approve it or return it
    to the applicant.</p></div>""")
    if not user.has(RoleName.HOD, RoleName.DEAN):
        st.info("Only the Head of Department and the Dean review cases here.", icon=":material/info:")
        return
    if flash := st.session_state.pop(K + "flash", None):
        st.success(flash, icon=":material/check_circle:")
    case_id = st.session_state.get(CASE_KEY)
    if case_id is None:
        _list(user)
    else:
        _detail(user, case_id)


def _list(user) -> None:
    if st.button("Refresh", icon=":material/refresh:", key=K + "refresh"):
        cache.clear()
        st.rerun()
    with session_scope() as s:
        cases = service.waiting_cases(s, user.roles)
    if not cases:
        st.info("No cases are waiting for your decision.", icon=":material/inbox:")
        return
    for c in cases:
        with st.container(key=f"card_case_{c.case_id}"):
            left, mid, right = st.columns([3.2, 2.2, 1.3], vertical_alignment="center")
            left.markdown(f"**{c.applicant_name}**  \n{c.department}")
            submitted = f"{c.submitted_at:%d %b %Y}" if c.submitted_at else "–"
            mid.markdown(f"{c.track.replace('_', ' ').title()}  \nSubmitted {submitted}")
            if right.button("Open review", key=f"{K}open_{c.case_id}", type="primary", use_container_width=True):
                st.session_state[CASE_KEY] = c.case_id
                st.rerun()


def _detail(user, case_id: int) -> None:
    if st.button("Back to the list", icon=":material/arrow_back:", key=K + "back"):
        st.session_state.pop(CASE_KEY)
        st.rerun()
    try:
        d = cache.load_cached(f"pfc:review:{case_id}", lambda s: service.case_detail(s, case_id, user.roles))
    except service.NotAllowed as e:
        st.session_state.pop(CASE_KEY, None)
        st.warning(str(e))
        return

    chip = {True: ("green", "All three agents pass"), False: ("red", "At least one agent does not pass"),
            None: ("amber", "Needs your judgement")}[d.report["overall_pass"] if d.report else None]
    with st.container(key="card_case_head"):
        theme.card_header("→", d.applicant_name, f"{d.department} · {d.track.replace('_', ' ').title()}"
                          f"{' · ' + d.specialization if d.specialization else ''}")
        theme.html(f'<span class="pf-chip {chip[0]}">{chip[1]}</span> '
                   f'<span class="pf-chip grey">Waiting for the {GATE_LABEL[d.gate]}</span>')

    if d.report is None:
        st.warning("The report is not ready yet. Try again in a moment.", icon=":material/hourglass_top:")
        return
    _flags_card(d.report)
    for name in ("eligibility", "research", "teaching", "service"):
        out = d.report.get("eligibility") if name == "eligibility" else d.report["sections"].get(name)
        if out:
            _agent_card(name, out)
    if d.decisions:
        _decisions_card(d.decisions)
    _decision_form(user, d)


def _flags_card(report: dict) -> None:
    flags = report["flags"]
    with st.container(key="card_flags"):
        theme.card_header("!", "Flags for you", "Everything the agents want a person to look at.")
        if not flags:
            theme.html('<div class="pf-note">No flags.</div>')
            return
        rows = ""
        for f in flags:
            human = f["severity"] == "needs_human"
            kind = "warn" if f["severity"] in ("warning", "needs_human") else "info"
            label = "NEEDS YOUR DECISION · " if human else ""
            rows += (f'<div class="pf-check"><div class="ic {kind}">{"!" if kind == "warn" else "i"}</div><div>'
                     f'<b>{label}{theme.esc(AGENT_TITLE.get(f.get("component"), ""))}</b>'
                     f'<small>{theme.esc(f["message"])}</small></div></div>')
        theme.html(rows)


def _agent_card(name: str, out: dict) -> None:
    kind, text = VERDICT.get(out["verdict"], ("grey", out["verdict"]))
    with st.container(key=f"card_agent_{name}"):
        theme.card_header(name[:1].upper(), AGENT_TITLE[name], out.get("narrative") or "")
        theme.html(f'<span class="pf-chip {kind}">{text}</span>')
        if out.get("is_stub"):
            theme.html('<div class="pf-note">Placeholder: this agent has not been built yet, so this result '
                       "carries no meaning.</div>")
        rows = ""
        for c in out.get("criteria", []):
            cls, mark = MARK[c["passed"]]
            figures = ""
            if c.get("required") is not None or c.get("actual") is not None:
                figures = f"required {c.get('required', '–')}, actual {c.get('actual', '–')}"
            ref = f" · Policy {c['policy_ref']}" if c.get("policy_ref") else ""
            rows += (f'<div class="pf-check"><div class="ic {cls}">{mark}</div><div><b>{theme.esc(c["label"])}</b>'
                     f'<small>{theme.esc(figures)}{theme.esc(ref)}</small></div></div>')
        if rows:
            theme.html(rows)


def _decisions_card(decisions: list) -> None:
    with st.container(key="card_decisions"):
        theme.card_header("✓", "Earlier decisions", "Made before the case reached you.")
        rows = ""
        for x in decisions:
            what = "Approved" if x.outcome == GateOutcome.APPROVE else "Returned for revision"
            extra = f" (sections {', '.join(x.sections)})" if x.sections else ""
            comment = f" — {x.comment}" if x.comment else ""
            rows += (f'<div class="pf-check"><div class="ic ok">✓</div><div>'
                     f'<b>{GATE_LABEL[x.gate.value]}: {what}{theme.esc(extra)}</b>'
                     f'<small>{theme.esc(x.decided_by)}{theme.esc(comment)}</small></div></div>')
        theme.html(rows)


@st.fragment
def _decision_form(user, d) -> None:
    """A fragment: typing the comment never re-runs the page above."""
    gate = Gate(d.gate)
    with st.container(key="card_decision"):
        theme.card_header("→", "Your decision", "Approving lets the case move on. Returning it unlocks it for the "
                                                "applicant, with your comment.")
        choice = st.radio("Decision", ["Approve", "Return for revision"], horizontal=True, key=K + "choice",
                          label_visibility="collapsed")
        returning = choice == "Return for revision"
        sections = []
        if returning:
            sections = [x.split(" · ")[0] for x in st.multiselect(
                "Sections to revise", [f"{c} · {t}" for c, t in SECTION_TITLES.items()], key=K + "sections")]
        comment = st.text_area("Comment" + (" (required)" if returning else " (optional)"), key=K + "comment",
                               max_chars=2000)
        confirmed = st.checkbox("I have read the report and this is my decision.", key=K + "confirm")
        if st.button("Record decision", type="primary", icon=":material/gavel:", key=K + "submit",
                     disabled=not confirmed):
            try:
                service.resume(d.case_id, user.id, gate,
                               GateOutcome.RETURN_FOR_REVISION if returning else GateOutcome.APPROVE,
                               comment, sections)
            except service.ReviewError as e:
                st.error(str(e))
                return
            for key in ("choice", "sections", "comment", "confirm"):
                st.session_state.pop(K + key, None)
            st.session_state.pop(CASE_KEY, None)
            st.session_state[K + "flash"] = ("Decision recorded. The system is continuing in the background; "
                                             "press Refresh in a few seconds.")
            st.rerun(scope="app")
