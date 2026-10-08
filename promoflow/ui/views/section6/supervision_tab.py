"""6H · Graduate teaching & thesis supervision — the tab inside the Section 6 (Teaching & Academic
Advising) page."""
from datetime import date

import streamlit as st

from promoflow.db.enums import GraduateDegree, SupervisionRole, SupervisionStatus
from promoflow.db.session import session_scope
from promoflow.dossier.section6 import supervision as s6h
from promoflow.ui import theme

K = "s6h_"
DEGREE_LABEL = {GraduateDegree.MSC: "MSc", GraduateDegree.PHD: "PhD"}
ROLE_LABEL = {SupervisionRole.MAIN: "Main supervisor", SupervisionRole.ASSOCIATE: "Associate (co-)supervisor"}
STATUS_LABEL = {SupervisionStatus.IN_PROGRESS: "In progress", SupervisionStatus.GRADUATED: "Graduated"}


def render(rows: list[s6h.SupervisionRow], editable: bool) -> None:
    editing = st.session_state.get(K + "editing")
    for row in rows:
        if editing == row.supervision.id:
            _form(editable, row)
        else:
            _summary(row, editable)
    if editable:
        if editing == "new":
            _form(editable, None)
        elif st.button("+ Add a supervision", key="s6h_add"):
            st.session_state[K + "editing"] = "new"
            st.rerun()


def _summary(row: s6h.SupervisionRow, editable: bool) -> None:
    sup = row.supervision
    with st.container(key=f"card_supervision_{sup.id}"):
        a, b = st.columns([5, 1])
        with a:
            theme.html(f"""<div class="pf-card-h"><h3>{theme.esc(sup.thesis_title)}</h3></div>
            <div class="pf-card-sub" style="margin-left:0">{DEGREE_LABEL[sup.degree]} · {ROLE_LABEL[sup.role]} ·
            {STATUS_LABEL[sup.status]}</div>""")
        with b:
            if editable:
                if st.button("Edit", key=f"s6h_edit_{sup.id}", use_container_width=True):
                    st.session_state[K + "editing"] = sup.id
                    st.rerun()
                if st.button("Delete", key=f"s6h_del_{sup.id}", use_container_width=True):
                    with session_scope() as s:
                        s6h.delete(s, st.session_state["current_user"].id, sup.id)
                    st.session_state["s6_flash"] = "Supervision entry removed."
                    st.rerun()


@st.fragment
def _form(editable: bool, row: "s6h.SupervisionRow | None") -> None:
    sup = row.supervision if row else None
    prefix = f"s6h_f_{sup.id if sup else 'new'}_"
    today = date.today()
    with st.container(key=f"card_supervision_form_{sup.id if sup else 'new'}"):
        theme.card_header("+", "Edit supervision" if sup else "Add a supervision",
                          "The student's name is used only for matching against §5A author lists; never sent to the LLM.")
        student_name = st.text_input("Student", value=sup.student_name if sup else "", key=prefix + "student")
        a, b = st.columns(2)
        degree = a.selectbox("Degree", list(GraduateDegree), format_func=DEGREE_LABEL.get,
                             index=list(GraduateDegree).index(sup.degree) if sup else None,
                             placeholder="Choose a degree", key=prefix + "degree")
        role = b.selectbox("Supervision role", list(SupervisionRole), format_func=ROLE_LABEL.get,
                           index=list(SupervisionRole).index(sup.role) if sup else None,
                           placeholder="Choose a role", key=prefix + "role")
        thesis_title = st.text_input("Thesis title", value=sup.thesis_title if sup else "", key=prefix + "thesis")
        c, d = st.columns(2)
        start_date = c.date_input("Start date", value=sup.start_date if sup else None, min_value=date(1970, 1, 1),
                                  max_value=today, format="DD/MM/YYYY", key=prefix + "start")
        status = d.selectbox("Status", list(SupervisionStatus), format_func=STATUS_LABEL.get,
                             index=list(SupervisionStatus).index(sup.status) if sup else None,
                             placeholder="Choose a status", key=prefix + "status")
        graduation_date = None
        if status == SupervisionStatus.GRADUATED:
            graduation_date = st.date_input("Graduation date", value=sup.graduation_date if sup else None,
                                            min_value=date(1970, 1, 1), max_value=date(2100, 1, 1),
                                            format="DD/MM/YYYY", key=prefix + "grad")
        label = "Evidence" if row is None or row.evidence is None else "Replace evidence"
        upload = st.file_uploader(label, type=["pdf"], key=prefix + "evidence",
                                  help="Supervision appointment letter.")

        values = {"student_name": student_name.strip(), "degree": degree, "role": role,
                 "thesis_title": thesis_title.strip(), "start_date": start_date, "status": status,
                 "graduation_date": graduation_date}
        upload_tuple = (upload.name, upload.getvalue()) if upload is not None else None

        save_col, cancel_col = st.columns([1, 1])
        if save_col.button("Save", type="primary", icon=":material/save:", key=prefix + "save",
                           use_container_width=True):
            errors = s6h.validate(values, today, row.evidence is not None if row else False, upload_tuple)
            if errors:
                theme.html('<div class="pf-err"><b>Please fix the following:</b><ul>'
                          + "".join(f"<li>{theme.esc(e)}</li>" for e in errors) + "</ul></div>")
                return
            user_id = st.session_state["current_user"].id
            with session_scope() as s:
                if sup is None:
                    s6h.add(s, user_id, values, upload_tuple)
                else:
                    s6h.update(s, user_id, sup.id, values, upload_tuple)
            st.session_state.pop(K + "editing", None)
            st.session_state["s6_flash"] = "Supervision entry saved."
            st.rerun()
        if cancel_col.button("Cancel", key=prefix + "cancel", use_container_width=True):
            st.session_state.pop(K + "editing", None)
            st.rerun()
