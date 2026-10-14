"""Shared helpers for every §5 research entry type: case access, and the "after current rank" rule that
applies to papers, creative works and books alike (spec §5A/§5A-2/§5B)."""
from datetime import date

from sqlalchemy.orm import Session

from promoflow.db.models import PromotionCase
from promoflow.dossier.section0 import EDITABLE, CaseLocked, active_case


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


# The policy says a counted item must date from AFTER the applicant's current rank was obtained. Returns True /
# False, or None when a date is missing.
def after_current_rank(item_date: date | None, current_rank_date: date | None) -> bool | None:
    """None means "can't tell yet" (one of the dates is missing) rather than a hard mismatch."""
    if item_date is None or current_rank_date is None:
        return None
    return item_date >= current_rank_date
