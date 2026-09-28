"""6C – Student satisfaction report (spec §10, Appendix E item 1): one per course-semester."""
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.db.enums import DocumentKind
from promoflow.db.models import CaseDocument, CourseTaught, StudentSatisfaction
from promoflow.dossier import audit, documents
from promoflow.dossier.section6.common import CaseLocked, case_for_entity, case_for_new_entry

FIELDS = ["course_taught_id", "respondents", "average_score", "scale_max"]
EVIDENCE_SLOT = "evidence"


@dataclass(frozen=True)
class SatisfactionRow:
    report: StudentSatisfaction
    evidence: CaseDocument | None


def load(s: Session, case_id: int) -> list[SatisfactionRow]:
    rows = s.scalars(select(StudentSatisfaction).where(StudentSatisfaction.case_id == case_id)).all()
    return [SatisfactionRow(r, documents.current(s, case_id, "6C", DocumentKind.EVIDENCE,
                                                 entity_table="student_satisfaction", entity_id=r.id,
                                                 slot=EVIDENCE_SLOT))
           for r in rows]


def coverage(reports: list[SatisfactionRow], courses: list[CourseTaught]) -> float:
    if not courses:
        return 0.0
    covered = {r.report.course_taught_id for r in reports}
    return len(covered) / len(courses)


def validate(s: Session, values: dict, has_evidence: bool, evidence_upload=None) -> list[str]:
    errors = []
    required = {"course_taught_id": "Course", "respondents": "Number of respondents",
               "average_score": "Average score", "scale_max": "Scale maximum"}
    for key, label in required.items():
        if values.get(key) in (None, ""):
            errors.append(f"{label} is required.")
    average_score, scale_max = values.get("average_score"), values.get("scale_max")
    if average_score is not None and scale_max is not None and not (0 <= average_score <= scale_max):
        errors.append("Average score must be between 0 and the scale maximum.")
    course_id, respondents = values.get("course_taught_id"), values.get("respondents")
    if course_id and respondents is not None:
        course = s.get(CourseTaught, course_id)
        if course and respondents > course.students:
            errors.append(f"Number of respondents cannot exceed the {course.students} students in that course.")
    if evidence_upload is None and not has_evidence:
        errors.append("Upload the satisfaction report.")
    return errors


def add(s: Session, user_id: int, values: dict, evidence_upload: tuple[str, bytes]) -> int:
    case = case_for_new_entry(s, user_id)
    r = StudentSatisfaction(case_id=case.id, **{f: values.get(f) for f in FIELDS})
    s.add(r)
    s.flush()
    filename, data = evidence_upload
    documents.replace(s, case.id, user_id, "6C", DocumentKind.EVIDENCE, filename, data,
                      entity_table="student_satisfaction", entity_id=r.id, slot=EVIDENCE_SLOT)
    audit.log(s, user_id=user_id, case_id=case.id, action="section6_satisfaction_added",
             entity_table="student_satisfaction", entity_id=r.id, before=None, after=audit.snapshot(r, FIELDS))
    return r.id


def update(s: Session, user_id: int, report_id: int, values: dict, evidence_upload=None) -> None:
    r = s.get(StudentSatisfaction, report_id)
    case = case_for_entity(s, r.case_id)
    before = audit.snapshot(r, FIELDS)
    for f in FIELDS:
        setattr(r, f, values.get(f))
    if evidence_upload is not None:
        filename, data = evidence_upload
        documents.replace(s, case.id, user_id, "6C", DocumentKind.EVIDENCE, filename, data,
                          entity_table="student_satisfaction", entity_id=r.id, slot=EVIDENCE_SLOT)
    s.flush()
    audit.log(s, user_id=user_id, case_id=case.id, action="section6_satisfaction_updated",
             entity_table="student_satisfaction", entity_id=r.id, before=before, after=audit.snapshot(r, FIELDS))


def delete(s: Session, user_id: int, report_id: int) -> None:
    r = s.get(StudentSatisfaction, report_id)
    case = case_for_entity(s, r.case_id)
    audit.log(s, user_id=user_id, case_id=case.id, action="section6_satisfaction_deleted",
             entity_table="student_satisfaction", entity_id=r.id, before=audit.snapshot(r, FIELDS), after=None)
    s.delete(r)
