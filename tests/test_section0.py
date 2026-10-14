"""Section 0 (applicant details and promotion track): the first save creates the draft case, later saves update it,
and a submitted case is locked. Each test is a small function whose name says what it checks. They use `app_env`
(see conftest.py), a fresh temporary database seeded with reference data and test accounts, so no test depends on
another and none touches the real database.
"""
from datetime import date

import pytest
from sqlalchemy import select

from promoflow.db.enums import CaseStatus, PromotionTrack, Rank
from promoflow.db.models import AuditLogEntry, CaseStatusHistory, PromotionCase, User
from promoflow.dossier import section0 as s0

# A fixed 'today', so the tests give the same answer on any day of the year.
TODAY = date(2026, 9, 25)
VALUES = {
    "academic_year": "2026/2027", "track": PromotionTrack.TO_ASSOCIATE, "specialization": "Computer Science",
    "fine_specialization": "Machine Learning", "research_keywords": ["NLP", "RAG"],
    "appointment_date": date(2019, 9, 1), "rank_on_appointment": Rank.ASSISTANT_PROFESSOR,
    "current_rank_date": date(2019, 9, 1), "scopus_author_id": "57193456789", "orcid": "0000-0002-1825-0097",
    "phd_outside_uae": True, "early_application": False, "exceptional_case": False,
    "exceptional_justification": "should be dropped", "previously_rejected": False, "rejection_date": None,
}


# The seeded test applicant (created by db/seed.py), looked up by email.
def applicant(s):
    return s.scalar(select(User).where(User.email == "applicant@promoflow.test"))


def test_first_save_creates_a_draft_then_updates_it(app_env):
    with app_env.session_scope() as s:
        uid = applicant(s).id
        case_id = s0.save(s, uid, dict(VALUES), TODAY)
    with app_env.session_scope() as s:
        case = s.get(PromotionCase, case_id)
        assert case.status == CaseStatus.DRAFT
        assert case.current_rank == Rank.ASSISTANT_PROFESSOR  # derived from the track
        assert case.exceptional_justification is None  # cleared when the toggle is off
        assert case.research_keywords == ["NLP", "RAG"]
        assert s.scalar(select(CaseStatusHistory).where(CaseStatusHistory.case_id == case_id)) is not None
        again = s0.save(s, uid, dict(VALUES, specialization="Informatics"), TODAY)
        assert again == case_id
    with app_env.session_scope() as s:
        audits = s.scalars(select(AuditLogEntry).where(AuditLogEntry.action == "section0_saved")).all()
        assert len(audits) == 2 and audits[-1].before["specialization"] == "Computer Science"
        ctx = s0.load(s, applicant(s).id, TODAY)
        assert ctx.values["specialization"] == "Informatics"
        assert set(ctx.criteria) == {PromotionTrack.TO_ASSOCIATE, PromotionTrack.TO_FULL}


def test_submitted_case_is_locked(app_env):
    with app_env.session_scope() as s:
        case_id = s0.save(s, applicant(s).id, dict(VALUES), TODAY)
        s.get(PromotionCase, case_id).status = CaseStatus.SUBMITTED
    with app_env.session_scope() as s:
        with pytest.raises(s0.CaseLocked):
            s0.save(s, applicant(s).id, dict(VALUES), TODAY)
