"""start_review / resume / select_referees / get_status on a submitted case, with stub agents and an in-memory
checkpointer (the database is the seeded SQLite test database)."""
from datetime import date

import pytest
from sqlalchemy import select

from promoflow.db.enums import CaseStatus, Gate, GateOutcome
from promoflow.db.models import CaseReport, CaseStatusHistory, Flag, GateDecision, User
from promoflow.dossier import section0 as s0
from promoflow.dossier import section11 as s11
from promoflow.workflow import service
from promoflow.workflow.graph import memory_checkpointer
from tests.test_eligibility_checker import ON, S0_VALUES

STUB = {"stub_eligible": True}


@pytest.fixture
def svc(app_env):
    service.configure(memory_checkpointer())
    service._busy.clear()
    service._errors.clear()
    return service


def uid(s, email: str) -> int:
    return s.scalar(select(User.id).where(User.email == f"{email}@promoflow.test"))


def submit(app_env, day: date = ON) -> int:
    """A submitted case for the test applicant (the second call is a resubmission after a revision)."""
    with app_env.session_scope() as s:
        applicant = uid(s, "applicant")
        case_id = s0.save(s, applicant, dict(S0_VALUES), day)
        s11.submit(s, applicant, day)
    return case_id


def status(app_env, case_id) -> CaseStatus:
    return service.get_status(case_id).case_status


def users(app_env):
    with app_env.session_scope() as s:
        return {name: uid(s, name) for name in ("applicant", "hod.cs", "dean.comp", "chancellor")}


def test_start_review_runs_the_agents_and_stops_at_the_hod(app_env, svc):
    case_id = submit(app_env)
    svc.start_review(case_id, options=STUB, wait=True)
    st = svc.get_status(case_id)
    assert st.case_status == CaseStatus.HOD_REVIEW and st.waiting_for == "hod"
    assert not st.running and st.error is None
    assert st.report["overall_pass"] is True and set(st.report["verdicts"]) == {"research", "teaching", "service"}
    with app_env.session_scope() as s:
        steps = [h.to_status for h in s.scalars(select(CaseStatusHistory).where(
            CaseStatusHistory.case_id == case_id).order_by(CaseStatusHistory.id))]
    # (creating the draft also wrote a first "draft" row)
    assert steps[-3:] == [CaseStatus.SUBMITTED, CaseStatus.UNDER_EVALUATION, CaseStatus.HOD_REVIEW]


def test_only_a_submitted_case_can_be_reviewed(app_env, svc):
    with app_env.session_scope() as s:
        case_id = s0.save(s, uid(s, "applicant"), dict(S0_VALUES), ON)      # still a draft
    with pytest.raises(svc.ReviewError):
        svc.start_review(case_id, options=STUB, wait=True)


def test_full_path_hod_dean_chancellor(app_env, svc):
    u = users(app_env)
    case_id = submit(app_env)
    svc.start_review(case_id, options=STUB, wait=True)
    svc.resume(case_id, u["hod.cs"], Gate.HOD, GateOutcome.APPROVE, wait=True)
    assert status(app_env, case_id) == CaseStatus.DEAN_REVIEW
    svc.resume(case_id, u["dean.comp"], Gate.DEAN, GateOutcome.APPROVE, "Agreed", wait=True)
    assert status(app_env, case_id) == CaseStatus.REFEREE_SELECTION
    svc.select_referees(case_id, u["chancellor"], [1, 2], wait=True)
    assert status(app_env, case_id) == CaseStatus.AWAITING_REFEREE_REPORTS
    with app_env.session_scope() as s:
        decisions = list(s.scalars(select(GateDecision).where(GateDecision.case_id == case_id)
                                   .order_by(GateDecision.id)))
    assert [(d.gate, d.outcome) for d in decisions] == [(Gate.HOD, GateOutcome.APPROVE), (Gate.DEAN, GateOutcome.APPROVE)]


def test_decisions_are_checked_against_gate_and_role(app_env, svc):
    u = users(app_env)
    case_id = submit(app_env)
    svc.start_review(case_id, options=STUB, wait=True)
    with pytest.raises(svc.ReviewError, match="not waiting"):
        svc.resume(case_id, u["dean.comp"], Gate.DEAN, GateOutcome.APPROVE)       # a stale Dean page
    with pytest.raises(svc.ReviewError, match="not allowed"):
        svc.resume(case_id, u["dean.comp"], Gate.HOD, GateOutcome.APPROVE)        # the Dean is not the HoD
    with pytest.raises(svc.ReviewError, match="not allowed"):
        svc.resume(case_id, u["applicant"], Gate.HOD, GateOutcome.APPROVE)
    assert status(app_env, case_id) == CaseStatus.HOD_REVIEW
    with pytest.raises(svc.ReviewError, match="Only the Chancellor|not waiting"):
        svc.select_referees(case_id, u["chancellor"], [1])


def test_return_for_revision_needs_sections_and_a_comment(app_env, svc):
    u = users(app_env)
    case_id = submit(app_env)
    svc.start_review(case_id, options=STUB, wait=True)
    with pytest.raises(svc.ReviewError, match="sections"):
        svc.resume(case_id, u["hod.cs"], Gate.HOD, GateOutcome.RETURN_FOR_REVISION, "Fix it")
    with pytest.raises(svc.ReviewError, match="comment"):
        svc.resume(case_id, u["hod.cs"], Gate.HOD, GateOutcome.RETURN_FOR_REVISION, "  ", ["5"])
    svc.resume(case_id, u["hod.cs"], Gate.HOD, GateOutcome.RETURN_FOR_REVISION, "5A is incomplete", ["5"], wait=True)
    assert status(app_env, case_id) == CaseStatus.RETURNED_FOR_REVISION
    with app_env.session_scope() as s:
        decision = s.scalar(select(GateDecision).where(GateDecision.case_id == case_id))
    assert decision.sections_to_revise == ["5"] and decision.comment == "5A is incomplete"


def test_not_eligible_case_ends_the_review(app_env, svc):
    case_id = submit(app_env)
    svc.start_review(case_id, options={"stub_eligible": False}, wait=True)
    assert status(app_env, case_id) == CaseStatus.NOT_ELIGIBLE


def test_resubmission_after_a_revision_is_a_fresh_run(app_env, svc):
    u = users(app_env)
    case_id = submit(app_env)
    svc.start_review(case_id, options=STUB, wait=True)
    svc.resume(case_id, u["hod.cs"], Gate.HOD, GateOutcome.RETURN_FOR_REVISION, "Fix 5A", ["5"], wait=True)
    with app_env.session_scope() as s:
        s11.submit(s, u["applicant"], date(2026, 10, 4))                          # the applicant resubmits
    svc.start_review(case_id, options=STUB, wait=True)
    assert status(app_env, case_id) == CaseStatus.HOD_REVIEW
    with app_env.session_scope() as s:
        versions = list(s.scalars(select(CaseReport.version).where(CaseReport.case_id == case_id)
                                  .order_by(CaseReport.version)))
    assert versions == [1, 2]


def test_a_failing_run_is_reported_not_lost(app_env, svc, monkeypatch):
    case_id = submit(app_env)

    def boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(service, "_get_graph", boom)
    svc.start_review(case_id, options=STUB, wait=True)
    st = svc.get_status(case_id)
    assert "boom" in st.error and not st.running
    with app_env.session_scope() as s:
        assert s.scalar(select(Flag.code).where(Flag.case_id == case_id)) == "workflow_error"
