"""7A-3 · Workshop or seminar organised / delivered — the tab inside the Section 7 (University & Community
Service) page."""
from datetime import date

import streamlit as st

from promoflow.db.enums import OrgLevel, WorkshopRole
from promoflow.db.session import session_scope
from promoflow.dossier.section7 import workshops as s7a3
from promoflow.ui import theme

K = "s7a3_"
LEVEL_LABEL = {OrgLevel.DEPARTMENT: "Department", OrgLevel.COLLEGE: "College", OrgLevel.UNIVERSITY: "University"}
ROLE_LABEL = {WorkshopRole.ORGANISER: "Organiser", WorkshopRole.LECTURER: "Lecturer",
             WorkshopRole.ORGANISER_AND_LECTURER: "Organiser and lecturer"}


def render(rows: list[s7a3.WorkshopRow], editable: bool) -> None:
    editing = st.session_state.get(K + "editing")
    for row in rows:
        if editing == row.workshop.id:
            _form(editable, row)
        else:
            _summary(row, editable)
    if editable:
        if editing == "new":
            _form(editable, None)
        elif st.button("+ Add a workshop or seminar", key="s7a3_add"):
            st.session_state[K + "editing"] = "new"
            st.rerun()


def _summary(row: s7a3.WorkshopRow, editable: bool) -> None:
    w = row.workshop
    with st.container(key=f"card_workshop_{w.id}"):
        a, b = st.columns([5, 1])
        with a:
            theme.html(f"""<div class="pf-card-h"><h3>{theme.esc(w.title)}</h3></div>
            <div class="pf-card-sub" style="margin-left:0">{LEVEL_LABEL[w.organized_by]} ·
            {ROLE_LABEL[w.role]} · {w.activity_date:%d %b %Y}</div>""")
        with b:
            if editable:
                if st.button("Edit", key=f"s7a3_edit_{w.id}", use_container_width=True):
                    st.session_state[K + "editing"] = w.id
                    st.rerun()
                if st.button("Delete", key=f"s7a3_del_{w.id}", use_container_width=True):
                    with session_scope() as s:
                        s7a3.delete(s, st.session_state["current_user"].id, w.id)
                    st.session_state["s7_flash"] = "Workshop removed."
                    st.rerun()


@st.fragment
def _form(editable: bool, row: "s7a3.WorkshopRow | None") -> None:
    w = row.workshop if row else None
    prefix = f"s7a3_f_{w.id if w else 'new'}_"
    today = date.today()
    with st.container(key=f"card_workshop_form_{w.id if w else 'new'}"):
        theme.card_header("+", "Edit workshop / seminar" if w else "Add a workshop or seminar")
        title = st.text_input("Title", value=w.title if w else "", key=prefix + "title")
        a, b = st.columns(2)
        organized_by = a.selectbox("Organised by", list(OrgLevel), format_func=LEVEL_LABEL.get,
                                   index=list(OrgLevel).index(w.organized_by) if w else None,
                                   placeholder="Choose a level", key=prefix + "org")
        role = b.selectbox("Applicant's role", list(WorkshopRole), format_func=ROLE_LABEL.get,
                           index=list(WorkshopRole).index(w.role) if w else None, placeholder="Choose a role",
                           key=prefix + "role")
        c, d = st.columns(2)
        activity_date = c.date_input("Date", value=w.activity_date if w else None, min_value=date(1970, 1, 1),
                                     max_value=today, format="DD/MM/YYYY", key=prefix + "date")
        attendees = d.number_input("Number of attendees (optional)", min_value=0, step=1,
                                   value=w.attendees if w and w.attendees else 0, key=prefix + "attendees")
        label = "Evidence" if row is None or row.evidence is None else "Replace evidence"
        upload = st.file_uploader(label, type=["pdf"], key=prefix + "evidence",
                                  help="Announcement, programme, certificate.")

        values = {"title": title.strip(), "organized_by": organized_by, "role": role,
                 "activity_date": activity_date, "attendees": int(attendees) or None}
        upload_tuple = (upload.name, upload.getvalue()) if upload is not None else None

        save_col, cancel_col = st.columns([1, 1])
        if save_col.button("Save", type="primary", icon=":material/save:", key=prefix + "save",
                           use_container_width=True):
            errors = s7a3.validate(values, today, row.evidence is not None if row else False, upload_tuple)
            if errors:
                theme.html('<div class="pf-err"><b>Please fix the following:</b><ul>'
                          + "".join(f"<li>{theme.esc(e)}</li>" for e in errors) + "</ul></div>")
                return
            user_id = st.session_state["current_user"].id
            with session_scope() as s:
                if w is None:
                    s7a3.add(s, user_id, values, upload_tuple)
                else:
                    s7a3.update(s, user_id, w.id, values, upload_tuple)
            st.session_state.pop(K + "editing", None)
            st.session_state["s7_flash"] = "Workshop saved."
            st.rerun()
        if cancel_col.button("Cancel", key=prefix + "cancel", use_container_width=True):
            st.session_state.pop(K + "editing", None)
            st.rerun()
