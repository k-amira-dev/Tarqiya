"""What the Chancellor's referee-selection page reads: the cases waiting for a selection, the shortlist of one case, and the invitation
emails that were queued after the selection. Reads the database only; the selection itself is `review_service.select_referees`.

A referee's name and contact details are confidential: they are shown here to the Chancellor and are never part of what the applicant sees.
"""
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.db.enums import CaseStatus, Rank
from promoflow.db.models import (
    Department, OutreachMessage, PromotionCase, Referee, RefereeCandidate, ReviewerAssignment, ScopusEvidence, User,
)

# The only rank a referee may hold (handbook 7.8C asks for full professors).
REQUIRED_RANK = Rank.PROFESSOR


def applicant_h_index(s: Session, case_id: int) -> int | None:
    """The h-index the applicant entered in Section 5F (the referee's is read from OpenAlex)."""
    return s.scalar(select(ScopusEvidence.h_index).where(ScopusEvidence.case_id == case_id))


def blocker(cand: RefereeCandidate, ref: Referee, applicant_h: int | None = None) -> str | None:
    """Why this candidate cannot be selected yet, or None when the Chancellor may pick them. The page shows the reason and
    `review_service.select_referees` refuses the same candidates, so the rule cannot be bypassed from the screen."""
    if cand.coi_coauthor or cand.coi_same_institution or cand.coi_used_within_5_years:
        return "Conflict of interest."
    if not cand.eligible:
        return "Not eligible."
    if applicant_h is not None and (ref.h_index is None or ref.h_index <= applicant_h):
        return "The referee's h-index must be higher than the applicant's."
    if not ref.rank_verified:
        return "A person must verify the rank and email first."
    if ref.rank != REQUIRED_RANK:
        return "Verified rank is not Professor."
    if not ref.email:
        return "No email on record."
    return None


# Cases the Chancellor can open: waiting for the selection, or already selected (read-only: the invitations and their status).
LISTED = (CaseStatus.REFEREE_SELECTION, CaseStatus.AWAITING_REFEREE_REPORTS)


@dataclass(frozen=True)
class ChancellorCase:
    case_id: int
    applicant_name: str
    department: str
    track: str
    submitted_at: datetime | None
    status: CaseStatus

    @property
    def waiting(self) -> bool:
        return self.status == CaseStatus.REFEREE_SELECTION


@dataclass(frozen=True)
class CandidateRow:
    candidate_id: int
    referee_id: int
    name: str
    university: str
    country: str
    h_index: int | None
    citations: int | None
    topics: list[str]
    match_score: float | None
    rationale: str | None
    conflicts: list[str]            # plain sentences, empty when there is no conflict of interest
    eligible: bool
    email: str | None
    rank: str | None                # a Rank value, or None when nobody has confirmed it yet
    applicant_h_index: int | None   # what the applicant entered, to compare with this referee's h_index
    rank_verified: bool             # a person checked the rank (and email) is correct and not out of date
    orcid: str | None
    blocked: str | None             # blocker(): why the Chancellor cannot pick this candidate yet
    selected: bool
    invited: bool                   # an invitation was queued for this candidate


@dataclass(frozen=True)
class MessageRow:
    referee_name: str
    kind: str
    subject: str
    body: str
    status: str


def cases(s: Session) -> list[ChancellorCase]:
    rows = s.execute(select(PromotionCase, User, Department.name_en).join(User, User.id == PromotionCase.applicant_id)
                     .outerjoin(Department, Department.id == User.department_id)
                     .where(PromotionCase.status.in_(LISTED)).order_by(PromotionCase.status.desc(), PromotionCase.submitted_at))
    return [ChancellorCase(c.id, u.full_name or u.email, dept or "", c.track.value, c.submitted_at, c.status) for c, u, dept in rows]


def _topics(raw) -> list[str]:
    out = []
    for t in raw or []:
        out.append(t if isinstance(t, str) else str(t.get("name") or t.get("display_name") or ""))
    return [t for t in out if t][:4]


def shortlist(s: Session, case_id: int) -> list[CandidateRow]:
    """The shortlist of one case, best match first."""
    invited = set(s.scalars(select(ReviewerAssignment.candidate_id).where(ReviewerAssignment.case_id == case_id)))
    applicant_h = applicant_h_index(s, case_id)
    rows = s.execute(select(RefereeCandidate, Referee).join(Referee, Referee.id == RefereeCandidate.referee_id)
                     .where(RefereeCandidate.case_id == case_id))
    out = []
    for c, r in rows:
        conflicts = [text for flag, text in ((c.coi_coauthor, "has co-authored with the applicant"),
                                             (c.coi_same_institution, "works at the applicant's institution"),
                                             (c.coi_used_within_5_years, "was used as a referee in the last 5 years")) if flag]
        out.append(CandidateRow(c.id, r.id, r.full_name, r.university, r.country_code, r.h_index, r.citation_count, _topics(r.topics),
                                float(c.match_score) if c.match_score is not None else None, c.match_rationale, conflicts, bool(c.eligible),
                                r.email, r.rank.value if r.rank else None, applicant_h, bool(r.rank_verified), r.orcid, blocker(c, r, applicant_h),
                                bool(c.selected_by_chancellor), c.id in invited))
    return sorted(out, key=lambda x: (-(x.match_score or 0), x.name))


def messages(s: Session, case_id: int) -> list[MessageRow]:
    rows = s.execute(select(OutreachMessage, Referee).join(ReviewerAssignment, ReviewerAssignment.id == OutreachMessage.assignment_id)
                     .join(Referee, Referee.id == ReviewerAssignment.referee_id)
                     .where(ReviewerAssignment.case_id == case_id).order_by(OutreachMessage.id))
    return [MessageRow(r.full_name, m.kind.value, m.subject, m.body, m.delivery_status.value) for m, r in rows]


# ---- what each contacted referee answered --------------------------------------------------------------------------

STATUS_LABEL = {"invited": "Invited, no answer yet", "reminded": "Reminded, no answer yet", "accepted": "Accepted, report not sent yet",
                "declined": "Declined", "replaced_no_response": "No response: replaced", "report_received": "Report received",
                "withdrawn": "Withdrawn"}


@dataclass(frozen=True)
class GradeRow:
    title: str
    grade: float


@dataclass(frozen=True)
class ResponseRow:
    assignment_id: int
    referee_name: str
    university: str
    status: str                      # a plain sentence
    invited_at: datetime | None
    responded_at: datetime | None
    last_reminder_at: datetime | None
    submitted_at: datetime | None    # None until the report arrives
    grades: list[GradeRow]
    average: float | None
    recommendation: str | None


def responses(s: Session, case_id: int) -> list[ResponseRow]:
    """One row per contacted referee: where the request stands and, once the report is in, each paper's grade, the average and the
    recommendation. For the Chancellor only: the applicant never sees any of it."""
    from promoflow.db.models import Publication, RefereePaperGrade, RefereeReport

    out = []
    rows = s.execute(select(ReviewerAssignment, Referee).join(Referee, Referee.id == ReviewerAssignment.referee_id)
                     .where(ReviewerAssignment.case_id == case_id).order_by(ReviewerAssignment.id))
    for a, ref in rows:
        report = s.scalar(select(RefereeReport).where(RefereeReport.assignment_id == a.id))
        grades = []
        if report is not None:
            grades = [GradeRow(title, float(g)) for title, g in s.execute(
                select(Publication.title, RefereePaperGrade.grade_pct).join(Publication, Publication.id == RefereePaperGrade.publication_id)
                .where(RefereePaperGrade.report_id == report.id).order_by(Publication.id))]
        out.append(ResponseRow(a.id, ref.full_name, ref.university, STATUS_LABEL.get(a.status.value, a.status.value), a.invited_at,
                               a.responded_at, a.last_reminder_at, report.submitted_at if report else None, grades,
                               round(sum(g.grade for g in grades) / len(grades), 2) if grades else None,
                               report.recommendation if report else None))
    return out
