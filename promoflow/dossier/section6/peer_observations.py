"""6B – Peer observation report (spec §10, Appendix E item 2)."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.db.enums import DocumentKind
from promoflow.db.models import CaseDocument, PeerObservation
from promoflow.dossier import audit, documents
from promoflow.dossier.section6.common import CaseLocked, case_for_entity, case_for_new_entry

FIELDS = ["course_taught_id", "observer_role_id", "observer_name", "observation_date", "rating", "scale_max"]
EVIDENCE_SLOT = "evidence"


@dataclass(frozen=True)
class PeerObservationRow:
    observation: PeerObservation
    evidence: CaseDocument | None


def load(s: Session, case_id: int) -> list[PeerObservationRow]:
    rows = s.scalars(select(PeerObservation).where(PeerObservation.case_id == case_id)
                     .order_by(PeerObservation.observation_date.desc())).all()
    return [PeerObservationRow(o, documents.current(s, case_id, "6B", DocumentKind.EVIDENCE,
                                                    entity_table="peer_observation", entity_id=o.id,
                                                    slot=EVIDENCE_SLOT))
           for o in rows]


def validate(values: dict, today: date, has_evidence: bool, evidence_upload=None) -> list[str]:
    errors = []
    required = {"course_taught_id": "Course observed", "observer_role_id": "Observer role",
               "observation_date": "Observation date", "rating": "Overall rating", "scale_max": "Rating scale maximum"}
    for key, label in required.items():
        if values.get(key) in (None, ""):
            errors.append(f"{label} is required.")
    if values.get("observation_date") and values["observation_date"] > today:
        errors.append("Observation date cannot be in the future.")
    rating, scale_max = values.get("rating"), values.get("scale_max")
    if rating is not None and scale_max is not None and not (0 <= rating <= scale_max):
        errors.append("Overall rating must be between 0 and the rating scale maximum.")
    if evidence_upload is None and not has_evidence:
        errors.append("Upload the observation report.")
    return errors


def add(s: Session, user_id: int, values: dict, evidence_upload: tuple[str, bytes]) -> int:
    case = case_for_new_entry(s, user_id)
    o = PeerObservation(case_id=case.id, **{f: values.get(f) for f in FIELDS})
    s.add(o)
    s.flush()
    filename, data = evidence_upload
    documents.replace(s, case.id, user_id, "6B", DocumentKind.EVIDENCE, filename, data,
                      entity_table="peer_observation", entity_id=o.id, slot=EVIDENCE_SLOT)
    audit.log(s, user_id=user_id, case_id=case.id, action="section6_observation_added",
             entity_table="peer_observation", entity_id=o.id, before=None, after=audit.snapshot(o, FIELDS))
    return o.id


def update(s: Session, user_id: int, observation_id: int, values: dict, evidence_upload=None) -> None:
    o = s.get(PeerObservation, observation_id)
    case = case_for_entity(s, o.case_id)
    before = audit.snapshot(o, FIELDS)
    for f in FIELDS:
        setattr(o, f, values.get(f))
    if evidence_upload is not None:
        filename, data = evidence_upload
        documents.replace(s, case.id, user_id, "6B", DocumentKind.EVIDENCE, filename, data,
                          entity_table="peer_observation", entity_id=o.id, slot=EVIDENCE_SLOT)
    s.flush()
    audit.log(s, user_id=user_id, case_id=case.id, action="section6_observation_updated",
             entity_table="peer_observation", entity_id=o.id, before=before, after=audit.snapshot(o, FIELDS))


def delete(s: Session, user_id: int, observation_id: int) -> None:
    o = s.get(PeerObservation, observation_id)
    case = case_for_entity(s, o.case_id)
    audit.log(s, user_id=user_id, case_id=case.id, action="section6_observation_deleted",
             entity_table="peer_observation", entity_id=o.id, before=audit.snapshot(o, FIELDS), after=None)
    s.delete(o)
