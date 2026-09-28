"""Section 1 – Application Form for Promotion (spec chapter 5): the two declarations and the signed form.

Document generation (Appendix I / A / B, the "GEN" component) is not built yet, so the applicant uploads the
signed application form directly rather than downloading a pre-filled template. The generated documents will
slot in later without changing this module's shape.
"""
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from promoflow.config import MAX_UPLOAD_BYTES
from promoflow.db.enums import CaseStatus, DocumentKind
from promoflow.db.models import AuditLogEntry, Book, CaseDocument, ConferencePaper, CreativeWork, Patent, Publication
from promoflow.dossier import documents
from promoflow.dossier.section0 import EDITABLE, CaseLocked, active_case

FIELDS = ["decl_not_from_thesis", "decl_after_current_rank", "application_signed_date"]
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "xls", "xlsx", "jpg", "jpeg", "png"}


@dataclass(frozen=True)
class Section1Context:
    case_id: int | None
    status: CaseStatus | None
    values: dict
    research_item_count: int
    signed_document: CaseDocument | None


def _json(v):
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v.value if hasattr(v, "value") else v


def _count(s: Session, model, case_id: int) -> int:
    return s.scalar(select(func.count()).select_from(model).where(model.case_id == case_id)) or 0


def research_item_count(s: Session, case_id: int) -> int:
    """§5.2: entries in §5A, 5A-2, 5B, 5C, 5G. §5A honours its own "submit for promotion" flag; the other
    entry types (not built yet) don't have one, so every row counts until that flag exists for them too."""
    n = s.scalar(select(func.count()).select_from(Publication)
                .where(Publication.case_id == case_id, Publication.submit_for_promotion.is_(True))) or 0
    for model in (CreativeWork, Book, ConferencePaper, Patent):
        n += _count(s, model, case_id)
    return n


def _signed_document(s: Session, case_id: int) -> CaseDocument | None:
    return documents.current(s, case_id, "1", DocumentKind.SIGNED_FORM)


def load(s: Session, user_id: int, today: date) -> Section1Context:
    case = active_case(s, user_id)
    if case is None:
        return Section1Context(None, None, {f: None for f in FIELDS}, 0, None)
    values = {f: getattr(case, f) for f in FIELDS}
    return Section1Context(case.id, case.status, values, research_item_count(s, case.id),
                           _signed_document(s, case.id))


def validate_section1(values: dict, has_signed_document: bool, today: date,
                      new_upload: tuple[str, bytes] | None = None) -> list[str]:
    """Blocking errors for saving Section 1 (spec §5.2: both declarations, the signed form and its date are Req)."""
    errors = []
    if not values.get("decl_not_from_thesis"):
        errors.append("Confirm that the items counted were not taken from your Master's or PhD thesis.")
    if not values.get("decl_after_current_rank"):
        errors.append("Confirm that all items were published, accepted or presented after your current rank.")
    signed_date = values.get("application_signed_date")
    if not signed_date:
        errors.append("Enter the date you signed the application form.")
    elif signed_date > today:
        errors.append("Date signed cannot be in the future.")
    if new_upload is None and not has_signed_document:
        errors.append("Upload the signed application form.")
    if new_upload is not None:
        filename, data = new_upload
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in ALLOWED_EXTENSIONS:
            errors.append("The signed application form must be a PDF, Word, Excel or image file.")
        if len(data) > MAX_UPLOAD_BYTES:
            errors.append(f"The signed application form must be under {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    return errors


def save(s: Session, user_id: int, values: dict, today: date,
         upload: tuple[str, bytes] | None = None) -> int:
    """Update the declarations and, if `upload` is given, attach a newly uploaded signed form.

    Section 1 never creates the case — Section 0 does that. Returns the case id.
    """
    case = active_case(s, user_id)
    if case is None:
        raise CaseLocked("Save Section 0 first to start your application.")
    if case.status not in EDITABLE:
        raise CaseLocked("This application has been submitted and can no longer be edited.")

    before = {f: _json(getattr(case, f)) for f in FIELDS}
    for f in FIELDS:
        setattr(case, f, values.get(f))
    case.updated_at = datetime.now(timezone.utc)

    if upload is not None:
        filename, data = upload
        documents.replace(s, case.id, user_id, "1", DocumentKind.SIGNED_FORM, filename, data,
                          signed_date=values.get("application_signed_date"))

    s.flush()
    after = {f: _json(getattr(case, f)) for f in FIELDS}
    if before != after or upload is not None:
        s.add(AuditLogEntry(user_id=user_id, case_id=case.id, action="section1_saved",
                            entity_table="promotion_case", entity_id=case.id, before=before, after=after))
    return case.id
