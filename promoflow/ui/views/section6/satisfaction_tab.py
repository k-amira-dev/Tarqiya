"""6C · Student satisfaction report — the tab inside the Section 6 (Teaching & Academic Advising) page."""
import hashlib

import streamlit as st

from promoflow.db.models import CourseTaught
from promoflow.db.session import session_scope
from promoflow.dossier.section6 import satisfaction as s6c
from promoflow.extraction.pdf_text import extract_text
from promoflow.extraction.student_evaluation import extract_student_evaluation, match_course
from promoflow.ui import theme
from promoflow.ui.views.section6 import imports_ui
from promoflow.workflow import llm as llm_module

K = "s6c_"


def render(rows: list[s6c.SatisfactionRow], courses: list[CourseTaught], course_options: dict[int, str],
          editable: bool) -> None:
    if editable:
        imports_ui.evaluations(courses)
    coverage = s6c.coverage(rows, courses)
    if courses:
        theme.html(f'<div class="pf-note">Coverage: {coverage:.0%} of course-semesters have a satisfaction '
                  "report.</div>")
    editing = st.session_state.get(K + "editing")
    for row in rows:
        if editing == row.report.id:
            _form(editable, course_options, courses, row)
        else:
            _summary(row, course_options, editable)
    if editable:
        if editing == "new":
            _form(editable, course_options, courses, None)
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
def _form(editable: bool, course_options: dict[int, str], courses: list[CourseTaught],
          row: "s6c.SatisfactionRow | None") -> None:
    r = row.report if row else None
    prefix = f"s6c_f_{r.id if r else 'new'}_"
    course_ids = list(course_options)
    with st.container(key=f"card_satisfaction_form_{r.id if r else 'new'}"):
        theme.card_header("+", "Edit satisfaction report" if r else "Add a satisfaction report")
        # 1) The report comes FIRST: when a file is chosen, the boxes below are filled from it.
        label = "Satisfaction report" if row is None or row.evidence is None else "Replace satisfaction report"
        upload = st.file_uploader(label, type=["pdf"], key=prefix + "evidence")
        found = _autofill(prefix, upload, courses, course_ids)

        # 2) The boxes. Their starting values live in session_state so that the autofill can change them.
        st.session_state.setdefault(prefix + "course", r.course_taught_id if r else None)
        st.session_state.setdefault(prefix + "respondents", r.respondents if r else 0)
        st.session_state.setdefault(prefix + "avg", float(r.average_score) if r else 0.0)
        st.session_state.setdefault(prefix + "scale", float(r.scale_max) if r else 5.0)
        course_taught_id = st.selectbox("Course", course_ids, format_func=course_options.get,
                                        placeholder="Choose a course", key=prefix + "course")
        _course_note(found, course_taught_id)
        a, b, c = st.columns(3)
        respondents = a.number_input("Number of respondents", min_value=0, step=1, key=prefix + "respondents")
        average_score = b.number_input("Average score", min_value=0.0, step=0.1, key=prefix + "avg")
        scale_max = c.number_input("Scale maximum", min_value=0.0, step=0.1, key=prefix + "scale")
        _value_note(found, "respondents", int(respondents), a)
        _value_note(found, "average_score", average_score, b)
        _value_note(found, "scale_max", scale_max, c)

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


# ---- autofill from the uploaded report ---------------------------------------------------------------------------

def _autofill(prefix: str, upload, courses: list[CourseTaught], course_ids: list[int]) -> dict | None:
    """Read the chosen PDF once and put what it says into the form's boxes. Returns what was found (for the notes).

    The boxes are only changed when a NEW file is chosen, so anything the applicant then edits is kept. The values are
    suggestions: the applicant checks them, and the original line from the document is shown next to each one."""
    if upload is None:
        for k in ("digest", "found"):
            st.session_state.pop(prefix + k, None)
        return None
    data = upload.getvalue()
    digest = hashlib.sha1(data).hexdigest()
    if st.session_state.get(prefix + "digest") != digest:
        with st.spinner("Reading the document…"):
            text = extract_text(data)
            if not text.ok:
                result = {"message": text.message, "fields": None, "warnings": []}
            else:
                try:
                    llm = llm_module.get_llm()
                except llm_module.LLMNotConfigured:
                    llm = None
                fields = extract_student_evaluation(text.text, llm)
                course_id = match_course(fields, courses)
                if course_id in course_ids:
                    st.session_state[prefix + "course"] = course_id
                if fields.respondents:
                    st.session_state[prefix + "respondents"] = int(fields.respondents.value)
                if fields.average_score:
                    st.session_state[prefix + "avg"] = float(fields.average_score.value)
                if fields.scale_max:
                    st.session_state[prefix + "scale"] = float(fields.scale_max.value)
                result = {"message": None, "fields": fields, "warnings": fields.warnings, "course_id": course_id}
        st.session_state[prefix + "digest"] = digest
        st.session_state[prefix + "found"] = result
    found = st.session_state.get(prefix + "found")
    if found is None:
        return None
    if found["fields"] is None:
        st.warning(found["message"], icon=":material/description:")
    else:
        f = found["fields"]
        left = f.missing() + ([] if found.get("course_id") else ["course"])
        msg = "We filled the boxes below from the document. Please check every value."
        if left:
            msg += " Please fill in yourself: " + ", ".join(n.replace("_", " ") for n in left) + "."
        st.info(msg, icon=":material/auto_fix_high:")
        for w in found["warnings"]:
            st.warning(w, icon=":material/warning:")
    return found


def _course_note(found: dict | None, chosen_id: int | None) -> None:
    """Under the Course box: which line of the document named the course, or that another course was chosen."""
    if not found or found["fields"] is None or found["fields"].course_code is None:
        return
    item = found["fields"].course_code
    if chosen_id is not None and found.get("course_id") == chosen_id:
        st.caption(f"Read from the document: “{item.snippet}”")
    else:
        st.caption(f"The document names {item.value}: “{item.snippet}”")


def _value_note(found: dict | None, name: str, current, column) -> None:
    """Under a number box: the line the value was read from, or that the applicant changed it."""
    if not found or found["fields"] is None or getattr(found["fields"], name) is None:
        return
    item = getattr(found["fields"], name)
    if float(current) == float(item.value):
        column.caption(f"Read from the document: “{item.snippet}”")
    else:
        column.caption(f"You changed this. The document says {item.value:g}: “{item.snippet}”")
