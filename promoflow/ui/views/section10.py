"""Section 10 – Cover Letter (spec chapter 12)."""
from datetime import date

import streamlit as st

from promoflow.db.session import session_scope
from promoflow.dossier import section10 as s10
from promoflow.dossier.section0 import EDITABLE
from promoflow.ui import theme

K = "s10_"


def render() -> None:
    user = st.session_state["current_user"]
    today = date.today()
    with session_scope() as s:
        ctx = s10.load(s, user.id)

    theme.html("""
    <div class="pf-hero"><div class="crumb">MY PROMOTION · SECTION 10 OF 11</div>
    <h1>Cover Letter</h1>
    <p>A signed cover letter addressed to the Promotions Committee.</p></div>""")

    if ctx.case_id is None:
        st.info("Save Section 0 (Applicant Details & Promotion Track) first — it creates your draft application.",
                icon=":material/info:")
        return

    editable = ctx.status in EDITABLE
    if flash := st.session_state.pop(K + "flash", None):
        st.success(flash, icon=":material/check_circle:")
    if not editable:
        st.info("This application has been submitted, so Section 10 is read-only.", icon=":material/lock:")

    with st.container(key="card_cover_letter"):
        theme.card_header("01", "Signed cover letter")
        if ctx.document is not None:
            theme.html(f'<div class="pf-note">Current file: {theme.esc(ctx.document.original_filename)}, '
                      f'uploaded {ctx.document.uploaded_at:%d %b %Y}.</div>')
        label = "Signed cover letter" if ctx.document is None else "Replace signed cover letter"
        upload = st.file_uploader(label, type=sorted(s10.ALLOWED_EXTENSIONS), key=K + "upload",
                                  disabled=not editable)
        cover_letter_signed_date = st.date_input("Date signed", value=ctx.cover_letter_signed_date,
                                                 min_value=date(2000, 1, 1), max_value=today, format="DD/MM/YYYY",
                                                 key=K + "date", disabled=not editable)

    if not editable:
        return
    if st.button("Save Section 10", type="primary", icon=":material/save:", key=K + "save"):
        upload_tuple = (upload.name, upload.getvalue()) if upload is not None else None
        errors = s10.validate(cover_letter_signed_date, ctx.document is not None, today, upload_tuple)
        if errors:
            theme.html('<div class="pf-err"><b>Please fix the following:</b><ul>'
                      + "".join(f"<li>{theme.esc(e)}</li>" for e in errors) + "</ul></div>")
            return
        try:
            with session_scope() as s:
                s10.save(s, user.id, cover_letter_signed_date, upload_tuple)
        except s10.CaseLocked as e:
            st.error(str(e))
            return
        st.session_state[K + "flash"] = "Section 10 saved."
        st.rerun()
