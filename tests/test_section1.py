"""Section 1 (declarations and the signed application form): saving, replacing the signed file (the old one is kept
as history), the research-item count, validation, and the locked case. Each test is a small function whose name
says what it checks. They use `app_env` (see conftest.py), a fresh temporary database seeded with reference data
and test accounts, so no test depends on another and none touches the real database.
"""
from datetime import date

import pytest
from sqlalchemy import select

from promoflow.db.enums import (
    AuthorRole, CaseStatus, DocumentKind, Language, LookupSource, PromotionTrack, PublicationStatus, Rank,
)
from promoflow.db.models import AuditLogEntry, CaseDocument, Publication, PromotionCase, User
from promoflow.dossier import section0 as s0
from promoflow.dossier import section1 as s1

# A fixed 'today', so the tests give the same answer on any day of the year.
TODAY = date(2026, 9, 25)
# Valid Section 0 answers. Every test starts from a draft case built with these.
S0_VALUES = {
    "academic_year": "2026/2027", "track": PromotionTrack.TO_ASSOCIATE, "specialization": "Computer Science",
    "fine_specialization": "Machine Learning", "research_keywords": ["NLP"],
    "appointment_date": date(2019, 9, 1), "rank_on_appointment": Rank.ASSISTANT_PROFESSOR,
    "current_rank_date": date(2019, 9, 1), "scopus_author_id": "57193456789", "orcid": None,
    "phd_outside_uae": False, "early_application": False, "exceptional_case": False,
    "exceptional_justification": None, "previously_rejected": False, "rejection_date": None,
}
S1_VALUES = {"decl_not_from_thesis": True, "decl_after_current_rank": True,
            "application_signed_date": date(2026, 9, 20)}


# The seeded test applicant (created by db/seed.py), looked up by email.
def applicant(s):
    return s.scalar(select(User).where(User.email == "applicant@promoflow.test"))


def test_save_before_section0_is_locked(app_env):
    with app_env.session_scope() as s:
        with pytest.raises(s1.CaseLocked):
            s1.save(s, applicant(s).id, dict(S1_VALUES), TODAY)


def test_save_declarations_and_signed_form(app_env):
    with app_env.session_scope() as s:
        uid = applicant(s).id
        case_id = s0.save(s, uid, dict(S0_VALUES), TODAY)
        s1.save(s, uid, dict(S1_VALUES), TODAY, upload=("signed.pdf", b"pdf-bytes"))
    with app_env.session_scope() as s:
        case = s.get(PromotionCase, case_id)
        assert case.decl_not_from_thesis is True
        assert case.application_signed_date == date(2026, 9, 20)
        doc = s.scalar(select(CaseDocument).where(CaseDocument.case_id == case_id))
        assert doc.kind == DocumentKind.SIGNED_FORM and doc.original_filename == "signed.pdf"
        assert doc.size_bytes == len(b"pdf-bytes") and doc.superseded_by_id is None
        assert s.scalar(select(AuditLogEntry).where(AuditLogEntry.action == "section1_saved")) is not None

        ctx = s1.load(s, uid, TODAY)
        assert ctx.case_id == case_id and ctx.signed_document.original_filename == "signed.pdf"


def test_reupload_supersedes_the_old_file(app_env):
    with app_env.session_scope() as s:
        uid = applicant(s).id
        case_id = s0.save(s, uid, dict(S0_VALUES), TODAY)
        s1.save(s, uid, dict(S1_VALUES), TODAY, upload=("first.pdf", b"one"))
        s1.save(s, uid, dict(S1_VALUES), TODAY, upload=("second.pdf", b"two"))
    with app_env.session_scope() as s:
        docs = s.scalars(select(CaseDocument).where(CaseDocument.case_id == case_id)).all()
        assert len(docs) == 2
        first = next(d for d in docs if d.original_filename == "first.pdf")
        second = next(d for d in docs if d.original_filename == "second.pdf")
        assert first.superseded_by_id == second.id
        ctx = s1.load(s, uid, TODAY)
        assert ctx.signed_document.original_filename == "second.pdf"


def test_submitted_case_is_locked(app_env):
    with app_env.session_scope() as s:
        uid = applicant(s).id
        case_id = s0.save(s, uid, dict(S0_VALUES), TODAY)
        s.get(PromotionCase, case_id).status = CaseStatus.SUBMITTED
    with app_env.session_scope() as s:
        with pytest.raises(s1.CaseLocked):
            s1.save(s, applicant(s).id, dict(S1_VALUES), TODAY)


def test_research_item_count_only_counts_submitted_publications(app_env):
    with app_env.session_scope() as s:
        uid = applicant(s).id
        case_id = s0.save(s, uid, dict(S0_VALUES), TODAY)
        common = dict(
            case_id=case_id, lookup_source=LookupSource.MANUAL, title="Paper", journal_name="J",
            publisher="P", language=Language.ENGLISH, status=PublicationStatus.PUBLISHED,
            issue_date=date(2024, 1, 1), author_position=1, total_authors=1,
            applicant_role=AuthorRole.SOLE, at_this_university=True, from_thesis=False,
        )
        s.add(Publication(submit_for_promotion=True, **common))
        s.add(Publication(submit_for_promotion=False, **common))
    with app_env.session_scope() as s:
        assert s1.research_item_count(s, case_id) == 1


def test_validate_section1():
    errors = s1.validate_section1({}, has_signed_document=False, today=TODAY)
    assert len(errors) == 4  # both declarations, date signed, and the file
    ok = s1.validate_section1(dict(S1_VALUES), has_signed_document=True, today=TODAY)
    assert ok == []
    future = s1.validate_section1(dict(S1_VALUES, application_signed_date=date(2099, 1, 1)),
                                  has_signed_document=True, today=TODAY)
    assert "future" in future[0]
    bad_ext = s1.validate_section1(dict(S1_VALUES), has_signed_document=False, today=TODAY,
                                   new_upload=("form.exe", b"x"))
    assert any("PDF" in e for e in bad_ext)
