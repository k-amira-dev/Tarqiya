"""The only door between the pages and the agents. Pages call these and never touch the graph:

    start_review(case_id)                        run the agents on a submitted case (in the background)
    resume(case_id, user_id, gate, outcome, ...) the HoD's or Dean's decision; the paused run continues
    select_referees(case_id, user_id, ids)       the Chancellor's selection
    get_status(case_id)                          what to show: case status, who it waits for, the report
    waiting_cases(s, grants)                     the cases waiting for a reviewer, inside their own scope
    case_detail(s, case_id, grants)              one waiting case in full (report + earlier decisions)

The database is the link: the graph runs in a background thread (a Streamlit script run must never wait for an
agent), writes its results to the tables, and this module keeps `promotion_case.status` in step. get_status reads
only the database, so it is as quick as any other page query.

A case can be submitted more than once (after a revision). Each submission is its own run ("v1", "v2", ...), so a
new run never inherits the old results.
"""
import logging
import threading
from collections.abc import Iterable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime

from langgraph.types import Command
from sqlalchemy import and_, func, or_, select

from promoflow.auth.service import RoleGrant
from promoflow.db import session as db_session
from promoflow.db.enums import CaseStatus, FlagSeverity, Gate, GateOutcome, RoleName
from promoflow.db.models import (
    AuditLogEntry, CaseReport, CaseStatusHistory, Department, Flag, GateDecision, PromotionCase, User, UserRole,
)
from promoflow.workflow.graph import build_graph, postgres_checkpointer

log = logging.getLogger(__name__)

WAITING_FOR = {CaseStatus.HOD_REVIEW: "hod", CaseStatus.DEAN_REVIEW: "dean",
               CaseStatus.REFEREE_SELECTION: "chancellor"}
GATE_STATUS = {"hod": CaseStatus.HOD_REVIEW, "dean": CaseStatus.DEAN_REVIEW,
               "chancellor": CaseStatus.REFEREE_SELECTION}
FINAL_STATUS = {"not_eligible": CaseStatus.NOT_ELIGIBLE, "returned_by_hod": CaseStatus.RETURNED_FOR_REVISION,
                "returned_by_dean": CaseStatus.RETURNED_FOR_REVISION,
                "referees_selected": CaseStatus.AWAITING_REFEREE_REPORTS}

_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="review")
_lock = threading.Lock()
_graph = None
_busy: set[int] = set()          # cases with a run in progress in this process
_errors: dict[int, str] = {}


class ReviewError(Exception):
    """A request that cannot be done now; the message is safe to show to the user."""


@dataclass(frozen=True)
class ReviewStatus:
    case_status: CaseStatus
    waiting_for: str | None       # "hod" | "dean" | "chancellor" | None
    running: bool                 # agents are working right now
    error: str | None
    report: dict | None           # the Report Builder's latest report


def configure(checkpointer=None) -> None:
    """Choose where paused runs are saved. The app uses Postgres (the default); tests pass an in-memory saver."""
    global _graph
    _graph = build_graph(checkpointer or postgres_checkpointer())


def _get_graph():
    with _lock:
        if _graph is None:
            configure()
        return _graph


def _submissions(s, case_id: int) -> int:
    return max(s.scalar(select(func.count()).select_from(CaseStatusHistory).where(
        CaseStatusHistory.case_id == case_id, CaseStatusHistory.to_status == CaseStatus.SUBMITTED)) or 0, 1)


def _config(case_id: int, version: int) -> dict:
    return {"configurable": {"thread_id": f"case-{case_id}-v{version}"}}


def _set_status(s, case: PromotionCase, new: CaseStatus, note: str, user_id: int | None = None) -> None:
    if case.status == new:
        return
    s.add(CaseStatusHistory(case_id=case.id, from_status=case.status, to_status=new, changed_by=user_id, note=note))
    s.add(AuditLogEntry(user_id=user_id, case_id=case.id, action="status_changed", entity_table="promotion_case",
                        entity_id=case.id, before={"status": case.status.value}, after={"status": new.value}))
    case.status = new


def _sync(case_id: int, version: int) -> None:
    """After the graph stops: save the report and move the case to the status that matches where it stopped."""
    snapshot = _get_graph().get_state(_config(case_id, version))
    values = snapshot.values
    gate = next((t.interrupts[0].value["gate"] for t in snapshot.tasks if t.interrupts), None)
    with db_session.session_scope() as s:
        case = s.get(PromotionCase, case_id)
        report = values.get("report")
        if report and not s.scalar(select(CaseReport.id).where(CaseReport.case_id == case_id,
                                                                CaseReport.version == version)):
            s.add(CaseReport(case_id=case_id, version=version, overall_pass=report.get("overall_pass"),
                             content=report))
        if gate:
            _set_status(s, case, GATE_STATUS[gate], f"Waiting for {gate}")
        elif values.get("final_status") in FINAL_STATUS:
            final = values["final_status"]
            new = FINAL_STATUS[final]
            verdict = values.get("results", {}).get("eligibility", {}).get("verdict")
            if final == "not_eligible" and verdict == "incomplete":
                new = CaseStatus.RETURNED_FOR_REVISION      # something is missing: the applicant can fix it
            _set_status(s, case, new, f"Review ended: {final}")


def _job(case_id: int, version: int, payload) -> None:
    try:
        _get_graph().invoke(payload, _config(case_id, version))
        _sync(case_id, version)
        _errors.pop(case_id, None)
    except Exception as e:                                     # shown to the user; the case stays where it was
        log.exception("Review of case %s failed", case_id)
        _errors[case_id] = f"{type(e).__name__}: {e}"
        try:
            with db_session.session_scope() as s:
                s.add(Flag(case_id=case_id, severity=FlagSeverity.NEEDS_HUMAN, code="workflow_error",
                           message=f"The review stopped with an error: {_errors[case_id]}"))
        except Exception:
            log.exception("Could not record the workflow error for case %s", case_id)
    finally:
        _busy.discard(case_id)


def _launch(case_id: int, version: int, payload, wait: bool) -> Future:
    with _lock:
        if case_id in _busy:
            raise ReviewError("This case is already being processed. Please wait a moment.")
        _busy.add(case_id)
    future = _pool.submit(_job, case_id, version, payload)
    if wait:
        future.result()
    return future


def start_review(case_id: int, *, options: dict | None = None, wait: bool = False) -> Future:
    """Start the agents on a submitted case. Returns at once unless `wait` (tests). `options` is for stub switches."""
    with db_session.session_scope() as s:
        case = s.get(PromotionCase, case_id)
        if case is None:
            raise ReviewError("Case not found.")
        if case.status != CaseStatus.SUBMITTED:
            raise ReviewError(f"Only a submitted case can be reviewed (this one is {case.status.value}).")
        version = _submissions(s, case_id)
        _set_status(s, case, CaseStatus.UNDER_EVALUATION, "Review started")
    _errors.pop(case_id, None)
    return _launch(case_id, version, {"case_id": case_id, "options": options or {}}, wait)


def _has_role(s, user_id: int, role: RoleName, case: PromotionCase) -> bool:
    """HoD decides only for their own department, the Dean for their own college, the Chancellor for all."""
    applicant = s.get(User, case.applicant_id)
    query = select(UserRole.id).where(UserRole.user_id == user_id, UserRole.role == role)
    if role == RoleName.HOD:
        query = query.where(UserRole.department_id == applicant.department_id)
    elif role == RoleName.DEAN:
        query = query.where(UserRole.college_id == applicant.college_id)
    return s.scalar(query) is not None


def resume(case_id: int, user_id: int, gate: Gate, outcome: GateOutcome, comment: str | None = None,
           sections: list[str] | None = None, *, wait: bool = False) -> Future:
    """The HoD's or Dean's decision. `gate` is the gate the user's page is for, so a stale page cannot decide
    for the next gate. Returning a case for revision needs the section codes and a comment."""
    outcome = GateOutcome(outcome)
    gate = Gate(gate)
    comment = (comment or "").strip() or None
    if outcome == GateOutcome.RETURN_FOR_REVISION and (not sections or not comment):
        raise ReviewError("Name the sections to revise and write a comment before returning a case.")
    with db_session.session_scope() as s:
        case = s.get(PromotionCase, case_id)
        if case is None:
            raise ReviewError("Case not found.")
        if WAITING_FOR.get(case.status) != gate.value:
            raise ReviewError("This case is not waiting for your decision.")
        if not _has_role(s, user_id, RoleName(gate.value), case):
            raise ReviewError("You are not allowed to decide on this case.")
        version = _submissions(s, case_id)
        revise = list(sections) if outcome == GateOutcome.RETURN_FOR_REVISION else None
        s.add(GateDecision(case_id=case_id, gate=gate, decided_by=user_id, outcome=outcome, comment=comment,
                           sections_to_revise=revise))
        s.add(AuditLogEntry(user_id=user_id, case_id=case_id, action=f"{gate.value}_decision",
                            entity_table="promotion_case", entity_id=case_id, before=None,
                            after={"outcome": outcome.value, "sections": revise}))
    payload = Command(resume={"outcome": outcome.value, "comment": comment, "sections": sections or []})
    return _launch(case_id, version, payload, wait)


def select_referees(case_id: int, user_id: int, candidate_ids: list[int], *, wait: bool = False) -> Future:
    """The Chancellor's selection from the shortlist. A selection, not an approval."""
    if not candidate_ids:
        raise ReviewError("Select at least one referee.")
    with db_session.session_scope() as s:
        case = s.get(PromotionCase, case_id)
        if case is None:
            raise ReviewError("Case not found.")
        if case.status != CaseStatus.REFEREE_SELECTION:
            raise ReviewError("This case is not waiting for referee selection.")
        if not _has_role(s, user_id, RoleName.CHANCELLOR, case):
            raise ReviewError("Only the Chancellor can select referees.")
        version = _submissions(s, case_id)
        s.add(AuditLogEntry(user_id=user_id, case_id=case_id, action="referees_selected",
                            entity_table="promotion_case", entity_id=case_id, before=None,
                            after={"candidate_ids": list(candidate_ids)}))
    return _launch(case_id, version, Command(resume={"selected": list(candidate_ids)}), wait)


def get_status(case_id: int) -> ReviewStatus:
    """Database only (no agent or checkpoint call), so it is cheap enough to call on every page load."""
    with db_session.session_scope() as s:
        case = s.get(PromotionCase, case_id)
        if case is None:
            raise ReviewError("Case not found.")
        report = s.scalar(select(CaseReport).where(CaseReport.case_id == case_id)
                          .order_by(CaseReport.version.desc()))
        status, content = case.status, (report.content if report else None)
    return ReviewStatus(status, WAITING_FOR.get(status), case_id in _busy, _errors.get(case_id), content)


# ---- what the review pages show ---------------------------------------------------------------------------------
# A reviewer only ever gets cases that are waiting at their own gate and inside their own department (HoD) or college
# (Dean). Plain queries, no agent involved.

class NotAllowed(Exception):
    pass


@dataclass(frozen=True)
class WaitingCase:
    case_id: int
    applicant_name: str
    department: str
    track: str
    submitted_at: datetime | None
    gate: str                      # "hod" | "dean"


@dataclass(frozen=True)
class DecisionRow:
    gate: Gate
    outcome: GateOutcome
    comment: str | None
    sections: list[str]
    decided_by: str
    decided_at: datetime


@dataclass(frozen=True)
class CaseDetail:
    case_id: int
    applicant_name: str
    department: str
    track: str
    specialization: str | None
    submitted_at: datetime | None
    gate: str
    report: dict | None
    decisions: list[DecisionRow]


def _waiting_query(grants: Iterable[RoleGrant]):
    scopes = []
    for g in grants:
        if g.role == RoleName.HOD and g.department_id is not None:
            scopes.append(and_(PromotionCase.status == CaseStatus.HOD_REVIEW, User.department_id == g.department_id))
        elif g.role == RoleName.DEAN and g.college_id is not None:
            scopes.append(and_(PromotionCase.status == CaseStatus.DEAN_REVIEW, User.college_id == g.college_id))
    if not scopes:
        return None
    return (select(PromotionCase, User, Department.name_en)
            .join(User, User.id == PromotionCase.applicant_id)
            .outerjoin(Department, Department.id == User.department_id)
            .where(or_(*scopes)).order_by(PromotionCase.submitted_at))


def _gate_of(case: PromotionCase) -> str:
    return "hod" if case.status == CaseStatus.HOD_REVIEW else "dean"


def waiting_cases(s, grants: Iterable[RoleGrant]) -> list[WaitingCase]:
    query = _waiting_query(grants)
    if query is None:
        return []
    return [WaitingCase(case.id, user.full_name or user.email, dept or "–", case.track.value, case.submitted_at,
                        _gate_of(case)) for case, user, dept in s.execute(query)]


def case_detail(s, case_id: int, grants: Iterable[RoleGrant]) -> CaseDetail:
    """One waiting case in full. Raises NotAllowed unless it is waiting at one of the reviewer's own gates."""
    query = _waiting_query(grants)
    row = s.execute(query.where(PromotionCase.id == case_id)).first() if query is not None else None
    if row is None:
        raise NotAllowed("This case is not waiting for your decision.")
    case, user, dept = row
    report = s.scalar(select(CaseReport).where(CaseReport.case_id == case_id).order_by(CaseReport.version.desc()))
    decisions = [DecisionRow(d.gate, d.outcome, d.comment, list(d.sections_to_revise or []),
                             decider.full_name or decider.email, d.decided_at)
                 for d, decider in s.execute(select(GateDecision, User).join(User, User.id == GateDecision.decided_by)
                                             .where(GateDecision.case_id == case_id).order_by(GateDecision.id))]
    return CaseDetail(case.id, user.full_name or user.email, dept or "–", case.track.value, case.specialization,
                      case.submitted_at, _gate_of(case), report.content if report else None, decisions)
