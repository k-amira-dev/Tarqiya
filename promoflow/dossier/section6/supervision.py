"""6H – Graduate teaching & thesis supervision (spec §10): scored for Full Professor only (item 5), also
used by the Research Agent's main-author-via-supervision rule."""
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.db.enums import DocumentKind, SupervisionStatus
from promoflow.db.models import CaseDocument, Supervision
from promoflow.dossier import audit, documents
from promoflow.dossier.section6.common import CaseLocked, case_for_entity, case_for_new_entry

# The columns of a graduate supervision that the form edits. add() and update() copy exactly these from the form
# values.
FIELDS = ["student_name", "degree", "role", "thesis_title", "start_date", "status", "graduation_date"]
# Name of the file slot that holds the evidence file of a graduate supervision.
EVIDENCE_SLOT = "evidence"


# A graduate supervision together with its evidence file, ready for the page to show.
@dataclass(frozen=True)
class SupervisionRow:
    supervision: Supervision
    evidence: CaseDocument | None


# All of this case's graduate supervisions, each with its evidence file.
def load(s: Session, case_id: int) -> list[SupervisionRow]:
    rows = s.scalars(select(Supervision).where(Supervision.case_id == case_id)
                     .order_by(Supervision.start_date.desc())).all()
    return [SupervisionRow(sup, documents.current(s, case_id, "6H", DocumentKind.EVIDENCE,
                                                  entity_table="supervision", entity_id=sup.id, slot=EVIDENCE_SLOT))
           for sup in rows]


# Check one graduate supervision's form BEFORE saving. Returns a list of messages for the applicant (an empty list
# means valid).
def validate(values: dict, today: date, has_evidence: bool, evidence_upload=None) -> list[str]:
    errors = []
    required = {"student_name": "Student", "degree": "Degree", "role": "Supervision role",
               "thesis_title": "Thesis title", "start_date": "Start date", "status": "Status"}
    for key, label in required.items():
        if values.get(key) in (None, ""):
            errors.append(f"{label} is required.")
    if values.get("start_date") and values["start_date"] > today:
        errors.append("Start date cannot be in the future.")
    if values.get("status") == SupervisionStatus.GRADUATED and not values.get("graduation_date"):
        errors.append("Graduation date is required once the student has graduated.")
    if evidence_upload is None and not has_evidence:
        errors.append("Upload the supervision appointment letter.")
    return errors


# Add a graduate supervision: refuse if the case is locked, create the row, attach the evidence file, and write an
# audit-log entry.
def add(s: Session, user_id: int, values: dict, evidence_upload: tuple[str, bytes]) -> int:
    case = case_for_new_entry(s, user_id)
    sup = Supervision(case_id=case.id, **{f: values.get(f) for f in FIELDS})
    s.add(sup)
    s.flush()
    filename, data = evidence_upload
    documents.replace(s, case.id, user_id, "6H", DocumentKind.EVIDENCE, filename, data,
                      entity_table="supervision", entity_id=sup.id, slot=EVIDENCE_SLOT)
    audit.log(s, user_id=user_id, case_id=case.id, action="section6_supervision_added", entity_table="supervision",
             entity_id=sup.id, before=None, after=audit.snapshot(sup, FIELDS))
    return sup.id


# Edit a graduate supervision. A new file replaces the old one (the old one is kept as history); the audit log
# records the values before and after.
def update(s: Session, user_id: int, supervision_id: int, values: dict, evidence_upload=None) -> None:
    sup = s.get(Supervision, supervision_id)
    case = case_for_entity(s, sup.case_id)
    before = audit.snapshot(sup, FIELDS)
    for f in FIELDS:
        setattr(sup, f, values.get(f))
    if evidence_upload is not None:
        filename, data = evidence_upload
        documents.replace(s, case.id, user_id, "6H", DocumentKind.EVIDENCE, filename, data,
                          entity_table="supervision", entity_id=sup.id, slot=EVIDENCE_SLOT)
    s.flush()
    audit.log(s, user_id=user_id, case_id=case.id, action="section6_supervision_updated",
             entity_table="supervision", entity_id=sup.id, before=before, after=audit.snapshot(sup, FIELDS))


# Delete a graduate supervision. The audit log keeps what it contained.
def delete(s: Session, user_id: int, supervision_id: int) -> None:
    sup = s.get(Supervision, supervision_id)
    case = case_for_entity(s, sup.case_id)
    audit.log(s, user_id=user_id, case_id=case.id, action="section6_supervision_deleted",
             entity_table="supervision", entity_id=sup.id, before=audit.snapshot(sup, FIELDS), after=None)
    s.delete(sup)
