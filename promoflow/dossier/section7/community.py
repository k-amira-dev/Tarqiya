"""7B – Community service activity (spec §11, optional): mapped by the Service Agent to Appendix F items
3 or 5 (there is no dedicated community-service line on the form).
"""
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.db.enums import DocumentKind
from promoflow.db.models import CaseDocument, CommunityActivity
from promoflow.dossier import audit, documents
from promoflow.dossier.section7.common import CaseLocked, case_for_entity, case_for_new_entry

FIELDS = ["activity_type_id", "funded_project_id", "title", "beneficiary_organisation", "applicant_role",
         "date_from", "date_to", "beneficiaries", "deliverables", "measurable_outcome"]
EVIDENCE_SLOT = "evidence"
FUNDED_PROJECT_CODES = {"funded_company", "funded_government", "funded_university"}


@dataclass(frozen=True)
class CommunityActivityRow:
    activity: CommunityActivity
    evidence: CaseDocument | None


def load(s: Session, case_id: int) -> list[CommunityActivityRow]:
    rows = s.scalars(select(CommunityActivity).where(CommunityActivity.case_id == case_id)
                     .order_by(CommunityActivity.date_from.desc())).all()
    return [CommunityActivityRow(a, documents.current(s, case_id, "7B", DocumentKind.EVIDENCE,
                                                      entity_table="community_activity", entity_id=a.id,
                                                      slot=EVIDENCE_SLOT))
           for a in rows]


def validate(values: dict, is_funded_project: bool, has_evidence: bool, evidence_upload=None) -> list[str]:
    errors = []
    required = {"activity_type_id": "Activity type", "title": "Title",
               "beneficiary_organisation": "Beneficiary organisation", "applicant_role": "Applicant's role",
               "date_from": "Time period start", "deliverables": "Deliverables"}
    for key, label in required.items():
        if values.get(key) in (None, ""):
            errors.append(f"{label} is required.")
    if is_funded_project and not values.get("funded_project_id"):
        errors.append("Link the funded project (entered in §5D) instead of re-entering it.")
    date_from, date_to = values.get("date_from"), values.get("date_to")
    if date_from and date_to and date_to < date_from:
        errors.append("Time period end must be on or after its start.")
    if evidence_upload is None and not has_evidence:
        errors.append("Upload evidence.")
    return errors


def add(s: Session, user_id: int, values: dict, evidence_upload: tuple[str, bytes]) -> int:
    case = case_for_new_entry(s, user_id)
    a = CommunityActivity(case_id=case.id, **{f: values.get(f) for f in FIELDS})
    s.add(a)
    s.flush()
    filename, data = evidence_upload
    documents.replace(s, case.id, user_id, "7B", DocumentKind.EVIDENCE, filename, data,
                      entity_table="community_activity", entity_id=a.id, slot=EVIDENCE_SLOT)
    audit.log(s, user_id=user_id, case_id=case.id, action="section7_community_added",
             entity_table="community_activity", entity_id=a.id, before=None, after=audit.snapshot(a, FIELDS))
    return a.id


def update(s: Session, user_id: int, activity_id: int, values: dict, evidence_upload=None) -> None:
    a = s.get(CommunityActivity, activity_id)
    case = case_for_entity(s, a.case_id)
    before = audit.snapshot(a, FIELDS)
    for f in FIELDS:
        setattr(a, f, values.get(f))
    if evidence_upload is not None:
        filename, data = evidence_upload
        documents.replace(s, case.id, user_id, "7B", DocumentKind.EVIDENCE, filename, data,
                          entity_table="community_activity", entity_id=a.id, slot=EVIDENCE_SLOT)
    s.flush()
    audit.log(s, user_id=user_id, case_id=case.id, action="section7_community_updated",
             entity_table="community_activity", entity_id=a.id, before=before, after=audit.snapshot(a, FIELDS))


def delete(s: Session, user_id: int, activity_id: int) -> None:
    a = s.get(CommunityActivity, activity_id)
    case = case_for_entity(s, a.case_id)
    audit.log(s, user_id=user_id, case_id=case.id, action="section7_community_deleted",
             entity_table="community_activity", entity_id=a.id, before=audit.snapshot(a, FIELDS), after=None)
    s.delete(a)
