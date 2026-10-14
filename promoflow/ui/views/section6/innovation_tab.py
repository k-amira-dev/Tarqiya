"""6G · Teaching innovation & educational technology — the tab inside the Section 6 (Teaching & Academic
Advising) page."""
import streamlit as st

from promoflow.db.session import session_scope
from promoflow.dossier.section6 import innovation as s6g
from promoflow.ui import theme
from promoflow.ui.views.section6.lookups import innovation_type_options

K = "s6g_"


def render(rows: list[s6g.InnovationRow], course_options: dict[int, str], editable: bool) -> None:
    editing = st.session_state.get(K + "editing")
    for row in rows:
        if editing == row.innovation.id:
            _form(editable, course_options, row)
        else:
            _summary(row, course_options, editable)
    if editable:
        if editing == "new":
            _form(editable, course_options, None)
        elif not course_options:
            st.info("Add a course in 6A first.", icon=":material/info:")
        elif st.button("+ Add a teaching innovation", key="s6g_add"):
            st.session_state[K + "editing"] = "new"
            st.rerun()


def _summary(row: s6g.InnovationRow, course_options: dict[int, str], editable: bool) -> None:
    i = row.innovation
    types = {o.id: o.label for o in innovation_type_options()}
    with st.container(key=f"card_innovation_{i.id}"):
        a, b = st.columns([5, 1])
        with a:
            theme.html(f"""<div class="pf-card-h"><h3>{theme.esc(types.get(i.innovation_type_id, ""))}</h3></div>
            <div class="pf-card-sub" style="margin-left:0">{theme.esc(course_options.get(i.course_taught_id, "—"))}</div>""")
        with b:
            if editable:
                if st.button("Edit", key=f"s6g_edit_{i.id}", use_container_width=True):
                    st.session_state[K + "editing"] = i.id
                    st.rerun()
                if st.button("Delete", key=f"s6g_del_{i.id}", use_container_width=True):
                    with session_scope() as s:
                        s6g.delete(s, st.session_state["current_user"].id, i.id)
                    st.session_state["s6_flash"] = "Teaching innovation removed."
                    st.rerun()


@st.fragment
def _form(editable: bool, course_options: dict[int, str], row: "s6g.InnovationRow | None") -> None:
    i = row.innovation if row else None
    prefix = f"s6g_f_{i.id if i else 'new'}_"
    types = innovation_type_options()
    type_ids = [t.id for t in types]
    type_labels = {t.id: t.label for t in types}
    course_ids = list(course_options)
    with st.container(key=f"card_innovation_form_{i.id if i else 'new'}"):
        theme.card_header("+", "Edit teaching innovation" if i else "Add a teaching innovation")
        innovation_type_id = st.selectbox("Type", type_ids, format_func=type_labels.get,
                                          index=type_ids.index(i.innovation_type_id) if i else None,
                                          placeholder="Choose a type", key=prefix + "type")
        course_taught_id = st.selectbox("Course", course_ids, format_func=course_options.get,
                                        index=course_ids.index(i.course_taught_id) if i else None,
                                        placeholder="Choose a course", key=prefix + "course")
        description = st.text_area("Description", value=(i.description if i else "") or "",
                                   help="What was done and how.", key=prefix + "description")
        measured_outcome = st.text_area("Measured outcome (optional)", value=(i.measured_outcome if i else "") or "",
                                        help="e.g. before/after results.", key=prefix + "outcome")
        label = "Evidence" if row is None or row.evidence is None else "Replace evidence"
        upload = st.file_uploader(label, type=["pdf", "jpg", "jpeg", "png"], key=prefix + "evidence",
                                  help="Materials, study report, screenshots.")

        values = {"innovation_type_id": innovation_type_id, "course_taught_id": course_taught_id,
                 "description": description.strip(), "measured_outcome": measured_outcome.strip() or None}
        upload_tuple = (upload.name, upload.getvalue()) if upload is not None else None

        save_col, cancel_col = st.columns([1, 1])
        if save_col.button("Save", type="primary", icon=":material/save:", key=prefix + "save",
                           use_container_width=True):
            errors = s6g.validate(values, row.evidence is not None if row else False, upload_tuple)
            if errors:
                theme.html('<div class="pf-err"><b>Please fix the following:</b><ul>'
                          + "".join(f"<li>{theme.esc(e)}</li>" for e in errors) + "</ul></div>")
                return
            user_id = st.session_state["current_user"].id
            with session_scope() as s:
                if i is None:
                    s6g.add(s, user_id, values, upload_tuple)
                else:
                    s6g.update(s, user_id, i.id, values, upload_tuple)
            st.session_state.pop(K + "editing", None)
            st.session_state["s6_flash"] = "Teaching innovation saved."
            st.rerun()
        if cancel_col.button("Cancel", key=prefix + "cancel", use_container_width=True):
            st.session_state.pop(K + "editing", None)
            st.rerun()
