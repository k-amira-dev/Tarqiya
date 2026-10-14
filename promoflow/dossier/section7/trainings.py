"""7A-4 – Training or educational activity delivered (spec §11, optional, Appendix F item 3)."""
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.db.enums import DocumentKind
from promoflow.db.models import CaseDocument, TrainingDelivered
from promoflow.dossier import audit, documents
from promoflow.dossier.section7.common import CaseLocked, case_for_entity, case_for_new_entry

# The columns of a training activity that the form edits. add() and update() copy exactly these from the form
# values.
FIELDS = ["title", "inside_university", "host_organisation", "activity_date", "hours", "participants"]
# Name of the file slot that holds the evidence file of a training activity.
EVIDENCE_SLOT = "evidence"


# A training activity together with its evidence file, ready for the page to show.
@dataclass(frozen=True)
class TrainingRow:
    training: TrainingDelivered
    evidence: CaseDocument | None


# All of this case's training activities, each with its evidence file.
def load(s: Session, case_id: int) -> list[TrainingRow]:
    rows = s.scalars(select(TrainingDelivered).where(TrainingDelivered.case_id == case_id)
                     .order_by(TrainingDelivered.activity_date.desc())).all()
    return [TrainingRow(t, documents.current(s, case_id, "7A-4", DocumentKind.EVIDENCE,
                                             entity_table="training_delivered", entity_id=t.id, slot=EVIDENCE_SLOT))
           for t in rows]


# Check one training activity's form BEFORE saving. Returns a list of messages for the applicant (an empty list
# means valid).
def validate(values: dict, today: date, has_evidence: bool, evidence_upload=None) -> list[str]:
    errors = []
    required = {"title": "Title", "host_organisation": "Host organisation", "activity_date": "Date"}
    for key, label in required.items():
        if values.get(key) in (None, ""):
            errors.append(f"{label} is required.")
    if values.get("inside_university") is None:
        errors.append("State whether this was inside or outside the university.")
    if values.get("activity_date") and values["activity_date"] > today:
        errors.append("Date cannot be in the future.")
    if evidence_upload is None and not has_evidence:
        errors.append("Upload evidence.")
    return errors


# Add a training activity: refuse if the case is locked, create the row, attach the evidence file, and write an
# audit-log entry.
def add(s: Session, user_id: int, values: dict, evidence_upload: tuple[str, bytes]) -> int:
    case = case_for_new_entry(s, user_id)
    t = TrainingDelivered(case_id=case.id, **{f: values.get(f) for f in FIELDS})
    s.add(t)
    s.flush()
    filename, data = evidence_upload
    documents.replace(s, case.id, user_id, "7A-4", DocumentKind.EVIDENCE, filename, data,
                      entity_table="training_delivered", entity_id=t.id, slot=EVIDENCE_SLOT)
    audit.log(s, user_id=user_id, case_id=case.id, action="section7_training_added",
             entity_table="training_delivered", entity_id=t.id, before=None, after=audit.snapshot(t, FIELDS))
    return t.id


# Edit a training activity. A new file replaces the old one (the old one is kept as history); the audit log records
# the values before and after.
def update(s: Session, user_id: int, training_id: int, values: dict, evidence_upload=None) -> None:
    t = s.get(TrainingDelivered, training_id)
    case = case_for_entity(s, t.case_id)
    before = audit.snapshot(t, FIELDS)
    for f in FIELDS:
        setattr(t, f, values.get(f))
    if evidence_upload is not None:
        filename, data = evidence_upload
        documents.replace(s, case.id, user_id, "7A-4", DocumentKind.EVIDENCE, filename, data,
                          entity_table="training_delivered", entity_id=t.id, slot=EVIDENCE_SLOT)
    s.flush()
    audit.log(s, user_id=user_id, case_id=case.id, action="section7_training_updated",
             entity_table="training_delivered", entity_id=t.id, before=before, after=audit.snapshot(t, FIELDS))


# Delete a training activity. The audit log keeps what it contained.
def delete(s: Session, user_id: int, training_id: int) -> None:
    t = s.get(TrainingDelivered, training_id)
    case = case_for_entity(s, t.case_id)
    audit.log(s, user_id=user_id, case_id=case.id, action="section7_training_deleted",
             entity_table="training_delivered", entity_id=t.id, before=audit.snapshot(t, FIELDS), after=None)
    s.delete(t)
