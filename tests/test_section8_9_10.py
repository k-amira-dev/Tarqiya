"""Sections 8, 9 and 10: recommendation letters, the signed Conditions Form and the signed cover letter. Each test is
a small function whose name says what it checks. They use `app_env` (see conftest.py), a fresh temporary database
seeded with reference data and test accounts, so no test depends on another and none touches the real database.
"""
from datetime import date

import pytest
from sqlalchemy import select

from promoflow.db.enums import CaseStatus, PromotionTrack, Rank
from promoflow.db.models import LookupValue, PromotionCase, RecommendationLetter, User
from promoflow.dossier import section0 as s0
from promoflow.dossier import section8, section9, section10

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


# Create the draft case from S0_VALUES and return its id (most tests need a case to attach entries to).
def _case(s):
    return s0.save(s, applicant(s).id, dict(S0_VALUES), TODAY)


def test_section8_letter_crud(app_env):
    with app_env.session_scope() as s:
        rel_id = s.scalar(select(LookupValue).where(LookupValue.list_code == "recommendation_relationship")).id
    with app_env.session_scope() as s:
        uid = applicant(s).id
        _case(s)
        letter_id = section8.add(s, uid, {
            "writer_name": "Dr Smith", "writer_rank": "Professor", "writer_institution": "MIT",
            "relationship_id": rel_id,
        }, ("letter.pdf", b"x"))
    with app_env.session_scope() as s:
        ctx = section8.load(s, applicant(s).id)
        assert len(ctx.letters) == 1
        section8.delete(s, applicant(s).id, letter_id)
    with app_env.session_scope() as s:
        assert s.get(RecommendationLetter, letter_id) is None


def test_section9_conditions_form(app_env):
    with app_env.session_scope() as s:
        with pytest.raises(section9.CaseLocked):
            section9.save(s, applicant(s).id, date(2026, 9, 1))
    with app_env.session_scope() as s:
        uid = applicant(s).id
        case_id = _case(s)
        section9.save(s, uid, date(2026, 9, 1), ("conditions.pdf", b"x"))
    with app_env.session_scope() as s:
        ctx = section9.load(s, applicant(s).id)
        assert ctx.conditions_signed_date == date(2026, 9, 1)
        assert ctx.document.original_filename == "conditions.pdf"
    errors = section9.validate(None, False, TODAY)
    assert len(errors) == 2


def test_section10_cover_letter(app_env):
    with app_env.session_scope() as s:
        uid = applicant(s).id
        case_id = _case(s)
        section10.save(s, uid, date(2026, 9, 1), ("cover.pdf", b"x"))
    with app_env.session_scope() as s:
        ctx = section10.load(s, applicant(s).id)
        assert ctx.cover_letter_signed_date == date(2026, 9, 1)
        assert ctx.document.original_filename == "cover.pdf"


def test_section9_submitted_case_is_locked(app_env):
    with app_env.session_scope() as s:
        uid = applicant(s).id
        case_id = _case(s)
        s.get(PromotionCase, case_id).status = CaseStatus.SUBMITTED
    with app_env.session_scope() as s:
        with pytest.raises(section9.CaseLocked):
            section9.save(s, applicant(s).id, date(2026, 9, 1))
