"""5E – Journals Classification Form (spec §9): one row per distinct journal in §5A, generated for the
applicant to review, sign and upload back. The per-journal "criteria confirmation" sub-form (for journals
missing from JournalRanking) isn't built yet — the official form's exact columns are still an open question.
"""
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.db.enums import DocumentKind
from promoflow.db.models import CaseDocument, Journal, JournalRanking, Publication
from promoflow.dossier import documents
from promoflow.dossier.section5.papers import DECLARED, PublicationRow, load as load_papers

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


# ---- journals declared in the signed form ---------------------------------------------------------------------------
#
# The classes (A, B, not counted) come from the journal table, matched by ISSN. When the signed Journals Classification Form is uploaded, its
# rows are read and every journal of the applicant's papers that is NOT in the table yet is added to it from the form, so the papers are
# counted. These rows are DECLARED by the applicant (marked in `scopus_source_id`) until an admin imports the official rankings, which
# then take over because a journal that already exists is never changed.


class FormJournal(BaseModel):
    journal_name: str | None = Field(description="the journal's name in English, as printed")
    journal_name_arabic: str | None = Field(description="the journal's name in Arabic, if the form prints it")
    classification: str | None = Field(description="the class or quartile printed for the journal: for example 'Q1', 'Q3-B', 'A' or 'B'")


class ClassificationForm(BaseModel):
    journals: list[FormJournal] = Field(description="one entry per journal row of the form, in the printed order")


def _norm(text: str | None) -> str:
    """Letters and digits only, lower case, with the Arabic and Persian look-alike letters made equal (the same name can be typed either way)."""
    t = unicodedata.normalize("NFKC", text or "").lower().replace("&", "and")
    t = t.translate(str.maketrans({"ی": "ي", "ى": "ي", "ک": "ك", "ة": "ه", "أ": "ا", "إ": "ا", "آ": "ا"}))
    return "".join(ch for ch in t if ch.isalnum())


def form_class(text: str | None) -> tuple[str | None, int | None]:
    """("A" or "B", quartile) from the form's class cell: "Q1" -> A, "Q3-B" -> B, "A" -> A, "B" -> B; (None, None) when it says neither."""
    t = (text or "").strip().upper()
    quartile = int(m.group(1)) if (m := re.search(r"Q([1-4])", t)) else None
    if re.search(r"(^|[^A-Z])B$", t) or t.endswith("-B"):
        return "B", quartile
    if t == "A" or quartile == 1:
        return "A", quartile or 1
    if quartile or t == "B":
        return "B", quartile
    return None, quartile


def declare_journals_from_form(s: Session, case_id: int, form: ClassificationForm, year: int) -> list[str]:
    """Add the form's journals that the applicant's papers use and the table lacks. Returns the names added."""
    papers = list(s.scalars(select(Publication).where(Publication.case_id == case_id)))
    added = []
    by_issn: dict[str, list[Publication]] = {}
    for p in papers:
        if p.issn:
            by_issn.setdefault(p.issn, []).append(p)
    for issn, pubs in by_issn.items():
        if s.scalar(select(Journal).where((Journal.issn == issn) | (Journal.eissn == issn))):
            continue                                                     # the table already knows it: never overwrite
        names = {_norm(p.journal_name) for p in pubs}
        row = next((r for r in form.journals if names & {_norm(r.journal_name), _norm(r.journal_name_arabic)} - {""}), None)
        cls, quartile = form_class(row.classification) if row else (None, None)
        if row is None or cls is None:
            continue
        journal = Journal(title=pubs[0].journal_name, issn=issn, publisher=pubs[0].publisher, scopus_source_id=DECLARED, isi_listed=(cls == "A"))
        s.add(journal)
        s.flush()
        s.add(JournalRanking(journal_id=journal.id, year=year, scopus_indexed=True, sjr_category="Declared in the Journals Classification Form",
                             sjr_percentile=Decimal("90") if cls == "A" else Decimal("50"), quartile=quartile or (1 if cls == "A" else 3)))
        added.append(f"{pubs[0].journal_name} (Class {cls})")
    s.flush()
    return added
