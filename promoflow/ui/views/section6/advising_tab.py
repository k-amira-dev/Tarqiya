"""6E · Academic advising — the tab inside the Section 6 (Teaching & Academic Advising) page."""
import streamlit as st

from promoflow.db.enums import Semester
from promoflow.db.session import session_scope
from promoflow.dossier.section6 import advising as s6e
from promoflow.ui import theme
from promoflow.ui.views.section6.courses_tab import SEMESTER_LABEL

K = "s6e_"


def render(rows: list[s6e.AdvisingRow], editable: bool) -> None:
    editing = st.session_state.get(K + "editing")
    for row in rows:
        if editing == row.semester.id:
            _form(editable, row)
        else:
            _summary(row, editable)
    if editable:
        if editing == "new":
            _form(editable, None)
        elif st.button("+ Add an advising semester", key="s6e_add"):
            st.session_state[K + "editing"] = "new"
            st.rerun()


def _summary(row: s6e.AdvisingRow, editable: bool) -> None:
    a = row.semester
    with st.container(key=f"card_advising_{a.id}"):
        col1, col2 = st.columns([5, 1])
        with col1:
            theme.html(f"""<div class="pf-card-h"><h3>{a.academic_year} {SEMESTER_LABEL[a.semester]}</h3></div>
            <div class="pf-card-sub" style="margin-left:0">{a.advisees} advisees · {a.meetings_held} meetings ·
            {a.cleared_warning}/{a.on_warning_at_start} cleared warning</div>""")
        with col2:
            if editable:
                if st.button("Edit", key=f"s6e_edit_{a.id}", use_container_width=True):
                    st.session_state[K + "editing"] = a.id
                    st.rerun()
                if st.button("Delete", key=f"s6e_del_{a.id}", use_container_width=True):
                    with session_scope() as s:
                        s6e.delete(s, st.session_state["current_user"].id, a.id)
                    st.session_state["s6_flash"] = "Advising semester removed."
                    st.rerun()


@st.fragment
def _form(editable: bool, row: "s6e.AdvisingRow | None") -> None:
    a = row.semester if row else None
    prefix = f"s6e_f_{a.id if a else 'new'}_"
    with st.container(key=f"card_advising_form_{a.id if a else 'new'}"):
        theme.card_header("+", "Edit advising semester" if a else "Add an advising semester")
        c1, c2 = st.columns(2)
        academic_year = c1.text_input("Academic year", value=a.academic_year if a else "",
                                      placeholder="2025/2026", key=prefix + "year")
        semester = c2.selectbox("Semester", list(Semester), format_func=SEMESTER_LABEL.get,
                                index=list(Semester).index(a.semester) if a else None,
                                placeholder="Choose a semester", key=prefix + "semester")
        c3, c4 = st.columns(2)
        advisees = c3.number_input("Number of advisees", min_value=0, step=1, value=a.advisees if a else 0,
                                   key=prefix + "advisees")
        meetings_held = c4.number_input("Advising meetings held", min_value=0, step=1,
                                        value=a.meetings_held if a else 0, key=prefix + "meetings")
        c5, c6, c7 = st.columns(3)
        on_warning = c5.number_input("On academic warning at start", min_value=0, step=1,
                                     value=a.on_warning_at_start if a else 0, key=prefix + "warning")
        cleared = c6.number_input("...cleared the warning", min_value=0, step=1,
                                  value=a.cleared_warning if a else 0, key=prefix + "cleared")
        improved = c7.number_input("...improved GPA without clearing", min_value=0, step=1,
                                   value=a.improved_gpa if a else 0, key=prefix + "improved")
        notes = st.text_area("Notes (optional)", value=(a.notes if a else "") or "", key=prefix + "notes")
        label = "Evidence" if row is None or row.evidence is None else "Replace evidence"
        upload = st.file_uploader(label, type=["pdf"], key=prefix + "evidence",
                                  help="Advisee list and meeting logs, student IDs anonymised.")

        values = {"academic_year": academic_year.strip(), "semester": semester, "advisees": int(advisees),
                 "meetings_held": int(meetings_held), "on_warning_at_start": int(on_warning),
                 "cleared_warning": int(cleared), "improved_gpa": int(improved), "notes": notes.strip() or None}
        upload_tuple = (upload.name, upload.getvalue()) if upload is not None else None

        save_col, cancel_col = st.columns([1, 1])
        if save_col.button("Save", type="primary", icon=":material/save:", key=prefix + "save",
                           use_container_width=True):
            errors = s6e.validate(values, row.evidence is not None if row else False, upload_tuple)
            if errors:
                theme.html('<div class="pf-err"><b>Please fix the following:</b><ul>'
                          + "".join(f"<li>{theme.esc(e)}</li>" for e in errors) + "</ul></div>")
                return
            user_id = st.session_state["current_user"].id
            with session_scope() as s:
                if a is None:
                    s6e.add(s, user_id, values, upload_tuple)
                else:
                    s6e.update(s, user_id, a.id, values, upload_tuple)
            st.session_state.pop(K + "editing", None)
            st.session_state["s6_flash"] = "Advising semester saved."
            st.rerun()
        if cancel_col.button("Cancel", key=prefix + "cancel", use_container_width=True):
            st.session_state.pop(K + "editing", None)
            st.rerun()
