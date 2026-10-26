"""5E · Journals Classification Form — the tab inside the Section 5 (Research) page."""
import streamlit as st

from promoflow.db.session import session_scope
from promoflow.dossier.section5 import classification as s5e
from promoflow.dossier.section5 import papers as s5p
from promoflow.ui import cache, theme
from promoflow.ui.views.section5.papers_tab import CLASS_LABEL

K = "s5e_"


def render(paper_rows: list[s5p.PublicationRow], case_id: int, editable: bool) -> None:
    with st.container(key="card_classification"):
        theme.card_header("5E", "Journals Classification Form",
                          "Generated from Section 5A: one row per distinct journal. Review it, sign it, and "
                          "upload the signed form below.")
        journals = s5e.distinct_journals(paper_rows)
        if not journals:
            theme.html('<div class="pf-note">No journals yet — add papers in 5A first.</div>')
        else:
            rows = ""
            for j in journals:
                label, cls = CLASS_LABEL[j.classification.journal_class]
                rows += (f'<div class="pf-check"><div class="ic {cls if cls != "green" else "ok"}">•</div>'
                        f'<div><b>{theme.esc(j.journal_name)}</b>'
                        f'<small>ISSN {theme.esc(j.issn or "—")} · {theme.esc(label)}</small></div></div>')
            theme.html(rows)

        signed = cache.load_cached(f"pfc:signedcls:{case_id}", lambda s: s5e.signed_form(s, case_id))
        if signed is not None:
            theme.html(f'<div class="pf-note">Current signed form: {theme.esc(signed.original_filename)}, '
                      f'uploaded {signed.uploaded_at:%d %b %Y}.</div>')
        if not editable:
            return
        label = "Signed Journals Classification Form" if signed is None else "Replace signed form"
        upload = st.file_uploader(label, type=["pdf"], key=K + "upload")
        if upload is not None and st.button("Upload signed form", type="primary", icon=":material/save:",
                                            key=K + "save"):
            with session_scope() as s:
                s5e.save_signed_form(s, case_id, st.session_state["current_user"].id,
                                    (upload.name, upload.getvalue()))
            with st.spinner("Reading the form…"):
                note = _declare_journals(case_id, upload.getvalue())
            st.session_state["s5_flash"] = "Signed classification form uploaded. " + note
            st.rerun()


def _declare_journals(case_id: int, data: bytes) -> str:
    """Read the uploaded form and add its journals (that the table lacks) so the papers are counted. Returns a sentence for the applicant."""
    from datetime import date

    from promoflow.extraction.doc_llm import ReadFailed
    from promoflow.extraction.picture_doc import read_entry_file
    from promoflow.ui.views import entries_ui

    text_llm, vision_llm = entries_ui._models()
    if text_llm is None:
        return "The form could not be read automatically here, so the journals were not classified."
    try:
        form, _, _ = read_entry_file(data, s5e.ClassificationForm, text_llm, vision_llm)
    except ReadFailed as e:
        return f"The journals in the form were not classified: {e}"
    with session_scope() as s:
        added = s5e.declare_journals_from_form(s, case_id, form, date.today().year)
    if not added:
        return "No new journals were needed: the papers' journals are already known, or the form did not match them (check the ISSN and journal name in 5A)."
    return "Journals counted from the form: " + "; ".join(added) + "."
