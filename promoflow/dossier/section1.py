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

# The case columns this section edits.
FIELDS = ["decl_not_from_thesis", "decl_after_current_rank", "application_signed_date"]
# File types accepted for the signed form (checked by file name ending).
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "xls", "xlsx", "jpg", "jpeg", "png"}


# Everything the Section 1 page needs, gathered in one object by load().
@dataclass(frozen=True)
class Section1Context:
    case_id: int | None
    status: CaseStatus | None
    values: dict
    research_item_count: int
    signed_document: CaseDocument | None


# Turn dates and enums into plain values for the audit log.
def _json(v):
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v.value if hasattr(v, "value") else v


# How many research entries the applicant has, counted with ONE query. Shown on the page next to the declarations.
def research_item_count(s: Session, case_id: int) -> int:
    """§5.2: entries in §5A, 5A-2, 5B, 5C, 5G, in one query. §5A honours its own "submit for promotion" flag; the
    other entry types (not built yet) don't have one, so every row counts until that flag exists for them too."""
    # A tiny sub-query: how many rows of `model` this case has. Several of them are combined into a single database
    # call.
    def count(model, *conditions):
        return select(func.count()).select_from(model).where(model.case_id == case_id, *conditions).scalar_subquery()

    counts = s.execute(select(
        count(Publication, Publication.submit_for_promotion.is_(True)), count(CreativeWork), count(Book),
        count(ConferencePaper), count(Patent))).one()
    return sum(c or 0 for c in counts)


# The applicant's current signed application form, if one was uploaded.
def _signed_document(s: Session, case_id: int) -> CaseDocument | None:
    return documents.current(s, case_id, "1", DocumentKind.SIGNED_FORM)


# Read what the page needs. Returns an empty context when the applicant has no case yet.
def load(s: Session, user_id: int, today: date) -> Section1Context:
    case = active_case(s, user_id)
    if case is None:
        return Section1Context(None, None, {f: None for f in FIELDS}, 0, None)
    values = {f: getattr(case, f) for f in FIELDS}
    return Section1Context(case.id, case.status, values, research_item_count(s, case.id),
                           _signed_document(s, case.id))


# Check the form BEFORE saving. Returns a list of messages for the applicant (an empty list means everything is
# valid).
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
        # The file type is read from the file name's ending, for example 'form.pdf' -> 'pdf'.
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in ALLOWED_EXTENSIONS:
            errors.append("The signed application form must be a PDF, Word, Excel or image file.")
        if len(data) > MAX_UPLOAD_BYTES:
            errors.append(f"The signed application form must be under {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    return errors


# Update the declarations and, if a file was uploaded, attach it. Section 1 never creates the case: Section 0 does.
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

    # Remember the values before the change, so the audit log can show before and after.
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
