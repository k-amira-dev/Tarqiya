"""Section 5 (research): journal classification, ISBN check, papers with their author lists, creative works, books,
conference papers, funded projects, patents, awards, the Scopus record and the journal classification form. Each
test is a small function whose name says what it checks. They use `app_env` (see conftest.py), a fresh temporary
database seeded with reference data and test accounts, so no test depends on another and none touches the real
database.
"""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from promoflow.db.enums import (
    AuthorRole, BookItemType, CaseStatus, InvestigatorRole, JournalClass, Language, MainAuthorBasis, PatentStatus,
    ProjectStatus, PromotionTrack, PublicationStatus, Rank,
)
from promoflow.db.models import Journal, JournalRanking, LookupValue, Publication, PromotionCase, User
from promoflow.dossier import section0 as s0
from promoflow.dossier import section5 as s5
from promoflow.dossier.section5 import awards, books, conference, creative, funded, papers, patents, scopus
from promoflow.dossier.section5 import classification
from promoflow.rules.research import classify_journal, isbn_is_valid

# A fixed 'today', so the tests give the same answer on any day of the year.
TODAY = date(2026, 9, 25)
# Valid Section 0 answers. Every test starts from a draft case built with these.
S0_VALUES = {
    "academic_year": "2026/2027", "track": PromotionTrack.TO_ASSOCIATE, "specialization": "Computer Science",
    "fine_specialization": "Machine Learning", "research_keywords": [],
    "appointment_date": date(2019, 9, 1), "rank_on_appointment": Rank.ASSISTANT_PROFESSOR,
    "current_rank_date": date(2019, 9, 1), "scopus_author_id": "57193456789", "orcid": None,
    "phd_outside_uae": False, "early_application": False, "exceptional_case": False,
    "exceptional_justification": None, "previously_rejected": False, "rejection_date": None,
}
PAPER = {
    "doi": None, "title": "A Great Paper", "journal_name": "Journal of Things", "issn": "1234-5678",
    "publisher": "Elsevier", "volume": "12", "issue": "3", "pages": "1-10", "language": Language.ENGLISH,
    "submit_for_promotion": True, "status": PublicationStatus.PUBLISHED, "issue_date": date(2024, 1, 1),
    "acceptance_date": None, "new_since_rejection": None, "author_position": 1, "total_authors": 2,
    "applicant_role": AuthorRole.MAIN, "main_author_basis": MainAuthorBasis.FIRST_AUTHOR, "main_author_explanation": None,
    "with_supervised_student": False, "at_this_university": True, "from_thesis": False,
    "impact_factor": None, "disputes_class": False, "dispute_reason": None,
}


# The seeded test applicant (created by db/seed.py), looked up by email.
def applicant(s):
    return s.scalar(select(User).where(User.email == "applicant@promoflow.test"))


# Create the draft case from S0_VALUES and return its id (most tests need a case to attach entries to).
def _case(s):
    return s0.save(s, applicant(s).id, dict(S0_VALUES), TODAY)


def test_classify_journal():
    assert classify_journal(scopus_indexed=False, sjr_percentile=None, isi_listed=False, has_impact_factor=False) \
        == JournalClass.NOT_COUNTED
    assert classify_journal(scopus_indexed=True, sjr_percentile=Decimal("50"), isi_listed=False,
                            has_impact_factor=False) == JournalClass.CLASS_B
    assert classify_journal(scopus_indexed=True, sjr_percentile=Decimal("85"), isi_listed=True,
                            has_impact_factor=True) == JournalClass.CLASS_A


def test_isbn_is_valid():
    assert isbn_is_valid("0-306-40615-2")
    assert isbn_is_valid("978-3-16-148410-0")
    assert not isbn_is_valid("0-306-40615-3")


def test_add_paper_before_section0_is_locked(app_env):
    with app_env.session_scope() as s:
        with pytest.raises(papers.CaseLocked):
            papers.add(s, applicant(s).id, dict(PAPER), [], None, None)


def test_add_paper_with_authors_and_classification(app_env):
    with app_env.session_scope() as s:
        journal = Journal(title="Journal of Things", issn="1234-5678", isi_listed=True)
        s.add(journal)
        s.flush()
        s.add(JournalRanking(journal_id=journal.id, year=2024, scopus_indexed=True, sjr_category="Comp. Sci.",
                             sjr_percentile=Decimal("85"), quartile=1, impact_factor=Decimal("3.2")))
    with app_env.session_scope() as s:
        uid = applicant(s).id
        case_id = _case(s)
        values = dict(PAPER, impact_factor=Decimal("3.2"))
        paper_id = papers.add(s, uid, values, ["Jane Collaborator"], ("paper.pdf", b"pdf"), None)
    with app_env.session_scope() as s:
        rows = papers.load(s, case_id)
        assert len(rows) == 1
        row = rows[0]
        assert row.publication.title == "A Great Paper"
        assert [a.display_name for a in sorted(row.authors, key=lambda a: a.position)] == \
            ["Test Applicant", "Jane Collaborator"]
        assert row.classification.journal_class == JournalClass.CLASS_A
        assert row.paper_file.original_filename == "paper.pdf"

        papers.update(s, uid, paper_id, dict(values, title="An Even Greater Paper"), ["Jane Collaborator"])
    with app_env.session_scope() as s:
        assert s.get(Publication, paper_id).title == "An Even Greater Paper"
        papers.delete(s, applicant(s).id, paper_id)
    with app_env.session_scope() as s:
        assert s.get(Publication, paper_id) is None


def test_validate_paper_requires_author_count_match():
    errors = papers.validate(dict(PAPER), TODAY, False, [], False, False,
                             paper_upload=("p.pdf", b"x"))
    assert any("other" in e and "author" in e for e in errors)
    ok = papers.validate(dict(PAPER), TODAY, False, ["Jane Collaborator"], False, False,
                         paper_upload=("p.pdf", b"x"))
    assert ok == []


def test_validate_paper_main_author_needs_basis():
    errors = papers.validate(dict(PAPER, main_author_basis=None), TODAY, False, ["X"], False, False,
                            paper_upload=("p.pdf", b"x"))
    assert any("basis" in e for e in errors)


def test_creative_work_crud(app_env):
    with app_env.session_scope() as s:
        code = s.scalar(select(LookupValue).where(LookupValue.list_code == "creative_form"))
        form_id = code.id
    with app_env.session_scope() as s:
        uid = applicant(s).id
        _case(s)
        values = {"form_id": form_id, "title": "Exhibit A", "venue": "Gallery", "organizing_institution": "UoS",
                 "date_from": date(2024, 1, 1), "date_to": date(2024, 1, 5), "approved": True}
        work_id = creative.add(s, uid, values, ("evidence.pdf", b"x"))
    with app_env.session_scope() as s:
        ctx = s5.load(s, applicant(s).id, TODAY)
        assert len(ctx.creative_works) == 1
        creative.delete(s, applicant(s).id, work_id)
    with app_env.session_scope() as s:
        ctx = s5.load(s, applicant(s).id, TODAY)
        assert ctx.creative_works == []


def test_book_validate_bad_isbn():
    values = {"item_type": BookItemType.TEXTBOOK, "book_title": "Intro to X", "publisher": "Pub",
             "publication_date": date(2024, 1, 1), "isbn": "0-306-40615-3", "main_or_sole_author": True,
             "refereed": False, "from_thesis": False}
    errors = books.validate(values, TODAY, has_evidence=True)
    assert any("ISBN" in e for e in errors)


def test_conference_funded_patent_award_crud(app_env):
    with app_env.session_scope() as s:
        funder = s.scalar(select(LookupValue).where(LookupValue.list_code == "funder_type")).id
        office = s.scalar(select(LookupValue).where(LookupValue.list_code == "patent_office")).id
        scope = s.scalar(select(LookupValue).where(LookupValue.list_code == "award_scope")).id
    with app_env.session_scope() as s:
        uid = applicant(s).id
        _case(s)
        conference.add(s, uid, {
            "title": "Conf paper", "conference_title": "ICSE", "organizer": "IEEE",
            "conference_date": date(2024, 5, 1), "place": "Dubai", "pages": None,
            "main_or_sole_author": True, "scopus_indexed": True, "doi": None,
        }, ("proceedings.pdf", b"x"))
        funded.add(s, uid, {
            "title": "Grant", "funding_body": "NSF", "funder_type_id": funder, "role": InvestigatorRole.PI,
            "amount": None, "currency": None, "start_date": date(2023, 1, 1), "end_date": None,
            "status": ProjectStatus.ONGOING,
        }, ("award_letter.pdf", b"x"))
        patents.add(s, uid, {
            "title": "A Patent", "patent_number": "US123", "office_id": office, "status": PatentStatus.GRANTED,
            "grant_date": date(2024, 1, 1), "inventors": "Test Applicant",
        }, ("cert.pdf", b"x"))
        awards.add(s, uid, {"name": "Best Paper", "awarding_body": "IEEE", "year": 2024, "scope_id": scope}, None)
    with app_env.session_scope() as s:
        ctx = s5.load(s, applicant(s).id, TODAY)
        assert len(ctx.conference_papers) == 1
        assert len(ctx.funded_projects) == 1
        assert len(ctx.patents) == 1
        assert len(ctx.awards) == 1


def test_scopus_evidence_save_and_validate(app_env):
    errors = scopus.validate({"h_index": None, "total_citations": None, "screenshot_date": None}, TODAY, False)
    assert len(errors) == 4
    with app_env.session_scope() as s:
        uid = applicant(s).id
        _case(s)
        scopus.save(s, uid, {"h_index": 10, "total_citations": 200, "screenshot_date": date(2026, 9, 1)},
                   ("scopus.png", b"x"))
    with app_env.session_scope() as s:
        ctx = s5.load(s, applicant(s).id, TODAY)
        assert ctx.scopus.evidence.h_index == 10
        assert ctx.scopus.screenshot.original_filename == "scopus.png"


def test_journal_classification_distinct_journals(app_env):
    with app_env.session_scope() as s:
        uid = applicant(s).id
        _case(s)
        papers.add(s, uid, dict(PAPER), ["Jane Collaborator"], ("p.pdf", b"x"), None)
        papers.add(s, uid, dict(PAPER, title="Second paper"), ["Jane Collaborator"], ("p2.pdf", b"x"), None)
    with app_env.session_scope() as s:
        ctx = s5.load(s, applicant(s).id, TODAY)
        journals = classification.distinct_journals(ctx.papers)
        assert len(journals) == 1  # both papers share the same ISSN


def test_submitted_case_is_locked(app_env):
    with app_env.session_scope() as s:
        uid = applicant(s).id
        case_id = _case(s)
        s.get(PromotionCase, case_id).status = CaseStatus.SUBMITTED
    with app_env.session_scope() as s:
        with pytest.raises(papers.CaseLocked):
            papers.add(s, applicant(s).id, dict(PAPER), [], None, None)
