"""Section 0 – Applicant Details & Promotion Track (spec chapter 4)."""
from datetime import date

import streamlit as st

from promoflow.db.enums import CaseStatus, PromotionTrack, Rank
from promoflow.db.session import session_scope
from promoflow.dossier import section0 as s0
from promoflow.rules.eligibility import (
    CURRENT_RANK_FOR, MAX_JUSTIFICATION, TARGET_RANK_FOR, section0_checks, validate_section0, years_between,
    assumed_submission_date,
)
from promoflow.ui import cache, theme

RANK_LABEL = {Rank.LECTURER: "Lecturer", Rank.ASSISTANT_PROFESSOR: "Assistant Professor",
              Rank.ASSOCIATE_PROFESSOR: "Associate Professor", Rank.PROFESSOR: "Professor"}
TRACK_LABEL = {PromotionTrack.TO_ASSOCIATE: "Assistant → Associate Professor",
               PromotionTrack.TO_FULL: "Associate Professor → Professor"}
STATUS_CHIP = {None: ("Not started", "draft"), CaseStatus.DRAFT: ("Draft", "draft"),
               CaseStatus.RETURNED_FOR_REVISION: ("Returned for revision", "draft")}
ICON = {"ok": "✓", "warn": "!", "fail": "✕", "info": "i"}
K = "s0_"  # widget-key prefix


def _academic_years(today: date, current: str | None) -> list[str]:
    base = today.year if today.month >= 8 else today.year - 1
    years = [f"{base}/{base + 1}", f"{base + 1}/{base + 2}"]
    return ([current] if current and current not in years else []) + years


def _prefill(ctx: s0.Section0Context, today: date) -> None:
    """Copy saved values into the widgets once per case (widgets then own their state)."""
    marker = ctx.case_id or "new"
    if st.session_state.get(K + "loaded") == marker:
        return
    v = ctx.values
    defaults = {
        "academic_year": v.get("academic_year") or _academic_years(today, None)[0],
        "track": v.get("track"), "specialization": v.get("specialization") or "",
        "fine_specialization": v.get("fine_specialization") or "",
        "research_keywords": v.get("research_keywords") or [],
        "appointment_date": v.get("appointment_date"), "rank_on_appointment": v.get("rank_on_appointment"),
        "current_rank_date": v.get("current_rank_date"), "scopus_author_id": v.get("scopus_author_id") or "",
        "orcid": v.get("orcid") or "", "phd_outside_uae": bool(v.get("phd_outside_uae")),
        "early_application": bool(v.get("early_application")), "exceptional_case": bool(v.get("exceptional_case")),
        "exceptional_justification": v.get("exceptional_justification") or "",
        "previously_rejected": bool(v.get("previously_rejected")), "rejection_date": v.get("rejection_date"),
    }
    for key, value in defaults.items():
        st.session_state[K + key] = value
    st.session_state[K + "loaded"] = marker


def _values() -> dict:
    return {f: st.session_state.get(K + f) for f in s0.FIELDS}


def render() -> None:
    user = st.session_state["current_user"]
    today = date.today()
    ctx = cache.load_cached(f"pfc:s0:{user.id}", lambda s: s0.load(s, user.id, today))
    _prefill(ctx, today)
    editable = ctx.status in (None, CaseStatus.DRAFT, CaseStatus.RETURNED_FOR_REVISION)
    chip_text, chip_cls = STATUS_CHIP.get(ctx.status, (ctx.status.value.replace("_", " ").capitalize()
                                                      if ctx.status else "", "draft"))

    theme.html(f"""
    <div class="pf-hero"><div class="crumb">MY PROMOTION · SECTION 0 OF 11</div>
    <h1>Applicant Details &amp; Promotion Track</h1>
    <p>Who you are and which promotion you are applying for. The rest of the dossier builds on these answers,
    and the eligibility preview on the right updates as you fill them in.</p>
    <div style="margin-top:14px"><span class="pf-chip draft">● {theme.esc(chip_text)}</span></div></div>""")

    if flash := st.session_state.pop(K + "flash", None):
        st.success(flash, icon=":material/check_circle:")
    if not editable:
        st.info("This application has been submitted, so Section 0 is read-only.", icon=":material/lock:")

    _form(ctx, user.id, today, editable)


@st.fragment
def _form(ctx, user_id: int, today: date, editable: bool) -> None:
    """Only this part re-runs while typing: no database access, just the widgets and the live preview."""
    left, right = st.columns([2.05, 1], gap="large")
    with left:
        _identity_card(ctx, today, editable)
        _track_card(ctx, editable)
        _rank_card(editable)
        _identifiers_card(editable)
        _special_card(editable)
        if editable:
            _save_bar(user_id, today)
    with right:
        _glance_card(ctx, today)


def _identity_card(ctx, today, editable) -> None:
    with st.container(key="card_identity"):
        theme.card_header("01", "Identity", "From your user profile. Contact the promotion office to change it.")
        i = ctx.identity
        theme.html(f"""<div class="pf-kv">
          <div><span>Full name</span><b>{theme.esc(i.full_name)}</b></div>
          <div><span>Employee ID</span><b>{theme.esc(i.employee_id)}</b></div>
          <div><span>Email</span><b>{theme.esc(i.email)}</b></div>
          <div><span>College</span><b>{theme.esc(i.college)}</b></div>
          <div><span>Department</span><b>{theme.esc(i.department)}</b></div>
          <div><span>Policy</span><b>{theme.esc(ctx.policy_title.split(" (")[0])}</b></div></div>""")
        years = _academic_years(today, st.session_state.get(K + "academic_year"))
        st.selectbox("Academic year", years, key=K + "academic_year", disabled=not editable)


def _track_card(ctx, editable) -> None:
    with st.container(key="card_track"):
        theme.card_header("02", "Promotion track", "This decides which thresholds apply to your application.")
        st.radio("Promotion track", list(PromotionTrack), key=K + "track", format_func=TRACK_LABEL.get,
                 horizontal=True, label_visibility="collapsed", disabled=not editable)
        track = st.session_state.get(K + "track")
        if track:
            c = ctx.criteria.get(track)
            theme.html(f'<div class="pf-note">Target rank: <b>{RANK_LABEL[TARGET_RANK_FOR[track]]}</b> · '
                       f'at least <b>{c.min_years_in_rank} years</b> in rank, including '
                       f'<b>{c.min_years_at_institution}</b> at this university.</div>' if c else "")
        a, b = st.columns(2)
        a.text_input("Specialization", key=K + "specialization", placeholder="e.g. Computer Science",
                     disabled=not editable)
        b.text_input("Fine specialization", key=K + "fine_specialization", placeholder="e.g. Machine Learning",
                     disabled=not editable)
        st.multiselect("Research keywords (up to 8)", options=st.session_state.get(K + "research_keywords") or [],
                       key=K + "research_keywords", accept_new_options=True, max_selections=8,
                       placeholder="Type a keyword and press Enter", disabled=not editable,
                       help="Used to check the topic relevance of your papers and to match external referees.")


def _rank_card(editable) -> None:
    with st.container(key="card_rank"):
        theme.card_header("03", "Appointment & current rank",
                          "Time in rank is the first eligibility rule, so these dates matter.")
        a, b = st.columns(2)
        a.date_input("Date of appointment at the University", key=K + "appointment_date",
                     min_value=date(1970, 1, 1), max_value=date.today(), format="DD/MM/YYYY", disabled=not editable)
        b.selectbox("Academic rank on appointment", list(Rank)[:-1], key=K + "rank_on_appointment",
                    format_func=RANK_LABEL.get, placeholder="Choose a rank", disabled=not editable)
        c, d = st.columns(2)
        track = st.session_state.get(K + "track")
        c.text_input("Current rank", value=RANK_LABEL[CURRENT_RANK_FOR[track]] if track else "Choose a track first",
                     disabled=True, help="Always one rank below the rank you are applying for.")
        d.date_input("Date current rank obtained", key=K + "current_rank_date",
                     min_value=date(1970, 1, 1), max_value=date.today(), format="DD/MM/YYYY", disabled=not editable)


def _identifiers_card(editable) -> None:
    with st.container(key="card_ids"):
        theme.card_header("04", "Research identifiers",
                          "Used to verify your h-index and citations, and to avoid conflicts of interest with referees.")
        a, b = st.columns(2)
        a.text_input("Scopus Author ID", key=K + "scopus_author_id", placeholder="e.g. 57193456789",
                     disabled=not editable)
        b.text_input("ORCID iD (optional)", key=K + "orcid", placeholder="0000-0000-0000-0000", disabled=not editable)
        theme.html('<div class="pf-note">Your OpenAlex profile is matched automatically from these identifiers; '
                   'you will be asked to confirm it.</div>')


def _special_card(editable) -> None:
    with st.container(key="card_special"):
        theme.card_header("05", "Special conditions", "Answer these honestly; they change which rules apply.")
        st.toggle("My PhD was awarded by a university outside the UAE", key=K + "phd_outside_uae",
                  disabled=not editable)
        if st.session_state.get(K + "phd_outside_uae"):
            theme.html('<div class="pf-note">The additional foreign-PhD requirements are checked manually by the '
                       'reviewer in this version of PromoFlow.</div>')
        st.toggle("I am applying early (my time in rank completes within 4 months of submission)",
                  key=K + "early_application", disabled=not editable)
        st.toggle("I am requesting the exceptional-case rule (exceptional research volume, after 4 years)",
                  key=K + "exceptional_case", disabled=not editable)
        if st.session_state.get(K + "exceptional_case"):
            st.text_area("Justification for the exceptional case", key=K + "exceptional_justification",
                         max_chars=MAX_JUSTIFICATION, height=120, disabled=not editable,
                         help="PromoFlow does not judge this request: your Head of Department decides.")
        st.toggle("I applied before and the application was rejected", key=K + "previously_rejected",
                  disabled=not editable)
        if st.session_state.get(K + "previously_rejected"):
            st.date_input("Date of the rejection decision", key=K + "rejection_date",
                          min_value=date(2000, 1, 1), max_value=date.today(), format="DD/MM/YYYY",
                          disabled=not editable)


def _save_bar(user_id: int, today: date) -> None:
    st.write("")
    a, b = st.columns([1, 2.2], vertical_alignment="center")
    save = a.button("Save Section 0", type="primary", icon=":material/save:", use_container_width=True, key="s0_save")
    b.caption("Your answers are saved as a draft. Nothing is submitted until the final Review & submit step.")
    if not save:
        return
    values = _values()
    errors = validate_section0(values, today)
    if errors:
        theme.html('<div class="pf-err"><b>Please fix the following before saving:</b><ul>'
                   + "".join(f"<li>{theme.esc(e)}</li>" for e in errors) + "</ul></div>")
        return
    try:
        with session_scope() as s:
            case_id = s0.save(s, user_id, values, today)
    except s0.CaseLocked as e:
        st.error(str(e))
        return
    st.session_state[K + "loaded"] = case_id
    st.session_state[K + "flash"] = "Section 0 saved."
    st.rerun()


def _glance_card(ctx, today) -> None:
    v = _values()
    track = v.get("track")
    on = assumed_submission_date(today)
    rank_date, appointed = v.get("current_rank_date"), v.get("appointment_date")
    in_rank = f"{years_between(rank_date, on):.1f}" if rank_date else "–"
    here = f"{years_between(max(rank_date, appointed), on):.1f}" if rank_date and appointed else "–"
    checks = section0_checks(
        track=track, current_rank_date=rank_date, appointment_date=appointed,
        early_application=bool(v.get("early_application")), exceptional_case=bool(v.get("exceptional_case")),
        previously_rejected=bool(v.get("previously_rejected")), rejection_date=v.get("rejection_date"),
        criteria=ctx.criteria.get(track) if track else None, today=today,
    )
    rows = "".join(
        f'<div class="pf-check"><div class="ic {c.status}">{ICON[c.status]}</div><div><b>{theme.esc(c.label)}</b>'
        f'<small>{theme.esc(c.detail)}{" · " + theme.esc(c.policy_ref) if c.policy_ref else ""}</small></div></div>'
        for c in checks)
    with st.container(key="card_glance"):
        theme.card_header("✓", "At a glance", f"Calculated for {on:%d %b %Y}")
        theme.html(f"""
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:0 0 10px">
          <div class="pf-stat"><b>{in_rank}</b><span>years in rank</span></div>
          <div class="pf-stat"><b>{here}</b><span>years here in rank</span></div></div>
        {rows}
        <div class="pf-note" style="margin-top:12px">A preview only. The Eligibility Checker confirms everything
        when you submit, using your full dossier.</div>""")
