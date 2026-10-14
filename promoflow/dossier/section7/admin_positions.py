"""7A-2 – Administrative position (spec §11, optional): mapped by the Service Agent to Appendix F item 1."""
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.db.enums import DocumentKind
from promoflow.db.models import AdministrativePosition, CaseDocument
from promoflow.dossier import audit, documents
from promoflow.dossier.section7.common import CaseLocked, case_for_entity, case_for_new_entry

# The columns of a administrative position that the form edits. add() and update() copy exactly these from the form
# values.
FIELDS = ["position_id", "unit", "date_from", "date_to"]
# Name of the file slot that holds the evidence file of a administrative position.
EVIDENCE_SLOT = "evidence"


# A administrative position together with its evidence file, ready for the page to show.
@dataclass(frozen=True)
class AdminPositionRow:
    position: AdministrativePosition
    evidence: CaseDocument | None


# All of this case's administrative positions, each with its evidence file.
def load(s: Session, case_id: int) -> list[AdminPositionRow]:
    rows = s.scalars(select(AdministrativePosition).where(AdministrativePosition.case_id == case_id)
                     .order_by(AdministrativePosition.date_from.desc())).all()
    return [AdminPositionRow(p, documents.current(s, case_id, "7A-2", DocumentKind.EVIDENCE,
                                                  entity_table="administrative_position", entity_id=p.id,
                                                  slot=EVIDENCE_SLOT))
           for p in rows]


# Check one administrative position's form BEFORE saving. Returns a list of messages for the applicant (an empty
# list means valid).
def validate(values: dict, has_evidence: bool, evidence_upload=None) -> list[str]:
    errors = []
    required = {"position_id": "Position", "unit": "Unit", "date_from": "From date"}
    for key, label in required.items():
        if values.get(key) in (None, ""):
            errors.append(f"{label} is required.")
    date_from, date_to = values.get("date_from"), values.get("date_to")
    if date_from and date_to and date_to < date_from:
        errors.append("\"To\" must be on or after \"From\".")
    if evidence_upload is None and not has_evidence:
        errors.append("Upload the appointment letter.")
    return errors


# Add a administrative position: refuse if the case is locked, create the row, attach the evidence file, and write
# an audit-log entry.
def add(s: Session, user_id: int, values: dict, evidence_upload: tuple[str, bytes]) -> int:
    case = case_for_new_entry(s, user_id)
    p = AdministrativePosition(case_id=case.id, **{f: values.get(f) for f in FIELDS})
    s.add(p)
    s.flush()
    filename, data = evidence_upload
    documents.replace(s, case.id, user_id, "7A-2", DocumentKind.EVIDENCE, filename, data,
                      entity_table="administrative_position", entity_id=p.id, slot=EVIDENCE_SLOT)
    audit.log(s, user_id=user_id, case_id=case.id, action="section7_admin_position_added",
             entity_table="administrative_position", entity_id=p.id, before=None, after=audit.snapshot(p, FIELDS))
    return p.id


# Edit a administrative position. A new file replaces the old one (the old one is kept as history); the audit log
# records the values before and after.
def update(s: Session, user_id: int, position_id: int, values: dict, evidence_upload=None) -> None:
    p = s.get(AdministrativePosition, position_id)
    case = case_for_entity(s, p.case_id)
    before = audit.snapshot(p, FIELDS)
    for f in FIELDS:
        setattr(p, f, values.get(f))
    if evidence_upload is not None:
        filename, data = evidence_upload
        documents.replace(s, case.id, user_id, "7A-2", DocumentKind.EVIDENCE, filename, data,
                          entity_table="administrative_position", entity_id=p.id, slot=EVIDENCE_SLOT)
    s.flush()
    audit.log(s, user_id=user_id, case_id=case.id, action="section7_admin_position_updated",
             entity_table="administrative_position", entity_id=p.id, before=before, after=audit.snapshot(p, FIELDS))


# Delete a administrative position. The audit log keeps what it contained.
def delete(s: Session, user_id: int, position_id: int) -> None:
    p = s.get(AdministrativePosition, position_id)
    case = case_for_entity(s, p.case_id)
    audit.log(s, user_id=user_id, case_id=case.id, action="section7_admin_position_deleted",
             entity_table="administrative_position", entity_id=p.id, before=audit.snapshot(p, FIELDS), after=None)
    s.delete(p)
