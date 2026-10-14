"""Section 0 – Applicant details & promotion track: load and save (UI-independent)."""
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.db.enums import CaseStatus, PromotionTrack
from promoflow.db.session import parallel
from promoflow.db.models import (
    AuditLogEntry, CaseStatusHistory, College, Department, PolicyVersion, PromotionCase, PromotionCriteria, User,
)
from promoflow.rules.eligibility import CURRENT_RANK_FOR, Criteria

# Cases the applicant can still edit; any other active status means the dossier is locked.
EDITABLE = {CaseStatus.DRAFT, CaseStatus.RETURNED_FOR_REVISION}
FINISHED = {CaseStatus.WITHDRAWN, CaseStatus.NOT_ELIGIBLE, CaseStatus.REFEREE_RESULTS_RECORDED}

FIELDS = [
    "academic_year", "track", "specialization", "fine_specialization", "research_keywords",
    "appointment_date", "rank_on_appointment", "current_rank_date", "scopus_author_id", "orcid",
    "phd_outside_uae", "early_application", "exceptional_case", "exceptional_justification",
    "previously_rejected", "rejection_date",
]


class CaseLocked(Exception):
    pass


@dataclass(frozen=True)
class Identity:
    full_name: str
    employee_id: str
    email: str
    college: str
    department: str


@dataclass(frozen=True)
class Section0Context:
    identity: Identity
    case_id: int | None
    status: CaseStatus | None
    values: dict
    policy_title: str
    criteria: dict  # PromotionTrack -> Criteria


def _json(v):
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v.value if hasattr(v, "value") else v


def current_policy(s: Session, today: date) -> PolicyVersion:
    policy = s.scalar(select(PolicyVersion).where(PolicyVersion.effective_from <= today)
                      .order_by(PolicyVersion.effective_from.desc()))
    if policy is None:
        raise RuntimeError("No policy version is loaded. Run: python -m promoflow.db.seed")
    return policy


def active_case(s: Session, user_id: int) -> PromotionCase | None:
    return s.scalar(select(PromotionCase).where(PromotionCase.applicant_id == user_id,
                                                PromotionCase.status.not_in(FINISHED))
                    .order_by(PromotionCase.created_at.desc()))


def load(s: Session, user_id: int, today: date) -> Section0Context:
    def identity(sess: Session) -> Identity:
        user = sess.get(User, user_id)
        college = sess.get(College, user.college_id) if user.college_id else None
        dept = sess.get(Department, user.department_id) if user.department_id else None
        return Identity(user.full_name or "", user.employee_id or "", user.email,
                        college.name_en if college else "Not set by Admin",
                        dept.name_en if dept else "Not set by Admin")

    def policy_and_criteria(sess: Session):
        policy = current_policy(sess, today)
        criteria = {
            c.track: Criteria(c.min_years_in_rank, c.min_years_at_institution, c.early_application_months,
                              c.exceptional_min_years, c.reapply_min_years, c.reapply_new_publications,
                              c.reapply_new_class_a, c.reapply_new_main_author)
            for c in sess.scalars(select(PromotionCriteria).where(PromotionCriteria.policy_version_id == policy.id))
        }
        return policy.title, criteria

    def case_snapshot(sess: Session):
        case = active_case(sess, user_id)
        if case is None:
            return None, None, {}
        values = {f: getattr(case, f) for f in FIELDS}
        values["research_keywords"] = list(case.research_keywords or [])
        return case.id, case.status, values

    ident, (policy_title, criteria), (case_id, status, values) = parallel(identity, policy_and_criteria, case_snapshot)
    return Section0Context(ident, case_id, status, values, policy_title, criteria)


def save(s: Session, user_id: int, values: dict, today: date) -> int:
    """Create the draft case on first save, otherwise update it. Returns the case id."""
    case = active_case(s, user_id)
    if case is not None and case.status not in EDITABLE:
        raise CaseLocked("This application has been submitted and can no longer be edited.")
    before = None
    if case is None:
        case = PromotionCase(applicant_id=user_id, policy_version_id=current_policy(s, today).id,
                             status=CaseStatus.DRAFT, track=values["track"], academic_year=values["academic_year"])
        s.add(case)
        s.flush()
        s.add(CaseStatusHistory(case_id=case.id, from_status=None, to_status=CaseStatus.DRAFT, changed_by=user_id,
                                note="Draft created from Section 0"))
    else:
        before = {f: _json(getattr(case, f)) for f in FIELDS}

    track = PromotionTrack(values["track"])
    for f in FIELDS:
        setattr(case, f, values.get(f))
    case.current_rank = CURRENT_RANK_FOR[track]  # always one rank below the target rank
    case.orcid = (values.get("orcid") or "").strip().upper() or None
    case.scopus_author_id = (values.get("scopus_author_id") or "").strip() or None
    if not case.exceptional_case:
        case.exceptional_justification = None
    if not case.previously_rejected:
        case.rejection_date = None
    case.updated_at = datetime.now(timezone.utc)
    s.flush()
    after = {f: _json(getattr(case, f)) for f in FIELDS}
    if before != after:
        s.add(AuditLogEntry(user_id=user_id, case_id=case.id, action="section0_saved",
                            entity_table="promotion_case", entity_id=case.id, before=before, after=after))
    return case.id
