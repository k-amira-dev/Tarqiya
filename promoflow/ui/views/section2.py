"""Section 2 – Curriculum Vitae (spec chapter 6)."""
from datetime import date

import streamlit as st

from promoflow.ui.views import entries_ui

from promoflow.db.session import session_scope
from promoflow.dossier import section2 as s2
from promoflow.dossier.section0 import EDITABLE
from promoflow.ui import cache, theme

K = "s2_"


def _prefill(ctx: s2.Section2Context) -> None:
    marker = ctx.case_id or "new"
    if st.session_state.get(K + "loaded") == marker:
        return
    st.session_state[K + "cv_last_updated"] = ctx.cv_last_updated
    st.session_state[K + "loaded"] = marker


def _file_size(n: int) -> str:
    return f"{n / 1024:.0f} KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.1f} MB"


def render() -> None:
    user = st.session_state["current_user"]
    today = date.today()
    ctx = cache.load_cached(f"pfc:s2:{user.id}", lambda s: s2.load(s, user.id, today))

    theme.html("""
    <div class="pf-hero"><div class="crumb">MY PROMOTION · SECTION 2 OF 11</div>
    <h1>Curriculum Vitae</h1>
    <p>Your detailed CV. Counts come from the structured sections that follow; the CV is kept on file for
    cross-checking.</p></div>""")

    if ctx.case_id is None:
        st.info("Save Section 0 (Applicant Details & Promotion Track) first — it creates your draft application.",
                icon=":material/info:")
        return

    _prefill(ctx)
    editable = ctx.status in EDITABLE
    if editable:
        entries_ui.panel("cv", "s2_flash")

    if flash := st.session_state.pop(K + "flash", None):
        st.success(flash, icon=":material/check_circle:")
    if not editable:
        st.info("This application has been submitted, so Section 2 is read-only.", icon=":material/lock:")

    _form(ctx, user.id, today, editable)


@st.fragment
def _form(ctx: s2.Section2Context, user_id: int, today: date, editable: bool) -> None:
    with st.container(key="card_cv"):
        theme.card_header("01", "Detailed CV", "PDF or Word, one file.")
        doc = ctx.cv_document
        if doc is not None:
            theme.html(f"""<div class="pf-kv"><div><span>Current file</span><b>{theme.esc(doc.original_filename)}</b></div>
            <div><span>Size</span><b>{_file_size(doc.size_bytes)}</b></div>
            <div><span>Uploaded</span><b>{doc.uploaded_at:%d %b %Y}</b></div></div>""")
        st.file_uploader("CV" if doc is None else "Replace your CV", type=sorted(s2.ALLOWED_EXTENSIONS),
                         key=K + "file", disabled=not editable, help="PDF or Word, up to 25 MB.")
        st.date_input("CV last updated", key=K + "cv_last_updated", min_value=date(2000, 1, 1),
                      max_value=date.today(), format="DD/MM/YYYY", disabled=not editable,
                      help="A warning is shown if this is more than 6 months before you submit.")

    if editable:
        _save_bar(user_id, today, ctx)


def _save_bar(user_id: int, today: date, ctx: s2.Section2Context) -> None:
    st.write("")
    a, b = st.columns([1, 2.2], vertical_alignment="center")
    save = a.button("Save Section 2", type="primary", icon=":material/save:", use_container_width=True, key="s2_save")
    b.caption("Your answers are saved as a draft. Nothing is submitted until the final Review & submit step.")
    if not save:
        return
    cv_last_updated = st.session_state.get(K + "cv_last_updated")
    uploaded = st.session_state.get(K + "file")
    upload = (uploaded.name, uploaded.getvalue()) if uploaded is not None else None
    errors = s2.validate_section2(cv_last_updated, ctx.cv_document is not None, today, upload)
    if errors:
        theme.html('<div class="pf-err"><b>Please fix the following before saving:</b><ul>'
                   + "".join(f"<li>{theme.esc(e)}</li>" for e in errors) + "</ul></div>")
        return
    try:
        with session_scope() as s:
            case_id = s2.save(s, user_id, cv_last_updated, today, upload)
    except s2.CaseLocked as e:
        st.error(str(e))
        return
    st.session_state[K + "loaded"] = case_id
    st.session_state[K + "flash"] = "Section 2 saved."
    st.session_state.pop(K + "file", None)
    st.rerun()
