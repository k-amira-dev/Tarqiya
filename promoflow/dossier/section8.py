"""Section 8 – Recommendation letter (spec chapter 12, repeatable, optional)."""
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.db.enums import CaseStatus, DocumentKind
from promoflow.db.models import CaseDocument, PromotionCase, RecommendationLetter
from promoflow.dossier import audit, documents
from promoflow.dossier.section0 import EDITABLE, CaseLocked, active_case

# The columns of a recommendation letter that the form edits. The writer's name is personal data: it is stored but
# never sent to a language model.
FIELDS = ["writer_name", "writer_rank", "writer_institution", "relationship_id"]
# Name of the file slot that holds the letter itself.
EVIDENCE_SLOT = "letter"


# A letter together with its uploaded file, ready for the page to show.
@dataclass(frozen=True)
class RecommendationLetterRow:
    letter: RecommendationLetter
    evidence: CaseDocument | None


# Everything the Section 8 page needs.
@dataclass(frozen=True)
class Section8Context:
    case_id: int | None
    status: CaseStatus | None
    letters: list[RecommendationLetterRow]


# All of the applicant's recommendation letters. This section is optional.
def load(s: Session, user_id: int) -> Section8Context:
    case = active_case(s, user_id)
    if case is None:
        return Section8Context(None, None, [])
    letters = s.scalars(select(RecommendationLetter).where(RecommendationLetter.case_id == case.id)).all()
    rows = [RecommendationLetterRow(letter, documents.current(s, case.id, "8", DocumentKind.EVIDENCE,
                                                             entity_table="recommendation_letter",
                                                             entity_id=letter.id, slot=EVIDENCE_SLOT))
           for letter in letters]
    return Section8Context(case.id, case.status, rows)


# Check one letter's form. Returns a list of messages (empty = valid). The letter file is required.
def validate(values: dict, has_evidence: bool, evidence_upload=None) -> list[str]:
    errors = []
    required = {"writer_name": "Writer's name", "writer_rank": "Writer's rank / title",
               "writer_institution": "Writer's institution", "relationship_id": "Relationship to applicant"}
    for key, label in required.items():
        if values.get(key) in (None, ""):
            errors.append(f"{label} is required.")
    if evidence_upload is None and not has_evidence:
        errors.append("Upload the letter.")
    return errors


# Add a letter and its file (same steps as the other lists: check, create, attach file, audit).
def add(s: Session, user_id: int, values: dict, evidence_upload: tuple[str, bytes]) -> int:
    case = active_case(s, user_id)
    if case is None:
        raise CaseLocked("Save Section 0 first to start your application.")
    if case.status not in EDITABLE:
        raise CaseLocked("This application has been submitted and can no longer be edited.")
    letter = RecommendationLetter(case_id=case.id, **{f: values.get(f) for f in FIELDS})
    s.add(letter)
    s.flush()
    filename, data = evidence_upload
    documents.replace(s, case.id, user_id, "8", DocumentKind.EVIDENCE, filename, data,
                      entity_table="recommendation_letter", entity_id=letter.id, slot=EVIDENCE_SLOT)
    audit.log(s, user_id=user_id, case_id=case.id, action="section8_letter_added",
             entity_table="recommendation_letter", entity_id=letter.id, before=None,
             after=audit.snapshot(letter, FIELDS))
    return letter.id


# Remove a letter. The audit log keeps what it contained.
def delete(s: Session, user_id: int, letter_id: int) -> None:
    letter = s.get(RecommendationLetter, letter_id)
    case = s.get(PromotionCase, letter.case_id)
    if case.status not in EDITABLE:
        raise CaseLocked("This application has been submitted and can no longer be edited.")
    audit.log(s, user_id=user_id, case_id=case.id, action="section8_letter_deleted",
             entity_table="recommendation_letter", entity_id=letter.id, before=audit.snapshot(letter, FIELDS),
             after=None)
    s.delete(letter)
