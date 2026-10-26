"""6A · Course taught — the tab inside the Section 6 (Teaching & Academic Advising) page."""
from datetime import date

import streamlit as st

from promoflow.db.enums import CourseLevel, DeliveryMode, Semester, TeachingRole
from promoflow.db.models import CourseTaught
from promoflow.db.session import session_scope
from promoflow.dossier.section6 import courses as s6a
from promoflow.ui import theme
from promoflow.ui.views.section6 import imports_ui

K = "s6a_"
SEMESTER_LABEL = {Semester.FALL: "Fall", Semester.SPRING: "Spring", Semester.SUMMER: "Summer"}
LEVEL_LABEL = {CourseLevel.UNDERGRADUATE: "Undergraduate", CourseLevel.GRADUATE: "Graduate"}
ROLE_LABEL = {TeachingRole.INSTRUCTOR: "Instructor", TeachingRole.INSTRUCTOR_COORDINATOR: "Instructor and course coordinator"}
DELIVERY_LABEL = {DeliveryMode.FACE_TO_FACE: "Face-to-face", DeliveryMode.BLENDED: "Blended", DeliveryMode.ONLINE: "Online"}


def render(courses: list[CourseTaught], report, case_id: int, editable: bool) -> None:
    with st.container(key="card_registrar_report"):
        theme.card_header("01", "Registrar teaching-load report", "One file for the whole list (spec 6A).")
        if report is not None:
            theme.html(f'<div class="pf-note">Current file: {theme.esc(report.original_filename)}, '
                      f'uploaded {report.uploaded_at:%d %b %Y}.</div>')
        if editable:
            label = "Registrar report" if report is None else "Replace registrar report"
            upload = st.file_uploader(label, type=["pdf"], key=K + "report")
            if upload is not None:
                imports_ui.registrar(upload)
            if upload is not None and st.button("Upload report", icon=":material/save:", key=K + "report_save"):
                with session_scope() as s:
                    s6a.save_registrar_report(s, case_id, st.session_state["current_user"].id,
                                             (upload.name, upload.getvalue()))
                st.session_state["s6_flash"] = "Registrar report uploaded."
                st.rerun()

    summary = s6a.diversity(courses)
    if courses:
        with st.container(key="card_diversity"):
            theme.card_header("02", "Diversity of courses taught", "Appendix E item 3.")
            theme.html(f"""<div class="pf-stat" style="max-width:220px"><b>{summary.distinct_courses}</b>
            <span>distinct courses of {summary.total_rows} rows</span></div>""")

    editing = st.session_state.get(K + "editing")
    for c in courses:
        if editing == c.id:
            _form(editable, c)
        else:
            _summary(c, editable)
    if editable:
        if editing == "new":
            _form(editable, None)
        elif st.button("+ Add a course", key="s6a_add"):
            st.session_state[K + "editing"] = "new"
            st.rerun()


def _summary(c: CourseTaught, editable: bool) -> None:
    with st.container(key=f"card_course_{c.id}"):
        a, b = st.columns([5, 1])
        with a:
            theme.html(f"""<div class="pf-card-h"><h3>{theme.esc(c.course_code)} · {theme.esc(c.course_title)}</h3></div>
            <div class="pf-card-sub" style="margin-left:0">{c.academic_year} {SEMESTER_LABEL[c.semester]} ·
            {LEVEL_LABEL[c.level]} · {c.students} students · {ROLE_LABEL[c.role]}</div>""")
        with b:
            if editable:
                if st.button("Edit", key=f"s6a_edit_{c.id}", use_container_width=True):
                    st.session_state[K + "editing"] = c.id
                    st.rerun()
                if st.button("Delete", key=f"s6a_del_{c.id}", use_container_width=True):
                    with session_scope() as s:
                        s6a.delete(s, st.session_state["current_user"].id, c.id)
                    st.session_state["s6_flash"] = "Course removed."
                    st.rerun()


@st.fragment
def _form(editable: bool, c: "CourseTaught | None") -> None:
    prefix = f"s6a_f_{c.id if c else 'new'}_"
    with st.container(key=f"card_course_form_{c.id if c else 'new'}"):
        theme.card_header("+", "Edit course" if c else "Add a course")
        a, b = st.columns(2)
        academic_year = a.text_input("Academic year", value=c.academic_year if c else "",
                                     placeholder="2025/2026", key=prefix + "year")
        semester = b.selectbox("Semester", list(Semester), format_func=SEMESTER_LABEL.get,
                               index=list(Semester).index(c.semester) if c else None,
                               placeholder="Choose a semester", key=prefix + "semester")
        d, e = st.columns(2)
        course_code = d.text_input("Course code", value=c.course_code if c else "", key=prefix + "code")
        course_title = e.text_input("Course title", value=c.course_title if c else "", key=prefix + "title")
        f, g = st.columns(2)
        level = f.selectbox("Level", list(CourseLevel), format_func=LEVEL_LABEL.get,
                            index=list(CourseLevel).index(c.level) if c else None,
                            placeholder="Choose a level", key=prefix + "level")
        role = g.selectbox("Role", list(TeachingRole), format_func=ROLE_LABEL.get,
                           index=list(TeachingRole).index(c.role) if c else None,
                           placeholder="Choose a role", key=prefix + "role")
        h, i = st.columns(2)
        sections = h.number_input("Number of sections", min_value=1, step=1, value=c.sections if c else 1,
                                  key=prefix + "sections")
        students = i.number_input("Number of students", min_value=0, step=1, value=c.students if c else 0,
                                  key=prefix + "students")
        delivery_mode = st.selectbox("Delivery mode", list(DeliveryMode), format_func=DELIVERY_LABEL.get,
                                     index=list(DeliveryMode).index(c.delivery_mode) if c else None,
                                     placeholder="Choose a delivery mode", key=prefix + "delivery")

        values = {"academic_year": academic_year.strip(), "semester": semester, "course_code": course_code.strip(),
                 "course_title": course_title.strip(), "level": level, "sections": int(sections),
                 "students": int(students), "role": role, "delivery_mode": delivery_mode}

        save_col, cancel_col = st.columns([1, 1])
        if save_col.button("Save course", type="primary", icon=":material/save:", key=prefix + "save",
                           use_container_width=True):
            errors = s6a.validate(values)
            if errors:
                theme.html('<div class="pf-err"><b>Please fix the following:</b><ul>'
                          + "".join(f"<li>{theme.esc(e)}</li>" for e in errors) + "</ul></div>")
                return
            user_id = st.session_state["current_user"].id
            with session_scope() as s:
                if c is None:
                    s6a.add(s, user_id, values)
                else:
                    s6a.update(s, user_id, c.id, values)
            st.session_state.pop(K + "editing", None)
            st.session_state["s6_flash"] = "Course saved."
            st.rerun()
        if cancel_col.button("Cancel", key=prefix + "cancel", use_container_width=True):
            st.session_state.pop(K + "editing", None)
            st.rerun()
