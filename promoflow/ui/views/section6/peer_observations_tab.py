"""6B · Peer observation report — the tab inside the Section 6 (Teaching & Academic Advising) page."""
from datetime import date

import streamlit as st

from promoflow.db.session import session_scope
from promoflow.dossier.section6 import peer_observations as s6b
from promoflow.ui import theme
from promoflow.ui.views.section6.lookups import observer_role_options

K = "s6b_"


def render(rows: list[s6b.PeerObservationRow], course_options: dict[int, str], editable: bool) -> None:
    editing = st.session_state.get(K + "editing")
    for row in rows:
        if editing == row.observation.id:
            _form(editable, course_options, row)
        else:
            _summary(row, course_options, editable)
    if editable:
        if editing == "new":
            _form(editable, course_options, None)
        elif not course_options:
            st.info("Add a course in 6A first.", icon=":material/info:")
        elif st.button("+ Add a peer observation", key="s6b_add"):
            st.session_state[K + "editing"] = "new"
            st.rerun()


def _summary(row: s6b.PeerObservationRow, course_options: dict[int, str], editable: bool) -> None:
    o = row.observation
    with st.container(key=f"card_obs_{o.id}"):
        a, b = st.columns([5, 1])
        with a:
            theme.html(f"""<div class="pf-card-h"><h3>{theme.esc(course_options.get(o.course_taught_id, "—"))}</h3></div>
            <div class="pf-card-sub" style="margin-left:0">{o.observation_date:%d %b %Y} · rating
            {o.rating}/{o.scale_max}</div>""")
        with b:
            if editable:
                if st.button("Edit", key=f"s6b_edit_{o.id}", use_container_width=True):
                    st.session_state[K + "editing"] = o.id
                    st.rerun()
                if st.button("Delete", key=f"s6b_del_{o.id}", use_container_width=True):
                    with session_scope() as s:
                        s6b.delete(s, st.session_state["current_user"].id, o.id)
                    st.session_state["s6_flash"] = "Observation removed."
                    st.rerun()


@st.fragment
def _form(editable: bool, course_options: dict[int, str], row: "s6b.PeerObservationRow | None") -> None:
    o = row.observation if row else None
    prefix = f"s6b_f_{o.id if o else 'new'}_"
    today = date.today()
    options = observer_role_options()
    ids = [c.id for c in options]
    labels = {c.id: c.label for c in options}
    course_ids = list(course_options)
    with st.container(key=f"card_obs_form_{o.id if o else 'new'}"):
        theme.card_header("+", "Edit peer observation" if o else "Add a peer observation")
        course_taught_id = st.selectbox("Course observed", course_ids, format_func=course_options.get,
                                        index=course_ids.index(o.course_taught_id) if o else None,
                                        placeholder="Choose a course", key=prefix + "course")
        a, b = st.columns(2)
        observer_role_id = a.selectbox("Observer role", ids, format_func=labels.get,
                                       index=ids.index(o.observer_role_id) if o else None,
                                       placeholder="Choose a role", key=prefix + "role")
        observer_name = b.text_input("Observer name (optional)", value=(o.observer_name if o else "") or "",
                                     key=prefix + "name", help="Sensitive; not sent to the LLM.")
        c, d = st.columns(2)
        observation_date = c.date_input("Observation date", value=o.observation_date if o else None,
                                        min_value=date(1970, 1, 1), max_value=today, format="DD/MM/YYYY",
                                        key=prefix + "date")
        e, f = st.columns(2)
        rating = e.number_input("Overall rating", min_value=0.0, step=0.1, value=float(o.rating) if o else 0.0,
                                key=prefix + "rating")
        scale_max = f.number_input("Rating scale maximum", min_value=0.0, step=0.1,
                                   value=float(o.scale_max) if o else 5.0, key=prefix + "scale")
        label = "Observation report" if row is None or row.evidence is None else "Replace observation report"
        upload = st.file_uploader(label, type=["pdf"], key=prefix + "evidence")

        values = {"course_taught_id": course_taught_id, "observer_role_id": observer_role_id,
                 "observer_name": observer_name.strip() or None, "observation_date": observation_date,
                 "rating": rating, "scale_max": scale_max}
        upload_tuple = (upload.name, upload.getvalue()) if upload is not None else None

        save_col, cancel_col = st.columns([1, 1])
        if save_col.button("Save", type="primary", icon=":material/save:", key=prefix + "save",
                           use_container_width=True):
            errors = s6b.validate(values, today, row.evidence is not None if row else False, upload_tuple)
            if errors:
                theme.html('<div class="pf-err"><b>Please fix the following:</b><ul>'
                          + "".join(f"<li>{theme.esc(e)}</li>" for e in errors) + "</ul></div>")
                return
            user_id = st.session_state["current_user"].id
            with session_scope() as s:
                if o is None:
                    s6b.add(s, user_id, values, upload_tuple)
                else:
                    s6b.update(s, user_id, o.id, values, upload_tuple)
            st.session_state.pop(K + "editing", None)
            st.session_state["s6_flash"] = "Peer observation saved."
            st.rerun()
        if cancel_col.button("Cancel", key=prefix + "cancel", use_container_width=True):
            st.session_state.pop(K + "editing", None)
            st.rerun()
