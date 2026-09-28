"""Section 10 – Cover Letter (spec chapter 12): the signed cover letter addressed to the Promotions
Committee, plus its date."""
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from promoflow.config import MAX_UPLOAD_BYTES
from promoflow.db.enums import CaseStatus, DocumentKind
from promoflow.db.models import CaseDocument
from promoflow.dossier import audit, documents
from promoflow.dossier.section0 import EDITABLE, CaseLocked, active_case

LETTER_SLOT = "cover_letter"
ALLOWED_EXTENSIONS = {"pdf"}


@dataclass(frozen=True)
class Section10Context:
    case_id: int | None
    status: CaseStatus | None
    cover_letter_signed_date: date | None
    document: CaseDocument | None


def load(s: Session, user_id: int) -> Section10Context:
    case = active_case(s, user_id)
    if case is None:
        return Section10Context(None, None, None, None)
    doc = documents.current(s, case.id, "10", DocumentKind.SIGNED_FORM, slot=LETTER_SLOT)
    return Section10Context(case.id, case.status, case.cover_letter_signed_date, doc)


def validate(cover_letter_signed_date: date | None, has_document: bool, today: date,
            upload: tuple[str, bytes] | None = None) -> list[str]:
    errors = []
    if not cover_letter_signed_date:
        errors.append("Enter the date the cover letter was signed.")
    elif cover_letter_signed_date > today:
        errors.append("Date cannot be in the future.")
    if upload is None and not has_document:
        errors.append("Upload the signed cover letter.")
    if upload is not None:
        filename, data = upload
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in ALLOWED_EXTENSIONS:
            errors.append("The cover letter must be a PDF.")
        if len(data) > MAX_UPLOAD_BYTES:
            errors.append(f"The cover letter must be under {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    return errors


def save(s: Session, user_id: int, cover_letter_signed_date: date, upload: tuple[str, bytes] | None = None) -> int:
    case = active_case(s, user_id)
    if case is None:
        raise CaseLocked("Save Section 0 first to start your application.")
    if case.status not in EDITABLE:
        raise CaseLocked("This application has been submitted and can no longer be edited.")

    before = case.cover_letter_signed_date.isoformat() if case.cover_letter_signed_date else None
    case.cover_letter_signed_date = cover_letter_signed_date
    case.updated_at = datetime.now(timezone.utc)
    if upload is not None:
        filename, data = upload
        documents.replace(s, case.id, user_id, "10", DocumentKind.SIGNED_FORM, filename, data,
                          slot=LETTER_SLOT, signed_date=cover_letter_signed_date)
    s.flush()
    after = case.cover_letter_signed_date.isoformat()
    if before != after or upload is not None:
        audit.log(s, user_id=user_id, case_id=case.id, action="section10_saved", entity_table="promotion_case",
                 entity_id=case.id, before={"cover_letter_signed_date": before},
                 after={"cover_letter_signed_date": after})
    return case.id
