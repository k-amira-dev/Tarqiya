"""The "read my document for me" panels of Section 6: 6A (registrar report), 6C (student evaluation report), 6E (advisee lists).

Every panel works the same way, and never saves anything without the applicant's confirmation:
  1. the applicant chooses the file(s) and presses Read (reading costs a fraction of a cent and takes seconds);
  2. a PREVIEW table shows what was read, with the reason next to any row that has a problem; rows with problems start unticked;
  3. the applicant ticks, fixes and presses Add; only then are entries created (through the normal, validated add() functions).
"""
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import streamlit as st

from promoflow.db.session import session_scope
from promoflow.dossier.section6 import imports
from promoflow.extraction import teaching_docs as T
from promoflow.extraction.doc_llm import ReadFailed, Usage
from promoflow.extraction.pdf_text import extract_text
from promoflow.workflow import llm as llm_module


def _llm():
    try:
        return llm_module.get_extraction_llm()
    except llm_module.LLMNotConfigured:
        st.error("Automatic reading is not set up on this server (no model key). You can still enter everything by hand.", icon=":material/error:")
        return None


def _text_of(upload):
    """The text of an uploaded PDF, or None after telling the applicant why not (for example a scan: those need the picture reader)."""
    t = extract_text(upload.getvalue())
    if not t.ok:
        st.warning(f"{upload.name}: {t.message}", icon=":material/description:")
        return None
    return t.text


def _digest(*uploads) -> str:
    return hashlib.sha1(b"".join(u.getvalue() for u in uploads)).hexdigest()


def _notes(notes: list[str]) -> None:
    for n in notes:
        st.warning(n, icon=":material/warning:")


def _problem_text(issues: list[str]) -> str:
    return "; ".join(issues)


# ---- 6A ---------------------------------------------------------------------------------------------------------------

def registrar(upload) -> None:
    """Under the registrar-report uploader: read it and add every course in it."""
    key = "imp_reg"
    if st.button("Read this report and fill in my courses", icon=":material/auto_fix_high:", type="primary", key=key + "_read"):
        llm, text = _llm(), _text_of(upload)
        if llm is not None and text is not None:
            with st.spinner("Reading the report…"):
                try:
                    st.session_state[key] = {"digest": _digest(upload), "res": T.read_registrar_report(text, llm)}
                except ReadFailed as e:
                    st.error(str(e), icon=":material/error:")
                    st.session_state.pop(key, None)
    state = st.session_state.get(key)
    if not state or state["digest"] != _digest(upload):
        return
    res = state["res"]
    st.caption(f"Read {len(res.drafts)} rows ({res.usage.describe()}). Check them, then add.")
    _notes(res.notes)
    df = pd.DataFrame([{"Add": d.ok, "Semester": f"{d.semester.capitalize()} {d.academic_year}" if d.semester else "?", "Course": d.course_code,
                        "Title": d.course_title, "Level": d.level, "Students": d.students, "Problem": _problem_text(d.issues)} for d in res.drafts])
    edited = st.data_editor(df, hide_index=True, use_container_width=True, key=key + "_table",
                            disabled=["Semester", "Course", "Title", "Students", "Problem"],
                            column_config={"Level": st.column_config.SelectboxColumn(options=["undergraduate", "graduate"], required=True)})
    chosen = [(d, lvl) for d, lvl, add in zip(res.drafts, edited["Level"], edited["Add"]) if add and d.ok]
    if st.button(f"Add {len(chosen)} courses and keep the report", type="primary", icon=":material/playlist_add:", key=key + "_add", disabled=not chosen):
        for d, lvl in chosen:
            d.level = lvl
        with session_scope() as s:
            report = imports.add_courses(s, st.session_state["current_user"].id, [d for d, _ in chosen], (upload.name, upload.getvalue()))
        st.session_state.pop(key, None)
        st.session_state["s6_flash"] = report.describe("courses")
        st.rerun()


# ---- 6C ---------------------------------------------------------------------------------------------------------------

def evaluations(courses: list) -> None:
    """At the top of 6C: read one evaluation report and add an entry for every course in it."""
    key = "imp_eval"
    with st.expander("Fill in many evaluations at once from one report", icon=":material/auto_fix_high:"):
        st.caption("Upload the student evaluation report that lists your courses. Each course must already be in 6A.")
        upload = st.file_uploader("Student evaluation report", type=["pdf"], key=key + "_file")
        if upload is None:
            return
        if not courses:
            st.info("Add your courses in 6A first.", icon=":material/info:")
            return
        if st.button("Read this report", icon=":material/auto_fix_high:", type="primary", key=key + "_read"):
            llm, text = _llm(), _text_of(upload)
            if llm is not None and text is not None:
                with st.spinner("Reading the report (a long table can take up to a minute)…"):
                    try:
                        st.session_state[key] = {"digest": _digest(upload), "res": T.read_student_evaluations(text, courses, llm), "text": text}
                    except ReadFailed as e:
                        st.error(str(e), icon=":material/error:")
                        st.session_state.pop(key, None)
        state = st.session_state.get(key)
        if not state or state["digest"] != _digest(upload):
            return
        res = state["res"]
        scale = next((d.scale_max for d in res.drafts if d.scale_max), None)
        st.caption(f"Read {len(res.drafts)} rows ({res.usage.describe()}).")
        _notes(res.notes)
        df = pd.DataFrame([{"Add": d.ok, "Course": d.label, "Students": d.students, "Responses": d.respondents, "Instructor score": d.average_score,
                            "Problem": _problem_text(d.issues)} for d in res.drafts])
        edited = st.data_editor(df, hide_index=True, use_container_width=True, key=key + "_table",
                                disabled=["Course", "Students", "Responses", "Instructor score", "Problem"])
        chosen = [d for d, add in zip(res.drafts, edited["Add"]) if add and d.ok]
        st.caption(f"Scores are out of {scale:g}." if scale else "The scale of the scores was not found in the report.")
        if st.button(f"Add {len(chosen)} evaluations", type="primary", icon=":material/playlist_add:", key=key + "_add", disabled=not chosen):
            with session_scope() as s:
                report = imports.add_satisfaction(s, st.session_state["current_user"].id, chosen, (upload.name, upload.getvalue()))
            st.session_state.pop(key, None)
            st.session_state["s6_flash"] = report.describe("student evaluations")
            st.rerun()


# ---- 6E ---------------------------------------------------------------------------------------------------------------

def _read_one(upload_name: str, data: bytes, llm):
    """Runs in a worker thread (no Streamlit calls in here)."""
    t = extract_text(data)
    if not t.ok:
        return upload_name, None, t.message, Usage()
    try:
        name, d, parsed, usage = T.read_advisee_list(upload_name, data, t.text, llm)
        return name, (d, parsed), None, usage
    except (ReadFailed, T.PrivacyError) as e:
        return upload_name, None, str(e), Usage()


def advising() -> None:
    """At the top of 6E: read several advisee lists (one per semester) and add one advising semester for each."""
    key = "imp_adv"
    with st.expander("Fill in many semesters at once from the advisee lists", icon=":material/auto_fix_high:"):
        st.caption("Upload the advisee lists of several semesters together. Student names and IDs are removed before the lists are read; "
                   "the warning figures are worked out by comparing one semester with the previous one.")
        uploads = st.file_uploader("Advisee lists", type=["pdf"], accept_multiple_files=True, key=key + "_files")
        if not uploads:
            return
        digest = _digest(*uploads)
        if st.button(f"Read {len(uploads)} lists", icon=":material/auto_fix_high:", type="primary", key=key + "_read"):
            llm = _llm()
            if llm is not None:
                items, problems, total = [], [], Usage()
                bar = st.progress(0.0, text="Reading…")
                with ThreadPoolExecutor(max_workers=3) as pool:
                    futures = [pool.submit(_read_one, u.name, u.getvalue(), llm) for u in uploads]
                    for done, f in enumerate(as_completed(futures), 1):
                        name, ok, err, usage = f.result()
                        total += usage
                        (items.append((name, *ok)) if ok else problems.append(f"{name}: {err}"))
                        bar.progress(done / len(futures), text=f"Read {done} of {len(futures)}")
                bar.empty()
                st.session_state[key] = {"digest": digest, "drafts": T.build_advising_drafts([(n, d, p) for n, d, p in items]), "problems": problems, "usage": total}
        state = st.session_state.get(key)
        if not state or state["digest"] != digest:
            return
        for p in state["problems"]:
            st.error(p, icon=":material/error:")
        drafts = state["drafts"]
        st.caption(f"Read {len(drafts)} lists ({state['usage'].describe()}). Fill in any empty number, then add.")
        df = pd.DataFrame([{"Add": all(v is not None for v in (d.meetings_held, d.on_warning_at_start, d.cleared_warning, d.improved_gpa)),
                            "Semester": d.label, "Advisees": d.advisees, "Meetings": d.meetings_held, "On warning at start": d.on_warning_at_start,
                            "Cleared warning": d.cleared_warning, "Improved GPA": d.improved_gpa, "Notes": _problem_text(d.issues)} for d in drafts])
        edited = st.data_editor(df, hide_index=True, use_container_width=True, key=key + "_table", disabled=["Semester", "Advisees", "Notes"])
        chosen = []
        for d, (_, row) in zip(drafts, edited.iterrows()):
            if row["Add"]:
                d.meetings_held, d.on_warning_at_start, d.cleared_warning, d.improved_gpa = (None if pd.isna(row[c]) else int(row[c]) for c in
                                                                                             ("Meetings", "On warning at start", "Cleared warning", "Improved GPA"))
                chosen.append(d)
        if st.button(f"Add {len(chosen)} semesters", type="primary", icon=":material/playlist_add:", key=key + "_add", disabled=not chosen):
            with session_scope() as s:
                report = imports.add_advising(s, st.session_state["current_user"].id, chosen)
            st.session_state.pop(key, None)
            st.session_state["s6_flash"] = report.describe("advising semesters") + ("" if not report.rejected else " " + "; ".join(report.rejected[:3]))
            st.rerun()
