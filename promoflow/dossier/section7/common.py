"""Shared helpers for every §7 service entry type: case access."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.db.models import FundedProject, PromotionCase
from promoflow.dossier.section0 import EDITABLE, CaseLocked, active_case

__all__ = ["CaseLocked", "case_for_new_entry", "case_for_entity", "funded_project_options"]


def funded_project_options(s: Session, case_id: int) -> dict[int, str]:
    """§5D entries, for §7B's "linked funded project" field (a project is entered once, not re-typed)."""
    projects = s.scalars(select(FundedProject).where(FundedProject.case_id == case_id)).all()
    return {p.id: p.title for p in projects}


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
