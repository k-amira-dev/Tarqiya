"""Section 4 – Academic Ranks & Experience (spec chapter 8)."""
from datetime import date

import streamlit as st

from promoflow.countries import COUNTRY_CODES, country_name
from promoflow.db.enums import Rank
from promoflow.db.session import session_scope
from promoflow.dossier import section4 as s4
from promoflow.dossier.section0 import EDITABLE
from promoflow.ui import theme

K = "s4_"
RANK_LABEL = {Rank.LECTURER: "Lecturer", Rank.ASSISTANT_PROFESSOR: "Assistant Professor",
             Rank.ASSOCIATE_PROFESSOR: "Associate Professor", Rank.PROFESSOR: "Professor"}


def render() -> None:
    user = st.session_state["current_user"]
    today = date.today()
    with session_scope() as s:
        ctx = s4.load(s, user.id, today)

    theme.html("""
    <div class="pf-hero"><div class="crumb">MY PROMOTION · SECTION 4 OF 11</div>
    <h1>Academic Ranks &amp; Experience</h1>
    <p>Your rank history drives time-in-rank, so it's entered as structured data rather than a single PDF.</p>
    </div>""")

    if ctx.case_id is None:
        st.info("Save Section 0 (Applicant Details & Promotion Track) first — it creates your draft application.",
                icon=":material/info:")
        return

    editable = ctx.status in EDITABLE
    if flash := st.session_state.pop(K + "flash", None):
        st.success(flash, icon=":material/check_circle:")
    if not editable:
        st.info("This application has been submitted, so Section 4 is read-only.", icon=":material/lock:")
    else:
        for problem in s4.section_checks(ctx.ranks, ctx.current_rank):
            st.warning(problem, icon=":material/warning:")

    st.subheader("4A · Rank history", divider="gray")
    editing_rank = st.session_state.get(K + "editing_rank")
    for row in ctx.ranks:
        if editing_rank == row.rank.id:
            _rank_form(today, editable, row)
        else:
            _rank_summary(row, today, editable)
    if editable:
        if editing_rank == "new":
            _rank_form(today, editable, None)
        elif st.button("+ Add a rank", key="s4_add_rank"):
            st.session_state[K + "editing_rank"] = "new"
            st.rerun()

    st.subheader("4B · Non-academic positions (optional)", divider="gray")
    editing_pos = st.session_state.get(K + "editing_position")
    for row in ctx.positions:
        if editing_pos == row.position.id:
            _position_form(editable, row)
        else:
            _position_summary(row, editable)
    if editable:
        if editing_pos == "new":
            _position_form(editable, None)
        elif st.button("+ Add a non-academic position", key="s4_add_position"):
            st.session_state[K + "editing_position"] = "new"
            st.rerun()


def _rank_summary(row: s4.RankRow, today: date, editable: bool) -> None:
    r = row.rank
    with st.container(key=f"card_rank_{r.id}"):
        a, b = st.columns([5, 1])
        with a:
            period = f"{r.held_from:%b %Y} – {'now' if r.held_to is None else f'{r.held_to:%b %Y}'}"
            theme.html(f"""<div class="pf-card-h"><h3>{theme.esc(RANK_LABEL[r.rank])}</h3></div>
            <div class="pf-card-sub" style="margin-left:0">{theme.esc(r.university)},
            {theme.esc(country_name(r.country_code))} · {period} · {s4.rank_years(r, today):.1f} years</div>""")
            if not r.at_this_university and row.evidence is None:
                theme.html('<div class="pf-note">Missing: experience certificate (this rank was held elsewhere).</div>')
        with b:
            if editable:
                if st.button("Edit", key=f"s4_edit_rank_{r.id}", use_container_width=True):
                    st.session_state[K + "editing_rank"] = r.id
                    st.rerun()
                if st.button("Delete", key=f"s4_del_rank_{r.id}", use_container_width=True):
                    with session_scope() as s:
                        s4.delete_rank(s, st.session_state["current_user"].id, r.id)
                    st.session_state[K + "flash"] = "Rank entry removed."
                    st.rerun()


def _rank_form(today: date, editable: bool, row: "s4.RankRow | None") -> None:
    r = row.rank if row else None
    prefix = f"s4_rf_{r.id if r else 'new'}_"
    with st.container(key=f"card_rank_form_{r.id if r else 'new'}"):
        theme.card_header("+", "Edit rank" if r else "Add a rank")
        a, b = st.columns(2)
        rank = a.selectbox("Academic rank", list(Rank), format_func=RANK_LABEL.get,
                           index=list(Rank).index(r.rank) if r else None, placeholder="Choose a rank",
                           key=prefix + "rank")
        date_obtained = b.date_input("Date rank obtained", value=r.date_obtained if r else None,
                                     min_value=date(1960, 1, 1), max_value=today, format="DD/MM/YYYY",
                                     key=prefix + "obtained")
        c, d = st.columns(2)
        university = c.text_input("University granting the rank", value=r.university if r else "", key=prefix + "uni")
        country_code = d.selectbox("Location / country", COUNTRY_CODES, format_func=country_name,
                                   index=COUNTRY_CODES.index(r.country_code) if r else None,
                                   placeholder="Choose a country", key=prefix + "country")
        e, f = st.columns(2)
        held_from = e.date_input("Held from", value=r.held_from if r else None, min_value=date(1960, 1, 1),
                                 max_value=today, format="DD/MM/YYYY", key=prefix + "from")
        held_to = None
        if not f.toggle("This is my current rank (no end date)", value=(r.held_to is None) if r else True,
                        key=prefix + "current"):
            held_to = f.date_input("Held to", value=r.held_to if r else None, min_value=date(1960, 1, 1),
                                   max_value=today, format="DD/MM/YYYY", key=prefix + "to")
        at_this_university = st.toggle("Held at this university", value=bool(r.at_this_university) if r else True,
                                       key=prefix + "here")
        evidence_upload = None
        if not at_this_university:
            evidence_label = "Experience certificate" if row is None or row.evidence is None else "Replace experience certificate"
            evidence_upload = st.file_uploader(evidence_label, type=["pdf", "jpg", "jpeg", "png"],
                                               key=prefix + "evidence",
                                               help="Recommended when this rank was held at another university.")

        values = {"rank": rank, "date_obtained": date_obtained, "university": university.strip(),
                 "country_code": country_code, "held_from": held_from, "held_to": held_to,
                 "at_this_university": at_this_university}
        evidence_tuple = (evidence_upload.name, evidence_upload.getvalue()) if evidence_upload is not None else None

        save_col, cancel_col = st.columns([1, 1])
        if save_col.button("Save rank", type="primary", icon=":material/save:", key=prefix + "save",
                           use_container_width=True):
            errors = s4.validate_rank(values, today)
            if errors:
                theme.html('<div class="pf-err"><b>Please fix the following:</b><ul>'
                           + "".join(f"<li>{theme.esc(e)}</li>" for e in errors) + "</ul></div>")
                return
            user_id = st.session_state["current_user"].id
            with session_scope() as s:
                if r is None:
                    s4.add_rank(s, user_id, values, evidence_tuple)
                else:
                    s4.update_rank(s, user_id, r.id, values, evidence_tuple)
            st.session_state.pop(K + "editing_rank", None)
            st.session_state[K + "flash"] = "Rank entry saved."
            st.rerun()
        if cancel_col.button("Cancel", key=prefix + "cancel", use_container_width=True):
            st.session_state.pop(K + "editing_rank", None)
            st.rerun()


def _position_summary(row: s4.PositionRow, editable: bool) -> None:
    p = row.position
    with st.container(key=f"card_position_{p.id}"):
        a, b = st.columns([5, 1])
        with a:
            to = "present" if p.date_to is None else f"{p.date_to:%b %Y}"
            theme.html(f"""<div class="pf-card-h"><h3>{theme.esc(p.position)}</h3></div>
            <div class="pf-card-sub" style="margin-left:0">{theme.esc(p.employer)},
            {theme.esc(country_name(p.country_code))} · {p.date_from:%b %Y} – {to}</div>""")
        with b:
            if editable:
                if st.button("Edit", key=f"s4_edit_pos_{p.id}", use_container_width=True):
                    st.session_state[K + "editing_position"] = p.id
                    st.rerun()
                if st.button("Delete", key=f"s4_del_pos_{p.id}", use_container_width=True):
                    with session_scope() as s:
                        s4.delete_position(s, st.session_state["current_user"].id, p.id)
                    st.session_state[K + "flash"] = "Position removed."
                    st.rerun()


def _position_form(editable: bool, row: "s4.PositionRow | None") -> None:
    p = row.position if row else None
    prefix = f"s4_pf_{p.id if p else 'new'}_"
    with st.container(key=f"card_position_form_{p.id if p else 'new'}"):
        theme.card_header("+", "Edit non-academic position" if p else "Add a non-academic position")
        a, b = st.columns(2)
        position = a.text_input("Position", value=p.position if p else "", key=prefix + "position")
        employer = b.text_input("Employer", value=p.employer if p else "", key=prefix + "employer")
        c, d = st.columns(2)
        country_code = c.selectbox("Country", COUNTRY_CODES, format_func=country_name,
                                   index=COUNTRY_CODES.index(p.country_code) if p else None,
                                   placeholder="Choose a country", key=prefix + "country")
        today = date.today()
        date_from = d.date_input("From", value=p.date_from if p else None, min_value=date(1960, 1, 1),
                                 max_value=today, format="DD/MM/YYYY", key=prefix + "from")
        date_to = st.date_input("To (leave empty if ongoing)", value=p.date_to if p else None,
                                min_value=date(1960, 1, 1), max_value=today, format="DD/MM/YYYY", key=prefix + "to")
        evidence_label = "Employment certificate (optional)" if row is None or row.evidence is None else "Replace employment certificate"
        evidence_upload = st.file_uploader(evidence_label, type=["pdf", "jpg", "jpeg", "png"], key=prefix + "evidence")

        values = {"position": position.strip(), "employer": employer.strip(), "country_code": country_code,
                 "date_from": date_from, "date_to": date_to}
        evidence_tuple = (evidence_upload.name, evidence_upload.getvalue()) if evidence_upload is not None else None

        save_col, cancel_col = st.columns([1, 1])
        if save_col.button("Save position", type="primary", icon=":material/save:", key=prefix + "save",
                           use_container_width=True):
            errors = s4.validate_position(values)
            if errors:
                theme.html('<div class="pf-err"><b>Please fix the following:</b><ul>'
                           + "".join(f"<li>{theme.esc(e)}</li>" for e in errors) + "</ul></div>")
                return
            user_id = st.session_state["current_user"].id
            with session_scope() as s:
                if p is None:
                    s4.add_position(s, user_id, values, evidence_tuple)
                else:
                    s4.update_position(s, user_id, p.id, values, evidence_tuple)
            st.session_state.pop(K + "editing_position", None)
            st.session_state[K + "flash"] = "Non-academic position saved."
            st.rerun()
        if cancel_col.button("Cancel", key=prefix + "cancel", use_container_width=True):
            st.session_state.pop(K + "editing_position", None)
            st.rerun()
