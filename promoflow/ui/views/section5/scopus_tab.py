"""5F · Scopus evidence & journal ranking screenshots — the tab inside the Section 5 (Research) page."""
from datetime import date

import streamlit as st

from promoflow.ui.views import entries_ui

from promoflow.db.session import session_scope
from promoflow.dossier.section5 import scopus as s5f
from promoflow.ui import theme

K = "s5f_"


def render(ctx: s5f.Section5FContext, editable: bool) -> None:
    if editable:
        entries_ui.panel("scopus", "s5_flash")
    with st.container(key="card_scopus"):
        theme.card_header("5F", "Scopus evidence", "A full-page screenshot of your Scopus author profile, "
                          "captured within 30 days of submission, showing name, affiliation, h-index and "
                          "total citations with the date visible.")
        if editable:
            entries_ui.autofill("scopus", K)
        e = ctx.evidence
        if e is not None:
            theme.html(f"""<div class="pf-kv"><div><span>h-index</span><b>{e.h_index}</b></div>
            <div><span>Total citations</span><b>{e.total_citations}</b></div>
            <div><span>Screenshot date</span><b>{e.screenshot_date:%d %b %Y}</b></div></div>""")
        a, b = st.columns(2)
        h_index = a.number_input("h-index (as shown on Scopus)", min_value=0, max_value=300, step=1,
                                 value=e.h_index if e else 0, key=K + "h_index", disabled=not editable)
        total_citations = b.number_input("Total citations (as shown on Scopus)", min_value=0, step=1,
                                         value=e.total_citations if e else 0, key=K + "citations",
                                         disabled=not editable)
        screenshot_date = st.date_input("Screenshot date", value=e.screenshot_date if e else None,
                                        min_value=date(2000, 1, 1), max_value=date.today(), format="DD/MM/YYYY",
                                        key=K + "date", disabled=not editable)
        label = "Scopus profile screenshot" if ctx.screenshot is None else "Replace screenshot"
        upload = st.file_uploader(label, type=["jpg", "jpeg", "png", "pdf"], key=K + "upload", disabled=not editable)

        if not editable:
            return
        if st.button("Save Scopus evidence", type="primary", icon=":material/save:", key=K + "save"):
            values = {"h_index": int(h_index), "total_citations": int(total_citations),
                     "screenshot_date": screenshot_date}
            upload_tuple = (upload.name, upload.getvalue()) if upload is not None else None
            errors = s5f.validate(values, date.today(), ctx.screenshot is not None, upload_tuple)
            if errors:
                theme.html('<div class="pf-err"><b>Please fix the following:</b><ul>'
                          + "".join(f"<li>{theme.esc(err)}</li>" for err in errors) + "</ul></div>")
                return
            with session_scope() as s:
                s5f.save(s, st.session_state["current_user"].id, values, upload_tuple)
            st.session_state["s5_flash"] = "Scopus evidence saved."
            st.rerun()
