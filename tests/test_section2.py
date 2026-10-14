"""Section 2 (curriculum vitae): saving the date and the file, validation, and the locked case. Each test is a small
function whose name says what it checks. They use `app_env` (see conftest.py), a fresh temporary database seeded
with reference data and test accounts, so no test depends on another and none touches the real database.
"""
from datetime import date

import pytest
from sqlalchemy import select

from promoflow.db.enums import CaseStatus, PromotionTrack, Rank
from promoflow.db.models import CaseDocument, PromotionCase, User
from promoflow.dossier import section0 as s0
from promoflow.dossier import section2 as s2

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


# The seeded test applicant (created by db/seed.py), looked up by email.
def applicant(s):
    return s.scalar(select(User).where(User.email == "applicant@promoflow.test"))


def test_save_before_section0_is_locked(app_env):
    with app_env.session_scope() as s:
        with pytest.raises(s2.CaseLocked):
            s2.save(s, applicant(s).id, date(2026, 8, 1), TODAY)


def test_save_cv_and_upload(app_env):
    with app_env.session_scope() as s:
        uid = applicant(s).id
        case_id = s0.save(s, uid, dict(S0_VALUES), TODAY)
        s2.save(s, uid, date(2026, 8, 1), TODAY, upload=("cv.pdf", b"cv-bytes"))
    with app_env.session_scope() as s:
        case = s.get(PromotionCase, case_id)
        assert case.cv_last_updated == date(2026, 8, 1)
        doc = s.scalar(select(CaseDocument).where(CaseDocument.case_id == case_id))
        assert doc.original_filename == "cv.pdf" and doc.superseded_by_id is None
        ctx = s2.load(s, uid, TODAY)
        assert ctx.cv_document.original_filename == "cv.pdf"


def test_submitted_case_is_locked(app_env):
    with app_env.session_scope() as s:
        uid = applicant(s).id
        case_id = s0.save(s, uid, dict(S0_VALUES), TODAY)
        s.get(PromotionCase, case_id).status = CaseStatus.SUBMITTED
    with app_env.session_scope() as s:
        with pytest.raises(s2.CaseLocked):
            s2.save(s, applicant(s).id, date(2026, 8, 1), TODAY)


def test_validate_section2():
    errors = s2.validate_section2(None, has_document=False, today=TODAY)
    assert len(errors) == 2
    assert s2.validate_section2(date(2026, 8, 1), has_document=True, today=TODAY) == []
    future = s2.validate_section2(date(2099, 1, 1), has_document=True, today=TODAY)
    assert "future" in future[0]
