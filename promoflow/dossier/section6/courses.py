"""6A – Course taught (spec §10): one row per course per semester, plus a single registrar teaching-load
report that covers the whole list (not one file per row)."""
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.db.enums import CourseLevel, DeliveryMode, DocumentKind, Semester, TeachingRole
from promoflow.db.models import CaseDocument, CourseTaught
from promoflow.dossier import audit, documents
from promoflow.dossier.section6.common import CaseLocked, case_for_entity, case_for_new_entry

FIELDS = ["academic_year", "semester", "course_code", "course_title", "level", "sections", "students", "role",
         "delivery_mode"]
REPORT_SLOT = "registrar_report"


@dataclass(frozen=True)
class DiversitySummary:
    distinct_courses: int
    total_rows: int
    most_repeated_share: float  # 0..1


def load(s: Session, case_id: int) -> list[CourseTaught]:
    return s.scalars(select(CourseTaught).where(CourseTaught.case_id == case_id)
                     .order_by(CourseTaught.academic_year.desc(), CourseTaught.semester)).all()


def registrar_report(s: Session, case_id: int) -> CaseDocument | None:
    return documents.current(s, case_id, "6A", DocumentKind.EVIDENCE, slot=REPORT_SLOT)


def diversity(courses: list[CourseTaught]) -> DiversitySummary:
    if not courses:
        return DiversitySummary(0, 0, 0.0)
    codes = [c.course_code for c in courses]
    distinct = len(set(codes))
    most_common = max(codes.count(c) for c in set(codes))
    return DiversitySummary(distinct, len(codes), most_common / len(codes))


def validate(values: dict) -> list[str]:
    errors = []
    required = {"academic_year": "Academic year", "semester": "Semester", "course_code": "Course code",
               "course_title": "Course title", "level": "Level", "role": "Role", "delivery_mode": "Delivery mode"}
    for key, label in required.items():
        if values.get(key) in (None, ""):
            errors.append(f"{label} is required.")
    if not values.get("sections") or values["sections"] < 1:
        errors.append("Number of sections must be at least 1.")
    if values.get("students") is None or values["students"] < 0:
        errors.append("Number of students is required.")
    return errors


def add(s: Session, user_id: int, values: dict) -> int:
    case = case_for_new_entry(s, user_id)
    c = CourseTaught(case_id=case.id, **{f: values.get(f) for f in FIELDS})
    s.add(c)
    s.flush()
    audit.log(s, user_id=user_id, case_id=case.id, action="section6_course_added", entity_table="course_taught",
             entity_id=c.id, before=None, after=audit.snapshot(c, FIELDS))
    return c.id


def update(s: Session, user_id: int, course_id: int, values: dict) -> None:
    c = s.get(CourseTaught, course_id)
    case = case_for_entity(s, c.case_id)
    before = audit.snapshot(c, FIELDS)
    for f in FIELDS:
        setattr(c, f, values.get(f))
    s.flush()
    audit.log(s, user_id=user_id, case_id=case.id, action="section6_course_updated", entity_table="course_taught",
             entity_id=c.id, before=before, after=audit.snapshot(c, FIELDS))


def delete(s: Session, user_id: int, course_id: int) -> None:
    c = s.get(CourseTaught, course_id)
    case = case_for_entity(s, c.case_id)
    audit.log(s, user_id=user_id, case_id=case.id, action="section6_course_deleted", entity_table="course_taught",
             entity_id=c.id, before=audit.snapshot(c, FIELDS), after=None)
    s.delete(c)


def save_registrar_report(s: Session, case_id: int, user_id: int, upload: tuple[str, bytes]) -> None:
    filename, data = upload
    documents.replace(s, case_id, user_id, "6A", DocumentKind.EVIDENCE, filename, data, slot=REPORT_SLOT)
