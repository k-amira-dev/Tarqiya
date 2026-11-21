"""6F · Course files & coordination — the tab inside the Section 6 (Teaching & Academic Advising) page."""
import streamlit as st

from promoflow.ui.views import entries_ui

from promoflow.db.session import session_scope
from promoflow.dossier.section6 import course_files as s6f
from promoflow.ui import theme
from promoflow.ui.views.section6.lookups import course_file_item_options, course_file_system_options

K = "s6f_"


def render(rows: list[s6f.CourseFileRow], course_options: dict[int, str], editable: bool) -> None:
    if editable:
        entries_ui.add_bar(["course_file"], "s6_flash", K + "editing", blocked=not course_options, blocked_why="Add a course in 6A first.")
    editing = st.session_state.get(K + "editing")
    for row in rows:
        if editing == row.course_file.id:
            _form(editable, course_options, row)
        else:
            _summary(row, course_options, editable)
    if editable:
        if editing == "new":
            _form(editable, course_options, None)
        elif not course_options:
            st.info("Add a course in 6A first.", icon=":material/info:")


def _summary(row: s6f.CourseFileRow, course_options: dict[int, str], editable: bool) -> None:
    f = row.course_file
    with st.container(key=f"card_coursefile_{f.id}"):
        a, b = st.columns([5, 1])
        with a:
            theme.html(f"""<div class="pf-card-h"><h3>{theme.esc(course_options.get(f.course_taught_id, "—"))}</h3></div>
            <div class="pf-card-sub" style="margin-left:0">{"Coordinator" if f.is_coordinator else "Instructor"} ·
            {len(f.items or [])} items included</div>""")
        with b:
            if editable:
                if st.button("Edit", key=f"s6f_edit_{f.id}", use_container_width=True):
                    st.session_state[K + "editing"] = f.id
                    st.rerun()
                if st.button("Delete", key=f"s6f_del_{f.id}", use_container_width=True):
                    with session_scope() as s:
                        s6f.delete(s, st.session_state["current_user"].id, f.id)
                    st.session_state["s6_flash"] = "Course file removed."
                    st.rerun()


@st.fragment
def _form(editable: bool, course_options: dict[int, str], row: "s6f.CourseFileRow | None") -> None:
    f = row.course_file if row else None
    prefix = f"s6f_f_{f.id if f else 'new'}_"
    systems = course_file_system_options()
    system_ids = [o.id for o in systems]
    system_labels = {o.id: o.label for o in systems}
    items = course_file_item_options()
    item_codes = {i.code: i.label for i in items}
    course_ids = list(course_options)
    with st.container(key=f"card_coursefile_form_{f.id if f else 'new'}"):
        theme.card_header("+", "Edit course file" if f else "Add a course file")
        entries_ui.autofill("course_file", prefix)
        course_taught_id = st.selectbox("Course", course_ids, format_func=course_options.get,
                                        index=course_ids.index(f.course_taught_id) if f else None,
                                        placeholder="Choose a course", key=prefix + "course")
        is_coordinator = st.toggle("Course coordinator?", value=bool(f.is_coordinator) if f else False,
                                   key=prefix + "coordinator")
        kept_in_id = st.selectbox("Course file kept in", system_ids, format_func=system_labels.get,
                                  index=system_ids.index(f.kept_in_id) if f else None,
                                  placeholder="Choose a system", key=prefix + "kept_in")
        selected_items = st.multiselect("Items included", list(item_codes), format_func=item_codes.get,
                                        default=(f.items or []) if f else [], key=prefix + "items")
        label = "Evidence" if row is None or row.evidence is None else "Replace evidence"
        upload = st.file_uploader(label, type=["pdf"], key=prefix + "evidence", help="Course file export or report.")

        values = {"course_taught_id": course_taught_id, "is_coordinator": is_coordinator, "kept_in_id": kept_in_id,
                 "items": selected_items or None}
        upload_tuple = (upload.name, upload.getvalue()) if upload is not None else None

        save_col, cancel_col = st.columns([1, 1])
        if save_col.button("Save", type="primary", icon=":material/save:", key=prefix + "save",
                           use_container_width=True):
            errors = s6f.validate(values, row.evidence is not None if row else False, upload_tuple)
            if errors:
                theme.html('<div class="pf-err"><b>Please fix the following:</b><ul>'
                          + "".join(f"<li>{theme.esc(e)}</li>" for e in errors) + "</ul></div>")
                return
            user_id = st.session_state["current_user"].id
            with session_scope() as s:
                if f is None:
                    s6f.add(s, user_id, values, upload_tuple)
                else:
                    s6f.update(s, user_id, f.id, values, upload_tuple)
            st.session_state.pop(K + "editing", None)
            st.session_state["s6_flash"] = "Course file saved."
            st.rerun()
        if cancel_col.button("Cancel", key=prefix + "cancel", use_container_width=True):
            st.session_state.pop(K + "editing", None)
            st.rerun()
