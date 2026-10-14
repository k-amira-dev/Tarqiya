"""Section 3 – Academic Degrees & Equivalency (spec chapter 7): one repeatable entry per degree.

Matches the "First: Academic Degrees Earned" table of Appendix I. Unlike Sections 0-2, this section is a
list of child entries (add / edit / delete), the pattern later sections (ranks, research, teaching, service)
will reuse.

THE "LIST OF ENTRIES" PATTERN (sections 3 to 7 all work like this)
Each entry has four functions: `load` (read the list), `validate_*` (check one entry's form, returning messages),
and `add` / `update` / `delete`. Every writer does the same things in the same order:
  1. find the case and refuse if it is locked (`CaseLocked`);
  2. take a `snapshot` of the entry BEFORE the change;
  3. change it and `flush` (send it to the database inside the transaction);
  4. write an audit-log row with before and after (`audit.log`).
Uploaded evidence files are attached through `documents.replace`, with a `slot` name to tell several files on one
entry apart (a degree's "certificate" and its "equivalency" certificate).
"""
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.db.enums import CaseStatus, DegreeLevel, DocumentKind
from promoflow.db.models import CaseDocument, Degree, PromotionCase
from promoflow.dossier import audit, documents
from promoflow.dossier.section0 import EDITABLE, CaseLocked, active_case

# The columns of a degree that the form edits (copied back and forth by add/update).
FIELDS = ["level", "specialization", "university", "country_code", "study_from", "study_to", "graduation_date",
         "thesis_title", "equivalency_required"]
# Master's and PhD degrees need a thesis title.
THESIS_LEVELS = {DegreeLevel.MASTER, DegreeLevel.PHD}
# Degrees that count as a doctorate. The Eligibility Checker requires at least one.
DOCTORATE_LEVELS = {DegreeLevel.PHD, DegreeLevel.OTHER_DOCTORATE}
# Names for the two files a degree can have, so they can be told apart.
CERT_SLOT = "certificate"
EQUIVALENCY_SLOT = "equivalency"


# A degree together with its two evidence files, ready for the page to show.
@dataclass(frozen=True)
class DegreeRow:
    degree: Degree
    certificate: CaseDocument | None
    equivalency_certificate: CaseDocument | None


# Everything the Section 3 page needs.
@dataclass(frozen=True)
class Section3Context:
    case_id: int | None
    status: CaseStatus | None
    degrees: list[DegreeRow]


# Attach the two evidence files to one degree.
def _row(s: Session, d: Degree) -> DegreeRow:
    return DegreeRow(
        d,
        documents.current(s, d.case_id, "3", DocumentKind.EVIDENCE, entity_table="degree", entity_id=d.id,
                          slot=CERT_SLOT),
        documents.current(s, d.case_id, "3", DocumentKind.EVIDENCE, entity_table="degree", entity_id=d.id,
                          slot=EQUIVALENCY_SLOT),
    )


# All of the applicant's degrees, oldest graduation first.
def load(s: Session, user_id: int, today: date) -> Section3Context:
    case = active_case(s, user_id)
    if case is None:
        return Section3Context(None, None, [])
    degrees = s.scalars(select(Degree).where(Degree.case_id == case.id)
                        .order_by(Degree.graduation_date)).all()
    return Section3Context(case.id, case.status, [_row(s, d) for d in degrees])


# True if at least one degree is a doctorate.
def has_doctorate(degrees: list[DegreeRow]) -> bool:
    return any(row.degree.level in DOCTORATE_LEVELS for row in degrees)


# Check one degree's form. Returns a list of messages (empty = valid). Uploads are checked as 'new file chosen' OR
# 'already has one'.
def validate_degree(values: dict, has_certificate: bool, today: date,
                    cert_upload: tuple[str, bytes] | None = None,
                    equivalency_upload: tuple[str, bytes] | None = None,
                    has_equivalency_certificate: bool = False) -> list[str]:
    errors = []
    required = {"level": "Degree level", "specialization": "Specialization", "university": "University",
               "country_code": "Country", "study_from": "Study period start", "study_to": "Study period end",
               "graduation_date": "Date of graduation"}
    for key, label in required.items():
        if values.get(key) in (None, ""):
            errors.append(f"{label} is required.")
    study_from, study_to = values.get("study_from"), values.get("study_to")
    if study_from and study_to and study_to <= study_from:
        errors.append("Study period end must be after its start.")
    grad = values.get("graduation_date")
    if grad and grad > today:
        errors.append("Date of graduation cannot be in the future.")
    level = values.get("level")
    if level in THESIS_LEVELS and not (values.get("thesis_title") or "").strip():
        errors.append("Enter the thesis / dissertation title.")
    if cert_upload is None and not has_certificate:
        errors.append("Upload the degree certificate.")
    if values.get("equivalency_required"):
        if equivalency_upload is None and not has_equivalency_certificate:
            errors.append("Upload the equivalency certificate, or turn off \"Equivalency required\".")
    return errors


# Add a degree with its certificate (required) and, optionally, an equivalency certificate.
def add(s: Session, user_id: int, values: dict, cert_upload: tuple[str, bytes],
       equivalency_upload: tuple[str, bytes] | None = None) -> int:
    case = active_case(s, user_id)
    if case is None:
        raise CaseLocked("Save Section 0 first to start your application.")
    if case.status not in EDITABLE:
        raise CaseLocked("This application has been submitted and can no longer be edited.")

    # Build the new row from the form values, using only the fields in FIELDS.
    degree = Degree(case_id=case.id, **{f: values.get(f) for f in FIELDS})
    s.add(degree)
    s.flush()
    filename, data = cert_upload
    documents.replace(s, case.id, user_id, "3", DocumentKind.EVIDENCE, filename, data,
                      entity_table="degree", entity_id=degree.id, slot=CERT_SLOT)
    if equivalency_upload is not None:
        filename, data = equivalency_upload
        documents.replace(s, case.id, user_id, "3", DocumentKind.EVIDENCE, filename, data,
                          entity_table="degree", entity_id=degree.id, slot=EQUIVALENCY_SLOT)
    s.flush()
    audit.log(s, user_id=user_id, case_id=case.id, action="section3_degree_added", entity_table="degree",
             entity_id=degree.id, before=None, after=audit.snapshot(degree, FIELDS))
    return degree.id


# Edit a degree; a new file replaces the old one (the old one is kept as history).
def update(s: Session, user_id: int, degree_id: int, values: dict,
          cert_upload: tuple[str, bytes] | None = None,
          equivalency_upload: tuple[str, bytes] | None = None) -> None:
    degree = s.get(Degree, degree_id)
    case = s.get(PromotionCase, degree.case_id)
    if case.status not in EDITABLE:
        raise CaseLocked("This application has been submitted and can no longer be edited.")

    before = audit.snapshot(degree, FIELDS)
    for f in FIELDS:
        setattr(degree, f, values.get(f))
    if cert_upload is not None:
        filename, data = cert_upload
        documents.replace(s, case.id, user_id, "3", DocumentKind.EVIDENCE, filename, data,
                          entity_table="degree", entity_id=degree.id, slot=CERT_SLOT)
    if equivalency_upload is not None:
        filename, data = equivalency_upload
        documents.replace(s, case.id, user_id, "3", DocumentKind.EVIDENCE, filename, data,
                          entity_table="degree", entity_id=degree.id, slot=EQUIVALENCY_SLOT)
    s.flush()
    audit.log(s, user_id=user_id, case_id=case.id, action="section3_degree_updated", entity_table="degree",
             entity_id=degree.id, before=before, after=audit.snapshot(degree, FIELDS))


# Remove a degree. The audit log keeps what it contained.
def delete(s: Session, user_id: int, degree_id: int) -> None:
    degree = s.get(Degree, degree_id)
    case = s.get(PromotionCase, degree.case_id)
    if case.status not in EDITABLE:
        raise CaseLocked("This application has been submitted and can no longer be edited.")
    audit.log(s, user_id=user_id, case_id=case.id, action="section3_degree_deleted", entity_table="degree",
             entity_id=degree.id, before=audit.snapshot(degree, FIELDS), after=None)
    s.delete(degree)
