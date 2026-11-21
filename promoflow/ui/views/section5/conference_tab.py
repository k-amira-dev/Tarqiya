"""5C · Conference paper entry — the tab inside the Section 5 (Research) page."""
from datetime import date

import streamlit as st

from promoflow.ui.views import entries_ui

from promoflow.db.session import session_scope
from promoflow.dossier.section5 import conference as s5c
from promoflow.ui import theme

K = "s5c_"


def render(rows: list[s5c.ConferencePaperRow], editable: bool) -> None:
    if editable:
        entries_ui.add_bar(["conference"], "s5_flash", K + "editing")
    editing = st.session_state.get(K + "editing")
    for row in rows:
        if editing == row.paper.id:
            _form(editable, row)
        else:
            _summary(row, editable)
    if editable:
        if editing == "new":
            _form(editable, None)
    theme.html('<div class="pf-note">Recorded and shown in the narrative; not counted towards the '
              "publication minimums unless the policy confirms they count.</div>")


def _summary(row: s5c.ConferencePaperRow, editable: bool) -> None:
    p = row.paper
    with st.container(key=f"card_conf_{p.id}"):
        a, b = st.columns([5, 1])
        with a:
            theme.html(f"""<div class="pf-card-h"><h3>{theme.esc(p.title)}</h3></div>
            <div class="pf-card-sub" style="margin-left:0">{theme.esc(p.conference_title)} ·
            {p.conference_date:%d %b %Y} · {theme.esc(p.place)}</div>""")
        with b:
            if editable:
                if st.button("Edit", key=f"s5c_edit_{p.id}", use_container_width=True):
                    st.session_state[K + "editing"] = p.id
                    st.rerun()
                if st.button("Delete", key=f"s5c_del_{p.id}", use_container_width=True):
                    with session_scope() as s:
                        s5c.delete(s, st.session_state["current_user"].id, p.id)
                    st.session_state["s5_flash"] = "Conference paper removed."
                    st.rerun()


@st.fragment
def _form(editable: bool, row: "s5c.ConferencePaperRow | None") -> None:
    p = row.paper if row else None
    prefix = f"s5c_f_{p.id if p else 'new'}_"
    today = date.today()
    with st.container(key=f"card_conf_form_{p.id if p else 'new'}"):
        theme.card_header("+", "Edit conference paper" if p else "Add a conference paper")
        entries_ui.autofill("conference", prefix)
        title = st.text_input("Paper title", value=p.title if p else "", key=prefix + "title")
        a, b = st.columns(2)
        conference_title = a.text_input("Conference title", value=p.conference_title if p else "",
                                        key=prefix + "conf_title")
        organizer = b.text_input("Name of conference organizer", value=p.organizer if p else "",
                                 key=prefix + "organizer")
        c, d = st.columns(2)
        conference_date = c.date_input("Date", value=p.conference_date if p else None, min_value=date(1970, 1, 1),
                                       max_value=today, format="DD/MM/YYYY", key=prefix + "date")
        place = d.text_input("Place", value=p.place if p else "", key=prefix + "place")
        e, f = st.columns(2)
        pages = e.text_input("Page numbers (optional)", value=(p.pages if p else "") or "", key=prefix + "pages")
        doi = f.text_input("DOI (optional)", value=(p.doi if p else "") or "", key=prefix + "doi")
        g, h = st.columns(2)
        main_or_sole_author = g.toggle("Main or sole author?", value=bool(p.main_or_sole_author) if p else True,
                                       key=prefix + "main_or_sole")
        scopus_indexed = h.toggle("Proceedings indexed in Scopus?", value=bool(p.scopus_indexed) if p else False,
                                  key=prefix + "scopus")
        label = "Evidence" if row is None or row.evidence is None else "Replace evidence"
        upload = st.file_uploader(label, type=["pdf"], key=prefix + "evidence",
                                  help="Proceedings paper or acceptance.")

        values = {"title": title.strip(), "conference_title": conference_title.strip(),
                 "organizer": organizer.strip(), "conference_date": conference_date, "place": place.strip(),
                 "pages": pages.strip() or None, "main_or_sole_author": main_or_sole_author,
                 "scopus_indexed": scopus_indexed, "doi": doi.strip() or None}
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
                if p is None:
                    s5c.add(s, user_id, values, upload_tuple)
                else:
                    s5c.update(s, user_id, p.id, values, upload_tuple)
            st.session_state.pop(K + "editing", None)
            st.session_state["s5_flash"] = "Conference paper saved."
            st.rerun()
        if cancel_col.button("Cancel", key=prefix + "cancel", use_container_width=True):
            st.session_state.pop(K + "editing", None)
            st.rerun()
