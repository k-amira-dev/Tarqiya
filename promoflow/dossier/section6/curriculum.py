"""6D – Curriculum development contribution (spec §10, Appendix E item 6)."""
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.db.enums import DocumentKind
from promoflow.db.models import CaseDocument, CurriculumContribution
from promoflow.dossier import audit, documents
from promoflow.dossier.section6.common import CaseLocked, case_for_entity, case_for_new_entry

FIELDS = ["contribution_type_id", "course_or_program", "changes", "self_classification", "description",
         "approved_by", "approval_date"]
EVIDENCE_SLOT = "evidence"
MAX_DESCRIPTION = 2000
MODIFICATION_CODE = "modified_course"


@dataclass(frozen=True)
class CurriculumRow:
    contribution: CurriculumContribution
    evidence: CaseDocument | None


def load(s: Session, case_id: int) -> list[CurriculumRow]:
    rows = s.scalars(select(CurriculumContribution).where(CurriculumContribution.case_id == case_id)
                     .order_by(CurriculumContribution.approval_date.desc())).all()
    return [CurriculumRow(c, documents.current(s, case_id, "6D", DocumentKind.EVIDENCE,
                                               entity_table="curriculum_contribution", entity_id=c.id,
                                               slot=EVIDENCE_SLOT))
           for c in rows]


def validate(values: dict, today: date, is_modification: bool, has_evidence: bool, evidence_upload=None
            ) -> list[str]:
    errors = []
    required = {"contribution_type_id": "Contribution type", "course_or_program": "Course or program",
               "description": "Description", "approved_by": "Approved by", "approval_date": "Approval date"}
    for key, label in required.items():
        if values.get(key) in (None, ""):
            errors.append(f"{label} is required.")
    if is_modification and not values.get("changes"):
        errors.append("Select what changed.")
    description = values.get("description") or ""
    if len(description) > MAX_DESCRIPTION:
        errors.append(f"Description is limited to {MAX_DESCRIPTION} characters.")
    if values.get("approval_date") and values["approval_date"] > today:
        errors.append("Approval date cannot be in the future.")
    if evidence_upload is None and not has_evidence:
        errors.append("Upload evidence (approval minutes; old and new syllabus).")
    return errors


def add(s: Session, user_id: int, values: dict, evidence_upload: tuple[str, bytes]) -> int:
    case = case_for_new_entry(s, user_id)
    c = CurriculumContribution(case_id=case.id, **{f: values.get(f) for f in FIELDS})
    s.add(c)
    s.flush()
    filename, data = evidence_upload
    documents.replace(s, case.id, user_id, "6D", DocumentKind.EVIDENCE, filename, data,
                      entity_table="curriculum_contribution", entity_id=c.id, slot=EVIDENCE_SLOT)
    audit.log(s, user_id=user_id, case_id=case.id, action="section6_curriculum_added",
             entity_table="curriculum_contribution", entity_id=c.id, before=None, after=audit.snapshot(c, FIELDS))
    return c.id


def update(s: Session, user_id: int, contribution_id: int, values: dict, evidence_upload=None) -> None:
    c = s.get(CurriculumContribution, contribution_id)
    case = case_for_entity(s, c.case_id)
    before = audit.snapshot(c, FIELDS)
    for f in FIELDS:
        setattr(c, f, values.get(f))
    if evidence_upload is not None:
        filename, data = evidence_upload
        documents.replace(s, case.id, user_id, "6D", DocumentKind.EVIDENCE, filename, data,
                          entity_table="curriculum_contribution", entity_id=c.id, slot=EVIDENCE_SLOT)
    s.flush()
    audit.log(s, user_id=user_id, case_id=case.id, action="section6_curriculum_updated",
             entity_table="curriculum_contribution", entity_id=c.id, before=before, after=audit.snapshot(c, FIELDS))


def delete(s: Session, user_id: int, contribution_id: int) -> None:
    c = s.get(CurriculumContribution, contribution_id)
    case = case_for_entity(s, c.case_id)
    audit.log(s, user_id=user_id, case_id=case.id, action="section6_curriculum_deleted",
             entity_table="curriculum_contribution", entity_id=c.id, before=audit.snapshot(c, FIELDS), after=None)
    s.delete(c)
