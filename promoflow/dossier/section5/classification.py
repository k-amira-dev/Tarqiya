"""5E – Journals Classification Form (spec §9): one row per distinct journal in §5A, generated for the
applicant to review, sign and upload back. The per-journal "criteria confirmation" sub-form (for journals
missing from JournalRanking) isn't built yet — the official form's exact columns are still an open question.
"""
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from promoflow.db.enums import DocumentKind
from promoflow.db.models import CaseDocument
from promoflow.dossier import documents
from promoflow.dossier.section5.papers import PublicationRow, load as load_papers

# Name of the file slot that holds the signed Journals Classification Form.
FORM_SLOT = "signed_classification"


# One journal that appears in the applicant's papers, with its class.
@dataclass(frozen=True)
class JournalClassificationRow:
    journal_name: str
    issn: str
    classification: object  # papers.Classification


# One row per distinct journal in Section 5A. This list is shown to the applicant to review, sign and upload back.
def distinct_journals(paper_rows: list[PublicationRow]) -> list[JournalClassificationRow]:
    seen: dict[str, JournalClassificationRow] = {}
    for row in paper_rows:
        key = row.publication.issn or row.publication.journal_name
        if key not in seen:
            seen[key] = JournalClassificationRow(row.publication.journal_name, row.publication.issn,
                                                  row.classification)
    return list(seen.values())


# The applicant's uploaded signed classification form, if any.
def signed_form(s: Session, case_id: int) -> CaseDocument | None:
    return documents.current(s, case_id, "5E", DocumentKind.SIGNED_FORM, slot=FORM_SLOT)


# Save the uploaded signed form (replacing an earlier one).
def save_signed_form(s: Session, case_id: int, user_id: int, upload: tuple[str, bytes]) -> None:
    filename, data = upload
    documents.replace(s, case_id, user_id, "5E", DocumentKind.SIGNED_FORM, filename, data, slot=FORM_SLOT)
