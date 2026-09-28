"""7A-1 – Committee membership (spec §11, Appendix F item 1)."""
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.db.enums import DocumentKind
from promoflow.db.models import CaseDocument, CommitteeMembership
from promoflow.dossier import audit, documents
from promoflow.dossier.section7.common import CaseLocked, case_for_entity, case_for_new_entry

FIELDS = ["committee_name", "level", "role_id", "date_from", "date_to", "contribution_summary"]
EVIDENCE_SLOT = "evidence"
MAX_SUMMARY = 1000


@dataclass(frozen=True)
class CommitteeRow:
    membership: CommitteeMembership
    evidence: CaseDocument | None


def load(s: Session, case_id: int) -> list[CommitteeRow]:
    rows = s.scalars(select(CommitteeMembership).where(CommitteeMembership.case_id == case_id)
                     .order_by(CommitteeMembership.date_from.desc())).all()
    return [CommitteeRow(m, documents.current(s, case_id, "7A-1", DocumentKind.EVIDENCE,
                                              entity_table="committee_membership", entity_id=m.id,
                                              slot=EVIDENCE_SLOT))
           for m in rows]


def validate(values: dict, has_evidence: bool, evidence_upload=None) -> list[str]:
    errors = []
    required = {"committee_name": "Committee name", "level": "Level", "role_id": "Role", "date_from": "From date"}
    for key, label in required.items():
        if values.get(key) in (None, ""):
            errors.append(f"{label} is required.")
    date_from, date_to = values.get("date_from"), values.get("date_to")
    if date_from and date_to and date_to < date_from:
        errors.append("\"To\" must be on or after \"From\".")
    summary = values.get("contribution_summary") or ""
    if len(summary) > MAX_SUMMARY:
        errors.append(f"Contribution summary is limited to {MAX_SUMMARY} characters.")
    if evidence_upload is None and not has_evidence:
        errors.append("Upload evidence (appointment letter or minutes).")
    return errors


def add(s: Session, user_id: int, values: dict, evidence_upload: tuple[str, bytes]) -> int:
    case = case_for_new_entry(s, user_id)
    m = CommitteeMembership(case_id=case.id, **{f: values.get(f) for f in FIELDS})
    s.add(m)
    s.flush()
    filename, data = evidence_upload
    documents.replace(s, case.id, user_id, "7A-1", DocumentKind.EVIDENCE, filename, data,
                      entity_table="committee_membership", entity_id=m.id, slot=EVIDENCE_SLOT)
    audit.log(s, user_id=user_id, case_id=case.id, action="section7_committee_added",
             entity_table="committee_membership", entity_id=m.id, before=None, after=audit.snapshot(m, FIELDS))
    return m.id


def update(s: Session, user_id: int, membership_id: int, values: dict, evidence_upload=None) -> None:
    m = s.get(CommitteeMembership, membership_id)
    case = case_for_entity(s, m.case_id)
    before = audit.snapshot(m, FIELDS)
    for f in FIELDS:
        setattr(m, f, values.get(f))
    if evidence_upload is not None:
        filename, data = evidence_upload
        documents.replace(s, case.id, user_id, "7A-1", DocumentKind.EVIDENCE, filename, data,
                          entity_table="committee_membership", entity_id=m.id, slot=EVIDENCE_SLOT)
    s.flush()
    audit.log(s, user_id=user_id, case_id=case.id, action="section7_committee_updated",
             entity_table="committee_membership", entity_id=m.id, before=before, after=audit.snapshot(m, FIELDS))


def delete(s: Session, user_id: int, membership_id: int) -> None:
    m = s.get(CommitteeMembership, membership_id)
    case = case_for_entity(s, m.case_id)
    audit.log(s, user_id=user_id, case_id=case.id, action="section7_committee_deleted",
             entity_table="committee_membership", entity_id=m.id, before=audit.snapshot(m, FIELDS), after=None)
    s.delete(m)
