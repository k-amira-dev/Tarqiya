"""5G · Patent entry — the tab inside the Section 5 (Research) page."""
from datetime import date

import streamlit as st

from promoflow.db.enums import PatentStatus
from promoflow.db.session import session_scope
from promoflow.dossier.section5 import patents as s5g
from promoflow.ui import theme
from promoflow.ui.views.section5.lookups import patent_office_options

K = "s5g_"
STATUS_LABEL = {PatentStatus.FILED: "Filed", PatentStatus.GRANTED: "Granted"}


def render(rows: list[s5g.PatentRow], editable: bool) -> None:
    editing = st.session_state.get(K + "editing")
    for row in rows:
        if editing == row.patent.id:
            _form(editable, row)
        else:
            _summary(row, editable)
    if editable:
        if editing == "new":
            _form(editable, None)
        elif st.button("+ Add a patent", key="s5g_add"):
            st.session_state[K + "editing"] = "new"
            st.rerun()
    theme.html('<div class="pf-note">Granted patents count as Class B, max 2 (Associate) / 3 (Full).</div>')


def _summary(row: s5g.PatentRow, editable: bool) -> None:
    p = row.patent
    with st.container(key=f"card_patent_{p.id}"):
        a, b = st.columns([5, 1])
        with a:
            theme.html(f"""<div class="pf-card-h"><h3>{theme.esc(p.title)}</h3></div>
            <div class="pf-card-sub" style="margin-left:0">{p.patent_number} · {STATUS_LABEL[p.status]}
            {" · granted " + f"{p.grant_date:%b %Y}" if p.grant_date else ""}</div>""")
        with b:
            if editable:
                if st.button("Edit", key=f"s5g_edit_{p.id}", use_container_width=True):
                    st.session_state[K + "editing"] = p.id
                    st.rerun()
                if st.button("Delete", key=f"s5g_del_{p.id}", use_container_width=True):
                    with session_scope() as s:
                        s5g.delete(s, st.session_state["current_user"].id, p.id)
                    st.session_state["s5_flash"] = "Patent removed."
                    st.rerun()


def _form(editable: bool, row: "s5g.PatentRow | None") -> None:
    p = row.patent if row else None
    prefix = f"s5g_f_{p.id if p else 'new'}_"
    today = date.today()
    options = patent_office_options()
    ids = list(options)
    with st.container(key=f"card_patent_form_{p.id if p else 'new'}"):
        theme.card_header("+", "Edit patent" if p else "Add a patent")
        title = st.text_input("Patent title", value=p.title if p else "", key=prefix + "title")
        a, b = st.columns(2)
        patent_number = a.text_input("Patent number", value=p.patent_number if p else "", key=prefix + "number")
        office_id = b.selectbox("Patent office", ids, format_func=options.get,
                                index=ids.index(p.office_id) if p else None, placeholder="Choose an office",
                                key=prefix + "office")
        c, d = st.columns(2)
        status = c.selectbox("Status", list(PatentStatus), format_func=STATUS_LABEL.get,
                             index=list(PatentStatus).index(p.status) if p else None,
                             placeholder="Choose a status", key=prefix + "status")
        grant_date = None
        if status == PatentStatus.GRANTED:
            grant_date = d.date_input("Grant date", value=p.grant_date if p else None, min_value=date(1970, 1, 1),
                                      max_value=today, format="DD/MM/YYYY", key=prefix + "grant_date")
        inventors = st.text_area("Inventors", value=p.inventors if p else "", key=prefix + "inventors")
        label = "Evidence" if row is None or row.evidence is None else "Replace evidence"
        upload = st.file_uploader(label, type=["pdf"], key=prefix + "evidence", help="Grant certificate.")

        values = {"title": title.strip(), "patent_number": patent_number.strip(), "office_id": office_id,
                 "status": status, "grant_date": grant_date, "inventors": inventors.strip()}
        upload_tuple = (upload.name, upload.getvalue()) if upload is not None else None

        save_col, cancel_col = st.columns([1, 1])
        if save_col.button("Save", type="primary", icon=":material/save:", key=prefix + "save",
                           use_container_width=True):
            errors = s5g.validate(values, today, row.evidence is not None if row else False, upload_tuple)
            if errors:
                theme.html('<div class="pf-err"><b>Please fix the following:</b><ul>'
                          + "".join(f"<li>{theme.esc(e)}</li>" for e in errors) + "</ul></div>")
                return
            user_id = st.session_state["current_user"].id
            with session_scope() as s:
                if p is None:
                    s5g.add(s, user_id, values, upload_tuple)
                else:
                    s5g.update(s, user_id, p.id, values, upload_tuple)
            st.session_state.pop(K + "editing", None)
            st.session_state["s5_flash"] = "Patent saved."
            st.rerun()
        if cancel_col.button("Cancel", key=prefix + "cancel", use_container_width=True):
            st.session_state.pop(K + "editing", None)
            st.rerun()
