"""6E – Academic advising (spec §10, Appendix E item 9): one entry per semester, counts only."""
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.db.enums import DocumentKind
from promoflow.db.models import AdvisingSemester, CaseDocument
from promoflow.dossier import audit, documents
from promoflow.dossier.section6.common import CaseLocked, case_for_entity, case_for_new_entry

# The columns of a advising semester that the form edits. add() and update() copy exactly these from the form
# values.
FIELDS = ["academic_year", "semester", "advisees", "meetings_held", "on_warning_at_start", "cleared_warning",
         "improved_gpa", "notes"]
# Name of the file slot that holds the evidence file of a advising semester.
EVIDENCE_SLOT = "evidence"


# A advising semester together with its evidence file, ready for the page to show.
@dataclass(frozen=True)
class AdvisingRow:
    semester: AdvisingSemester
    evidence: CaseDocument | None


# All of this case's advising semesters, each with its evidence file.
def load(s: Session, case_id: int) -> list[AdvisingRow]:
    rows = s.scalars(select(AdvisingSemester).where(AdvisingSemester.case_id == case_id)
                     .order_by(AdvisingSemester.academic_year.desc())).all()
    return [AdvisingRow(a, documents.current(s, case_id, "6E", DocumentKind.EVIDENCE,
                                             entity_table="advising_semester", entity_id=a.id, slot=EVIDENCE_SLOT))
           for a in rows]


# Check one advising semester's form BEFORE saving. Returns a list of messages for the applicant (an empty list
# means valid).
def validate(values: dict, has_evidence: bool, evidence_upload=None) -> list[str]:
    errors = []
    required = {"academic_year": "Academic year", "semester": "Semester", "advisees": "Number of advisees",
               "meetings_held": "Advising meetings held", "on_warning_at_start": "Advisees on academic warning",
               "cleared_warning": "Advisees who cleared the warning", "improved_gpa": "Advisees who improved GPA"}
    for key, label in required.items():
        if values.get(key) in (None, ""):
            errors.append(f"{label} is required.")
    on_warning, cleared, improved = (values.get("on_warning_at_start"), values.get("cleared_warning"),
                                     values.get("improved_gpa"))
    if on_warning is not None and cleared is not None and cleared > on_warning:
        errors.append("Advisees who cleared the warning cannot exceed those on warning at the start.")
    elif on_warning is not None and cleared is not None and improved is not None and improved > on_warning - cleared:
        errors.append("Advisees who improved GPA cannot exceed the remaining warning count.")
    if evidence_upload is None and not has_evidence:
        errors.append("Upload evidence (advisee list and meeting logs, student IDs anonymised).")
    return errors


# Add a advising semester: refuse if the case is locked, create the row, attach the evidence file, and write an
# audit-log entry.
def add(s: Session, user_id: int, values: dict, evidence_upload: tuple[str, bytes]) -> int:
    case = case_for_new_entry(s, user_id)
    a = AdvisingSemester(case_id=case.id, **{f: values.get(f) for f in FIELDS})
    s.add(a)
    s.flush()
    filename, data = evidence_upload
    documents.replace(s, case.id, user_id, "6E", DocumentKind.EVIDENCE, filename, data,
                      entity_table="advising_semester", entity_id=a.id, slot=EVIDENCE_SLOT)
    audit.log(s, user_id=user_id, case_id=case.id, action="section6_advising_added",
             entity_table="advising_semester", entity_id=a.id, before=None, after=audit.snapshot(a, FIELDS))
    return a.id


# Edit a advising semester. A new file replaces the old one (the old one is kept as history); the audit log records
# the values before and after.
def update(s: Session, user_id: int, semester_id: int, values: dict, evidence_upload=None) -> None:
    a = s.get(AdvisingSemester, semester_id)
    case = case_for_entity(s, a.case_id)
    before = audit.snapshot(a, FIELDS)
    for f in FIELDS:
        setattr(a, f, values.get(f))
    if evidence_upload is not None:
        filename, data = evidence_upload
        documents.replace(s, case.id, user_id, "6E", DocumentKind.EVIDENCE, filename, data,
                          entity_table="advising_semester", entity_id=a.id, slot=EVIDENCE_SLOT)
    s.flush()
    audit.log(s, user_id=user_id, case_id=case.id, action="section6_advising_updated",
             entity_table="advising_semester", entity_id=a.id, before=before, after=audit.snapshot(a, FIELDS))


# Delete a advising semester. The audit log keeps what it contained.
def delete(s: Session, user_id: int, semester_id: int) -> None:
    a = s.get(AdvisingSemester, semester_id)
    case = case_for_entity(s, a.case_id)
    audit.log(s, user_id=user_id, case_id=case.id, action="section6_advising_deleted",
             entity_table="advising_semester", entity_id=a.id, before=audit.snapshot(a, FIELDS), after=None)
    s.delete(a)
