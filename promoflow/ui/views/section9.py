"""Section 9 – Conditions Form (spec chapter 12)."""
from datetime import date

import streamlit as st

from promoflow.ui.views import entries_ui

from promoflow.db.session import session_scope
from promoflow.dossier import section9 as s9
from promoflow.dossier.section0 import EDITABLE
from promoflow.ui import cache, theme

K = "s9_"


def render() -> None:
    user = st.session_state["current_user"]
    today = date.today()
    ctx = cache.load_cached(f"pfc:s9:{user.id}", lambda s: s9.load(s, user.id))

    theme.html("""
    <div class="pf-hero"><div class="crumb">MY PROMOTION · SECTION 9 OF 11</div>
    <h1>Conditions Form</h1>
    <p>The signed Conditions Form provided by Faculty Affairs.</p></div>""")

    if ctx.case_id is None:
        st.info("Save Section 0 (Applicant Details & Promotion Track) first — it creates your draft application.",
                icon=":material/info:")
        return

    editable = ctx.status in EDITABLE
    if editable:
        entries_ui.panel("conditions", "s9_flash")
    if flash := st.session_state.pop(K + "flash", None):
        st.success(flash, icon=":material/check_circle:")
    if not editable:
        st.info("This application has been submitted, so Section 9 is read-only.", icon=":material/lock:")

    _form(ctx, user.id, today, editable)


@st.fragment
def _form(ctx, user_id: int, today: date, editable: bool) -> None:
    with st.container(key="card_conditions"):
        theme.card_header("01", "Signed Conditions Form")
        if ctx.document is not None:
            theme.html(f'<div class="pf-note">Current file: {theme.esc(ctx.document.original_filename)}, '
                      f'uploaded {ctx.document.uploaded_at:%d %b %Y}.</div>')
        label = "Signed Conditions Form" if ctx.document is None else "Replace signed Conditions Form"
        upload = st.file_uploader(label, type=sorted(s9.ALLOWED_EXTENSIONS), key=K + "upload",
                                  disabled=not editable)
        conditions_signed_date = st.date_input("Date signed", value=ctx.conditions_signed_date,
                                               min_value=date(2000, 1, 1), max_value=today, format="DD/MM/YYYY",
                                               key=K + "date", disabled=not editable)

    if not editable:
        return
    if st.button("Save Section 9", type="primary", icon=":material/save:", key=K + "save"):
        upload_tuple = (upload.name, upload.getvalue()) if upload is not None else None
        errors = s9.validate(conditions_signed_date, ctx.document is not None, today, upload_tuple)
        if errors:
            theme.html('<div class="pf-err"><b>Please fix the following:</b><ul>'
                      + "".join(f"<li>{theme.esc(e)}</li>" for e in errors) + "</ul></div>")
            return
        try:
            with session_scope() as s:
                s9.save(s, user_id, conditions_signed_date, upload_tuple)
        except s9.CaseLocked as e:
            st.error(str(e))
            return
        st.session_state[K + "flash"] = "Section 9 saved."
        st.rerun()
