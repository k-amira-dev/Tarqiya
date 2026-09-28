"""5B – Book / book chapter entry (spec §9). Caps (max counts per type) are Research Agent features, not
built yet; they're documented in the UI as a reminder rather than enforced here.
"""
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.db.enums import BookItemType, DocumentKind
from promoflow.db.models import Book, CaseDocument
from promoflow.dossier import audit, documents
from promoflow.dossier.section5.common import CaseLocked, case_for_entity, case_for_new_entry
from promoflow.rules.research import isbn_is_valid

FIELDS = ["item_type", "book_title", "chapter_title", "publisher", "publication_date", "isbn",
         "main_or_sole_author", "financial_support_by", "refereed", "referee_count", "from_thesis"]
EVIDENCE_SLOT = "evidence"


@dataclass(frozen=True)
class BookRow:
    book: Book
    evidence: CaseDocument | None


def load(s: Session, case_id: int) -> list[BookRow]:
    books = s.scalars(select(Book).where(Book.case_id == case_id).order_by(Book.id)).all()
    return [BookRow(b, documents.current(s, case_id, "5B", DocumentKind.EVIDENCE, entity_table="book",
                                         entity_id=b.id, slot=EVIDENCE_SLOT))
           for b in books]


def validate(values: dict, today: date, has_evidence: bool, evidence_upload=None) -> list[str]:
    errors = []
    required = {"item_type": "Item type", "book_title": "Book title", "publisher": "Publisher",
               "publication_date": "Publication year / month", "isbn": "ISBN"}
    for key, label in required.items():
        if values.get(key) in (None, ""):
            errors.append(f"{label} is required.")
    if values.get("item_type") == BookItemType.CHAPTER and not (values.get("chapter_title") or "").strip():
        errors.append("Chapter title is required for a book chapter.")
    isbn = (values.get("isbn") or "").strip()
    if isbn and not isbn_is_valid(isbn):
        errors.append("ISBN does not pass the ISBN-10/13 checksum.")
    if values.get("publication_date") and values["publication_date"] > today:
        errors.append("Publication date cannot be in the future.")
    if values.get("main_or_sole_author") is None:
        errors.append("State whether you are the main or sole author.")
    if values.get("refereed") and not values.get("referee_count"):
        errors.append("Enter the number of referees.")
    if values.get("item_type") == BookItemType.HERITAGE and (values.get("referee_count") or 0) < 2:
        errors.append("Heritage books must be refereed by at least 2 referees.")
    if values.get("from_thesis") is None:
        errors.append("State whether this is derived from your thesis.")
    if evidence_upload is None and not has_evidence:
        errors.append("Upload evidence (cover, copyright page and table of contents, or the chapter PDF).")
    return errors


def add(s: Session, user_id: int, values: dict, evidence_upload: tuple[str, bytes]) -> int:
    case = case_for_new_entry(s, user_id)
    b = Book(case_id=case.id, **{f: values.get(f) for f in FIELDS})
    s.add(b)
    s.flush()
    filename, data = evidence_upload
    documents.replace(s, case.id, user_id, "5B", DocumentKind.EVIDENCE, filename, data,
                      entity_table="book", entity_id=b.id, slot=EVIDENCE_SLOT)
    audit.log(s, user_id=user_id, case_id=case.id, action="section5_book_added", entity_table="book",
             entity_id=b.id, before=None, after=audit.snapshot(b, FIELDS))
    return b.id


def update(s: Session, user_id: int, book_id: int, values: dict, evidence_upload=None) -> None:
    b = s.get(Book, book_id)
    case = case_for_entity(s, b.case_id)
    before = audit.snapshot(b, FIELDS)
    for f in FIELDS:
        setattr(b, f, values.get(f))
    if evidence_upload is not None:
        filename, data = evidence_upload
        documents.replace(s, case.id, user_id, "5B", DocumentKind.EVIDENCE, filename, data,
                          entity_table="book", entity_id=b.id, slot=EVIDENCE_SLOT)
    s.flush()
    audit.log(s, user_id=user_id, case_id=case.id, action="section5_book_updated", entity_table="book",
             entity_id=b.id, before=before, after=audit.snapshot(b, FIELDS))


def delete(s: Session, user_id: int, book_id: int) -> None:
    b = s.get(Book, book_id)
    case = case_for_entity(s, b.case_id)
    audit.log(s, user_id=user_id, case_id=case.id, action="section5_book_deleted", entity_table="book",
             entity_id=b.id, before=audit.snapshot(b, FIELDS), after=None)
    s.delete(b)
