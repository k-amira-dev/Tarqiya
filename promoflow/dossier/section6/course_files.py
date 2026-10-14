"""6F – Course files & coordination (spec §10, Appendix E item 4)."""
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.db.enums import DocumentKind
from promoflow.db.models import CaseDocument, CourseFile
from promoflow.dossier import audit, documents
from promoflow.dossier.section6.common import CaseLocked, case_for_entity, case_for_new_entry

# The columns of a course file record that the form edits. add() and update() copy exactly these from the form
# values.
FIELDS = ["course_taught_id", "is_coordinator", "kept_in_id", "items"]
# Name of the file slot that holds the evidence file of a course file record.
EVIDENCE_SLOT = "evidence"


# A course file record together with its evidence file, ready for the page to show.
@dataclass(frozen=True)
class CourseFileRow:
    course_file: CourseFile
    evidence: CaseDocument | None


# All of this case's course file records, each with its evidence file.
def load(s: Session, case_id: int) -> list[CourseFileRow]:
    rows = s.scalars(select(CourseFile).where(CourseFile.case_id == case_id)).all()
    return [CourseFileRow(f, documents.current(s, case_id, "6F", DocumentKind.EVIDENCE,
                                               entity_table="course_file", entity_id=f.id, slot=EVIDENCE_SLOT))
           for f in rows]


# Check one course file record's form BEFORE saving. Returns a list of messages for the applicant (an empty list
# means valid).
def validate(values: dict, has_evidence: bool, evidence_upload=None) -> list[str]:
    errors = []
    required = {"course_taught_id": "Course", "kept_in_id": "Course file kept in"}
    for key, label in required.items():
        if values.get(key) in (None, ""):
            errors.append(f"{label} is required.")
    if values.get("is_coordinator") is None:
        errors.append("State whether you are the course coordinator.")
    if not values.get("items"):
        errors.append("Select at least one item included in the course file.")
    if evidence_upload is None and not has_evidence:
        errors.append("Upload the course file export or report.")
    return errors


# Add a course file record: refuse if the case is locked, create the row, attach the evidence file, and write an
# audit-log entry.
def add(s: Session, user_id: int, values: dict, evidence_upload: tuple[str, bytes]) -> int:
    case = case_for_new_entry(s, user_id)
    f = CourseFile(case_id=case.id, **{k: values.get(k) for k in FIELDS})
    s.add(f)
    s.flush()
    filename, data = evidence_upload
    documents.replace(s, case.id, user_id, "6F", DocumentKind.EVIDENCE, filename, data,
                      entity_table="course_file", entity_id=f.id, slot=EVIDENCE_SLOT)
    audit.log(s, user_id=user_id, case_id=case.id, action="section6_course_file_added", entity_table="course_file",
             entity_id=f.id, before=None, after=audit.snapshot(f, FIELDS))
    return f.id


# Edit a course file record. A new file replaces the old one (the old one is kept as history); the audit log records
# the values before and after.
def update(s: Session, user_id: int, course_file_id: int, values: dict, evidence_upload=None) -> None:
    f = s.get(CourseFile, course_file_id)
    case = case_for_entity(s, f.case_id)
    before = audit.snapshot(f, FIELDS)
    for k in FIELDS:
        setattr(f, k, values.get(k))
    if evidence_upload is not None:
        filename, data = evidence_upload
        documents.replace(s, case.id, user_id, "6F", DocumentKind.EVIDENCE, filename, data,
                          entity_table="course_file", entity_id=f.id, slot=EVIDENCE_SLOT)
    s.flush()
    audit.log(s, user_id=user_id, case_id=case.id, action="section6_course_file_updated",
             entity_table="course_file", entity_id=f.id, before=before, after=audit.snapshot(f, FIELDS))


# Delete a course file record. The audit log keeps what it contained.
def delete(s: Session, user_id: int, course_file_id: int) -> None:
    f = s.get(CourseFile, course_file_id)
    case = case_for_entity(s, f.case_id)
    audit.log(s, user_id=user_id, case_id=case.id, action="section6_course_file_deleted",
             entity_table="course_file", entity_id=f.id, before=audit.snapshot(f, FIELDS), after=None)
    s.delete(f)
