"""7A-2 · Administrative position — the tab inside the Section 7 (University & Community Service) page."""
from datetime import date

import streamlit as st

from promoflow.db.session import session_scope
from promoflow.dossier.section7 import admin_positions as s7a2
from promoflow.ui import theme
from promoflow.ui.views.section7.lookups import admin_position_options

K = "s7a2_"


def render(rows: list[s7a2.AdminPositionRow], editable: bool) -> None:
    editing = st.session_state.get(K + "editing")
    for row in rows:
        if editing == row.position.id:
            _form(editable, row)
        else:
            _summary(row, editable)
    if editable:
        if editing == "new":
            _form(editable, None)
        elif st.button("+ Add an administrative position", key="s7a2_add"):
            st.session_state[K + "editing"] = "new"
            st.rerun()


def _summary(row: s7a2.AdminPositionRow, editable: bool) -> None:
    p = row.position
    positions = {o.id: o.label for o in admin_position_options()}
    with st.container(key=f"card_admin_{p.id}"):
        a, b = st.columns([5, 1])
        with a:
            to = "ongoing" if p.date_to is None else f"{p.date_to:%b %Y}"
            theme.html(f"""<div class="pf-card-h"><h3>{theme.esc(positions.get(p.position_id, ""))}</h3></div>
            <div class="pf-card-sub" style="margin-left:0">{theme.esc(p.unit)} ·
            {p.date_from:%b %Y} – {to}</div>""")
        with b:
            if editable:
                if st.button("Edit", key=f"s7a2_edit_{p.id}", use_container_width=True):
                    st.session_state[K + "editing"] = p.id
                    st.rerun()
                if st.button("Delete", key=f"s7a2_del_{p.id}", use_container_width=True):
                    with session_scope() as s:
                        s7a2.delete(s, st.session_state["current_user"].id, p.id)
                    st.session_state["s7_flash"] = "Administrative position removed."
                    st.rerun()


@st.fragment
def _form(editable: bool, row: "s7a2.AdminPositionRow | None") -> None:
    p = row.position if row else None
    prefix = f"s7a2_f_{p.id if p else 'new'}_"
    today = date.today()
    positions = admin_position_options()
    position_ids = [o.id for o in positions]
    position_labels = {o.id: o.label for o in positions}
    with st.container(key=f"card_admin_form_{p.id if p else 'new'}"):
        theme.card_header("+", "Edit administrative position" if p else "Add an administrative position")
        position_id = st.selectbox("Position", position_ids, format_func=position_labels.get,
                                   index=position_ids.index(p.position_id) if p else None,
                                   placeholder="Choose a position", key=prefix + "position")
        unit = st.text_input("Unit", value=p.unit if p else "", key=prefix + "unit")
        a, b = st.columns(2)
        date_from = a.date_input("From", value=p.date_from if p else None, min_value=date(1970, 1, 1),
                                 max_value=today, format="DD/MM/YYYY", key=prefix + "from")
        is_ongoing = b.toggle("Ongoing", value=(p.date_to is None) if p else True, key=prefix + "ongoing")
        date_to = None
        if not is_ongoing:
            date_to = st.date_input("To", value=p.date_to if p else None, min_value=date(1970, 1, 1),
                                    max_value=today, format="DD/MM/YYYY", key=prefix + "to")
        label = "Evidence" if row is None or row.evidence is None else "Replace evidence"
        upload = st.file_uploader(label, type=["pdf"], key=prefix + "evidence", help="Appointment letter.")

        values = {"position_id": position_id, "unit": unit.strip(), "date_from": date_from, "date_to": date_to}
        upload_tuple = (upload.name, upload.getvalue()) if upload is not None else None

        save_col, cancel_col = st.columns([1, 1])
        if save_col.button("Save", type="primary", icon=":material/save:", key=prefix + "save",
                           use_container_width=True):
            errors = s7a2.validate(values, row.evidence is not None if row else False, upload_tuple)
            if errors:
                theme.html('<div class="pf-err"><b>Please fix the following:</b><ul>'
                          + "".join(f"<li>{theme.esc(e)}</li>" for e in errors) + "</ul></div>")
                return
            user_id = st.session_state["current_user"].id
            with session_scope() as s:
                if p is None:
                    s7a2.add(s, user_id, values, upload_tuple)
                else:
                    s7a2.update(s, user_id, p.id, values, upload_tuple)
            st.session_state.pop(K + "editing", None)
            st.session_state["s7_flash"] = "Administrative position saved."
            st.rerun()
        if cancel_col.button("Cancel", key=prefix + "cancel", use_container_width=True):
            st.session_state.pop(K + "editing", None)
            st.rerun()
