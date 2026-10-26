"""Nobody decides on their own application: a Head of Department or an (acting) Dean may also be an applicant."""
from datetime import date

import pytest
from sqlalchemy import select

from promoflow.auth.service import roles_for
from promoflow.db.enums import CaseStatus, Gate, GateOutcome
from promoflow.db.models import User
from promoflow.dossier import section0 as s0
from promoflow.dossier import section11 as s11
from promoflow.workflow import review_service
from promoflow.workflow.graph import memory_checkpointer
from tests.test_eligibility_checker import ON, S0_VALUES

STUB = {"stub_eligible": True}


@pytest.fixture
def svc(app_env):
    review_service.configure(memory_checkpointer())
    review_service._busy.clear()
    review_service._errors.clear()
    return review_service


def user_and_grants(app_env, name: str):
    with app_env.session_scope() as s:
        u = s.scalar(select(User).where(User.email == f"{name}@promoflow.test"))
        return u.id, list(roles_for(s, u))


def submit_own_case(app_env, user_id: int, day: date = ON) -> int:
    with app_env.session_scope() as s:
        case_id = s0.save(s, user_id, dict(S0_VALUES), day)
        s11.submit(s, user_id, day)
    return case_id


def test_a_head_of_department_cannot_see_or_decide_their_own_case(app_env, svc):
    hod_id, grants = user_and_grants(app_env, "hod.cs")
    case_id = submit_own_case(app_env, hod_id)
    svc.start_review(case_id, options=STUB, wait=True)
    assert svc.get_status(case_id).case_status == CaseStatus.HOD_REVIEW
    with app_env.session_scope() as s:
        assert [c.case_id for c in svc.waiting_cases(s, grants, hod_id)] == []        # not in their own list
        assert [c.case_id for c in svc.waiting_cases(s, grants)] == [case_id]           # the plain query still finds it
        with pytest.raises(svc.NotAllowed):
            svc.case_detail(s, case_id, grants, hod_id)
    with pytest.raises(svc.ReviewError, match="not allowed"):
        svc.resume(case_id, hod_id, Gate.HOD, GateOutcome.APPROVE, wait=True)
    assert svc.get_status(case_id).case_status == CaseStatus.HOD_REVIEW


def test_a_dean_can_apply_and_the_head_still_reviews_the_case(app_env, svc):
    dean_id, dean_grants = user_and_grants(app_env, "dean.comp")
    hod_id, _ = user_and_grants(app_env, "hod.cs")
    case_id = submit_own_case(app_env, dean_id)                       # the Dean has the applicant role too
    svc.start_review(case_id, options=STUB, wait=True)
    svc.resume(case_id, hod_id, Gate.HOD, GateOutcome.APPROVE, wait=True)       # the Head of the department decides
    assert svc.get_status(case_id).case_status == CaseStatus.DEAN_REVIEW
    with app_env.session_scope() as s:
        assert svc.waiting_cases(s, dean_grants, dean_id) == []                  # the Dean never reviews their own case
    with pytest.raises(svc.ReviewError, match="not allowed"):
        svc.resume(case_id, dean_id, Gate.DEAN, GateOutcome.APPROVE, wait=True)
    assert svc.get_status(case_id).case_status == CaseStatus.DEAN_REVIEW


def test_other_cases_are_unaffected(app_env, svc):
    applicant_id, _ = user_and_grants(app_env, "applicant")
    hod_id, hod_grants = user_and_grants(app_env, "hod.cs")
    case_id = submit_own_case(app_env, applicant_id)
    svc.start_review(case_id, options=STUB, wait=True)
    with app_env.session_scope() as s:
        assert [c.case_id for c in svc.waiting_cases(s, hod_grants, hod_id)] == [case_id]
    svc.resume(case_id, hod_id, Gate.HOD, GateOutcome.APPROVE, wait=True)
    assert svc.get_status(case_id).case_status == CaseStatus.DEAN_REVIEW
