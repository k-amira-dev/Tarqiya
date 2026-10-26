"""7A-4 · Training or educational activity delivered — the tab inside the Section 7 (University &
Community Service) page."""
from datetime import date

import streamlit as st

from promoflow.ui.views import entries_ui

from promoflow.db.session import session_scope
from promoflow.dossier.section7 import trainings as s7a4
from promoflow.ui import theme

K = "s7a4_"


def render(rows: list[s7a4.TrainingRow], editable: bool) -> None:
    if editable:
        entries_ui.panel("training", "s7_flash")
    editing = st.session_state.get(K + "editing")
    for row in rows:
        if editing == row.training.id:
            _form(editable, row)
        else:
            _summary(row, editable)
    if editable:
        if editing == "new":
            _form(editable, None)
        elif st.button("+ Add a training activity", key="s7a4_add"):
            st.session_state[K + "editing"] = "new"
            st.rerun()


def _summary(row: s7a4.TrainingRow, editable: bool) -> None:
    t = row.training
    with st.container(key=f"card_training_{t.id}"):
        a, b = st.columns([5, 1])
        with a:
            theme.html(f"""<div class="pf-card-h"><h3>{theme.esc(t.title)}</h3></div>
            <div class="pf-card-sub" style="margin-left:0">{"Inside" if t.inside_university else "Outside"}
            the university · {theme.esc(t.host_organisation)} · {t.activity_date:%d %b %Y}</div>""")
        with b:
            if editable:
                if st.button("Edit", key=f"s7a4_edit_{t.id}", use_container_width=True):
                    st.session_state[K + "editing"] = t.id
                    st.rerun()
                if st.button("Delete", key=f"s7a4_del_{t.id}", use_container_width=True):
                    with session_scope() as s:
                        s7a4.delete(s, st.session_state["current_user"].id, t.id)
                    st.session_state["s7_flash"] = "Training activity removed."
                    st.rerun()


@st.fragment
def _form(editable: bool, row: "s7a4.TrainingRow | None") -> None:
    t = row.training if row else None
    prefix = f"s7a4_f_{t.id if t else 'new'}_"
    today = date.today()
    with st.container(key=f"card_training_form_{t.id if t else 'new'}"):
        theme.card_header("+", "Edit training activity" if t else "Add a training activity")
        title = st.text_input("Title", value=t.title if t else "", key=prefix + "title")
        a, b = st.columns(2)
        inside_university = a.toggle("Inside the university (off = outside)",
                                     value=bool(t.inside_university) if t else True, key=prefix + "inside")
        host_organisation = b.text_input("Host organisation", value=t.host_organisation if t else "",
                                         key=prefix + "host")
        c, d, e = st.columns(3)
        activity_date = c.date_input("Date", value=t.activity_date if t else None, min_value=date(1970, 1, 1),
                                     max_value=today, format="DD/MM/YYYY", key=prefix + "date")
        hours = d.number_input("Hours (optional)", min_value=0.0, step=0.5, value=float(t.hours) if t and t.hours else 0.0,
                               key=prefix + "hours")
        participants = e.number_input("Participants (optional)", min_value=0, step=1,
                                      value=t.participants if t and t.participants else 0, key=prefix + "participants")
        label = "Evidence" if row is None or row.evidence is None else "Replace evidence"
        upload = st.file_uploader(label, type=["pdf"], key=prefix + "evidence")

        values = {"title": title.strip(), "inside_university": inside_university,
                 "host_organisation": host_organisation.strip(), "activity_date": activity_date,
                 "hours": hours or None, "participants": int(participants) or None}
        upload_tuple = (upload.name, upload.getvalue()) if upload is not None else None

        save_col, cancel_col = st.columns([1, 1])
        if save_col.button("Save", type="primary", icon=":material/save:", key=prefix + "save",
                           use_container_width=True):
            errors = s7a4.validate(values, today, row.evidence is not None if row else False, upload_tuple)
            if errors:
                theme.html('<div class="pf-err"><b>Please fix the following:</b><ul>'
                          + "".join(f"<li>{theme.esc(e)}</li>" for e in errors) + "</ul></div>")
                return
            user_id = st.session_state["current_user"].id
            with session_scope() as s:
                if t is None:
                    s7a4.add(s, user_id, values, upload_tuple)
                else:
                    s7a4.update(s, user_id, t.id, values, upload_tuple)
            st.session_state.pop(K + "editing", None)
            st.session_state["s7_flash"] = "Training activity saved."
            st.rerun()
        if cancel_col.button("Cancel", key=prefix + "cancel", use_container_width=True):
            st.session_state.pop(K + "editing", None)
            st.rerun()
