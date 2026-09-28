"""5G – Patent entry (spec §9). Only granted patents count, as Class B (capped)."""
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.db.enums import DocumentKind, PatentStatus
from promoflow.db.models import CaseDocument, Patent
from promoflow.dossier import audit, documents
from promoflow.dossier.section5.common import CaseLocked, case_for_entity, case_for_new_entry

FIELDS = ["title", "patent_number", "office_id", "status", "grant_date", "inventors"]
EVIDENCE_SLOT = "evidence"


@dataclass(frozen=True)
class PatentRow:
    patent: Patent
    evidence: CaseDocument | None


def load(s: Session, case_id: int) -> list[PatentRow]:
    patents = s.scalars(select(Patent).where(Patent.case_id == case_id).order_by(Patent.id)).all()
    return [PatentRow(p, documents.current(s, case_id, "5G", DocumentKind.EVIDENCE, entity_table="patent",
                                           entity_id=p.id, slot=EVIDENCE_SLOT))
           for p in patents]


def validate(values: dict, today: date, has_evidence: bool, evidence_upload=None) -> list[str]:
    errors = []
    required = {"title": "Patent title", "patent_number": "Patent number", "office_id": "Patent office",
               "status": "Status", "inventors": "Inventors"}
    for key, label in required.items():
        if values.get(key) in (None, ""):
            errors.append(f"{label} is required.")
    if values.get("status") == PatentStatus.GRANTED:
        if not values.get("grant_date"):
            errors.append("Grant date is required for a granted patent.")
        elif values["grant_date"] > today:
            errors.append("Grant date cannot be in the future.")
    if evidence_upload is None and not has_evidence:
        errors.append("Upload evidence (the grant certificate).")
    return errors


def add(s: Session, user_id: int, values: dict, evidence_upload: tuple[str, bytes]) -> int:
    case = case_for_new_entry(s, user_id)
    p = Patent(case_id=case.id, **{f: values.get(f) for f in FIELDS})
    s.add(p)
    s.flush()
    filename, data = evidence_upload
    documents.replace(s, case.id, user_id, "5G", DocumentKind.EVIDENCE, filename, data,
                      entity_table="patent", entity_id=p.id, slot=EVIDENCE_SLOT)
    audit.log(s, user_id=user_id, case_id=case.id, action="section5_patent_added", entity_table="patent",
             entity_id=p.id, before=None, after=audit.snapshot(p, FIELDS))
    return p.id


def update(s: Session, user_id: int, patent_id: int, values: dict, evidence_upload=None) -> None:
    p = s.get(Patent, patent_id)
    case = case_for_entity(s, p.case_id)
    before = audit.snapshot(p, FIELDS)
    for f in FIELDS:
        setattr(p, f, values.get(f))
    if evidence_upload is not None:
        filename, data = evidence_upload
        documents.replace(s, case.id, user_id, "5G", DocumentKind.EVIDENCE, filename, data,
                          entity_table="patent", entity_id=p.id, slot=EVIDENCE_SLOT)
    s.flush()
    audit.log(s, user_id=user_id, case_id=case.id, action="section5_patent_updated", entity_table="patent",
             entity_id=p.id, before=before, after=audit.snapshot(p, FIELDS))


def delete(s: Session, user_id: int, patent_id: int) -> None:
    p = s.get(Patent, patent_id)
    case = case_for_entity(s, p.case_id)
    audit.log(s, user_id=user_id, case_id=case.id, action="section5_patent_deleted", entity_table="patent",
             entity_id=p.id, before=audit.snapshot(p, FIELDS), after=None)
    s.delete(p)
