"""7A-1 · Committee membership — the tab inside the Section 7 (University & Community Service) page."""
from datetime import date

import streamlit as st

from promoflow.db.enums import OrgLevel
from promoflow.db.session import session_scope
from promoflow.dossier.section7 import committees as s7a1
from promoflow.ui import theme
from promoflow.ui.views.section7.lookups import committee_role_options

K = "s7a1_"
LEVEL_LABEL = {OrgLevel.DEPARTMENT: "Department", OrgLevel.COLLEGE: "College", OrgLevel.UNIVERSITY: "University"}


def render(rows: list[s7a1.CommitteeRow], editable: bool) -> None:
    editing = st.session_state.get(K + "editing")
    for row in rows:
        if editing == row.membership.id:
            _form(editable, row)
        else:
            _summary(row, editable)
    if editable:
        if editing == "new":
            _form(editable, None)
        elif st.button("+ Add a committee membership", key="s7a1_add"):
            st.session_state[K + "editing"] = "new"
            st.rerun()


def _summary(row: s7a1.CommitteeRow, editable: bool) -> None:
    m = row.membership
    roles = {o.id: o.label for o in committee_role_options()}
    with st.container(key=f"card_committee_{m.id}"):
        a, b = st.columns([5, 1])
        with a:
            to = "ongoing" if m.date_to is None else f"{m.date_to:%b %Y}"
            theme.html(f"""<div class="pf-card-h"><h3>{theme.esc(m.committee_name)}</h3></div>
            <div class="pf-card-sub" style="margin-left:0">{LEVEL_LABEL[m.level]} ·
            {theme.esc(roles.get(m.role_id, ""))} · {m.date_from:%b %Y} – {to}</div>""")
        with b:
            if editable:
                if st.button("Edit", key=f"s7a1_edit_{m.id}", use_container_width=True):
                    st.session_state[K + "editing"] = m.id
                    st.rerun()
                if st.button("Delete", key=f"s7a1_del_{m.id}", use_container_width=True):
                    with session_scope() as s:
                        s7a1.delete(s, st.session_state["current_user"].id, m.id)
                    st.session_state["s7_flash"] = "Committee membership removed."
                    st.rerun()


@st.fragment
def _form(editable: bool, row: "s7a1.CommitteeRow | None") -> None:
    m = row.membership if row else None
    prefix = f"s7a1_f_{m.id if m else 'new'}_"
    today = date.today()
    roles = committee_role_options()
    role_ids = [r.id for r in roles]
    role_labels = {r.id: r.label for r in roles}
    with st.container(key=f"card_committee_form_{m.id if m else 'new'}"):
        theme.card_header("+", "Edit committee membership" if m else "Add a committee membership")
        committee_name = st.text_input("Committee name", value=m.committee_name if m else "",
                                       placeholder="e.g. Exams committee", key=prefix + "name")
        a, b = st.columns(2)
        level = a.selectbox("Level", list(OrgLevel), format_func=LEVEL_LABEL.get,
                            index=list(OrgLevel).index(m.level) if m else None, placeholder="Choose a level",
                            key=prefix + "level")
        role_id = b.selectbox("Role", role_ids, format_func=role_labels.get,
                              index=role_ids.index(m.role_id) if m else None, placeholder="Choose a role",
                              key=prefix + "role")
        c, d = st.columns(2)
        date_from = c.date_input("From", value=m.date_from if m else None, min_value=date(1970, 1, 1),
                                 max_value=today, format="DD/MM/YYYY", key=prefix + "from")
        is_ongoing = d.toggle("Ongoing", value=(m.date_to is None) if m else True, key=prefix + "ongoing")
        date_to = None
        if not is_ongoing:
            date_to = st.date_input("To", value=m.date_to if m else None, min_value=date(1970, 1, 1),
                                    max_value=today, format="DD/MM/YYYY", key=prefix + "to")
        contribution_summary = st.text_area("Contribution summary (optional)",
                                            value=(m.contribution_summary if m else "") or "",
                                            max_chars=s7a1.MAX_SUMMARY, key=prefix + "summary",
                                            help="Deliverables and outcomes.")
        label = "Evidence" if row is None or row.evidence is None else "Replace evidence"
        upload = st.file_uploader(label, type=["pdf"], key=prefix + "evidence",
                                  help="Appointment letter or minutes.")

        values = {"committee_name": committee_name.strip(), "level": level, "role_id": role_id,
                 "date_from": date_from, "date_to": date_to,
                 "contribution_summary": contribution_summary.strip() or None}
        upload_tuple = (upload.name, upload.getvalue()) if upload is not None else None

        save_col, cancel_col = st.columns([1, 1])
        if save_col.button("Save", type="primary", icon=":material/save:", key=prefix + "save",
                           use_container_width=True):
            errors = s7a1.validate(values, row.evidence is not None if row else False, upload_tuple)
            if errors:
                theme.html('<div class="pf-err"><b>Please fix the following:</b><ul>'
                          + "".join(f"<li>{theme.esc(e)}</li>" for e in errors) + "</ul></div>")
                return
            user_id = st.session_state["current_user"].id
            with session_scope() as s:
                if m is None:
                    s7a1.add(s, user_id, values, upload_tuple)
                else:
                    s7a1.update(s, user_id, m.id, values, upload_tuple)
            st.session_state.pop(K + "editing", None)
            st.session_state["s7_flash"] = "Committee membership saved."
            st.rerun()
        if cancel_col.button("Cancel", key=prefix + "cancel", use_container_width=True):
            st.session_state.pop(K + "editing", None)
            st.rerun()
