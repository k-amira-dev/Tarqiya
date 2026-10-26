"""7A-5 · Policy contribution — the tab inside the Section 7 (University & Community Service) page."""
from datetime import date

import streamlit as st

from promoflow.ui.views import entries_ui

from promoflow.db.enums import OrgLevel
from promoflow.db.session import session_scope
from promoflow.dossier.section7 import policy_contributions as s7a5
from promoflow.ui import theme
from promoflow.ui.views.section7.lookups import policy_role_options

K = "s7a5_"
LEVEL_LABEL = {OrgLevel.DEPARTMENT: "Department", OrgLevel.COLLEGE: "College", OrgLevel.UNIVERSITY: "University"}


def render(rows: list[s7a5.PolicyContributionRow], editable: bool) -> None:
    if editable:
        entries_ui.panel("policy", "s7_flash")
    editing = st.session_state.get(K + "editing")
    for row in rows:
        if editing == row.contribution.id:
            _form(editable, row)
        else:
            _summary(row, editable)
    if editable:
        if editing == "new":
            _form(editable, None)
        elif st.button("+ Add a policy contribution", key="s7a5_add"):
            st.session_state[K + "editing"] = "new"
            st.rerun()


def _summary(row: s7a5.PolicyContributionRow, editable: bool) -> None:
    p = row.contribution
    roles = {o.id: o.label for o in policy_role_options()}
    with st.container(key=f"card_policy_{p.id}"):
        a, b = st.columns([5, 1])
        with a:
            theme.html(f"""<div class="pf-card-h"><h3>{theme.esc(p.policy_name)}</h3></div>
            <div class="pf-card-sub" style="margin-left:0">{LEVEL_LABEL[p.level]} ·
            {theme.esc(roles.get(p.role_id, ""))} · {p.activity_date:%d %b %Y}</div>""")
        with b:
            if editable:
                if st.button("Edit", key=f"s7a5_edit_{p.id}", use_container_width=True):
                    st.session_state[K + "editing"] = p.id
                    st.rerun()
                if st.button("Delete", key=f"s7a5_del_{p.id}", use_container_width=True):
                    with session_scope() as s:
                        s7a5.delete(s, st.session_state["current_user"].id, p.id)
                    st.session_state["s7_flash"] = "Policy contribution removed."
                    st.rerun()


@st.fragment
def _form(editable: bool, row: "s7a5.PolicyContributionRow | None") -> None:
    p = row.contribution if row else None
    prefix = f"s7a5_f_{p.id if p else 'new'}_"
    today = date.today()
    roles = policy_role_options()
    role_ids = [r.id for r in roles]
    role_labels = {r.id: r.label for r in roles}
    with st.container(key=f"card_policy_form_{p.id if p else 'new'}"):
        theme.card_header("+", "Edit policy contribution" if p else "Add a policy contribution")
        entries_ui.autofill("policy", prefix)
        policy_name = st.text_input("Policy / regulation", value=p.policy_name if p else "", key=prefix + "name")
        a, b = st.columns(2)
        level = a.selectbox("Level", list(OrgLevel), format_func=LEVEL_LABEL.get,
                            index=list(OrgLevel).index(p.level) if p else None, placeholder="Choose a level",
                            key=prefix + "level")
        role_id = b.selectbox("Role", role_ids, format_func=role_labels.get,
                              index=role_ids.index(p.role_id) if p else None, placeholder="Choose a role",
                              key=prefix + "role")
        activity_date = st.date_input("Date", value=p.activity_date if p else None, min_value=date(1970, 1, 1),
                                      max_value=today, format="DD/MM/YYYY", key=prefix + "date")
        label = "Evidence" if row is None or row.evidence is None else "Replace evidence"
        upload = st.file_uploader(label, type=["pdf"], key=prefix + "evidence")

        values = {"policy_name": policy_name.strip(), "level": level, "role_id": role_id,
                 "activity_date": activity_date}
        upload_tuple = (upload.name, upload.getvalue()) if upload is not None else None

        save_col, cancel_col = st.columns([1, 1])
        if save_col.button("Save", type="primary", icon=":material/save:", key=prefix + "save",
                           use_container_width=True):
            errors = s7a5.validate(values, today, row.evidence is not None if row else False, upload_tuple)
            if errors:
                theme.html('<div class="pf-err"><b>Please fix the following:</b><ul>'
                          + "".join(f"<li>{theme.esc(e)}</li>" for e in errors) + "</ul></div>")
                return
            user_id = st.session_state["current_user"].id
            with session_scope() as s:
                if p is None:
                    s7a5.add(s, user_id, values, upload_tuple)
                else:
                    s7a5.update(s, user_id, p.id, values, upload_tuple)
            st.session_state.pop(K + "editing", None)
            st.session_state["s7_flash"] = "Policy contribution saved."
            st.rerun()
        if cancel_col.button("Cancel", key=prefix + "cancel", use_container_width=True):
            st.session_state.pop(K + "editing", None)
            st.rerun()
