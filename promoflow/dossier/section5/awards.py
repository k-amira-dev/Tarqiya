"""5H – Award entry (spec §9). Narrative only; not counted."""
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.db.enums import DocumentKind
from promoflow.db.models import Award, CaseDocument
from promoflow.dossier import audit, documents
from promoflow.dossier.section5.common import CaseLocked, case_for_entity, case_for_new_entry

# The columns of a award that the form edits. add() and update() copy exactly these from the form values.
FIELDS = ["name", "awarding_body", "year", "scope_id"]
# Name of the file slot that holds the evidence file of a award.
EVIDENCE_SLOT = "evidence"


# A award together with its evidence file, ready for the page to show.
@dataclass(frozen=True)
class AwardRow:
    award: Award
    evidence: CaseDocument | None


# All of this case's awards, each with its evidence file.
def load(s: Session, case_id: int) -> list[AwardRow]:
    awards = s.scalars(select(Award).where(Award.case_id == case_id).order_by(Award.id)).all()
    return [AwardRow(a, documents.current(s, case_id, "5H", DocumentKind.EVIDENCE, entity_table="award",
                                          entity_id=a.id, slot=EVIDENCE_SLOT))
           for a in awards]


# Check one award's form BEFORE saving. Returns a list of messages for the applicant (an empty list means valid).
def validate(values: dict, today: date) -> list[str]:
    errors = []
    required = {"name": "Award / prize name", "awarding_body": "Awarding body", "year": "Year", "scope_id": "Scope"}
    for key, label in required.items():
        if values.get(key) in (None, ""):
            errors.append(f"{label} is required.")
    if values.get("year") and values["year"] > today.year:
        errors.append("Year cannot be in the future.")
    return errors


# Add a award: refuse if the case is locked, create the row, attach the evidence file, and write an audit-log entry.
def add(s: Session, user_id: int, values: dict, evidence_upload: tuple[str, bytes] | None) -> int:
    case = case_for_new_entry(s, user_id)
    a = Award(case_id=case.id, **{f: values.get(f) for f in FIELDS})
    s.add(a)
    s.flush()
    if evidence_upload is not None:
        filename, data = evidence_upload
        documents.replace(s, case.id, user_id, "5H", DocumentKind.EVIDENCE, filename, data,
                          entity_table="award", entity_id=a.id, slot=EVIDENCE_SLOT)
    audit.log(s, user_id=user_id, case_id=case.id, action="section5_award_added", entity_table="award",
             entity_id=a.id, before=None, after=audit.snapshot(a, FIELDS))
    return a.id


# Edit a award. A new file replaces the old one (the old one is kept as history); the audit log records the values
# before and after.
def update(s: Session, user_id: int, award_id: int, values: dict, evidence_upload=None) -> None:
    a = s.get(Award, award_id)
    case = case_for_entity(s, a.case_id)
    before = audit.snapshot(a, FIELDS)
    for f in FIELDS:
        setattr(a, f, values.get(f))
    if evidence_upload is not None:
        filename, data = evidence_upload
        documents.replace(s, case.id, user_id, "5H", DocumentKind.EVIDENCE, filename, data,
                          entity_table="award", entity_id=a.id, slot=EVIDENCE_SLOT)
    s.flush()
    audit.log(s, user_id=user_id, case_id=case.id, action="section5_award_updated", entity_table="award",
             entity_id=a.id, before=before, after=audit.snapshot(a, FIELDS))


# Delete a award. The audit log keeps what it contained.
def delete(s: Session, user_id: int, award_id: int) -> None:
    a = s.get(Award, award_id)
    case = case_for_entity(s, a.case_id)
    audit.log(s, user_id=user_id, case_id=case.id, action="section5_award_deleted", entity_table="award",
             entity_id=a.id, before=audit.snapshot(a, FIELDS), after=None)
    s.delete(a)
