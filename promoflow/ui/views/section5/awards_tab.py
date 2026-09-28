"""5H · Award entry — the tab inside the Section 5 (Research) page."""
from datetime import date

import streamlit as st

from promoflow.db.session import session_scope
from promoflow.dossier.section5 import awards as s5h
from promoflow.ui import theme
from promoflow.ui.views.section5.lookups import award_scope_options

K = "s5h_"


def render(rows: list[s5h.AwardRow], editable: bool) -> None:
    editing = st.session_state.get(K + "editing")
    for row in rows:
        if editing == row.award.id:
            _form(editable, row)
        else:
            _summary(row, editable)
    if editable:
        if editing == "new":
            _form(editable, None)
        elif st.button("+ Add an award", key="s5h_add"):
            st.session_state[K + "editing"] = "new"
            st.rerun()


def _summary(row: s5h.AwardRow, editable: bool) -> None:
    a = row.award
    options = award_scope_options()
    with st.container(key=f"card_award_{a.id}"):
        col1, col2 = st.columns([5, 1])
        with col1:
            theme.html(f"""<div class="pf-card-h"><h3>{theme.esc(a.name)}</h3></div>
            <div class="pf-card-sub" style="margin-left:0">{theme.esc(a.awarding_body)} · {a.year} ·
            {theme.esc(options.get(a.scope_id, ""))}</div>""")
        with col2:
            if editable:
                if st.button("Edit", key=f"s5h_edit_{a.id}", use_container_width=True):
                    st.session_state[K + "editing"] = a.id
                    st.rerun()
                if st.button("Delete", key=f"s5h_del_{a.id}", use_container_width=True):
                    with session_scope() as s:
                        s5h.delete(s, st.session_state["current_user"].id, a.id)
                    st.session_state["s5_flash"] = "Award removed."
                    st.rerun()


def _form(editable: bool, row: "s5h.AwardRow | None") -> None:
    a = row.award if row else None
    prefix = f"s5h_f_{a.id if a else 'new'}_"
    today = date.today()
    options = award_scope_options()
    ids = list(options)
    with st.container(key=f"card_award_form_{a.id if a else 'new'}"):
        theme.card_header("+", "Edit award" if a else "Add an award")
        name = st.text_input("Award / prize name", value=a.name if a else "", key=prefix + "name")
        c1, c2 = st.columns(2)
        awarding_body = c1.text_input("Awarding body", value=a.awarding_body if a else "", key=prefix + "body")
        year = c2.number_input("Year", min_value=1970, max_value=today.year, step=1,
                               value=a.year if a else today.year, key=prefix + "year")
        scope_id = st.selectbox("Scope", ids, format_func=options.get, index=ids.index(a.scope_id) if a else None,
                                placeholder="Choose a scope", key=prefix + "scope")
        label = "Evidence (optional)" if row is None or row.evidence is None else "Replace evidence"
        upload = st.file_uploader(label, type=["pdf", "jpg", "jpeg", "png"], key=prefix + "evidence")

        values = {"name": name.strip(), "awarding_body": awarding_body.strip(), "year": int(year),
                 "scope_id": scope_id}
        upload_tuple = (upload.name, upload.getvalue()) if upload is not None else None

        save_col, cancel_col = st.columns([1, 1])
        if save_col.button("Save", type="primary", icon=":material/save:", key=prefix + "save",
                           use_container_width=True):
            errors = s5h.validate(values, today)
            if errors:
                theme.html('<div class="pf-err"><b>Please fix the following:</b><ul>'
                          + "".join(f"<li>{theme.esc(e)}</li>" for e in errors) + "</ul></div>")
                return
            user_id = st.session_state["current_user"].id
            with session_scope() as s:
                if a is None:
                    s5h.add(s, user_id, values, upload_tuple)
                else:
                    s5h.update(s, user_id, a.id, values, upload_tuple)
            st.session_state.pop(K + "editing", None)
            st.session_state["s5_flash"] = "Award saved."
            st.rerun()
        if cancel_col.button("Cancel", key=prefix + "cancel", use_container_width=True):
            st.session_state.pop(K + "editing", None)
            st.rerun()
