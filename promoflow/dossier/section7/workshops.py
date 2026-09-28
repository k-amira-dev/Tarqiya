"""7A-3 – Workshop or seminar organised / delivered (spec §11, optional, Appendix F item 4)."""
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.db.enums import DocumentKind
from promoflow.db.models import CaseDocument, WorkshopDelivered
from promoflow.dossier import audit, documents
from promoflow.dossier.section7.common import CaseLocked, case_for_entity, case_for_new_entry

FIELDS = ["title", "organized_by", "role", "activity_date", "attendees"]
EVIDENCE_SLOT = "evidence"


@dataclass(frozen=True)
class WorkshopRow:
    workshop: WorkshopDelivered
    evidence: CaseDocument | None


def load(s: Session, case_id: int) -> list[WorkshopRow]:
    rows = s.scalars(select(WorkshopDelivered).where(WorkshopDelivered.case_id == case_id)
                     .order_by(WorkshopDelivered.activity_date.desc())).all()
    return [WorkshopRow(w, documents.current(s, case_id, "7A-3", DocumentKind.EVIDENCE,
                                             entity_table="workshop_delivered", entity_id=w.id, slot=EVIDENCE_SLOT))
           for w in rows]


def validate(values: dict, today: date, has_evidence: bool, evidence_upload=None) -> list[str]:
    errors = []
    required = {"title": "Title", "organized_by": "Organised by", "role": "Applicant's role",
               "activity_date": "Date"}
    for key, label in required.items():
        if values.get(key) in (None, ""):
            errors.append(f"{label} is required.")
    if values.get("activity_date") and values["activity_date"] > today:
        errors.append("Date cannot be in the future.")
    if evidence_upload is None and not has_evidence:
        errors.append("Upload evidence (announcement, programme, certificate).")
    return errors


def add(s: Session, user_id: int, values: dict, evidence_upload: tuple[str, bytes]) -> int:
    case = case_for_new_entry(s, user_id)
    w = WorkshopDelivered(case_id=case.id, **{f: values.get(f) for f in FIELDS})
    s.add(w)
    s.flush()
    filename, data = evidence_upload
    documents.replace(s, case.id, user_id, "7A-3", DocumentKind.EVIDENCE, filename, data,
                      entity_table="workshop_delivered", entity_id=w.id, slot=EVIDENCE_SLOT)
    audit.log(s, user_id=user_id, case_id=case.id, action="section7_workshop_added",
             entity_table="workshop_delivered", entity_id=w.id, before=None, after=audit.snapshot(w, FIELDS))
    return w.id


def update(s: Session, user_id: int, workshop_id: int, values: dict, evidence_upload=None) -> None:
    w = s.get(WorkshopDelivered, workshop_id)
    case = case_for_entity(s, w.case_id)
    before = audit.snapshot(w, FIELDS)
    for f in FIELDS:
        setattr(w, f, values.get(f))
    if evidence_upload is not None:
        filename, data = evidence_upload
        documents.replace(s, case.id, user_id, "7A-3", DocumentKind.EVIDENCE, filename, data,
                          entity_table="workshop_delivered", entity_id=w.id, slot=EVIDENCE_SLOT)
    s.flush()
    audit.log(s, user_id=user_id, case_id=case.id, action="section7_workshop_updated",
             entity_table="workshop_delivered", entity_id=w.id, before=before, after=audit.snapshot(w, FIELDS))


def delete(s: Session, user_id: int, workshop_id: int) -> None:
    w = s.get(WorkshopDelivered, workshop_id)
    case = case_for_entity(s, w.case_id)
    audit.log(s, user_id=user_id, case_id=case.id, action="section7_workshop_deleted",
             entity_table="workshop_delivered", entity_id=w.id, before=audit.snapshot(w, FIELDS), after=None)
    s.delete(w)
