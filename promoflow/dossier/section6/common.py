"""Shared helpers for every §6 teaching entry type: case access and the §6A course dropdown that §6B, 6C,
6F and 6G all link to."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.db.models import CourseTaught, PromotionCase
from promoflow.dossier.section0 import EDITABLE, CaseLocked, active_case

__all__ = ["CaseLocked", "case_for_new_entry", "case_for_entity", "course_options", "course_options_from"]


# The case to add a new entry to: it must exist (Section 0 creates it) and must be editable.
def case_for_new_entry(s: Session, user_id: int) -> PromotionCase:
    case = active_case(s, user_id)
    if case is None:
        raise CaseLocked("Save Section 0 first to start your application.")
    if case.status not in EDITABLE:
        raise CaseLocked("This application has been submitted and can no longer be edited.")
    return case


# The case that owns an existing entry, refusing if it is locked.
def case_for_entity(s: Session, case_id: int) -> PromotionCase:
    case = s.get(PromotionCase, case_id)
    if case.status not in EDITABLE:
        raise CaseLocked("This application has been submitted and can no longer be edited.")
    return case


# Turn a list of courses into dropdown choices ({course id: label}). Sections 6B, 6C, 6F and 6G let the applicant
# pick the course an entry is about.
def course_options_from(courses: list[CourseTaught]) -> dict[int, str]:
    """§6A rows as labels, for the "Course" link field in 6B, 6C, 6F and 6G."""
    return {c.id: f"{c.course_code} · {c.course_title} ({c.academic_year} {c.semester.value.capitalize()})"
           for c in courses}


# The same, but reading the courses from the database first.
def course_options(s: Session, case_id: int) -> dict[int, str]:
    courses = s.scalars(select(CourseTaught).where(CourseTaught.case_id == case_id)
                        .order_by(CourseTaught.academic_year.desc())).all()
    return course_options_from(list(courses))
