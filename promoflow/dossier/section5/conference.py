"""5C – Conference paper entry (spec §9). Recorded in the narrative; not counted towards the publication
minimums unless the policy confirms they count (open question)."""
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.db.enums import DocumentKind
from promoflow.db.models import CaseDocument, ConferencePaper
from promoflow.dossier import audit, documents
from promoflow.dossier.section5.common import CaseLocked, case_for_entity, case_for_new_entry

FIELDS = ["title", "conference_title", "organizer", "conference_date", "place", "pages",
         "main_or_sole_author", "scopus_indexed", "doi"]
EVIDENCE_SLOT = "evidence"


@dataclass(frozen=True)
class ConferencePaperRow:
    paper: ConferencePaper
    evidence: CaseDocument | None


def load(s: Session, case_id: int) -> list[ConferencePaperRow]:
    papers = s.scalars(select(ConferencePaper).where(ConferencePaper.case_id == case_id)
                       .order_by(ConferencePaper.id)).all()
    return [ConferencePaperRow(p, documents.current(s, case_id, "5C", DocumentKind.EVIDENCE,
                                                    entity_table="conference_paper", entity_id=p.id,
                                                    slot=EVIDENCE_SLOT))
           for p in papers]


def validate(values: dict, today: date, has_evidence: bool, evidence_upload=None) -> list[str]:
    errors = []
    required = {"title": "Paper title", "conference_title": "Conference title", "organizer": "Name of organizer",
               "conference_date": "Date", "place": "Place"}
    for key, label in required.items():
        if values.get(key) in (None, ""):
            errors.append(f"{label} is required.")
    if values.get("conference_date") and values["conference_date"] > today:
        errors.append("Date cannot be in the future.")
    if values.get("main_or_sole_author") is None:
        errors.append("State whether you are the main or sole author.")
    if values.get("scopus_indexed") is None:
        errors.append("State whether the proceedings are indexed in Scopus.")
    if evidence_upload is None and not has_evidence:
        errors.append("Upload evidence (the proceedings paper or acceptance).")
    return errors


def add(s: Session, user_id: int, values: dict, evidence_upload: tuple[str, bytes]) -> int:
    case = case_for_new_entry(s, user_id)
    p = ConferencePaper(case_id=case.id, **{f: values.get(f) for f in FIELDS})
    s.add(p)
    s.flush()
    filename, data = evidence_upload
    documents.replace(s, case.id, user_id, "5C", DocumentKind.EVIDENCE, filename, data,
                      entity_table="conference_paper", entity_id=p.id, slot=EVIDENCE_SLOT)
    audit.log(s, user_id=user_id, case_id=case.id, action="section5_conference_added",
             entity_table="conference_paper", entity_id=p.id, before=None, after=audit.snapshot(p, FIELDS))
    return p.id


def update(s: Session, user_id: int, paper_id: int, values: dict, evidence_upload=None) -> None:
    p = s.get(ConferencePaper, paper_id)
    case = case_for_entity(s, p.case_id)
    before = audit.snapshot(p, FIELDS)
    for f in FIELDS:
        setattr(p, f, values.get(f))
    if evidence_upload is not None:
        filename, data = evidence_upload
        documents.replace(s, case.id, user_id, "5C", DocumentKind.EVIDENCE, filename, data,
                          entity_table="conference_paper", entity_id=p.id, slot=EVIDENCE_SLOT)
    s.flush()
    audit.log(s, user_id=user_id, case_id=case.id, action="section5_conference_updated",
             entity_table="conference_paper", entity_id=p.id, before=before, after=audit.snapshot(p, FIELDS))


def delete(s: Session, user_id: int, paper_id: int) -> None:
    p = s.get(ConferencePaper, paper_id)
    case = case_for_entity(s, p.case_id)
    audit.log(s, user_id=user_id, case_id=case.id, action="section5_conference_deleted",
             entity_table="conference_paper", entity_id=p.id, before=audit.snapshot(p, FIELDS), after=None)
    s.delete(p)
