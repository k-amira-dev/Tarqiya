"""6G – Teaching innovation & educational technology (spec §10, Appendix E items 7-8)."""
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.db.enums import DocumentKind
from promoflow.db.models import CaseDocument, TeachingInnovation
from promoflow.dossier import audit, documents
from promoflow.dossier.section6.common import CaseLocked, case_for_entity, case_for_new_entry

# The columns of a teaching innovation that the form edits. add() and update() copy exactly these from the form
# values.
FIELDS = ["innovation_type_id", "course_taught_id", "description", "measured_outcome"]
# Name of the file slot that holds the evidence file of a teaching innovation.
EVIDENCE_SLOT = "evidence"


# A teaching innovation together with its evidence file, ready for the page to show.
@dataclass(frozen=True)
class InnovationRow:
    innovation: TeachingInnovation
    evidence: CaseDocument | None


# All of this case's teaching innovations, each with its evidence file.
def load(s: Session, case_id: int) -> list[InnovationRow]:
    rows = s.scalars(select(TeachingInnovation).where(TeachingInnovation.case_id == case_id)).all()
    return [InnovationRow(i, documents.current(s, case_id, "6G", DocumentKind.EVIDENCE,
                                               entity_table="teaching_innovation", entity_id=i.id,
                                               slot=EVIDENCE_SLOT))
           for i in rows]


# Check one teaching innovation's form BEFORE saving. Returns a list of messages for the applicant (an empty list
# means valid).
def validate(values: dict, has_evidence: bool, evidence_upload=None) -> list[str]:
    errors = []
    required = {"innovation_type_id": "Type", "course_taught_id": "Course", "description": "Description"}
    for key, label in required.items():
        if values.get(key) in (None, ""):
            errors.append(f"{label} is required.")
    if evidence_upload is None and not has_evidence:
        errors.append("Upload evidence (materials, study report, screenshots).")
    return errors


# Add a teaching innovation: refuse if the case is locked, create the row, attach the evidence file, and write an
# audit-log entry.
def add(s: Session, user_id: int, values: dict, evidence_upload: tuple[str, bytes]) -> int:
    case = case_for_new_entry(s, user_id)
    i = TeachingInnovation(case_id=case.id, **{f: values.get(f) for f in FIELDS})
    s.add(i)
    s.flush()
    filename, data = evidence_upload
    documents.replace(s, case.id, user_id, "6G", DocumentKind.EVIDENCE, filename, data,
                      entity_table="teaching_innovation", entity_id=i.id, slot=EVIDENCE_SLOT)
    audit.log(s, user_id=user_id, case_id=case.id, action="section6_innovation_added",
             entity_table="teaching_innovation", entity_id=i.id, before=None, after=audit.snapshot(i, FIELDS))
    return i.id


# Edit a teaching innovation. A new file replaces the old one (the old one is kept as history); the audit log
# records the values before and after.
def update(s: Session, user_id: int, innovation_id: int, values: dict, evidence_upload=None) -> None:
    i = s.get(TeachingInnovation, innovation_id)
    case = case_for_entity(s, i.case_id)
    before = audit.snapshot(i, FIELDS)
    for f in FIELDS:
        setattr(i, f, values.get(f))
    if evidence_upload is not None:
        filename, data = evidence_upload
        documents.replace(s, case.id, user_id, "6G", DocumentKind.EVIDENCE, filename, data,
                          entity_table="teaching_innovation", entity_id=i.id, slot=EVIDENCE_SLOT)
    s.flush()
    audit.log(s, user_id=user_id, case_id=case.id, action="section6_innovation_updated",
             entity_table="teaching_innovation", entity_id=i.id, before=before, after=audit.snapshot(i, FIELDS))


# Delete a teaching innovation. The audit log keeps what it contained.
def delete(s: Session, user_id: int, innovation_id: int) -> None:
    i = s.get(TeachingInnovation, innovation_id)
    case = case_for_entity(s, i.case_id)
    audit.log(s, user_id=user_id, case_id=case.id, action="section6_innovation_deleted",
             entity_table="teaching_innovation", entity_id=i.id, before=audit.snapshot(i, FIELDS), after=None)
    s.delete(i)
