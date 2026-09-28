"""5D · Funded research project entry — the tab inside the Section 5 (Research) page."""
from datetime import date

import streamlit as st

from promoflow.db.enums import InvestigatorRole, ProjectStatus
from promoflow.db.session import session_scope
from promoflow.dossier.section5 import funded as s5d
from promoflow.ui import theme
from promoflow.ui.views.section5.lookups import funder_type_options

K = "s5d_"
ROLE_LABEL = {InvestigatorRole.PI: "Principal Investigator (PI)", InvestigatorRole.CI: "Co-Investigator (CI)"}
STATUS_LABEL = {ProjectStatus.ONGOING: "Ongoing", ProjectStatus.COMPLETED: "Completed"}


def render(rows: list[s5d.FundedProjectRow], editable: bool) -> None:
    editing = st.session_state.get(K + "editing")
    for row in rows:
        if editing == row.project.id:
            _form(editable, row)
        else:
            _summary(row, editable)
    if editable:
        if editing == "new":
            _form(editable, None)
        elif st.button("+ Add a funded project", key="s5d_add"):
            st.session_state[K + "editing"] = "new"
            st.rerun()


def _summary(row: s5d.FundedProjectRow, editable: bool) -> None:
    p = row.project
    with st.container(key=f"card_funded_{p.id}"):
        a, b = st.columns([5, 1])
        with a:
            to = "ongoing" if p.end_date is None else f"{p.end_date:%b %Y}"
            theme.html(f"""<div class="pf-card-h"><h3>{theme.esc(p.title)}</h3></div>
            <div class="pf-card-sub" style="margin-left:0">{theme.esc(p.funding_body)} · {ROLE_LABEL[p.role]} ·
            {p.start_date:%b %Y} – {to} · {STATUS_LABEL[p.status]}</div>""")
        with b:
            if editable:
                if st.button("Edit", key=f"s5d_edit_{p.id}", use_container_width=True):
                    st.session_state[K + "editing"] = p.id
                    st.rerun()
                if st.button("Delete", key=f"s5d_del_{p.id}", use_container_width=True):
                    with session_scope() as s:
                        s5d.delete(s, st.session_state["current_user"].id, p.id)
                    st.session_state["s5_flash"] = "Funded project removed."
                    st.rerun()


def _form(editable: bool, row: "s5d.FundedProjectRow | None") -> None:
    p = row.project if row else None
    prefix = f"s5d_f_{p.id if p else 'new'}_"
    today = date.today()
    funder_options = funder_type_options()
    funder_ids = list(funder_options)
    with st.container(key=f"card_funded_form_{p.id if p else 'new'}"):
        theme.card_header("+", "Edit funded project" if p else "Add a funded project")
        title = st.text_input("Project title", value=p.title if p else "", key=prefix + "title")
        a, b = st.columns(2)
        funding_body = a.text_input("Funding body", value=p.funding_body if p else "", key=prefix + "body")
        funder_type_id = b.selectbox("Funder type", funder_ids, format_func=funder_options.get,
                                     index=funder_ids.index(p.funder_type_id) if p else None,
                                     placeholder="Choose a funder type", key=prefix + "funder_type")
        c, d = st.columns(2)
        role = c.selectbox("Role", list(InvestigatorRole), format_func=ROLE_LABEL.get,
                           index=list(InvestigatorRole).index(p.role) if p else None,
                           placeholder="Choose a role", key=prefix + "role")
        status = d.selectbox("Status", list(ProjectStatus), format_func=STATUS_LABEL.get,
                             index=list(ProjectStatus).index(p.status) if p else None,
                             placeholder="Choose a status", key=prefix + "status")
        e, f = st.columns(2)
        amount = e.number_input("Amount (optional)", min_value=0.0, step=100.0,
                                value=float(p.amount) if p and p.amount else 0.0, key=prefix + "amount")
        currency = f.text_input("Currency (optional)", value=(p.currency if p else "") or "", max_chars=3,
                                key=prefix + "currency")
        g, h = st.columns(2)
        start_date = g.date_input("Start date", value=p.start_date if p else None, min_value=date(1970, 1, 1),
                                  max_value=today, format="DD/MM/YYYY", key=prefix + "start")
        end_date = h.date_input("End date", value=p.end_date if p else None, min_value=date(1970, 1, 1),
                                max_value=date(2100, 1, 1), format="DD/MM/YYYY", key=prefix + "end")
        label = "Evidence" if row is None or row.evidence is None else "Replace evidence"
        upload = st.file_uploader(label, type=["pdf"], key=prefix + "evidence", help="Award letter or contract.")

        values = {"title": title.strip(), "funding_body": funding_body.strip(), "funder_type_id": funder_type_id,
                 "role": role, "amount": amount or None, "currency": currency.strip().upper() or None,
                 "start_date": start_date, "end_date": end_date, "status": status}
        upload_tuple = (upload.name, upload.getvalue()) if upload is not None else None

        save_col, cancel_col = st.columns([1, 1])
        if save_col.button("Save", type="primary", icon=":material/save:", key=prefix + "save",
                           use_container_width=True):
            errors = s5d.validate(values, today, row.evidence is not None if row else False, upload_tuple)
            if errors:
                theme.html('<div class="pf-err"><b>Please fix the following:</b><ul>'
                          + "".join(f"<li>{theme.esc(e)}</li>" for e in errors) + "</ul></div>")
                return
            user_id = st.session_state["current_user"].id
            with session_scope() as s:
                if p is None:
                    s5d.add(s, user_id, values, upload_tuple)
                else:
                    s5d.update(s, user_id, p.id, values, upload_tuple)
            st.session_state.pop(K + "editing", None)
            st.session_state["s5_flash"] = "Funded project saved."
            st.rerun()
        if cancel_col.button("Cancel", key=prefix + "cancel", use_container_width=True):
            st.session_state.pop(K + "editing", None)
            st.rerun()
