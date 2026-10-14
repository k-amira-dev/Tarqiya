"""Section 4 – Academic Ranks & Experience (spec chapter 8): rank history (4A) and non-academic positions (4B).

Rank history is structured rather than a single PDF upload because time-in-rank is the first eligibility rule
and can't be computed from a scanned certificate.
"""
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.db.enums import CaseStatus, DocumentKind, Rank
from promoflow.db.models import CaseDocument, NonAcademicPosition, PromotionCase, RankHistory
from promoflow.dossier import audit, documents
from promoflow.dossier.section0 import EDITABLE, CaseLocked, active_case
from promoflow.rules.eligibility import years_between

# The columns the forms edit, one list for rank history (4A) and one for non-academic positions (4B).
RANK_FIELDS = ["rank", "date_obtained", "university", "country_code", "held_from", "held_to", "at_this_university"]
POSITION_FIELDS = ["position", "employer", "country_code", "date_from", "date_to"]
# Names for the evidence file of each kind of entry.
EXPERIENCE_SLOT = "experience"
EVIDENCE_SLOT = "evidence"


# A rank together with its evidence file.
@dataclass(frozen=True)
class RankRow:
    rank: RankHistory
    evidence: CaseDocument | None


# A non-academic position together with its evidence file.
@dataclass(frozen=True)
class PositionRow:
    position: NonAcademicPosition
    evidence: CaseDocument | None


# Everything the Section 4 page needs.
@dataclass(frozen=True)
class Section4Context:
    case_id: int | None
    status: CaseStatus | None
    current_rank: Rank | None
    ranks: list[RankRow]
    positions: list[PositionRow]


# Read the rank history and the other positions, oldest first. The Eligibility Checker uses the rank history to
# confirm time in rank.
def load(s: Session, user_id: int, today: date) -> Section4Context:
    case = active_case(s, user_id)
    if case is None:
        return Section4Context(None, None, None, [], [])
    ranks = s.scalars(select(RankHistory).where(RankHistory.case_id == case.id)
                      .order_by(RankHistory.held_from)).all()
    positions = s.scalars(select(NonAcademicPosition).where(NonAcademicPosition.case_id == case.id)
                          .order_by(NonAcademicPosition.date_from)).all()
    rank_rows = [RankRow(r, documents.current(s, case.id, "4", DocumentKind.EVIDENCE,
                                              entity_table="rank_history", entity_id=r.id, slot=EXPERIENCE_SLOT))
                for r in ranks]
    position_rows = [PositionRow(p, documents.current(s, case.id, "4", DocumentKind.EVIDENCE,
                                                       entity_table="non_academic_position", entity_id=p.id,
                                                       slot=EVIDENCE_SLOT))
                     for p in positions]
    return Section4Context(case.id, case.status, case.current_rank, rank_rows, position_rows)


# How long a rank was held, in years (an unfinished rank counts up to today).
def rank_years(r: RankHistory, today: date) -> float:
    return years_between(r.held_from, r.held_to or today)


# Section-level problems for the page's warning banner.
def section_checks(ranks: list[RankRow], current_rank: Rank | None) -> list[str]:
    return rank_entry_checks([row.rank for row in ranks], current_rank)


# Problems in the WHOLE rank history, such as two current ranks, overlapping periods, or a current rank that
# disagrees with Section 0. They are shown as a banner and are also used by the Eligibility Checker.
def rank_entry_checks(entries: list[RankHistory], current_rank: Rank | None) -> list[str]:
    """Section-level problems shown as a banner, not blocking a single entry's save (spec §8 validation note)."""
    problems = []
    # Sort by start date, then compare each rank with the next one to find overlaps.
    ordered = sorted(entries, key=lambda r: r.held_from)
    current_entries = [r for r in ordered if r.held_to is None]
    if len(current_entries) > 1:
        problems.append("Only one rank entry can be marked as current (no end date).")
    for prev, nxt in zip(ordered, ordered[1:]):
        prev_end = prev.held_to or date.max
        if nxt.held_from < prev_end:
            problems.append(f"{prev.held_from:%b %Y}–{'now' if not prev.held_to else f'{prev.held_to:%b %Y}'} "
                            f"overlaps with {nxt.held_from:%b %Y}.")
    if current_entries and current_rank is not None and current_entries[0].rank != current_rank:
        problems.append("Your current rank entry does not match the current rank from Section 0.")
    return problems


# Check one rank entry's form. Returns a list of messages.
def validate_rank(values: dict, today: date) -> list[str]:
    errors = []
    required = {"rank": "Academic rank", "date_obtained": "Date rank obtained", "university": "University granting the rank",
               "country_code": "Location / country", "held_from": "Held from"}
    for key, label in required.items():
        if values.get(key) in (None, ""):
            errors.append(f"{label} is required.")
    if values.get("date_obtained") and values["date_obtained"] > today:
        errors.append("Date rank obtained cannot be in the future.")
    held_from, held_to = values.get("held_from"), values.get("held_to")
    if held_from and held_to and held_to <= held_from:
        errors.append("\"Held to\" must be after \"Held from\".")
    return errors


# Check one non-academic position's form. Returns a list of messages.
def validate_position(values: dict) -> list[str]:
    errors = []
    required = {"position": "Position", "employer": "Employer", "country_code": "Country", "date_from": "From date"}
    for key, label in required.items():
        if values.get(key) in (None, ""):
            errors.append(f"{label} is required.")
    date_from, date_to = values.get("date_from"), values.get("date_to")
    if date_from and date_to and date_to <= date_from:
        errors.append("\"To\" must be after \"From\".")
    return errors


# The case that owns an entry, refusing if it is locked.
def _case_for(s: Session, case_id: int) -> PromotionCase:
    case = s.get(PromotionCase, case_id)
    if case.status not in EDITABLE:
        raise CaseLocked("This application has been submitted and can no longer be edited.")
    return case


# Add a rank history entry (same steps as every 'add': check, create, attach evidence, audit).
def add_rank(s: Session, user_id: int, values: dict, evidence: tuple[str, bytes] | None) -> int:
    case = active_case(s, user_id)
    if case is None:
        raise CaseLocked("Save Section 0 first to start your application.")
    if case.status not in EDITABLE:
        raise CaseLocked("This application has been submitted and can no longer be edited.")
    rank = RankHistory(case_id=case.id, **{f: values.get(f) for f in RANK_FIELDS})
    s.add(rank)
    s.flush()
    if evidence is not None:
        filename, data = evidence
        documents.replace(s, case.id, user_id, "4", DocumentKind.EVIDENCE, filename, data,
                          entity_table="rank_history", entity_id=rank.id, slot=EXPERIENCE_SLOT)
    audit.log(s, user_id=user_id, case_id=case.id, action="section4_rank_added", entity_table="rank_history",
             entity_id=rank.id, before=None, after=audit.snapshot(rank, RANK_FIELDS))
    return rank.id


# Edit a rank history entry.
def update_rank(s: Session, user_id: int, rank_id: int, values: dict,
               evidence: tuple[str, bytes] | None = None) -> None:
    rank = s.get(RankHistory, rank_id)
    case = _case_for(s, rank.case_id)
    before = audit.snapshot(rank, RANK_FIELDS)
    for f in RANK_FIELDS:
        setattr(rank, f, values.get(f))
    if evidence is not None:
        filename, data = evidence
        documents.replace(s, case.id, user_id, "4", DocumentKind.EVIDENCE, filename, data,
                          entity_table="rank_history", entity_id=rank.id, slot=EXPERIENCE_SLOT)
    s.flush()
    audit.log(s, user_id=user_id, case_id=case.id, action="section4_rank_updated", entity_table="rank_history",
             entity_id=rank.id, before=before, after=audit.snapshot(rank, RANK_FIELDS))


# Delete a rank history entry.
def delete_rank(s: Session, user_id: int, rank_id: int) -> None:
    rank = s.get(RankHistory, rank_id)
    case = _case_for(s, rank.case_id)
    audit.log(s, user_id=user_id, case_id=case.id, action="section4_rank_deleted", entity_table="rank_history",
             entity_id=rank.id, before=audit.snapshot(rank, RANK_FIELDS), after=None)
    s.delete(rank)


# Add a non-academic position.
def add_position(s: Session, user_id: int, values: dict, evidence: tuple[str, bytes] | None) -> int:
    case = active_case(s, user_id)
    if case is None:
        raise CaseLocked("Save Section 0 first to start your application.")
    if case.status not in EDITABLE:
        raise CaseLocked("This application has been submitted and can no longer be edited.")
    position = NonAcademicPosition(case_id=case.id, **{f: values.get(f) for f in POSITION_FIELDS})
    s.add(position)
    s.flush()
    if evidence is not None:
        filename, data = evidence
        documents.replace(s, case.id, user_id, "4", DocumentKind.EVIDENCE, filename, data,
                          entity_table="non_academic_position", entity_id=position.id, slot=EVIDENCE_SLOT)
    audit.log(s, user_id=user_id, case_id=case.id, action="section4_position_added",
             entity_table="non_academic_position", entity_id=position.id, before=None,
             after=audit.snapshot(position, POSITION_FIELDS))
    return position.id


# Edit a non-academic position.
def update_position(s: Session, user_id: int, position_id: int, values: dict,
                    evidence: tuple[str, bytes] | None = None) -> None:
    position = s.get(NonAcademicPosition, position_id)
    case = _case_for(s, position.case_id)
    before = audit.snapshot(position, POSITION_FIELDS)
    for f in POSITION_FIELDS:
        setattr(position, f, values.get(f))
    if evidence is not None:
        filename, data = evidence
        documents.replace(s, case.id, user_id, "4", DocumentKind.EVIDENCE, filename, data,
                          entity_table="non_academic_position", entity_id=position.id, slot=EVIDENCE_SLOT)
    s.flush()
    audit.log(s, user_id=user_id, case_id=case.id, action="section4_position_updated",
             entity_table="non_academic_position", entity_id=position.id, before=before,
             after=audit.snapshot(position, POSITION_FIELDS))


# Delete a non-academic position.
def delete_position(s: Session, user_id: int, position_id: int) -> None:
    position = s.get(NonAcademicPosition, position_id)
    case = _case_for(s, position.case_id)
    audit.log(s, user_id=user_id, case_id=case.id, action="section4_position_deleted",
             entity_table="non_academic_position", entity_id=position.id,
             before=audit.snapshot(position, POSITION_FIELDS), after=None)
    s.delete(position)
