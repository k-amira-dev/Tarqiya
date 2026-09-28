"""Shared helpers for every §6 teaching entry type: case access and the §6A course dropdown that §6B, 6C,
6F and 6G all link to."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.db.models import CourseTaught, PromotionCase
from promoflow.dossier.section0 import EDITABLE, CaseLocked, active_case

__all__ = ["CaseLocked", "case_for_new_entry", "case_for_entity", "course_options"]


def case_for_new_entry(s: Session, user_id: int) -> PromotionCase:
    case = active_case(s, user_id)
    if case is None:
        raise CaseLocked("Save Section 0 first to start your application.")
    if case.status not in EDITABLE:
        raise CaseLocked("This application has been submitted and can no longer be edited.")
    return case


def case_for_entity(s: Session, case_id: int) -> PromotionCase:
    case = s.get(PromotionCase, case_id)
    if case.status not in EDITABLE:
        raise CaseLocked("This application has been submitted and can no longer be edited.")
    return case


def course_options(s: Session, case_id: int) -> dict[int, str]:
    """§6A rows, for the "Course" link field in 6B, 6C, 6F and 6G."""
    courses = s.scalars(select(CourseTaught).where(CourseTaught.case_id == case_id)
                        .order_by(CourseTaught.academic_year.desc())).all()
    return {c.id: f"{c.course_code} · {c.course_title} ({c.academic_year} {c.semester.value.capitalize()})"
           for c in courses}
