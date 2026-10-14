"""Section 2 – Curriculum Vitae (spec chapter 6): one file plus its last-updated date.

The CV is not the source of any count (those come from the structured sections); it is only cross-checked
against them later. Cross-checking is a Research/Teaching/Service Agent feature, not built yet.
"""
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from promoflow.config import MAX_UPLOAD_BYTES
from promoflow.db.enums import CaseStatus, DocumentKind
from promoflow.db.models import AuditLogEntry, CaseDocument
from promoflow.dossier import documents
from promoflow.dossier.section0 import EDITABLE, CaseLocked, active_case

# A CV must be a PDF or a Word document.
ALLOWED_EXTENSIONS = {"pdf", "docx"}


# Everything the Section 2 page needs, gathered in one object by load().
@dataclass(frozen=True)
class Section2Context:
    case_id: int | None
    status: CaseStatus | None
    cv_last_updated: date | None
    cv_document: CaseDocument | None


# The applicant's current CV file, if one was uploaded.
def _cv_document(s: Session, case_id: int) -> CaseDocument | None:
    return documents.current(s, case_id, "2", DocumentKind.CV)


# Read what the page needs. Returns an empty context when the applicant has no case yet.
def load(s: Session, user_id: int, today: date) -> Section2Context:
    case = active_case(s, user_id)
    if case is None:
        return Section2Context(None, None, None, None)
    return Section2Context(case.id, case.status, case.cv_last_updated, _cv_document(s, case.id))


# Check the form before saving. Returns a list of messages (empty = valid).
def validate_section2(cv_last_updated: date | None, has_document: bool, today: date,
                      new_upload: tuple[str, bytes] | None = None) -> list[str]:
    errors = []
    if not cv_last_updated:
        errors.append("Enter when your CV was last updated.")
    elif cv_last_updated > today:
        errors.append("CV last-updated date cannot be in the future.")
    if new_upload is None and not has_document:
        errors.append("Upload your CV.")
    if new_upload is not None:
        filename, data = new_upload
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in ALLOWED_EXTENSIONS:
            errors.append("The CV must be a PDF or Word document.")
        if len(data) > MAX_UPLOAD_BYTES:
            errors.append(f"The CV must be under {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    return errors


# Save the 'last updated' date and, if a new file was chosen, replace the CV. Raises CaseLocked if the case cannot
# be edited.
def save(s: Session, user_id: int, cv_last_updated: date, today: date,
        upload: tuple[str, bytes] | None = None) -> int:
    case = active_case(s, user_id)
    if case is None:
        raise CaseLocked("Save Section 0 first to start your application.")
    if case.status not in EDITABLE:
        raise CaseLocked("This application has been submitted and can no longer be edited.")

    before = case.cv_last_updated.isoformat() if case.cv_last_updated else None
    case.cv_last_updated = cv_last_updated
    case.updated_at = datetime.now(timezone.utc)

    if upload is not None:
        filename, data = upload
        documents.replace(s, case.id, user_id, "2", DocumentKind.CV, filename, data)

    s.flush()
    after = case.cv_last_updated.isoformat()
    if before != after or upload is not None:
        s.add(AuditLogEntry(user_id=user_id, case_id=case.id, action="section2_saved",
                            entity_table="promotion_case", entity_id=case.id,
                            before={"cv_last_updated": before}, after={"cv_last_updated": after}))
    return case.id
