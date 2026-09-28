"""6D · Curriculum development contribution — the tab inside the Section 6 (Teaching & Academic Advising) page."""
from datetime import date

import streamlit as st

from promoflow.db.enums import DevelopmentDepth, OrgLevel
from promoflow.db.session import session_scope
from promoflow.dossier.section6 import curriculum as s6d
from promoflow.ui import theme
from promoflow.ui.views.section6.lookups import course_change_options, curriculum_contribution_type_options

K = "s6d_"
ORG_LABEL = {OrgLevel.DEPARTMENT: "Department council", OrgLevel.COLLEGE: "College council",
            OrgLevel.UNIVERSITY: "University"}
DEPTH_LABEL = {DevelopmentDepth.DEEP: "Deep (book or objectives changed)", DevelopmentDepth.MILD: "Mild (partial content change)"}


def render(rows: list[s6d.CurriculumRow], editable: bool) -> None:
    editing = st.session_state.get(K + "editing")
    for row in rows:
        if editing == row.contribution.id:
            _form(editable, row)
        else:
            _summary(row, editable)
    if editable:
        if editing == "new":
            _form(editable, None)
        elif st.button("+ Add a curriculum contribution", key="s6d_add"):
            st.session_state[K + "editing"] = "new"
            st.rerun()


def _summary(row: s6d.CurriculumRow, editable: bool) -> None:
    c = row.contribution
    types = {o.id: o.label for o in curriculum_contribution_type_options()}
    with st.container(key=f"card_curriculum_{c.id}"):
        a, b = st.columns([5, 1])
        with a:
            theme.html(f"""<div class="pf-card-h"><h3>{theme.esc(c.course_or_program)}</h3></div>
            <div class="pf-card-sub" style="margin-left:0">{theme.esc(types.get(c.contribution_type_id, ""))} ·
            approved {c.approval_date:%d %b %Y}</div>""")
        with b:
            if editable:
                if st.button("Edit", key=f"s6d_edit_{c.id}", use_container_width=True):
                    st.session_state[K + "editing"] = c.id
                    st.rerun()
                if st.button("Delete", key=f"s6d_del_{c.id}", use_container_width=True):
                    with session_scope() as s:
                        s6d.delete(s, st.session_state["current_user"].id, c.id)
                    st.session_state["s6_flash"] = "Curriculum contribution removed."
                    st.rerun()


def _form(editable: bool, row: "s6d.CurriculumRow | None") -> None:
    c = row.contribution if row else None
    prefix = f"s6d_f_{c.id if c else 'new'}_"
    today = date.today()
    types = curriculum_contribution_type_options()
    type_ids = [t.id for t in types]
    type_labels = {t.id: t.label for t in types}
    type_codes = {t.id: t.code for t in types}
    changes = course_change_options()
    change_codes = {ch.code: ch.label for ch in changes}
    with st.container(key=f"card_curriculum_form_{c.id if c else 'new'}"):
        theme.card_header("+", "Edit curriculum contribution" if c else "Add a curriculum contribution")
        contribution_type_id = st.selectbox("Contribution type", type_ids, format_func=type_labels.get,
                                            index=type_ids.index(c.contribution_type_id) if c else None,
                                            placeholder="Choose a type", key=prefix + "type")
        is_modification = type_codes.get(contribution_type_id) == s6d.MODIFICATION_CODE
        course_or_program = st.text_input("Course or program", value=c.course_or_program if c else "",
                                          key=prefix + "course")
        selected_changes = []
        if is_modification:
            selected_changes = st.multiselect("What changed", list(change_codes), format_func=change_codes.get,
                                              default=(c.changes or []) if c else [], key=prefix + "changes")
        self_classification = st.selectbox("Applicant's own classification (optional)", [None] + list(DevelopmentDepth),
                                           format_func=lambda v: "—" if v is None else DEPTH_LABEL[v],
                                           index=(list(DevelopmentDepth).index(c.self_classification) + 1
                                                 if c and c.self_classification else 0),
                                           key=prefix + "depth")
        description = st.text_area("Description", value=(c.description if c else "") or "", max_chars=s6d.MAX_DESCRIPTION,
                                   key=prefix + "description")
        a, b = st.columns(2)
        approved_by = a.selectbox("Approved by", list(OrgLevel), format_func=ORG_LABEL.get,
                                  index=list(OrgLevel).index(c.approved_by) if c else None,
                                  placeholder="Choose a level", key=prefix + "approved_by")
        approval_date = b.date_input("Approval date", value=c.approval_date if c else None,
                                     min_value=date(1970, 1, 1), max_value=today, format="DD/MM/YYYY",
                                     key=prefix + "approval_date")
        label = "Evidence" if row is None or row.evidence is None else "Replace evidence"
        upload = st.file_uploader(label, type=["pdf"], key=prefix + "evidence",
                                  help="Approval minutes; old and new syllabus.")

        values = {"contribution_type_id": contribution_type_id, "course_or_program": course_or_program.strip(),
                 "changes": selected_changes or None, "self_classification": self_classification,
                 "description": description.strip(), "approved_by": approved_by, "approval_date": approval_date}
        upload_tuple = (upload.name, upload.getvalue()) if upload is not None else None

        save_col, cancel_col = st.columns([1, 1])
        if save_col.button("Save", type="primary", icon=":material/save:", key=prefix + "save",
                           use_container_width=True):
            errors = s6d.validate(values, today, is_modification, row.evidence is not None if row else False,
                                  upload_tuple)
            if errors:
                theme.html('<div class="pf-err"><b>Please fix the following:</b><ul>'
                          + "".join(f"<li>{theme.esc(e)}</li>" for e in errors) + "</ul></div>")
                return
            user_id = st.session_state["current_user"].id
            with session_scope() as s:
                if c is None:
                    s6d.add(s, user_id, values, upload_tuple)
                else:
                    s6d.update(s, user_id, c.id, values, upload_tuple)
            st.session_state.pop(K + "editing", None)
            st.session_state["s6_flash"] = "Curriculum contribution saved."
            st.rerun()
        if cancel_col.button("Cancel", key=prefix + "cancel", use_container_width=True):
            st.session_state.pop(K + "editing", None)
            st.rerun()
