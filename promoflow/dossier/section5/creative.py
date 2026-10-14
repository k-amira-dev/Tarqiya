"""5A-2 – Creative / studio work entry (spec §9): approved creative works count as Class B (capped)."""
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.db.enums import DocumentKind
from promoflow.db.models import CaseDocument, CreativeWork
from promoflow.dossier import audit, documents
from promoflow.dossier.section5.common import CaseLocked, case_for_entity, case_for_new_entry

# The columns of a creative or studio work that the form edits. add() and update() copy exactly these from the form
# values.
FIELDS = ["form_id", "title", "venue", "organizing_institution", "date_from", "date_to", "approved"]
# Name of the file slot that holds the evidence file of a creative or studio work.
EVIDENCE_SLOT = "evidence"


# A creative or studio work together with its evidence file, ready for the page to show.
@dataclass(frozen=True)
class CreativeWorkRow:
    work: CreativeWork
    evidence: CaseDocument | None


# All of this case's creative works, each with its evidence file.
def load(s: Session, case_id: int) -> list[CreativeWorkRow]:
    works = s.scalars(select(CreativeWork).where(CreativeWork.case_id == case_id).order_by(CreativeWork.id)).all()
    return [CreativeWorkRow(w, documents.current(s, case_id, "5A-2", DocumentKind.EVIDENCE,
                                                 entity_table="creative_work", entity_id=w.id, slot=EVIDENCE_SLOT))
           for w in works]


# Check one creative or studio work's form BEFORE saving. Returns a list of messages for the applicant (an empty
# list means valid).
def validate(values: dict, today: date, has_evidence: bool, evidence_upload=None) -> list[str]:
    errors = []
    required = {"form_id": "Form of presentation", "title": "Title / content and quantity", "venue": "Venue",
               "organizing_institution": "Organizing institution", "date_from": "Start date"}
    for key, label in required.items():
        if values.get(key) in (None, ""):
            errors.append(f"{label} is required.")
    date_from, date_to = values.get("date_from"), values.get("date_to")
    if date_from and date_from > today:
        errors.append("Start date cannot be in the future.")
    if date_from and date_to and date_to < date_from:
        errors.append("End date must be on or after the start date.")
    if values.get("approved") is None:
        errors.append("State whether this work was approved as creative work.")
    if evidence_upload is None and not has_evidence:
        errors.append("Upload evidence (catalogue, programme or approval letter).")
    return errors


# Add a creative or studio work: refuse if the case is locked, create the row, attach the evidence file, and write
# an audit-log entry.
def add(s: Session, user_id: int, values: dict, evidence_upload: tuple[str, bytes]) -> int:
    case = case_for_new_entry(s, user_id)
    w = CreativeWork(case_id=case.id, **{f: values.get(f) for f in FIELDS})
    s.add(w)
    s.flush()
    filename, data = evidence_upload
    documents.replace(s, case.id, user_id, "5A-2", DocumentKind.EVIDENCE, filename, data,
                      entity_table="creative_work", entity_id=w.id, slot=EVIDENCE_SLOT)
    audit.log(s, user_id=user_id, case_id=case.id, action="section5_creative_added", entity_table="creative_work",
             entity_id=w.id, before=None, after=audit.snapshot(w, FIELDS))
    return w.id


# Edit a creative or studio work. A new file replaces the old one (the old one is kept as history); the audit log
# records the values before and after.
def update(s: Session, user_id: int, work_id: int, values: dict, evidence_upload=None) -> None:
    w = s.get(CreativeWork, work_id)
    case = case_for_entity(s, w.case_id)
    before = audit.snapshot(w, FIELDS)
    for f in FIELDS:
        setattr(w, f, values.get(f))
    if evidence_upload is not None:
        filename, data = evidence_upload
        documents.replace(s, case.id, user_id, "5A-2", DocumentKind.EVIDENCE, filename, data,
                          entity_table="creative_work", entity_id=w.id, slot=EVIDENCE_SLOT)
    s.flush()
    audit.log(s, user_id=user_id, case_id=case.id, action="section5_creative_updated", entity_table="creative_work",
             entity_id=w.id, before=before, after=audit.snapshot(w, FIELDS))


# Delete a creative or studio work. The audit log keeps what it contained.
def delete(s: Session, user_id: int, work_id: int) -> None:
    w = s.get(CreativeWork, work_id)
    case = case_for_entity(s, w.case_id)
    audit.log(s, user_id=user_id, case_id=case.id, action="section5_creative_deleted", entity_table="creative_work",
             entity_id=w.id, before=audit.snapshot(w, FIELDS), after=None)
    s.delete(w)
