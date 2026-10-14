"""5A · Journal paper entry — the tab inside the Section 5 (Research) page."""
from datetime import date

import streamlit as st

from promoflow.db.enums import AuthorRole, JournalClass, Language, MainAuthorBasis, PublicationStatus
from promoflow.db.session import session_scope
from promoflow.dossier.section5 import papers as s5p
from promoflow.dossier.section5.common import after_current_rank
from promoflow.ui import theme

K = "s5a_"
LANGUAGE_LABEL = {Language.ENGLISH: "English", Language.ARABIC: "Arabic", Language.OTHER: "Other"}
STATUS_LABEL = {PublicationStatus.PUBLISHED: "Published", PublicationStatus.ACCEPTED: "Accepted (in press)"}
ROLE_LABEL = {AuthorRole.SOLE: "Sole author", AuthorRole.MAIN: "Main author", AuthorRole.CO_AUTHOR: "Co-author"}
BASIS_LABEL = {MainAuthorBasis.FIRST_AUTHOR: "First author", MainAuthorBasis.CORRESPONDING_AUTHOR: "Corresponding author",
              MainAuthorBasis.SUPERVISION_RULE: "Supervision rule", MainAuthorBasis.OTHER: "Other"}
CLASS_LABEL = {JournalClass.CLASS_A: ("Class A", "green"), JournalClass.CLASS_B: ("Class B", "grey"),
              JournalClass.NOT_COUNTED: ("Not counted", "amber")}


def render(current_rank_date: date | None, previously_rejected: bool, rows: list[s5p.PublicationRow],
          editable: bool) -> None:
    editing = st.session_state.get(K + "editing")
    for row in rows:
        if editing == row.publication.id:
            _form(current_rank_date, previously_rejected, editable, row)
        else:
            _summary(row, current_rank_date, editable)
    if editable:
        if editing == "new":
            _form(current_rank_date, previously_rejected, editable, None)
        elif st.button("+ Add a journal paper", key="s5a_add"):
            st.session_state[K + "editing"] = "new"
            st.rerun()


def _summary(row: s5p.PublicationRow, current_rank_date, editable: bool) -> None:
    p = row.publication
    label, cls = CLASS_LABEL[row.classification.journal_class]
    on_or_after = after_current_rank(p.issue_date or p.acceptance_date, current_rank_date)
    with st.container(key=f"card_paper_{p.id}"):
        a, b = st.columns([5, 1])
        with a:
            theme.html(f"""<div class="pf-card-h"><h3>{theme.esc(p.title)}</h3></div>
            <div class="pf-card-sub" style="margin-left:0">{theme.esc(p.journal_name)} ·
            {STATUS_LABEL[p.status]} · {ROLE_LABEL[p.applicant_role]}
            <span class="pf-chip {cls}" style="margin-left:6px">{theme.esc(label)}</span></div>""")
            if on_or_after is False:
                theme.html('<div class="pf-note">Dated before your current rank was obtained — flagged, '
                          'excluded from counting.</div>')
            if not p.submit_for_promotion:
                theme.html('<div class="pf-note">Kept on record; not submitted for promotion.</div>')
        with b:
            if editable:
                if st.button("Edit", key=f"s5a_edit_{p.id}", use_container_width=True):
                    st.session_state[K + "editing"] = p.id
                    st.rerun()
                if st.button("Delete", key=f"s5a_del_{p.id}", use_container_width=True):
                    with session_scope() as s:
                        s5p.delete(s, st.session_state["current_user"].id, p.id)
                    st.session_state["s5_flash"] = "Paper removed."
                    st.rerun()


@st.fragment
def _form(current_rank_date, previously_rejected: bool, editable: bool, row: "s5p.PublicationRow | None") -> None:
    p = row.publication if row else None
    prefix = f"s5a_f_{p.id if p else 'new'}_"
    today = date.today()
    with st.container(key=f"card_paper_form_{p.id if p else 'new'}"):
        theme.card_header("+", "Edit journal paper" if p else "Add a journal paper")
        title = st.text_input("Paper title", value=p.title if p else "", key=prefix + "title")
        a, b = st.columns(2)
        journal_name = a.text_input("Journal name", value=p.journal_name if p else "", key=prefix + "journal")
        issn = b.text_input("ISSN / eISSN", value=p.issn if p else "", placeholder="1234-5678",
                            key=prefix + "issn")
        c, d = st.columns(2)
        publisher = c.text_input("Publisher", value=p.publisher if p else "", key=prefix + "publisher")
        language = d.selectbox("Language", list(Language), format_func=LANGUAGE_LABEL.get,
                               index=list(Language).index(p.language) if p else None,
                               placeholder="Choose a language", key=prefix + "language")

        st.write("**Status and dates**")
        e, f = st.columns(2)
        status = e.selectbox("Publication status", list(PublicationStatus), format_func=STATUS_LABEL.get,
                             index=list(PublicationStatus).index(p.status) if p else None,
                             placeholder="Choose status", key=prefix + "status")
        volume = issue = pages = issue_date = acceptance_date = None
        if status == PublicationStatus.PUBLISHED:
            issue_date = f.date_input("Date of issue", value=p.issue_date if p else None,
                                      min_value=date(1970, 1, 1), max_value=today, format="DD/MM/YYYY",
                                      key=prefix + "issue_date", help="Only the month and year are used.")
            g, h, i = st.columns(3)
            volume = g.text_input("Volume", value=p.volume if p else "", key=prefix + "volume")
            issue = h.text_input("Issue", value=p.issue if p else "", key=prefix + "issue")
            pages = i.text_input("Pages", value=p.pages if p else "", key=prefix + "pages")
        elif status == PublicationStatus.ACCEPTED:
            acceptance_date = f.date_input("Acceptance date", value=p.acceptance_date if p else None,
                                           min_value=date(1970, 1, 1), max_value=today, format="DD/MM/YYYY",
                                           key=prefix + "acceptance_date")
        new_since_rejection = None
        if previously_rejected:
            new_since_rejection = st.toggle("New since your previous rejected application?",
                                            value=bool(p.new_since_rejection) if p else False,
                                            key=prefix + "new_since_rejection")

        st.write("**Authorship**")
        j, k = st.columns(2)
        total_authors = j.number_input("Total number of authors", min_value=1, step=1,
                                       value=p.total_authors if p else 1, key=prefix + "total")
        author_position = k.number_input("Your position in the author list", min_value=1, step=1,
                                         value=p.author_position if p else 1, key=prefix + "position")
        existing_others = [a.display_name for a in sorted(row.authors, key=lambda a: a.position)
                          if not a.is_applicant] if row else []
        other_authors_text = st.text_area("Other authors (one per line, in order)",
                                          value="\n".join(existing_others), key=prefix + "others",
                                          help="Don't include yourself — your name is inserted at your position above.")
        l, m = st.columns(2)
        applicant_role = l.selectbox("Applicant's role", list(AuthorRole), format_func=ROLE_LABEL.get,
                                     index=list(AuthorRole).index(p.applicant_role) if p else None,
                                     placeholder="Choose a role", key=prefix + "role")
        main_author_basis = main_author_explanation = None
        if applicant_role == AuthorRole.MAIN:
            main_author_basis = m.selectbox("Basis for main-author claim", list(MainAuthorBasis),
                                            format_func=BASIS_LABEL.get,
                                            index=list(MainAuthorBasis).index(p.main_author_basis) if p and p.main_author_basis else None,
                                            placeholder="Choose a basis", key=prefix + "basis")
            if main_author_basis == MainAuthorBasis.OTHER:
                main_author_explanation = st.text_area("Explanation", value=(p.main_author_explanation if p else "") or "",
                                                       key=prefix + "explanation")
        with_supervised_student = st.toggle("A co-author is a student I supervise(d)",
                                            value=bool(p.with_supervised_student) if p else False,
                                            key=prefix + "supervised",
                                            help="Linking to a specific §6H supervision entry isn't available yet.")

        st.write("**Institution and originality**")
        n, o = st.columns(2)
        at_this_university = n.toggle("Produced while at this university", value=bool(p.at_this_university) if p else True,
                                      key=prefix + "here")
        from_thesis = o.toggle("Derived from my Master's or PhD thesis", value=bool(p.from_thesis) if p else False,
                               key=prefix + "thesis")

        st.write("**Journal classification**")
        impact_factor = st.number_input("ISI impact factor (required to claim Class A)", min_value=0.0, step=0.01,
                                        value=float(p.impact_factor) if p and p.impact_factor else 0.0,
                                        key=prefix + "impact_factor")
        theme.html('<div class="pf-note">Scopus indexing, SJR percentile and journal class are matched '
                  "automatically from the ISSN once it's in our journal-ranking table; otherwise the paper "
                  'shows as "Not counted" until an admin adds the journal.</div>')

        st.write("**Evidence**")
        paper_upload = acceptance_upload = None
        if status == PublicationStatus.PUBLISHED:
            paper_label = "Paper file" if row is None or row.paper_file is None else "Replace paper file"
            paper_upload = st.file_uploader(paper_label, type=["pdf"], key=prefix + "paper_file")
        elif status == PublicationStatus.ACCEPTED:
            acc_label = "Acceptance letter" if row is None or row.acceptance_letter is None else "Replace acceptance letter"
            acceptance_upload = st.file_uploader(acc_label, type=["pdf"], key=prefix + "acceptance_file")

        submit_for_promotion = st.toggle("Submit this paper for promotion?",
                                         value=bool(p.submit_for_promotion) if p else True, key=prefix + "submit")

        values = {
            "title": title.strip(), "journal_name": journal_name.strip(), "issn": issn.strip(),
            "publisher": publisher.strip(), "volume": (volume or "").strip() or None,
            "issue": (issue or "").strip() or None, "pages": (pages or "").strip() or None, "language": language,
            "submit_for_promotion": submit_for_promotion, "status": status, "issue_date": issue_date,
            "acceptance_date": acceptance_date, "new_since_rejection": new_since_rejection,
            "author_position": int(author_position), "total_authors": int(total_authors),
            "applicant_role": applicant_role, "main_author_basis": main_author_basis,
            "main_author_explanation": (main_author_explanation or "").strip() or None,
            "with_supervised_student": with_supervised_student, "at_this_university": at_this_university,
            "from_thesis": from_thesis, "impact_factor": impact_factor or None, "disputes_class": False,
            "dispute_reason": None,
        }
        other_authors = [line.strip() for line in other_authors_text.splitlines() if line.strip()]
        paper_tuple = (paper_upload.name, paper_upload.getvalue()) if paper_upload is not None else None
        acceptance_tuple = (acceptance_upload.name, acceptance_upload.getvalue()) if acceptance_upload is not None else None

        save_col, cancel_col = st.columns([1, 1])
        if save_col.button("Save paper", type="primary", icon=":material/save:", key=prefix + "save",
                           use_container_width=True):
            errors = s5p.validate(values, today, previously_rejected, other_authors,
                                  row.paper_file is not None if row else False,
                                  row.acceptance_letter is not None if row else False,
                                  paper_tuple, acceptance_tuple)
            if errors:
                theme.html('<div class="pf-err"><b>Please fix the following:</b><ul>'
                          + "".join(f"<li>{theme.esc(e)}</li>" for e in errors) + "</ul></div>")
                return
            user_id = st.session_state["current_user"].id
            with session_scope() as s:
                if p is None:
                    s5p.add(s, user_id, values, other_authors, paper_tuple, acceptance_tuple)
                else:
                    s5p.update(s, user_id, p.id, values, other_authors, paper_tuple, acceptance_tuple)
            st.session_state.pop(K + "editing", None)
            st.session_state["s5_flash"] = "Paper saved."
            st.rerun()
        if cancel_col.button("Cancel", key=prefix + "cancel", use_container_width=True):
            st.session_state.pop(K + "editing", None)
            st.rerun()
