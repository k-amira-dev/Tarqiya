"""Section 8 – Recommendation letter (spec chapter 12, repeatable, optional)."""
import streamlit as st

from promoflow.db.session import session_scope
from promoflow.dossier import section8 as s8
from promoflow.dossier.section0 import EDITABLE
from promoflow.ui import theme
from promoflow.ui.views.section7.lookups import recommendation_relationship_options

K = "s8_"


def render() -> None:
    user = st.session_state["current_user"]
    with session_scope() as s:
        ctx = s8.load(s, user.id)

    theme.html("""
    <div class="pf-hero"><div class="crumb">MY PROMOTION · SECTION 8 OF 11</div>
    <h1>Recommendation Letters</h1>
    <p>Optional. Add as many letters as you have.</p></div>""")

    if ctx.case_id is None:
        st.info("Save Section 0 (Applicant Details & Promotion Track) first — it creates your draft application.",
                icon=":material/info:")
        return

    editable = ctx.status in EDITABLE
    if flash := st.session_state.pop("s8_flash", None):
        st.success(flash, icon=":material/check_circle:")
    if not editable:
        st.info("This application has been submitted, so Section 8 is read-only.", icon=":material/lock:")

    relationships = {o.id: o.label for o in recommendation_relationship_options()}
    for row in ctx.letters:
        _summary(row, relationships, editable)

    editing = st.session_state.get(K + "editing")
    if editable:
        if editing == "new":
            _form()
        elif st.button("+ Add a recommendation letter", key="s8_add"):
            st.session_state[K + "editing"] = "new"
            st.rerun()


def _summary(row: s8.RecommendationLetterRow, relationships: dict, editable: bool) -> None:
    letter = row.letter
    with st.container(key=f"card_letter_{letter.id}"):
        a, b = st.columns([5, 1])
        with a:
            theme.html(f"""<div class="pf-card-h"><h3>{theme.esc(letter.writer_name)}</h3></div>
            <div class="pf-card-sub" style="margin-left:0">{theme.esc(letter.writer_rank)},
            {theme.esc(letter.writer_institution)} · {theme.esc(relationships.get(letter.relationship_id, ""))}</div>""")
        with b:
            if editable and st.button("Delete", key=f"s8_del_{letter.id}", use_container_width=True):
                with session_scope() as s:
                    s8.delete(s, st.session_state["current_user"].id, letter.id)
                st.session_state["s8_flash"] = "Letter removed."
                st.rerun()


def _form() -> None:
    relationships = recommendation_relationship_options()
    rel_ids = [r.id for r in relationships]
    rel_labels = {r.id: r.label for r in relationships}
    with st.container(key="card_letter_form"):
        theme.card_header("+", "Add a recommendation letter")
        writer_name = st.text_input("Writer's name", key="s8_f_name", help="Sensitive.")
        a, b = st.columns(2)
        writer_rank = a.text_input("Writer's rank / title", key="s8_f_rank")
        writer_institution = b.text_input("Writer's institution", key="s8_f_institution")
        relationship_id = st.selectbox("Relationship to applicant", rel_ids, format_func=rel_labels.get,
                                       index=None, placeholder="Choose a relationship", key="s8_f_relationship")
        upload = st.file_uploader("Letter", type=["pdf"], key="s8_f_evidence")

        values = {"writer_name": writer_name.strip(), "writer_rank": writer_rank.strip(),
                 "writer_institution": writer_institution.strip(), "relationship_id": relationship_id}
        upload_tuple = (upload.name, upload.getvalue()) if upload is not None else None

        save_col, cancel_col = st.columns([1, 1])
        if save_col.button("Save letter", type="primary", icon=":material/save:", key="s8_f_save",
                           use_container_width=True):
            errors = s8.validate(values, False, upload_tuple)
            if errors:
                theme.html('<div class="pf-err"><b>Please fix the following:</b><ul>'
                          + "".join(f"<li>{theme.esc(e)}</li>" for e in errors) + "</ul></div>")
                return
            with session_scope() as s:
                s8.add(s, st.session_state["current_user"].id, values, upload_tuple)
            st.session_state.pop("s8_editing", None)
            st.session_state["s8_flash"] = "Letter saved."
            st.rerun()
        if cancel_col.button("Cancel", key="s8_f_cancel", use_container_width=True):
            st.session_state.pop("s8_editing", None)
            st.rerun()
