"""The outcome of the referee stage: once the minimum number of reports is in, the average of the referees' grades is compared with the
pass mark, and the applicant is told the result.

By default a person from the Chancellor's Office releases the result (a promotion decision is hard to take back). Setting
REFEREE_RESULT_AUTO_RELEASE=true releases it the moment the last needed report arrives. Releasing moves the case to
"referee_results_recorded" and writes one audit entry that holds the figures, so no new table is needed.
"""
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow import config
from promoflow.db import session as db_session
from promoflow.db.enums import CaseStatus, RoleName
from promoflow.db.models import (
    AuditLogEntry, PromotionCase, PromotionCriteria, RefereePaperGrade, RefereeReport, ReviewerAssignment,
)
from promoflow.rules import referees as rules

RELEASED = "referee_result_released"


class ResultError(Exception):
    """Shown to the person who tried to release the result."""


@dataclass
class ResultView:
    reports: int = 0
    minimum: int = 0
    average: float | None = None
    pass_mark: float = 0.0
    passed: bool | None = None            # None until the minimum number of reports is in
    released: bool = False


def _target_rank(case: PromotionCase) -> str:
    return "Associate Professor" if case.track.value == "to_associate" else "Professor"


def _outcome(s: Session, case: PromotionCase) -> tuple[rules.RefereeOutcome, int, float]:
    crit = s.scalar(select(PromotionCriteria).where(PromotionCriteria.policy_version_id == case.policy_version_id,
                                                    PromotionCriteria.track == case.track))
    if crit is None:
        raise ResultError("No promotion criteria are loaded for this case.")
    rows = s.execute(select(RefereeReport.id, RefereePaperGrade.grade_pct)
                     .join(ReviewerAssignment, ReviewerAssignment.id == RefereeReport.assignment_id)
                     .join(RefereePaperGrade, RefereePaperGrade.report_id == RefereeReport.id)
                     .where(ReviewerAssignment.case_id == case.id))
    by_report: dict[int, list[float]] = {}
    for rid, pct in rows:
        by_report.setdefault(rid, []).append(float(pct))
    minimum, pass_mark = crit.min_referee_reports, float(crit.min_referee_average_pct)
    return rules.referee_outcome(by_report, minimum, pass_mark), minimum, pass_mark


def released_entry(s: Session, case_id: int) -> AuditLogEntry | None:
    return s.scalar(select(AuditLogEntry).where(AuditLogEntry.case_id == case_id, AuditLogEntry.action == RELEASED)
                    .order_by(AuditLogEntry.id.desc()).limit(1))


def view(s: Session, case_id: int) -> ResultView:
    """The current figures for the Chancellor's page. Reads only."""
    case = s.get(PromotionCase, case_id)
    outcome, minimum, pass_mark = _outcome(s, case)
    return ResultView(reports=outcome.reports, minimum=minimum, average=outcome.overall_average, pass_mark=pass_mark,
                      passed=outcome.passed, released=released_entry(s, case_id) is not None)


def release(case_id: int, user_id: int | None) -> ResultView:
    """Tell the applicant. `user_id` is the Chancellor who released it, or None when the system did it (automatic release)."""
    from promoflow.workflow import review_service

    with db_session.session_scope() as s:
        case = s.get(PromotionCase, case_id)
        if case is None:
            raise ResultError("Case not found.")
        if user_id is not None and not review_service._has_role(s, user_id, RoleName.CHANCELLOR, case):
            raise ResultError("Only the Chancellor can release the result.")
        if released_entry(s, case_id) is not None or case.status == CaseStatus.REFEREE_RESULTS_RECORDED:
            raise ResultError("The result of this case has already been released.")
        if case.status != CaseStatus.AWAITING_REFEREE_REPORTS:
            raise ResultError("This case is not waiting for referee reports.")
        outcome, minimum, pass_mark = _outcome(s, case)
        if not outcome.enough_reports:
            raise ResultError(f"Only {outcome.reports} of the {minimum} referee reports needed have arrived.")
        s.add(AuditLogEntry(user_id=user_id, case_id=case_id, action=RELEASED, entity_table="promotion_case", entity_id=case_id,
                            after={"passed": bool(outcome.passed), "average": outcome.overall_average, "reports": outcome.reports,
                                   "pass_mark": pass_mark, "target_rank": _target_rank(case)},
                            detail="released by a person" if user_id else "released automatically"))
        review_service._set_status(s, case, CaseStatus.REFEREE_RESULTS_RECORDED,
                                   "Referee result released to the applicant", user_id)
        return ResultView(reports=outcome.reports, minimum=minimum, average=outcome.overall_average, pass_mark=pass_mark,
                          passed=outcome.passed, released=True)


def release_if_automatic(case_id: int) -> bool:
    """Called after every submitted report. Releases at once only when REFEREE_RESULT_AUTO_RELEASE is on and the minimum is met."""
    if not config.REFEREE_RESULT_AUTO_RELEASE:
        return False
    try:
        release(case_id, None)
    except ResultError:
        return False
    return True


# ---- what the applicant sees ----------------------------------------------------------------------------------------

@dataclass
class ApplicantResult:
    """Pass or fail only. No grade, average or pass mark ever reaches the applicant, so none is carried here."""
    passed: bool
    target_rank: str
    released_at: datetime | None


def for_applicant(s: Session, applicant_id: int) -> ApplicantResult | None:
    """The released result of the applicant's latest case, or None. A case with no released result shows nothing here."""
    case = s.scalar(select(PromotionCase).where(PromotionCase.applicant_id == applicant_id).order_by(PromotionCase.id.desc()).limit(1))
    if case is None:
        return None
    entry = released_entry(s, case.id)
    if entry is None or not entry.after:
        return None
    a = entry.after
    return ApplicantResult(passed=bool(a.get("passed")), target_rank=a.get("target_rank") or _target_rank(case),
                           released_at=entry.occurred_at)


def message(r: ApplicantResult) -> tuple[str, str]:
    """(title, text) for the applicant's page."""
    if r.passed:
        return ("Congratulations, you have been promoted",
                f"Your application for promotion to {r.target_rank} was successful.")
    return ("Your promotion application was not successful",
            f"Your application for promotion to {r.target_rank} was not approved.")
