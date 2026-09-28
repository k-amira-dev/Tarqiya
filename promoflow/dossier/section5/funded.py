"""5D – Funded research project entry (spec §9). A project entered once here can be linked from §7B
instead of re-entered; that link isn't built yet since §7 doesn't exist."""
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.db.enums import DocumentKind, InvestigatorRole, ProjectStatus
from promoflow.db.models import CaseDocument, FundedProject
from promoflow.dossier import audit, documents
from promoflow.dossier.section5.common import CaseLocked, case_for_entity, case_for_new_entry

FIELDS = ["title", "funding_body", "funder_type_id", "role", "amount", "currency", "start_date", "end_date", "status"]
EVIDENCE_SLOT = "evidence"


@dataclass(frozen=True)
class FundedProjectRow:
    project: FundedProject
    evidence: CaseDocument | None


def load(s: Session, case_id: int) -> list[FundedProjectRow]:
    projects = s.scalars(select(FundedProject).where(FundedProject.case_id == case_id)
                         .order_by(FundedProject.id)).all()
    return [FundedProjectRow(p, documents.current(s, case_id, "5D", DocumentKind.EVIDENCE,
                                                  entity_table="funded_project", entity_id=p.id,
                                                  slot=EVIDENCE_SLOT))
           for p in projects]


def validate(values: dict, today: date, has_evidence: bool, evidence_upload=None) -> list[str]:
    errors = []
    required = {"title": "Project title", "funding_body": "Funding body", "funder_type_id": "Funder type",
               "role": "Role", "start_date": "Start date", "status": "Status"}
    for key, label in required.items():
        if values.get(key) in (None, ""):
            errors.append(f"{label} is required.")
    if values.get("start_date") and values.get("end_date") and values["end_date"] < values["start_date"]:
        errors.append("End date must be on or after the start date.")
    if evidence_upload is None and not has_evidence:
        errors.append("Upload evidence (award letter or contract).")
    return errors


def add(s: Session, user_id: int, values: dict, evidence_upload: tuple[str, bytes]) -> int:
    case = case_for_new_entry(s, user_id)
    p = FundedProject(case_id=case.id, **{f: values.get(f) for f in FIELDS})
    s.add(p)
    s.flush()
    filename, data = evidence_upload
    documents.replace(s, case.id, user_id, "5D", DocumentKind.EVIDENCE, filename, data,
                      entity_table="funded_project", entity_id=p.id, slot=EVIDENCE_SLOT)
    audit.log(s, user_id=user_id, case_id=case.id, action="section5_funded_added", entity_table="funded_project",
             entity_id=p.id, before=None, after=audit.snapshot(p, FIELDS))
    return p.id


def update(s: Session, user_id: int, project_id: int, values: dict, evidence_upload=None) -> None:
    p = s.get(FundedProject, project_id)
    case = case_for_entity(s, p.case_id)
    before = audit.snapshot(p, FIELDS)
    for f in FIELDS:
        setattr(p, f, values.get(f))
    if evidence_upload is not None:
        filename, data = evidence_upload
        documents.replace(s, case.id, user_id, "5D", DocumentKind.EVIDENCE, filename, data,
                          entity_table="funded_project", entity_id=p.id, slot=EVIDENCE_SLOT)
    s.flush()
    audit.log(s, user_id=user_id, case_id=case.id, action="section5_funded_updated", entity_table="funded_project",
             entity_id=p.id, before=before, after=audit.snapshot(p, FIELDS))


def delete(s: Session, user_id: int, project_id: int) -> None:
    p = s.get(FundedProject, project_id)
    case = case_for_entity(s, p.case_id)
    audit.log(s, user_id=user_id, case_id=case.id, action="section5_funded_deleted", entity_table="funded_project",
             entity_id=p.id, before=audit.snapshot(p, FIELDS), after=None)
    s.delete(p)
