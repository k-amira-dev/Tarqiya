"""Reviews – the Head of Department's and the Dean's pages. Cases waiting at their gate, the Report Builder's report,
and the decision. Nothing here runs an agent: the decision button calls promoflow.workflow.review_service.resume()."""
import re

import streamlit as st

from promoflow.db.enums import Gate, GateOutcome, RoleName
from promoflow.db.session import session_scope
from promoflow.ui import cache, report_view as rv, theme
from promoflow.workflow import review_service

K = "rev_"
CASE_KEY = K + "case"
GATE_LABEL = {"hod": "Head of Department", "dean": "Dean"}
SECTION_TITLES = {
    "0": "Applicant details", "1": "Application form", "2": "Curriculum vitae", "3": "Degrees & equivalency",
    "4": "Ranks & experience", "5": "Research", "6": "Teaching & advising", "7": "University & community service",
    "8": "Recommendation letters", "9": "Conditions form", "10": "Cover letter",
}
# The evaluations' names as shown to people (the code calls them agents; the screens never do).
AGENT_TITLE = rv.TITLE
VERDICT = {"pass": ("green", "Pass"), "fail": ("red", "Does not pass"), "needs_human": ("amber", "Needs a person"),
           "incomplete": ("amber", "Incomplete")}
MARK = {True: ("ok", "✓"), False: ("fail", "✕"), None: ("warn", "!")}


def render() -> None:
    user = st.session_state["current_user"]
    theme.html("""
    <div class="pf-hero"><div class="crumb">REVIEWS</div>
    <h1>Cases awaiting my decision</h1>
    <p>Tarqiya prepares a report; you decide. Nothing moves to the next step until you approve it or return it
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
        cases = review_service.waiting_cases(s, user.roles, user.id)
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
        d = cache.load_cached(f"pfc:review:{case_id}", lambda s: review_service.case_detail(s, case_id, user.roles, user.id))
    except review_service.NotAllowed as e:
        st.session_state.pop(CASE_KEY, None)
        st.warning(str(e))
        return

    placeholders = [rv.TITLE[n] for n, o in (d.report["sections"].items() if d.report else []) if o.get("is_stub")]
    chip = {True: ("green", "All available evaluations pass" if placeholders else "All three evaluations pass"),
            False: ("red", "At least one evaluation does not pass"),
            None: ("amber", "Needs your judgement")}[d.report["overall_pass"] if d.report else None]
    with st.container(key="card_case_head"):
        theme.card_header("→", d.applicant_name, f"{d.department} · {d.track.replace('_', ' ').title()}"
                          f"{' · ' + d.specialization if d.specialization else ''}")
        theme.html(f'<span class="pf-chip {chip[0]}">{chip[1]}</span> '
                   f'<span class="pf-chip grey">Waiting for the {GATE_LABEL[d.gate]}</span>'
                   + "".join(f' <span class="pf-chip grey">{t}: not built yet</span>' for t in placeholders))

    if d.report is None:
        st.warning("The report is not ready yet. Try again in a moment.", icon=":material/hourglass_top:")
        return
    _summary_strip(d.report)
    _flags_card(d.report)
    for name in ("eligibility", "research", "teaching", "service"):
        out = d.report.get("eligibility") if name == "eligibility" else d.report["sections"].get(name)
        if out:
            _agent_card(name, out, d.case_id)
    if d.decisions:
        _decisions_card(d.decisions)
    _decision_form(user, d)


def _flags_card(report: dict) -> None:
    flags = report["flags"]
    with st.container(key="card_flags"):
        theme.card_header("!", "Flags for you", "Everything the evaluations flagged for a person to look at.")
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


def _summary_strip(report: dict) -> None:
    """Four tiles at the top: each evaluation's result in one glance."""
    tiles = ""
    for name in ("eligibility", "research", "teaching", "service"):
        out = report.get("eligibility") if name == "eligibility" else report["sections"].get(name)
        if not out:
            continue
        t = rv.summary(name, out)
        kind, text = ("grey", "Placeholder") if out.get("is_stub") else VERDICT.get(t.verdict, ("grey", t.verdict))
        tiles += (f'<div class="pf-sumtile"><h5>{theme.esc(t.title)}</h5><div class="big">{theme.esc(t.figure)}</div>'
                  f'<div class="sub">{theme.esc(t.detail)}</div><span class="pf-chip {kind}">{text}</span></div>')
    theme.html(f'<div class="pf-sum">{tiles}</div>')


def _agent_card(name: str, out: dict, case_id: int | None = None) -> None:
    kind, text = ("grey", "Placeholder") if out.get("is_stub") else VERDICT.get(out["verdict"], ("grey", out["verdict"]))
    title = rv.TITLE[name]
    table = rv.points_table(out)
    with st.container(key=f"card_agent_{name}"):
        # No long paragraph: the numbers are in the score banner and the table, the reasoning is one click away.
        reasoning = name == "research" and not out.get("is_stub") and out.get("narrative")
        theme.card_header(name[:1].upper(), title, "" if table or reasoning else (out.get("narrative") or ""))
        if out.get("is_stub"):
            theme.html(f'<span class="pf-chip {kind}">{text}</span>')
            theme.html('<div class="pf-note">Placeholder: this evaluation has not been built yet, so this result '
                       "carries no meaning.</div>")
            return
        if table:
            _points_view(table, kind, text)
        else:
            theme.html(f'<span class="pf-chip {kind}">{text}</span>')
            _checks_table(rv.check_rows(out))
            if name == "research" and case_id is not None:
                _papers_table(case_id, out)
            if reasoning:
                _reasoning(out["narrative"])


def _papers_table(case_id: int, out: dict) -> None:
    """Research: one row per paper with the rules' decisions (class, counted, credited role) and the model's topic check."""
    from sqlalchemy import select

    from promoflow.db.models import Publication
    from promoflow.dossier.section5.papers import DECLARED, classify_many

    ids = [it["entity_id"] for it in out.get("items", []) if it.get("entity_table") == "publication"]
    if not ids:
        return
    with session_scope() as s:
        pubs = list(s.scalars(select(Publication).where(Publication.id.in_(ids))))
        classes = classify_many(s, pubs)
        papers = {p.id: (p.title, p.journal_name, bool(classes[p.id].journal and classes[p.id].journal.scopus_source_id == DECLARED)) for p in pubs}
    rows = ""
    for r in rv.paper_rows(out, papers):
        source = '<br><small style="color:var(--muted)">class declared in the applicant&#39;s form, not an official ranking</small>' if r.declared else ""
        topic_cls = "" if r.topic_ok else " low"
        rows += (f'<tr><td>{theme.esc(r.title)}<br><small style="color:var(--muted)">{theme.esc(r.journal)}</small></td>'
                 f'<td><span class="pf-tag">{r.journal_class}</span>{source}</td>'
                 f'<td>{"Yes" if r.counted else "No"}</td><td>{theme.esc(r.credited)}</td>'
                 f'<td><span class="pf-tag{topic_cls}">{theme.esc(r.topic)}</span></td></tr>')
    st.markdown("**Papers: what was decided for each**")
    theme.html('<table class="pf-tbl"><thead><tr><th>Paper</th><th>Journal class (rule)</th><th>Counted</th><th>Credited as</th>'
               f'<th>Topic fit (AI)</th></tr></thead><tbody>{rows}</tbody></table>')


def _reasoning(narrative: str) -> None:
    """The Research evaluation's explanation, one point per line, in an expander under the table (like Teaching and Service)."""
    parts = [p.strip() for p in re.split(r"\s-\s(?=[A-Z])", narrative) if p.strip()]
    with st.expander("Why these results? The reasoning"):
        theme.html("".join(f'<div class="pf-reason">{theme.esc(p)}</div>' for p in parts))


def _points_view(table: "rv.PointsTable", kind: str, text: str) -> None:
    """Teaching / Service: the score banner, the points table and the reasoning."""
    mx = table.max_total
    banner = f'<div class="big">{rv.g(table.total)}{f"<small> / {rv.g(mx)}</small>" if mx else ""}</div>'
    meter = ""
    if mx:
        fill = min(table.total / mx, 1) * 100
        color = "var(--g-500)" if table.passed else "var(--red)"
        mark = f'<u style="left:{table.pass_mark / mx * 100:.1f}%"></u>' if table.pass_mark is not None else ""
        meter = (f'<div class="pf-meter-wrap"><div class="pf-meter"><i style="width:{fill:.1f}%;background:{color}">'
                 f'</i>{mark}</div><div class="pf-meter-lab">Pass mark {rv.g(table.pass_mark)} '
                 f'(the black line) · <span class="pf-chip {kind}">{text}</span></div></div>')
    theme.html(f'<div class="pf-score">{banner}{meter}</div>')

    models = table.models                              # committee only: one column per model
    rows = ""
    for r in table.rows:
        if r.no_evidence:
            cell = '<span class="pf-tag none">No evidence entered</span>'
        else:
            cls = "g" if (r.share or 0) >= 0.75 else "a" if (r.share or 0) >= 0.4 else "r"
            bar = f'<div class="pf-bar"><i class="{cls}" style="width:{(r.share or 0) * 100:.0f}%"></i></div>'                 if r.max_points else ""
            cell = f'<div class="pf-pts"><b>{rv.g(r.points)} / {rv.g(r.max_points)}</b>{bar}</div>'                 if r.max_points else f'<div class="pf-pts"><b>{rv.g(r.points)}</b></div>'
        conf = (f'<span class="pf-tag{" low" if r.confidence == "Low" else ""}">{r.confidence}</span>'
                if r.confidence and not r.no_evidence else "")
        votes = {m: pts for m, pts, _ in r.opinions}
        # A model's own score is shaded when it differs from the decision (the median), so disagreement is visible at a glance.
        model_cells = "".join(
            f'<td class="r" style="text-align:center">' + (
                f'<span class="pf-tag{"" if votes[m] == r.points else " low"}">{rv.g(votes[m])}</span>' if m in votes else "–") + "</td>"
            for m in models)
        flag = ' <span class="pf-chip amber">Models disagree: decide</span>' if r.disagree else ""
        style = ' style="background:var(--amber-50)"' if r.disagree else ""
        rows += (f'<tr{style}><td class="n">{r.item_no}</td><td>{theme.esc(r.label)}{flag}</td>{model_cells}<td>{cell}</td>'
                 f'<td><span class="pf-tag">{theme.esc(r.how)}</span></td><td>{conf}</td></tr>')
    model_heads = "".join(f'<th style="text-align:center">{theme.esc(m)}</th>' for m in models)
    points_head = "Decision (median)" if models else "Points"
    theme.html(f'<table class="pf-tbl"><thead><tr><th>#</th><th>What is assessed</th>{model_heads}<th>{points_head}</th>'
               f'<th>How decided</th><th>Confidence</th></tr></thead><tbody>{rows}</tbody></table>')
    if models:
        theme.html('<div class="pf-note">Each model scored every AI-assisted item on its own. The decision is the median of their points. '
                   "A shaded score differs from the decision. When the scores are far apart the item is marked for you to decide.</div>")

    with st.expander("Why these points? The reasoning for each item"):
        parts = ""
        for r in table.rows:
            parts += f'<div class="pf-reason"><b>Item {r.item_no} · {rv.g(r.points)} points.</b> {theme.esc(r.reason)}</div>'
            for m, pts, why in r.opinions:             # what each model said, when a committee scored the item
                parts += (f'<div class="pf-reason" style="margin-left:18px"><b>{theme.esc(m)} · {rv.g(pts)} points.</b> '
                          f'{theme.esc(why)}</div>')
        theme.html(parts)


def _checks_table(checks: list) -> None:
    """Eligibility: one row per condition, with what the policy asks for and what the applicant has."""
    rows = ""
    for c in checks:
        cls, mark = MARK[c.passed]
        ref = f'<br><small style="color:var(--muted)">Policy {theme.esc(c.policy_ref)}</small>' if c.policy_ref else ""
        rows += (f'<tr><td>{theme.esc(c.label)}{ref}</td><td class="r">{rv.g(c.required)}</td>'
                 f'<td class="r">{rv.g(c.actual)}</td><td class="r"><span class="pf-res {cls}">{mark}</span></td></tr>')
    if rows:
        theme.html('<table class="pf-tbl"><thead><tr><th>Condition</th><th class="r" style="text-align:right">'
                   'Required</th><th class="r" style="text-align:right">Actual</th>'
                   f'<th style="text-align:right">Met</th></tr></thead><tbody>{rows}</tbody></table>')


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
                review_service.resume(d.case_id, user.id, gate,
                               GateOutcome.RETURN_FOR_REVISION if returning else GateOutcome.APPROVE,
                               comment, sections)
            except review_service.ReviewError as e:
                st.error(str(e))
                return
            for key in ("choice", "sections", "comment", "confirm"):
                st.session_state.pop(K + key, None)
            st.session_state.pop(CASE_KEY, None)
            st.session_state[K + "flash"] = ("Decision recorded. The system is continuing in the background; "
                                             "press Refresh in a few seconds.")
            st.rerun(scope="app")
