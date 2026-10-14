"""What the HoD and the Dean see: only cases waiting at their own gate, inside their own department/college."""
import pytest
from sqlalchemy import select

from promoflow.admin import create_user
from promoflow.auth.service import roles_for
from promoflow.db.enums import Component, Gate, GateOutcome, RoleName, Verdict
from promoflow.db.models import User
from promoflow.workflow import service
from promoflow.workflow.nodes import stub_result
from promoflow.workflow.nodes.report import build_report
from tests.test_workflow_service import STUB, submit, svc, uid  # noqa: F401  (svc is a fixture)


def grants(app_env, email: str):
    with app_env.session_scope() as s:
        return roles_for(s, s.scalar(select(User).where(User.email == f"{email}@promoflow.test")))


def waiting(app_env, email: str):
    with app_env.session_scope() as s:
        return service.waiting_cases(s, grants(app_env, email))


def test_nothing_is_waiting_before_the_review_runs(app_env, svc):
    submit(app_env)
    assert waiting(app_env, "hod.cs") == []


def test_the_hod_sees_the_case_and_nobody_else_does(app_env, svc):
    case_id = submit(app_env)
    svc.start_review(case_id, options=STUB, wait=True)
    [case] = waiting(app_env, "hod.cs")
    assert case.case_id == case_id and case.gate == "hod" and case.applicant_name == "Test Applicant"
    assert waiting(app_env, "dean.comp") == [] and waiting(app_env, "chancellor") == []


def test_after_the_hod_approves_it_moves_to_the_dean_with_the_hods_comment(app_env, svc):
    case_id = submit(app_env)
    with app_env.session_scope() as s:
        hod, dean = uid(s, "hod.cs"), uid(s, "dean.comp")
    svc.start_review(case_id, options=STUB, wait=True)
    svc.resume(case_id, hod, Gate.HOD, GateOutcome.APPROVE, "Strong research record", wait=True)
    assert waiting(app_env, "hod.cs") == []
    [case] = waiting(app_env, "dean.comp")
    assert case.gate == "dean"
    with app_env.session_scope() as s:
        detail = service.case_detail(s, case_id, grants(app_env, "dean.comp"))
    [earlier] = detail.decisions
    assert earlier.gate == Gate.HOD and earlier.comment == "Strong research record"
    assert earlier.decided_by == "Test Head of CS"


def test_the_report_carries_eligibility_and_every_flag(app_env, svc):
    case_id = submit(app_env)
    svc.start_review(case_id, options=STUB, wait=True)
    with app_env.session_scope() as s:
        report = service.case_detail(s, case_id, grants(app_env, "hod.cs")).report
    assert report["eligibility"]["verdict"] == "pass" and set(report["sections"]) == {"research", "teaching", "service"}
    assert {f["component"] for f in report["flags"]} == {"eligibility", "research", "teaching", "service"}


def test_a_head_of_another_department_cannot_open_the_case(app_env, svc):
    case_id = submit(app_env)
    svc.start_review(case_id, options=STUB, wait=True)
    with app_env.session_scope() as s:
        create_user(s, email="hod.physics@promoflow.test", full_name="Other HoD", college="College of Sciences",
                    department="Physics", password="a-long-test-password", roles=[RoleName.HOD])
    assert waiting(app_env, "hod.physics") == []
    with app_env.session_scope() as s:
        with pytest.raises(service.NotAllowed):
            service.case_detail(s, case_id, grants(app_env, "hod.physics"))


def test_a_person_without_a_reviewer_role_gets_nothing(app_env, svc):
    case_id = submit(app_env)
    svc.start_review(case_id, options=STUB, wait=True)
    assert waiting(app_env, "applicant") == []


def test_eligibility_needing_a_person_makes_the_overall_result_open():
    results = {}
    for comp in (Component.RESEARCH, Component.TEACHING, Component.SERVICE):
        results.update(stub_result(comp, Verdict.PASS)["results"])
    assert build_report(results)["overall_pass"] is True
    results.update(stub_result(Component.ELIGIBILITY, Verdict.NEEDS_HUMAN)["results"])
    report = build_report(results)
    assert report["overall_pass"] is None
    assert any(f["component"] == "eligibility" for f in report["flags"])
