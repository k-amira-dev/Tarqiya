"""Section 9 – Conditions Form (spec chapter 12): the signed form Faculty Affairs provides, plus its date.

The bilingual "Conditions Checklist" (Associate Professor Conditions Checklist, points 1-11) is pending the
template (spec open question); only the signed-file upload is built so far.
"""
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from promoflow.config import MAX_UPLOAD_BYTES
from promoflow.db.enums import CaseStatus, DocumentKind
from promoflow.db.models import CaseDocument
from promoflow.dossier import audit, documents
from promoflow.dossier.section0 import EDITABLE, CaseLocked, active_case

# Name of the file slot that holds the signed Conditions Form.
FORM_SLOT = "conditions_form"
# The signed form must be a PDF.
ALLOWED_EXTENSIONS = {"pdf"}


# Everything the Section 9 page needs.
@dataclass(frozen=True)
class Section9Context:
    case_id: int | None
    status: CaseStatus | None
    conditions_signed_date: date | None
    document: CaseDocument | None


# Read the signed date and the uploaded form, if any.
def load(s: Session, user_id: int) -> Section9Context:
    case = active_case(s, user_id)
    if case is None:
        return Section9Context(None, None, None, None)
    doc = documents.current(s, case.id, "9", DocumentKind.SIGNED_FORM, slot=FORM_SLOT)
    return Section9Context(case.id, case.status, case.conditions_signed_date, doc)


# Check the form before saving: a signing date (not in the future) and a PDF. Returns a list of messages.
def validate(conditions_signed_date: date | None, has_document: bool, today: date,
            upload: tuple[str, bytes] | None = None) -> list[str]:
    errors = []
    if not conditions_signed_date:
        errors.append("Enter the date the Conditions Form was signed.")
    elif conditions_signed_date > today:
        errors.append("Date signed cannot be in the future.")
    if upload is None and not has_document:
        errors.append("Upload the signed Conditions Form.")
    if upload is not None:
        filename, data = upload
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in ALLOWED_EXTENSIONS:
            errors.append("The Conditions Form must be a PDF.")
        if len(data) > MAX_UPLOAD_BYTES:
            errors.append(f"The Conditions Form must be under {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    return errors


# Save the signing date and, if a new file was chosen, replace the form. The Eligibility Checker later confirms the
# file is present.
def save(s: Session, user_id: int, conditions_signed_date: date, upload: tuple[str, bytes] | None = None) -> int:
    case = active_case(s, user_id)
    if case is None:
        raise CaseLocked("Save Section 0 first to start your application.")
    if case.status not in EDITABLE:
        raise CaseLocked("This application has been submitted and can no longer be edited.")

    before = case.conditions_signed_date.isoformat() if case.conditions_signed_date else None
    case.conditions_signed_date = conditions_signed_date
    case.updated_at = datetime.now(timezone.utc)
    if upload is not None:
        filename, data = upload
        documents.replace(s, case.id, user_id, "9", DocumentKind.SIGNED_FORM, filename, data,
                          slot=FORM_SLOT, signed_date=conditions_signed_date)
    s.flush()
    after = case.conditions_signed_date.isoformat()
    if before != after or upload is not None:
        audit.log(s, user_id=user_id, case_id=case.id, action="section9_saved", entity_table="promotion_case",
                 entity_id=case.id, before={"conditions_signed_date": before},
                 after={"conditions_signed_date": after})
    return case.id
