"""6C · Student satisfaction report — the tab inside the Section 6 (Teaching & Academic Advising) page."""
import streamlit as st

from promoflow.db.models import CourseTaught
from promoflow.db.session import session_scope
from promoflow.dossier.section6 import satisfaction as s6c
from promoflow.ui import theme

K = "s6c_"


def render(rows: list[s6c.SatisfactionRow], courses: list[CourseTaught], course_options: dict[int, str],
          editable: bool) -> None:
    coverage = s6c.coverage(rows, courses)
    if courses:
        theme.html(f'<div class="pf-note">Coverage: {coverage:.0%} of course-semesters have a satisfaction '
                  "report.</div>")
    editing = st.session_state.get(K + "editing")
    for row in rows:
        if editing == row.report.id:
            _form(editable, course_options, row)
        else:
            _summary(row, course_options, editable)
    if editable:
        if editing == "new":
            _form(editable, course_options, None)
        elif not course_options:
            st.info("Add a course in 6A first.", icon=":material/info:")
        elif st.button("+ Add a satisfaction report", key="s6c_add"):
            st.session_state[K + "editing"] = "new"
            st.rerun()


def _summary(row: s6c.SatisfactionRow, course_options: dict[int, str], editable: bool) -> None:
    r = row.report
    with st.container(key=f"card_satisfaction_{r.id}"):
        a, b = st.columns([5, 1])
        with a:
            theme.html(f"""<div class="pf-card-h"><h3>{theme.esc(course_options.get(r.course_taught_id, "—"))}</h3></div>
            <div class="pf-card-sub" style="margin-left:0">Score {r.average_score}/{r.scale_max} ·
            {r.respondents} respondents</div>""")
        with b:
            if editable:
                if st.button("Edit", key=f"s6c_edit_{r.id}", use_container_width=True):
                    st.session_state[K + "editing"] = r.id
                    st.rerun()
                if st.button("Delete", key=f"s6c_del_{r.id}", use_container_width=True):
                    with session_scope() as s:
                        s6c.delete(s, st.session_state["current_user"].id, r.id)
                    st.session_state["s6_flash"] = "Satisfaction report removed."
                    st.rerun()


@st.fragment
def _form(editable: bool, course_options: dict[int, str], row: "s6c.SatisfactionRow | None") -> None:
    r = row.report if row else None
    prefix = f"s6c_f_{r.id if r else 'new'}_"
    course_ids = list(course_options)
    with st.container(key=f"card_satisfaction_form_{r.id if r else 'new'}"):
        theme.card_header("+", "Edit satisfaction report" if r else "Add a satisfaction report")
        course_taught_id = st.selectbox("Course", course_ids, format_func=course_options.get,
                                        index=course_ids.index(r.course_taught_id) if r else None,
                                        placeholder="Choose a course", key=prefix + "course")
        a, b, c = st.columns(3)
        respondents = a.number_input("Number of respondents", min_value=0, step=1,
                                     value=r.respondents if r else 0, key=prefix + "respondents")
        average_score = b.number_input("Average score", min_value=0.0, step=0.1,
                                       value=float(r.average_score) if r else 0.0, key=prefix + "avg")
        scale_max = c.number_input("Scale maximum", min_value=0.0, step=0.1,
                                   value=float(r.scale_max) if r else 5.0, key=prefix + "scale")
        label = "Satisfaction report" if row is None or row.evidence is None else "Replace satisfaction report"
        upload = st.file_uploader(label, type=["pdf"], key=prefix + "evidence")

        values = {"course_taught_id": course_taught_id, "respondents": int(respondents),
                 "average_score": average_score, "scale_max": scale_max}
        upload_tuple = (upload.name, upload.getvalue()) if upload is not None else None

        save_col, cancel_col = st.columns([1, 1])
        if save_col.button("Save", type="primary", icon=":material/save:", key=prefix + "save",
                           use_container_width=True):
            user_id = st.session_state["current_user"].id
            with session_scope() as s:
                errors = s6c.validate(s, values, row.evidence is not None if row else False, upload_tuple)
                if errors:
                    theme.html('<div class="pf-err"><b>Please fix the following:</b><ul>'
                              + "".join(f"<li>{theme.esc(e)}</li>" for e in errors) + "</ul></div>")
                    return
                if r is None:
                    s6c.add(s, user_id, values, upload_tuple)
                else:
                    s6c.update(s, user_id, r.id, values, upload_tuple)
            st.session_state.pop(K + "editing", None)
            st.session_state["s6_flash"] = "Satisfaction report saved."
            st.rerun()
        if cancel_col.button("Cancel", key=prefix + "cancel", use_container_width=True):
            st.session_state.pop(K + "editing", None)
            st.rerun()
