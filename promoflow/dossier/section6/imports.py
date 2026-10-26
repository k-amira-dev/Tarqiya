"""Saving what was read from a whole document (extraction/teaching_docs.py) as ordinary Section 6 entries, one call per document type.

Every entry goes through the SAME validation and the SAME add() functions as an entry typed by hand (locked-case check, audit log,
evidence file attached), so an imported entry is indistinguishable from a typed one. Entries that already exist are skipped, so
importing the same report twice never creates duplicates. Each function returns what it did, for the page to report.
"""
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from promoflow.dossier.section6 import advising as s6e
from promoflow.dossier.section6 import courses as s6a
from promoflow.dossier.section6 import satisfaction as s6c
from promoflow.dossier.section6.common import case_for_new_entry
from promoflow.extraction.teaching_docs import norm_code


def _one_import_at_a_time(s: Session, case_id: int) -> None:
    """Make a second import for the same application WAIT until the first has finished (and committed).

    Without this, a double-click starts two imports at once; the second cannot see the first one's rows yet, so it adds every entry again.
    With it, the second import waits, then loads the existing entries and correctly skips them. PostgreSQL only (the test database has one user)."""
    if s.get_bind().dialect.name == "postgresql":
        s.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": 6_000_000_000 + case_id})


@dataclass
class ImportReport:
    added: int = 0
    skipped_existing: int = 0
    rejected: list[str] = None          # rows refused by validation, with the reason

    def __post_init__(self):
        self.rejected = self.rejected or []

    def describe(self, noun: str) -> str:
        text = f"Added {self.added} {noun}."
        if self.skipped_existing:
            text += f" {self.skipped_existing} already existed and were skipped."
        if self.rejected:
            text += f" {len(self.rejected)} could not be added."
        return text


def add_courses(s: Session, user_id: int, drafts: list, report_upload: tuple[str, bytes] | None = None) -> ImportReport:
    """6A: add the courses and keep the report itself as the registrar-report evidence."""
    case = case_for_new_entry(s, user_id)
    _one_import_at_a_time(s, case.id)
    have = {(c.academic_year, c.semester.value, norm_code(c.course_code)) for c in s6a.load(s, case.id)}
    out = ImportReport()
    for d in drafts:
        key = (d.academic_year, d.semester, d.course_code)
        if key in have:
            out.skipped_existing += 1
            continue
        values = {"academic_year": d.academic_year, "semester": d.semester, "course_code": d.course_code, "course_title": d.course_title,
                  "level": d.level, "sections": 1, "students": d.students, "role": "instructor", "delivery_mode": "face_to_face"}
        errors = s6a.validate(values)
        if errors:
            out.rejected.append(f"{d.course_code} {d.academic_year} {d.semester}: {errors[0]}")
            continue
        s6a.add(s, user_id, values)
        have.add(key)
        out.added += 1
    if report_upload is not None:
        s6a.save_registrar_report(s, case.id, user_id, report_upload)
    return out


def add_satisfaction(s: Session, user_id: int, drafts: list, upload: tuple[str, bytes]) -> ImportReport:
    """6C: one entry per course that is matched to a 6A course and has no problems; every entry keeps the report as its evidence."""
    case = case_for_new_entry(s, user_id)
    _one_import_at_a_time(s, case.id)
    have = {r.report.course_taught_id for r in s6c.load(s, case.id)}
    out = ImportReport()
    for d in drafts:
        if d.course_taught_id in have:
            out.skipped_existing += 1
            continue
        values = {"course_taught_id": d.course_taught_id, "respondents": d.respondents, "average_score": d.average_score, "scale_max": d.scale_max}
        errors = s6c.validate(s, values, has_evidence=False, evidence_upload=upload)
        if errors:
            out.rejected.append(f"{d.label}: {errors[0]}")
            continue
        s6c.add(s, user_id, values, upload)
        have.add(d.course_taught_id)
        out.added += 1
    return out


def add_advising(s: Session, user_id: int, drafts: list) -> ImportReport:
    """6E: one entry per semester list, each keeping its own list as the evidence."""
    case = case_for_new_entry(s, user_id)
    _one_import_at_a_time(s, case.id)
    have = {(r.semester.academic_year, r.semester.semester.value) for r in s6e.load(s, case.id)}
    out = ImportReport()
    for d in drafts:
        if (d.academic_year, d.semester) in have:
            out.skipped_existing += 1
            continue
        values = {"academic_year": d.academic_year, "semester": d.semester, "advisees": d.advisees, "meetings_held": d.meetings_held,
                  "on_warning_at_start": d.on_warning_at_start, "cleared_warning": d.cleared_warning, "improved_gpa": d.improved_gpa, "notes": None}
        errors = s6e.validate(values, has_evidence=False, evidence_upload=(d.filename, d.data))
        if errors:
            out.rejected.append(f"{d.label}: {errors[0]}")
            continue
        s6e.add(s, user_id, values, (d.filename, d.data))
        have.add((d.academic_year, d.semester))
        out.added += 1
    return out
