"""Section 4 (rank history and non-academic positions): add, update and delete, the checks for two current ranks or a
mismatch with Section 0, validation, and the locked case. Each test is a small function whose name says what it
checks. They use `app_env` (see conftest.py), a fresh temporary database seeded with reference data and test
accounts, so no test depends on another and none touches the real database.
"""
from datetime import date

import pytest
from sqlalchemy import select

from promoflow.db.enums import CaseStatus, PromotionTrack, Rank
from promoflow.db.models import PromotionCase, RankHistory, User
from promoflow.dossier import section0 as s0
from promoflow.dossier import section4 as s4

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
CURRENT_RANK = {
    "rank": Rank.ASSISTANT_PROFESSOR, "date_obtained": date(2019, 9, 1), "university": "University of Sharjah",
    "country_code": "AE", "held_from": date(2019, 9, 1), "held_to": None, "at_this_university": True,
}
POSITION = {"position": "IT Manager", "employer": "Acme Inc", "country_code": "AE",
           "date_from": date(2010, 1, 1), "date_to": date(2015, 1, 1)}


# The seeded test applicant (created by db/seed.py), looked up by email.
def applicant(s):
    return s.scalar(select(User).where(User.email == "applicant@promoflow.test"))


# Create the draft case from S0_VALUES and return its id (most tests need a case to attach entries to).
def _case(s):
    return s0.save(s, applicant(s).id, dict(S0_VALUES), TODAY)


def test_add_rank_before_section0_is_locked(app_env):
    with app_env.session_scope() as s:
        with pytest.raises(s4.CaseLocked):
            s4.add_rank(s, applicant(s).id, dict(CURRENT_RANK), None)


def test_add_update_delete_rank(app_env):
    with app_env.session_scope() as s:
        uid = applicant(s).id
        _case(s)
        rank_id = s4.add_rank(s, uid, dict(CURRENT_RANK), None)
    with app_env.session_scope() as s:
        ctx = s4.load(s, applicant(s).id, TODAY)
        assert len(ctx.ranks) == 1 and ctx.ranks[0].rank.rank == Rank.ASSISTANT_PROFESSOR
        assert s4.section_checks(ctx.ranks, ctx.current_rank) == []

        s4.update_rank(s, applicant(s).id, rank_id, dict(CURRENT_RANK, university="New University"))
    with app_env.session_scope() as s:
        assert s.get(RankHistory, rank_id).university == "New University"
        s4.delete_rank(s, applicant(s).id, rank_id)
    with app_env.session_scope() as s:
        assert s.get(RankHistory, rank_id) is None


def test_section_checks_flag_two_current_entries_and_mismatch(app_env):
    with app_env.session_scope() as s:
        uid = applicant(s).id
        _case(s)
        s4.add_rank(s, uid, dict(CURRENT_RANK, rank=Rank.LECTURER, held_from=date(2015, 1, 1),
                                 held_to=date(2019, 8, 31)), None)
        s4.add_rank(s, uid, dict(CURRENT_RANK), None)
        s4.add_rank(s, uid, dict(CURRENT_RANK, rank=Rank.ASSOCIATE_PROFESSOR, held_from=date(2020, 1, 1),
                                 held_to=None), None)
    with app_env.session_scope() as s:
        ctx = s4.load(s, applicant(s).id, TODAY)
        problems = s4.section_checks(ctx.ranks, ctx.current_rank)
        assert any("Only one rank entry" in p for p in problems)


def test_add_update_delete_position(app_env):
    with app_env.session_scope() as s:
        uid = applicant(s).id
        _case(s)
        position_id = s4.add_position(s, uid, dict(POSITION), None)
    with app_env.session_scope() as s:
        ctx = s4.load(s, applicant(s).id, TODAY)
        assert len(ctx.positions) == 1 and ctx.positions[0].position.employer == "Acme Inc"
        s4.delete_position(s, applicant(s).id, position_id)
    with app_env.session_scope() as s:
        ctx = s4.load(s, applicant(s).id, TODAY)
        assert ctx.positions == []


def test_validate_rank_and_position():
    assert s4.validate_rank({}, TODAY) != []
    assert s4.validate_rank(dict(CURRENT_RANK), TODAY) == []
    assert s4.validate_position({}) != []
    assert s4.validate_position(dict(POSITION)) == []


def test_submitted_case_is_locked(app_env):
    with app_env.session_scope() as s:
        uid = applicant(s).id
        case_id = _case(s)
        s.get(PromotionCase, case_id).status = CaseStatus.SUBMITTED
    with app_env.session_scope() as s:
        with pytest.raises(s4.CaseLocked):
            s4.add_rank(s, applicant(s).id, dict(CURRENT_RANK), None)
