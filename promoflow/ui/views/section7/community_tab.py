"""7B · Community service activity — the tab inside the Section 7 (University & Community Service) page."""
from datetime import date

import streamlit as st

from promoflow.db.session import session_scope
from promoflow.dossier.section7 import community as s7b
from promoflow.dossier.section7.common import funded_project_options
from promoflow.ui import theme
from promoflow.ui.views.section7.lookups import community_activity_type_options

K = "s7b_"


def render(rows: list[s7b.CommunityActivityRow], case_id: int, editable: bool) -> None:
    editing = st.session_state.get(K + "editing")
    for row in rows:
        if editing == row.activity.id:
            _form(editable, case_id, row)
        else:
            _summary(row, editable)
    if editable:
        if editing == "new":
            _form(editable, case_id, None)
        elif st.button("+ Add a community service activity", key="s7b_add"):
            st.session_state[K + "editing"] = "new"
            st.rerun()


def _summary(row: s7b.CommunityActivityRow, editable: bool) -> None:
    a = row.activity
    types = {o.id: o.label for o in community_activity_type_options()}
    with st.container(key=f"card_community_{a.id}"):
        col1, col2 = st.columns([5, 1])
        with col1:
            to = "ongoing" if a.date_to is None else f"{a.date_to:%b %Y}"
            theme.html(f"""<div class="pf-card-h"><h3>{theme.esc(a.title)}</h3></div>
            <div class="pf-card-sub" style="margin-left:0">{theme.esc(types.get(a.activity_type_id, ""))} ·
            {theme.esc(a.beneficiary_organisation)} · {a.date_from:%b %Y} – {to}</div>""")
        with col2:
            if editable:
                if st.button("Edit", key=f"s7b_edit_{a.id}", use_container_width=True):
                    st.session_state[K + "editing"] = a.id
                    st.rerun()
                if st.button("Delete", key=f"s7b_del_{a.id}", use_container_width=True):
                    with session_scope() as s:
                        s7b.delete(s, st.session_state["current_user"].id, a.id)
                    st.session_state["s7_flash"] = "Community activity removed."
                    st.rerun()


def _form(editable: bool, case_id: int, row: "s7b.CommunityActivityRow | None") -> None:
    a = row.activity if row else None
    prefix = f"s7b_f_{a.id if a else 'new'}_"
    today = date.today()
    types = community_activity_type_options()
    type_ids = [t.id for t in types]
    type_labels = {t.id: t.label for t in types}
    type_codes = {t.id: t.code for t in types}
    with session_scope() as s:
        project_options = funded_project_options(s, case_id)
    with st.container(key=f"card_community_form_{a.id if a else 'new'}"):
        theme.card_header("+", "Edit community activity" if a else "Add a community service activity")
        activity_type_id = st.selectbox("Activity type", type_ids, format_func=type_labels.get,
                                        index=type_ids.index(a.activity_type_id) if a else None,
                                        placeholder="Choose a type", key=prefix + "type")
        is_funded_project = type_codes.get(activity_type_id) in s7b.FUNDED_PROJECT_CODES
        funded_project_id = None
        if is_funded_project:
            if project_options:
                project_ids = list(project_options)
                funded_project_id = st.selectbox("Linked funded project", project_ids,
                                                 format_func=project_options.get,
                                                 index=project_ids.index(a.funded_project_id)
                                                 if a and a.funded_project_id in project_options else None,
                                                 placeholder="Choose the §5D project", key=prefix + "project")
            else:
                st.info("Enter the project in §5D (Research) first, then link it here.", icon=":material/info:")
        title = st.text_input("Title", value=a.title if a else "", key=prefix + "title")
        c1, c2 = st.columns(2)
        beneficiary_organisation = c1.text_input("Beneficiary organisation",
                                                 value=a.beneficiary_organisation if a else "", key=prefix + "beneficiary")
        applicant_role = c2.text_input("Applicant's role", value=a.applicant_role if a else "", key=prefix + "role")
        c3, c4 = st.columns(2)
        date_from = c3.date_input("Time period – from", value=a.date_from if a else None,
                                  min_value=date(1970, 1, 1), max_value=today, format="DD/MM/YYYY",
                                  key=prefix + "from")
        date_to = c4.date_input("Time period – to (optional)", value=a.date_to if a else None,
                                min_value=date(1970, 1, 1), max_value=date(2100, 1, 1), format="DD/MM/YYYY",
                                key=prefix + "to")
        beneficiaries = st.number_input("Number of beneficiaries (optional)", min_value=0, step=1,
                                        value=a.beneficiaries if a and a.beneficiaries else 0,
                                        key=prefix + "beneficiaries")
        deliverables = st.text_area("Deliverables", value=(a.deliverables if a else "") or "", key=prefix + "deliverables")
        measurable_outcome = st.text_area("Measurable outcome (optional)",
                                          value=(a.measurable_outcome if a else "") or "", key=prefix + "outcome")
        label = "Evidence" if row is None or row.evidence is None else "Replace evidence"
        upload = st.file_uploader(label, type=["pdf", "jpg", "jpeg", "png"], key=prefix + "evidence")

        values = {"activity_type_id": activity_type_id, "funded_project_id": funded_project_id,
                 "title": title.strip(), "beneficiary_organisation": beneficiary_organisation.strip(),
                 "applicant_role": applicant_role.strip(), "date_from": date_from, "date_to": date_to,
                 "beneficiaries": int(beneficiaries) or None, "deliverables": deliverables.strip(),
                 "measurable_outcome": measurable_outcome.strip() or None}
        upload_tuple = (upload.name, upload.getvalue()) if upload is not None else None

        save_col, cancel_col = st.columns([1, 1])
        if save_col.button("Save", type="primary", icon=":material/save:", key=prefix + "save",
                           use_container_width=True):
            errors = s7b.validate(values, is_funded_project, row.evidence is not None if row else False, upload_tuple)
            if errors:
                theme.html('<div class="pf-err"><b>Please fix the following:</b><ul>'
                          + "".join(f"<li>{theme.esc(e)}</li>" for e in errors) + "</ul></div>")
                return
            user_id = st.session_state["current_user"].id
            with session_scope() as s:
                if a is None:
                    s7b.add(s, user_id, values, upload_tuple)
                else:
                    s7b.update(s, user_id, a.id, values, upload_tuple)
            st.session_state.pop(K + "editing", None)
            st.session_state["s7_flash"] = "Community activity saved."
            st.rerun()
        if cancel_col.button("Cancel", key=prefix + "cancel", use_container_width=True):
            st.session_state.pop(K + "editing", None)
            st.rerun()
