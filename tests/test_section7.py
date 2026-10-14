"""Section 7 (service): committees, administrative positions, workshops, trainings, policy contributions and
community activities. Each test is a small function whose name says what it checks. They use `app_env` (see
conftest.py), a fresh temporary database seeded with reference data and test accounts, so no test depends on
another and none touches the real database.
"""
from datetime import date

import pytest
from sqlalchemy import select

from promoflow.db.enums import CaseStatus, OrgLevel, PromotionTrack, Rank, WorkshopRole
from promoflow.db.models import LookupValue, PromotionCase, User
from promoflow.dossier import section0 as s0
from promoflow.dossier import section7 as s7
from promoflow.dossier.section7 import (
    admin_positions, committees, community, policy_contributions, trainings, workshops,
)

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


def test_add_committee_before_section0_is_locked(app_env):
    with app_env.session_scope() as s:
        role_id = s.scalar(select(LookupValue).where(LookupValue.list_code == "committee_role")).id
        with pytest.raises(committees.CaseLocked):
            committees.add(s, applicant(s).id, {
                "committee_name": "Exams committee", "level": OrgLevel.DEPARTMENT, "role_id": role_id,
                "date_from": date(2023, 1, 1), "date_to": None, "contribution_summary": None,
            }, ("letter.pdf", b"x"))


def test_committee_crud(app_env):
    with app_env.session_scope() as s:
        role_id = s.scalar(select(LookupValue).where(LookupValue.list_code == "committee_role")).id
    with app_env.session_scope() as s:
        uid = applicant(s).id
        _case(s)
        cid = committees.add(s, uid, {
            "committee_name": "Exams committee", "level": OrgLevel.DEPARTMENT, "role_id": role_id,
            "date_from": date(2023, 1, 1), "date_to": None, "contribution_summary": "Chaired 4 meetings.",
        }, ("letter.pdf", b"x"))
    with app_env.session_scope() as s:
        ctx = s7.load(s, applicant(s).id)
        assert len(ctx.committees) == 1
        committees.delete(s, applicant(s).id, cid)
    with app_env.session_scope() as s:
        ctx = s7.load(s, applicant(s).id)
        assert ctx.committees == []


def test_admin_position_and_workshop_and_training_and_policy(app_env):
    with app_env.session_scope() as s:
        position_id = s.scalar(select(LookupValue).where(LookupValue.list_code == "admin_position")).id
        policy_role_id = s.scalar(select(LookupValue).where(LookupValue.list_code == "policy_role")).id
    with app_env.session_scope() as s:
        uid = applicant(s).id
        _case(s)
        admin_positions.add(s, uid, {"position_id": position_id, "unit": "CS Department",
                                     "date_from": date(2022, 1, 1), "date_to": None}, ("letter.pdf", b"x"))
        workshops.add(s, uid, {"title": "AI workshop", "organized_by": OrgLevel.DEPARTMENT,
                               "role": WorkshopRole.ORGANISER_AND_LECTURER, "activity_date": date(2024, 3, 1),
                               "attendees": 30}, ("cert.pdf", b"x"))
        trainings.add(s, uid, {"title": "New faculty training", "inside_university": True,
                               "host_organisation": "UoS CTL", "activity_date": date(2024, 2, 1), "hours": 6,
                               "participants": 20}, ("cert.pdf", b"x"))
        policy_contributions.add(s, uid, {"policy_name": "Academic Integrity Policy", "level": OrgLevel.COLLEGE,
                                          "role_id": policy_role_id, "activity_date": date(2023, 5, 1)},
                                 ("minutes.pdf", b"x"))
    with app_env.session_scope() as s:
        ctx = s7.load(s, applicant(s).id)
        assert len(ctx.admin_positions) == 1
        assert len(ctx.workshops) == 1
        assert len(ctx.trainings) == 1
        assert len(ctx.policy_contributions) == 1


def test_community_activity_requires_funded_project_link():
    errors = community.validate({"activity_type_id": 1, "title": "x", "beneficiary_organisation": "y",
                                 "applicant_role": "z", "date_from": date(2024, 1, 1), "deliverables": "d"},
                                is_funded_project=True, has_evidence=True)
    assert any("funded project" in e for e in errors)
    ok = community.validate({"activity_type_id": 1, "funded_project_id": 5, "title": "x",
                            "beneficiary_organisation": "y", "applicant_role": "z", "date_from": date(2024, 1, 1),
                            "deliverables": "d"}, is_funded_project=True, has_evidence=True)
    assert ok == []


def test_community_activity_crud(app_env):
    with app_env.session_scope() as s:
        activity_type_id = s.scalar(select(LookupValue).where(LookupValue.list_code == "community_activity_type")).id
    with app_env.session_scope() as s:
        uid = applicant(s).id
        _case(s)
        aid = community.add(s, uid, {
            "activity_type_id": activity_type_id, "funded_project_id": None, "title": "School workshop",
            "beneficiary_organisation": "Local school", "applicant_role": "Speaker", "date_from": date(2024, 1, 1),
            "date_to": date(2024, 1, 1), "beneficiaries": 40, "deliverables": "One-day workshop",
            "measurable_outcome": None,
        }, ("evidence.pdf", b"x"))
    with app_env.session_scope() as s:
        ctx = s7.load(s, applicant(s).id)
        assert len(ctx.community) == 1
        community.delete(s, applicant(s).id, aid)
    with app_env.session_scope() as s:
        ctx = s7.load(s, applicant(s).id)
        assert ctx.community == []


def test_submitted_case_is_locked(app_env):
    with app_env.session_scope() as s:
        role_id = s.scalar(select(LookupValue).where(LookupValue.list_code == "committee_role")).id
    with app_env.session_scope() as s:
        uid = applicant(s).id
        case_id = _case(s)
        s.get(PromotionCase, case_id).status = CaseStatus.SUBMITTED
    with app_env.session_scope() as s:
        with pytest.raises(committees.CaseLocked):
            committees.add(s, applicant(s).id, {
                "committee_name": "Exams committee", "level": OrgLevel.DEPARTMENT, "role_id": role_id,
                "date_from": date(2023, 1, 1), "date_to": None, "contribution_summary": None,
            }, ("letter.pdf", b"x"))
