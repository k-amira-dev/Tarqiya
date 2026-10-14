"""Section 1 – Application Form for Promotion (spec chapter 5)."""
from datetime import date

import streamlit as st

from promoflow.db.session import session_scope
from promoflow.dossier import section1 as s1
from promoflow.dossier.section0 import EDITABLE
from promoflow.ui import cache, theme

K = "s1_"  # widget-key prefix


def _prefill(ctx: s1.Section1Context) -> None:
    marker = ctx.case_id or "new"
    if st.session_state.get(K + "loaded") == marker:
        return
    v = ctx.values
    st.session_state[K + "decl_not_from_thesis"] = bool(v.get("decl_not_from_thesis"))
    st.session_state[K + "decl_after_current_rank"] = bool(v.get("decl_after_current_rank"))
    st.session_state[K + "application_signed_date"] = v.get("application_signed_date")
    st.session_state[K + "loaded"] = marker


def _values() -> dict:
    return {f: st.session_state.get(K + f) for f in s1.FIELDS}


def _file_size(n: int) -> str:
    return f"{n / 1024:.0f} KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.1f} MB"


def render() -> None:
    user = st.session_state["current_user"]
    today = date.today()
    ctx = cache.load_cached(f"pfc:s1:{user.id}", lambda s: s1.load(s, user.id, today))

    theme.html(f"""
    <div class="pf-hero"><div class="crumb">MY PROMOTION · SECTION 1 OF 11</div>
    <h1>Application Form for Promotion</h1>
    <p>Your declarations for the promotion committee, and the signed application form itself.</p></div>""")

    if ctx.case_id is None:
        st.info("Save Section 0 (Applicant Details & Promotion Track) first — it creates your draft application.",
                icon=":material/info:")
        return

    _prefill(ctx)
    editable = ctx.status in EDITABLE

    if flash := st.session_state.pop(K + "flash", None):
        st.success(flash, icon=":material/check_circle:")
    if not editable:
        st.info("This application has been submitted, so Section 1 is read-only.", icon=":material/lock:")

    _form(ctx, user.id, today, editable)


@st.fragment
def _form(ctx: s1.Section1Context, user_id: int, today: date, editable: bool) -> None:
    _items_card(ctx)
    _declarations_card(editable)
    _form_card(ctx, editable)
    if editable:
        _save_bar(user_id, today, ctx)


def _items_card(ctx: s1.Section1Context) -> None:
    with st.container(key="card_items"):
        theme.card_header("01", "Research items submitted",
                          "Counted automatically from Sections 5A, 5A-2, 5B, 5C and 5G.")
        theme.html(f"""<div class="pf-stat" style="max-width:220px"><b>{ctx.research_item_count}</b>
        <span>items counted so far</span></div>
        <div class="pf-note" style="margin-top:10px">This total updates once you enter your papers, creative
        works, books, conference papers and patents in Sections 5A–5G. It will read 0 until those sections are
        filled in.</div>""")


def _declarations_card(editable: bool) -> None:
    with st.container(key="card_declarations"):
        theme.card_header("02", "Declarations", "From the application form's declaration (Appendix I, Ninth).")
        st.toggle("The items counted above were not taken from my Master's or PhD thesis",
                 key=K + "decl_not_from_thesis", disabled=not editable)
        st.toggle("All items were published, accepted or presented after I obtained my current rank",
                 key=K + "decl_after_current_rank", disabled=not editable)
        theme.html('<div class="pf-note">Each paper you enter in §5A/§5B also records its own "derived from '
                   'thesis?" answer; a paper marked Yes there is excluded from the count above, and any item '
                   'dated before your current rank is flagged for the reviewer.</div>')


def _form_card(ctx: s1.Section1Context, editable: bool) -> None:
    with st.container(key="card_form"):
        theme.card_header("03", "Signed application form",
                          "Document generation (Appendix I, A and B) is not built yet. For now, get the official "
                          "application form template from the promotion office, fill it in by hand, sign it, and "
                          "upload it here.")
        doc = ctx.signed_document
        if doc is not None:
            theme.html(f"""<div class="pf-kv"><div><span>Current file</span><b>{theme.esc(doc.original_filename)}</b></div>
            <div><span>Size</span><b>{_file_size(doc.size_bytes)}</b></div>
            <div><span>Uploaded</span><b>{doc.uploaded_at:%d %b %Y}</b></div></div>""")
        st.file_uploader("Signed application form" if doc is None else "Replace the signed application form",
                         type=sorted(s1.ALLOWED_EXTENSIONS), key=K + "file", disabled=not editable,
                         help="PDF, Word, Excel or image, up to 25 MB.")
        st.date_input("Date signed", key=K + "application_signed_date", min_value=date(2000, 1, 1),
                      max_value=date.today(), format="DD/MM/YYYY", disabled=not editable)


def _save_bar(user_id: int, today: date, ctx: s1.Section1Context) -> None:
    st.write("")
    a, b = st.columns([1, 2.2], vertical_alignment="center")
    save = a.button("Save Section 1", type="primary", icon=":material/save:", use_container_width=True, key="s1_save")
    b.caption("Your answers are saved as a draft. Nothing is submitted until the final Review & submit step.")
    if not save:
        return
    values = _values()
    uploaded = st.session_state.get(K + "file")
    upload = (uploaded.name, uploaded.getvalue()) if uploaded is not None else None
    errors = s1.validate_section1(values, ctx.signed_document is not None, today, upload)
    if errors:
        theme.html('<div class="pf-err"><b>Please fix the following before saving:</b><ul>'
                   + "".join(f"<li>{theme.esc(e)}</li>" for e in errors) + "</ul></div>")
        return
    try:
        with session_scope() as s:
            case_id = s1.save(s, user_id, values, today, upload)
    except s1.CaseLocked as e:
        st.error(str(e))
        return
    st.session_state[K + "loaded"] = case_id
    st.session_state[K + "flash"] = "Section 1 saved."
    st.session_state.pop(K + "file", None)
    st.rerun()
