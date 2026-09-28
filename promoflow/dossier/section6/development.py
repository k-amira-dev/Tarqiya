"""6I – Teaching-development activity attended (spec §10, Appendix E item 10). Activities the applicant
organised or delivered (rather than attended) go in §7A-3 instead."""
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.db.enums import DocumentKind
from promoflow.db.models import CaseDocument, TeachingDevelopment
from promoflow.dossier import audit, documents
from promoflow.dossier.section6.common import CaseLocked, case_for_entity, case_for_new_entry

FIELDS = ["title", "format", "topic_id", "organizer", "activity_date", "hours"]
EVIDENCE_SLOT = "certificate"


@dataclass(frozen=True)
class DevelopmentRow:
    activity: TeachingDevelopment
    certificate: CaseDocument | None


def load(s: Session, case_id: int) -> list[DevelopmentRow]:
    rows = s.scalars(select(TeachingDevelopment).where(TeachingDevelopment.case_id == case_id)
                     .order_by(TeachingDevelopment.activity_date.desc())).all()
    return [DevelopmentRow(d, documents.current(s, case_id, "6I", DocumentKind.EVIDENCE,
                                                entity_table="teaching_development", entity_id=d.id,
                                                slot=EVIDENCE_SLOT))
           for d in rows]


def validate(values: dict, today: date, has_certificate: bool, upload=None) -> list[str]:
    errors = []
    required = {"title": "Title", "format": "Type", "topic_id": "Topic", "organizer": "Organizer",
               "activity_date": "Date"}
    for key, label in required.items():
        if values.get(key) in (None, ""):
            errors.append(f"{label} is required.")
    if values.get("activity_date") and values["activity_date"] > today:
        errors.append("Date cannot be in the future.")
    if upload is None and not has_certificate:
        errors.append("Upload the certificate.")
    return errors


def add(s: Session, user_id: int, values: dict, upload: tuple[str, bytes]) -> int:
    case = case_for_new_entry(s, user_id)
    d = TeachingDevelopment(case_id=case.id, **{f: values.get(f) for f in FIELDS})
    s.add(d)
    s.flush()
    filename, data = upload
    documents.replace(s, case.id, user_id, "6I", DocumentKind.EVIDENCE, filename, data,
                      entity_table="teaching_development", entity_id=d.id, slot=EVIDENCE_SLOT)
    audit.log(s, user_id=user_id, case_id=case.id, action="section6_development_added",
             entity_table="teaching_development", entity_id=d.id, before=None, after=audit.snapshot(d, FIELDS))
    return d.id


def update(s: Session, user_id: int, activity_id: int, values: dict, upload=None) -> None:
    d = s.get(TeachingDevelopment, activity_id)
    case = case_for_entity(s, d.case_id)
    before = audit.snapshot(d, FIELDS)
    for f in FIELDS:
        setattr(d, f, values.get(f))
    if upload is not None:
        filename, data = upload
        documents.replace(s, case.id, user_id, "6I", DocumentKind.EVIDENCE, filename, data,
                          entity_table="teaching_development", entity_id=d.id, slot=EVIDENCE_SLOT)
    s.flush()
    audit.log(s, user_id=user_id, case_id=case.id, action="section6_development_updated",
             entity_table="teaching_development", entity_id=d.id, before=before, after=audit.snapshot(d, FIELDS))


def delete(s: Session, user_id: int, activity_id: int) -> None:
    d = s.get(TeachingDevelopment, activity_id)
    case = case_for_entity(s, d.case_id)
    audit.log(s, user_id=user_id, case_id=case.id, action="section6_development_deleted",
             entity_table="teaching_development", entity_id=d.id, before=audit.snapshot(d, FIELDS), after=None)
    s.delete(d)
