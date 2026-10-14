"""Section 11 (review and submit): the completeness checklist, Submit blocked outside a submission window, allowed
inside one, and blocked a second time. Each test is a small function whose name says what it checks. They use
`app_env` (see conftest.py), a fresh temporary database seeded with reference data and test accounts, so no test
depends on another and none touches the real database.
"""
from datetime import date

import pytest
from sqlalchemy import select

from promoflow.db.enums import CaseStatus, PromotionTrack, Rank
from promoflow.db.models import PromotionCase, User
from promoflow.dossier import section0 as s0
from promoflow.dossier import section11 as s11

# A fixed 'today', so the tests give the same answer on any day of the year.
TODAY = date(2026, 9, 25)  # not a submission window
WINDOW_DAY = date(2026, 10, 3)  # inside the Oct 1-7 window
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


def test_load_with_no_case(app_env):
    with app_env.session_scope() as s:
        ctx = s11.load(s, applicant(s).id, TODAY)
        assert ctx.case_id is None and ctx.sections == [] and not ctx.can_submit


def test_load_reflects_incomplete_sections(app_env):
    with app_env.session_scope() as s:
        _case(s)
    with app_env.session_scope() as s:
        ctx = s11.load(s, applicant(s).id, TODAY)
        assert ctx.case_id is not None
        assert ctx.completed_count < len(ctx.sections)
        by_code = {row.code: row for row in ctx.sections}
        assert by_code["0"].complete is True  # section0 fully filled by S0_VALUES
        assert by_code["3"].complete is False  # no degrees yet
        assert not ctx.can_submit


def test_submit_blocked_outside_window(app_env):
    with app_env.session_scope() as s:
        uid = applicant(s).id
        _case(s)
    with app_env.session_scope() as s:
        with pytest.raises(s11.CaseLocked):
            s11.submit(s, applicant(s).id, TODAY)


def test_submit_succeeds_in_window(app_env):
    with app_env.session_scope() as s:
        uid = applicant(s).id
        case_id = _case(s)
    with app_env.session_scope() as s:
        s11.submit(s, applicant(s).id, WINDOW_DAY)
    with app_env.session_scope() as s:
        case = s.get(PromotionCase, case_id)
        assert case.status == CaseStatus.SUBMITTED
        assert case.submitted_at is not None


def test_submit_twice_is_locked(app_env):
    with app_env.session_scope() as s:
        _case(s)
    with app_env.session_scope() as s:
        s11.submit(s, applicant(s).id, WINDOW_DAY)
    with app_env.session_scope() as s:
        with pytest.raises(s11.CaseLocked):
            s11.submit(s, applicant(s).id, WINDOW_DAY)
