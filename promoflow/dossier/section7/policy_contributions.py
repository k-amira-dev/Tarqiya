"""7A-5 – Policy contribution (spec §11, optional): mapped by the Service Agent to Appendix F item 1."""
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.db.enums import DocumentKind
from promoflow.db.models import CaseDocument, PolicyContribution
from promoflow.dossier import audit, documents
from promoflow.dossier.section7.common import CaseLocked, case_for_entity, case_for_new_entry

# The columns of a policy contribution that the form edits. add() and update() copy exactly these from the form
# values.
FIELDS = ["policy_name", "level", "role_id", "activity_date"]
# Name of the file slot that holds the evidence file of a policy contribution.
EVIDENCE_SLOT = "evidence"


# A policy contribution together with its evidence file, ready for the page to show.
@dataclass(frozen=True)
class PolicyContributionRow:
    contribution: PolicyContribution
    evidence: CaseDocument | None


# All of this case's policy contributions, each with its evidence file.
def load(s: Session, case_id: int) -> list[PolicyContributionRow]:
    rows = s.scalars(select(PolicyContribution).where(PolicyContribution.case_id == case_id)
                     .order_by(PolicyContribution.activity_date.desc())).all()
    return [PolicyContributionRow(p, documents.current(s, case_id, "7A-5", DocumentKind.EVIDENCE,
                                                       entity_table="policy_contribution", entity_id=p.id,
                                                       slot=EVIDENCE_SLOT))
           for p in rows]


# Check one policy contribution's form BEFORE saving. Returns a list of messages for the applicant (an empty list
# means valid).
def validate(values: dict, today: date, has_evidence: bool, evidence_upload=None) -> list[str]:
    errors = []
    required = {"policy_name": "Policy / regulation", "level": "Level", "role_id": "Role",
               "activity_date": "Date"}
    for key, label in required.items():
        if values.get(key) in (None, ""):
            errors.append(f"{label} is required.")
    if values.get("activity_date") and values["activity_date"] > today:
        errors.append("Date cannot be in the future.")
    if evidence_upload is None and not has_evidence:
        errors.append("Upload evidence.")
    return errors


# Add a policy contribution: refuse if the case is locked, create the row, attach the evidence file, and write an
# audit-log entry.
def add(s: Session, user_id: int, values: dict, evidence_upload: tuple[str, bytes]) -> int:
    case = case_for_new_entry(s, user_id)
    p = PolicyContribution(case_id=case.id, **{f: values.get(f) for f in FIELDS})
    s.add(p)
    s.flush()
    filename, data = evidence_upload
    documents.replace(s, case.id, user_id, "7A-5", DocumentKind.EVIDENCE, filename, data,
                      entity_table="policy_contribution", entity_id=p.id, slot=EVIDENCE_SLOT)
    audit.log(s, user_id=user_id, case_id=case.id, action="section7_policy_added",
             entity_table="policy_contribution", entity_id=p.id, before=None, after=audit.snapshot(p, FIELDS))
    return p.id


# Edit a policy contribution. A new file replaces the old one (the old one is kept as history); the audit log
# records the values before and after.
def update(s: Session, user_id: int, contribution_id: int, values: dict, evidence_upload=None) -> None:
    p = s.get(PolicyContribution, contribution_id)
    case = case_for_entity(s, p.case_id)
    before = audit.snapshot(p, FIELDS)
    for f in FIELDS:
        setattr(p, f, values.get(f))
    if evidence_upload is not None:
        filename, data = evidence_upload
        documents.replace(s, case.id, user_id, "7A-5", DocumentKind.EVIDENCE, filename, data,
                          entity_table="policy_contribution", entity_id=p.id, slot=EVIDENCE_SLOT)
    s.flush()
    audit.log(s, user_id=user_id, case_id=case.id, action="section7_policy_updated",
             entity_table="policy_contribution", entity_id=p.id, before=before, after=audit.snapshot(p, FIELDS))


# Delete a policy contribution. The audit log keeps what it contained.
def delete(s: Session, user_id: int, contribution_id: int) -> None:
    p = s.get(PolicyContribution, contribution_id)
    case = case_for_entity(s, p.case_id)
    audit.log(s, user_id=user_id, case_id=case.id, action="section7_policy_deleted",
             entity_table="policy_contribution", entity_id=p.id, before=audit.snapshot(p, FIELDS), after=None)
    s.delete(p)
