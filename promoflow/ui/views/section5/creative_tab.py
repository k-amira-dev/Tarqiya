"""5A-2 · Creative / studio work entry — the tab inside the Section 5 (Research) page."""
from datetime import date

import streamlit as st

from promoflow.db.session import session_scope
from promoflow.dossier.section5 import creative as s5c
from promoflow.ui import theme
from promoflow.ui.views.section5.lookups import creative_form_options

K = "s5a2_"


def render(rows: list[s5c.CreativeWorkRow], editable: bool) -> None:
    editing = st.session_state.get(K + "editing")
    for row in rows:
        if editing == row.work.id:
            _form(editable, row)
        else:
            _summary(row, editable)
    if editable:
        if editing == "new":
            _form(editable, None)
        elif st.button("+ Add a creative / studio work", key="s5a2_add"):
            st.session_state[K + "editing"] = "new"
            st.rerun()


def _summary(row: s5c.CreativeWorkRow, editable: bool) -> None:
    w = row.work
    options = creative_form_options()
    with st.container(key=f"card_creative_{w.id}"):
        a, b = st.columns([5, 1])
        with a:
            theme.html(f"""<div class="pf-card-h"><h3>{theme.esc(w.title)}</h3></div>
            <div class="pf-card-sub" style="margin-left:0">{theme.esc(options.get(w.form_id, ""))} ·
            {theme.esc(w.venue)} · {w.date_from:%b %Y}{'–' + f'{w.date_to:%b %Y}' if w.date_to else ''}
            · {"Approved" if w.approved else "Not yet approved"}</div>""")
        with b:
            if editable:
                if st.button("Edit", key=f"s5a2_edit_{w.id}", use_container_width=True):
                    st.session_state[K + "editing"] = w.id
                    st.rerun()
                if st.button("Delete", key=f"s5a2_del_{w.id}", use_container_width=True):
                    with session_scope() as s:
                        s5c.delete(s, st.session_state["current_user"].id, w.id)
                    st.session_state["s5_flash"] = "Creative work removed."
                    st.rerun()


@st.fragment
def _form(editable: bool, row: "s5c.CreativeWorkRow | None") -> None:
    w = row.work if row else None
    prefix = f"s5a2_f_{w.id if w else 'new'}_"
    today = date.today()
    options = creative_form_options()
    ids = list(options)
    with st.container(key=f"card_creative_form_{w.id if w else 'new'}"):
        theme.card_header("+", "Edit creative work" if w else "Add a creative / studio work")
        form_id = st.selectbox("Form of presentation", ids, format_func=options.get,
                               index=ids.index(w.form_id) if w else None, placeholder="Choose a form",
                               key=prefix + "form")
        title = st.text_input("Title / content and quantity", value=w.title if w else "", key=prefix + "title")
        a, b = st.columns(2)
        venue = a.text_input("Venue", value=w.venue if w else "", key=prefix + "venue")
        org = b.text_input("Organizing institution", value=w.organizing_institution if w else "", key=prefix + "org")
        c, d = st.columns(2)
        date_from = c.date_input("From", value=w.date_from if w else None, min_value=date(1970, 1, 1),
                                 max_value=today, format="DD/MM/YYYY", key=prefix + "from")
        date_to = d.date_input("To", value=w.date_to if w else None, min_value=date(1970, 1, 1), max_value=today,
                               format="DD/MM/YYYY", key=prefix + "to")
        approved = st.toggle("Approved as creative work?", value=bool(w.approved) if w else False,
                             key=prefix + "approved")
        label = "Evidence" if row is None or row.evidence is None else "Replace evidence"
        upload = st.file_uploader(label, type=["pdf", "jpg", "jpeg", "png"], key=prefix + "evidence",
                                  help="Catalogue, programme or approval letter.")

        values = {"form_id": form_id, "title": title.strip(), "venue": venue.strip(),
                 "organizing_institution": org.strip(), "date_from": date_from, "date_to": date_to,
                 "approved": approved}
        upload_tuple = (upload.name, upload.getvalue()) if upload is not None else None

        save_col, cancel_col = st.columns([1, 1])
        if save_col.button("Save", type="primary", icon=":material/save:", key=prefix + "save",
                           use_container_width=True):
            errors = s5c.validate(values, today, row.evidence is not None if row else False, upload_tuple)
            if errors:
                theme.html('<div class="pf-err"><b>Please fix the following:</b><ul>'
                          + "".join(f"<li>{theme.esc(e)}</li>" for e in errors) + "</ul></div>")
                return
            user_id = st.session_state["current_user"].id
            with session_scope() as s:
                if w is None:
                    s5c.add(s, user_id, values, upload_tuple)
                else:
                    s5c.update(s, user_id, w.id, values, upload_tuple)
            st.session_state.pop(K + "editing", None)
            st.session_state["s5_flash"] = "Creative work saved."
            st.rerun()
        if cancel_col.button("Cancel", key=prefix + "cancel", use_container_width=True):
            st.session_state.pop(K + "editing", None)
            st.rerun()
