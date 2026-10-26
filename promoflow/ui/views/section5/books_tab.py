"""5B · Book / book chapter entry — the tab inside the Section 5 (Research) page."""
from datetime import date

import streamlit as st

from promoflow.ui.views import entries_ui

from promoflow.db.enums import BookItemType
from promoflow.db.session import session_scope
from promoflow.dossier.section5 import books as s5b
from promoflow.ui import theme

K = "s5b_"
TYPE_LABEL = {BookItemType.KNOWLEDGE_CONTRIBUTION: "Knowledge-contribution book", BookItemType.SPECIALIZED: "Specialized book",
             BookItemType.TEXTBOOK: "Textbook", BookItemType.HERITAGE: "Heritage book", BookItemType.CHAPTER: "Book chapter"}


def render(rows: list[s5b.BookRow], editable: bool) -> None:
    if editable:
        entries_ui.panel("book", "s5_flash")
    editing = st.session_state.get(K + "editing")
    for row in rows:
        if editing == row.book.id:
            _form(editable, row)
        else:
            _summary(row, editable)
    if editable:
        if editing == "new":
            _form(editable, None)
        elif st.button("+ Add a book / book chapter", key="s5b_add"):
            st.session_state[K + "editing"] = "new"
            st.rerun()
    theme.html('<div class="pf-note">Caps (p.6): knowledge-contribution books max 2; specialized max 1; '
              'textbooks max 1; heritage max 1 (Class B); all books combined max 2 (Associate) / 3 (Full). '
              "Caps aren't enforced automatically yet.</div>")


def _summary(row: s5b.BookRow, editable: bool) -> None:
    b = row.book
    with st.container(key=f"card_book_{b.id}"):
        a, col = st.columns([5, 1])
        with a:
            title = b.chapter_title if b.item_type == BookItemType.CHAPTER and b.chapter_title else b.book_title
            theme.html(f"""<div class="pf-card-h"><h3>{theme.esc(title)}</h3></div>
            <div class="pf-card-sub" style="margin-left:0">{TYPE_LABEL[b.item_type]} ·
            {theme.esc(b.publisher)} · {b.publication_date:%b %Y}</div>""")
            if row.evidence is None:
                theme.html('<div class="pf-note">Missing: evidence.</div>')
        with col:
            if editable:
                if st.button("Edit", key=f"s5b_edit_{b.id}", use_container_width=True):
                    st.session_state[K + "editing"] = b.id
                    st.rerun()
                if st.button("Delete", key=f"s5b_del_{b.id}", use_container_width=True):
                    with session_scope() as s:
                        s5b.delete(s, st.session_state["current_user"].id, b.id)
                    st.session_state["s5_flash"] = "Book entry removed."
                    st.rerun()


@st.fragment
def _form(editable: bool, row: "s5b.BookRow | None") -> None:
    b = row.book if row else None
    prefix = f"s5b_f_{b.id if b else 'new'}_"
    today = date.today()
    with st.container(key=f"card_book_form_{b.id if b else 'new'}"):
        theme.card_header("+", "Edit book entry" if b else "Add a book / book chapter")
        entries_ui.autofill("book", prefix)
        item_type = st.selectbox("Item type", list(BookItemType), format_func=TYPE_LABEL.get,
                                 index=list(BookItemType).index(b.item_type) if b else None,
                                 placeholder="Choose a type", key=prefix + "type")
        book_title = st.text_input("Book title", value=b.book_title if b else "", key=prefix + "book_title")
        chapter_title = None
        if item_type == BookItemType.CHAPTER:
            chapter_title = st.text_input("Chapter title", value=(b.chapter_title if b else "") or "",
                                          key=prefix + "chapter_title")
        a, c = st.columns(2)
        publisher = a.text_input("Publisher", value=b.publisher if b else "", key=prefix + "publisher")
        publication_date = c.date_input("Publication year / month", value=b.publication_date if b else None,
                                        min_value=date(1970, 1, 1), max_value=today, format="DD/MM/YYYY",
                                        key=prefix + "pub_date", help="Only the month and year are used.")
        d, e = st.columns(2)
        isbn = d.text_input("ISBN", value=b.isbn if b else "", key=prefix + "isbn")
        main_or_sole_author = e.toggle("Main or sole author?", value=bool(b.main_or_sole_author) if b else True,
                                       key=prefix + "main_or_sole")
        financial_support_by = st.text_input("Financial support provided by (optional)",
                                             value=(b.financial_support_by if b else "") or "",
                                             key=prefix + "support")
        f, g = st.columns(2)
        refereed = f.toggle("Refereed?", value=bool(b.refereed) if b else False, key=prefix + "refereed")
        referee_count = None
        if refereed:
            referee_count = g.number_input("Number of referees", min_value=0, step=1,
                                           value=b.referee_count if b and b.referee_count else 0,
                                           key=prefix + "referee_count")
        from_thesis = st.toggle("Derived from thesis?", value=bool(b.from_thesis) if b else False,
                                key=prefix + "thesis")
        label = "Evidence" if row is None or row.evidence is None else "Replace evidence"
        upload = st.file_uploader(label, type=["pdf"], key=prefix + "evidence",
                                  help="Cover, copyright page and table of contents (book) or chapter PDF.")

        values = {"item_type": item_type, "book_title": book_title.strip(),
                 "chapter_title": (chapter_title or "").strip() or None, "publisher": publisher.strip(),
                 "publication_date": publication_date, "isbn": isbn.strip(),
                 "main_or_sole_author": main_or_sole_author,
                 "financial_support_by": financial_support_by.strip() or None, "refereed": refereed,
                 "referee_count": int(referee_count) if referee_count is not None else None,
                 "from_thesis": from_thesis}
        upload_tuple = (upload.name, upload.getvalue()) if upload is not None else None

        save_col, cancel_col = st.columns([1, 1])
        if save_col.button("Save", type="primary", icon=":material/save:", key=prefix + "save",
                           use_container_width=True):
            errors = s5b.validate(values, today, row.evidence is not None if row else False, upload_tuple)
            if errors:
                theme.html('<div class="pf-err"><b>Please fix the following:</b><ul>'
                          + "".join(f"<li>{theme.esc(e)}</li>" for e in errors) + "</ul></div>")
                return
            user_id = st.session_state["current_user"].id
            with session_scope() as s:
                if b is None:
                    s5b.add(s, user_id, values, upload_tuple)
                else:
                    s5b.update(s, user_id, b.id, values, upload_tuple)
            st.session_state.pop(K + "editing", None)
            st.session_state["s5_flash"] = "Book entry saved."
            st.rerun()
        if cancel_col.button("Cancel", key=prefix + "cancel", use_container_width=True):
            st.session_state.pop(K + "editing", None)
            st.rerun()
