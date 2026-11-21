"""Saving entries read from evidence documents (extraction/entry_docs.py) through the sections' own validated add() functions.

Like section6/imports.py: an imported entry is indistinguishable from one typed by hand (locked-case check, validation, audit log, the
document attached as its evidence), entries that already exist are skipped, and only one import per application runs at a time.
"""
import re
from datetime import date
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.db.enums import DocumentKind
from promoflow.db.models import (
    AdministrativePosition, Award, Book, CommitteeMembership, CommunityActivity, ConferencePaper, CourseFile, CourseTaught, CreativeWork, CurriculumContribution, Degree, FundedProject,
    Journal, LookupValue, NonAcademicPosition, Patent, PeerObservation, PolicyContribution, Publication, RankHistory, RecommendationLetter, Supervision,
    TeachingDevelopment, TeachingInnovation, TrainingDelivered, WorkshopDelivered,
)
from promoflow.dossier import documents, section2 as s2, section3 as s3, section4 as s4, section8 as s8, section9 as s9, section10 as s10
from promoflow.dossier.section0 import active_case
from promoflow.dossier.section5 import awards as s5aw, books as s5b, conference as s5c, creative as s5cr, funded as s5d, papers as s5p, patents as s5g, scopus as s5sc
from promoflow.dossier.section5.common import case_for_new_entry as case5
from promoflow.dossier.section6 import course_files as s6f, curriculum as s6d, innovation as s6g, peer_observations as s6b
from promoflow.dossier.section7 import policy_contributions as s7a5
from promoflow.dossier.section6 import development as s6i
from promoflow.dossier.section6 import supervision as s6h
from promoflow.dossier.section6.common import case_for_new_entry as case6
from promoflow.dossier.section6.imports import ImportReport, _one_import_at_a_time
from promoflow.dossier.section7 import admin_positions as s7a2
from promoflow.dossier.section7 import committees as s7a1
from promoflow.dossier.section7 import community as s7b
from promoflow.dossier.section7 import trainings as s7a4
from promoflow.dossier.section7 import workshops as s7a3
from promoflow.dossier.section7.common import case_for_new_entry as case7
from promoflow.extraction.entry_docs import Ctx, KINDS


def load_ctx(s: Session, applicant_name: str = "", user_id: int | None = None) -> Ctx:
    """What the builders need besides the document: the dropdown lists (code -> database id and code -> label), the journal table, and, for the
    applicant, their Section 6A courses and whether the application follows a rejected one."""
    from promoflow.extraction.entry_docs_more import norm_name

    ctx = Ctx(applicant_name=applicant_name)
    for row in s.scalars(select(LookupValue)):
        ctx.ids.setdefault(row.list_code, {})[row.code] = row.id
        ctx.labels.setdefault(row.list_code, {})[row.code] = row.label_en
    for j in s.scalars(select(Journal)):
        ctx.journals.setdefault(norm_name(j.title), (j.issn or j.eissn, j.publisher))
    case = active_case(s, user_id) if user_id else None
    if case is not None:
        ctx.previously_rejected = bool(case.previously_rejected)
        ctx.courses = [SimpleNamespace(id=c.id, course_code=c.course_code, academic_year=c.academic_year, semester=getattr(c.semester, "value", c.semester),
                                       role=getattr(c.role, "value", c.role))
                       for c in s.scalars(select(CourseTaught).where(CourseTaught.case_id == case.id).order_by(CourseTaught.id))]
    return ctx


def _low(x) -> str:
    return (x or "").strip().lower()


def _paper_validate(accepted: bool):
    def check(v, up):
        return s5p.validate(v, date.today(), bool(v.get("_prev_rejected")), v.get("_other_authors") or [], False, False,
                            None if accepted else up, up if accepted else None)
    return check


def _paper_add(accepted: bool):
    def add(s, user_id, v, up):
        return s5p.add(s, user_id, v, v.get("_other_authors") or [], None if accepted else up, up if accepted else None)
    return add


# kind -> (model, key of an existing row, key of a draft's final values, case function, validate(values, upload) -> errors, add)
ADDERS = {
    "committee": (CommitteeMembership, lambda r: (_low(r.committee_name), r.date_from), lambda v: (_low(v["committee_name"]), v["date_from"]), case7,
                  lambda v, up: s7a1.validate(v, False, up), s7a1.add),
    "admin": (AdministrativePosition, lambda r: (r.position_id, r.date_from), lambda v: (v["position_id"], v["date_from"]), case7,
              lambda v, up: s7a2.validate(v, False, up), s7a2.add),
    "workshop": (WorkshopDelivered, lambda r: (_low(r.title), r.activity_date), lambda v: (_low(v["title"]), v["activity_date"]), case7,
                 lambda v, up: s7a3.validate(v, date.today(), False, up), s7a3.add),
    "training": (TrainingDelivered, lambda r: (_low(r.title), r.activity_date), lambda v: (_low(v["title"]), v["activity_date"]), case7,
                 lambda v, up: s7a4.validate(v, date.today(), False, up), s7a4.add),
    "community": (CommunityActivity, lambda r: (_low(r.title), r.date_from), lambda v: (_low(v["title"]), v["date_from"]), case7,
                  lambda v, up: s7b.validate(v, False, False, up), s7b.add),
    "development": (TeachingDevelopment, lambda r: (_low(r.title), r.activity_date), lambda v: (_low(v["title"]), v["activity_date"]), case6,
                    lambda v, up: s6i.validate(v, date.today(), False, up), s6i.add),
    "supervision": (Supervision, lambda r: (_low(r.thesis_title), r.start_date), lambda v: (_low(v["thesis_title"]), v["start_date"]), case6,
                    lambda v, up: s6h.validate(v, date.today(), False, up), s6h.add),
    "degree": (Degree, lambda r: (r.level, r.graduation_date), lambda v: (v["level"], v["graduation_date"]), case5,
               lambda v, up: s3.validate_degree(v, False, date.today(), up), s3.add),
    "rank": (RankHistory, lambda r: (r.rank, r.held_from), lambda v: (v["rank"], v["held_from"]), case5,
             lambda v, up: s4.validate_rank(v, date.today()), s4.add_rank),
    "position": (NonAcademicPosition, lambda r: (_low(r.position), r.date_from), lambda v: (_low(v["position"]), v["date_from"]), case5,
                 lambda v, up: s4.validate_position(v), s4.add_position),
    "paper": (Publication, lambda r: (_low(r.title),), lambda v: (_low(v["title"]),), case5, _paper_validate(False), _paper_add(False)),
    "acceptance": (Publication, lambda r: (_low(r.title),), lambda v: (_low(v["title"]),), case5, _paper_validate(True), _paper_add(True)),
    "book": (Book, lambda r: (_low(r.book_title), _low(r.chapter_title)), lambda v: (_low(v["book_title"]), _low(v["chapter_title"])), case5,
             lambda v, up: s5b.validate(v, date.today(), False, up), s5b.add),
    "conference": (ConferencePaper, lambda r: (_low(r.title), r.conference_date), lambda v: (_low(v["title"]), v["conference_date"]), case5,
                   lambda v, up: s5c.validate(v, date.today(), False, up), s5c.add),
    "funded": (FundedProject, lambda r: (_low(r.title), r.start_date), lambda v: (_low(v["title"]), v["start_date"]), case5,
               lambda v, up: s5d.validate(v, date.today(), False, up), s5d.add),
    "award": (Award, lambda r: (_low(r.name), r.year), lambda v: (_low(v["name"]), v["year"]), case5,
              lambda v, up: s5aw.validate(v, date.today()), s5aw.add),
    "patent": (Patent, lambda r: (_low(r.patent_number),), lambda v: (_low(v["patent_number"]),), case5,
               lambda v, up: s5g.validate(v, date.today(), False, up), s5g.add),
    "creative": (CreativeWork, lambda r: (_low(r.title), r.date_from), lambda v: (_low(v["title"]), v["date_from"]), case5,
                 lambda v, up: s5cr.validate(v, date.today(), False, up), s5cr.add),
    "scopus": (None, None, None, case5, lambda v, up: s5sc.validate(v, date.today(), False, up), s5sc.save),
    "peer_observation": (PeerObservation, lambda r: (r.course_taught_id, r.observation_date), lambda v: (v["course_taught_id"], v["observation_date"]), case6,
                         lambda v, up: s6b.validate(v, date.today(), False, up), s6b.add),
    "curriculum": (CurriculumContribution, lambda r: (_low(r.course_or_program), r.approval_date), lambda v: (_low(v["course_or_program"]), v["approval_date"]), case6,
                   lambda v, up: s6d.validate(v, date.today(), bool(v.get("_modified")), False, up), s6d.add),
    "innovation": (TeachingInnovation, lambda r: (r.course_taught_id, _low(r.description)), lambda v: (v["course_taught_id"], _low(v["description"])), case6,
                   lambda v, up: s6g.validate(v, False, up), s6g.add),
    "course_file": (CourseFile, lambda r: (r.course_taught_id,), lambda v: (v["course_taught_id"],), case6,
                    lambda v, up: s6f.validate(v, False, up), s6f.add),
    "policy": (PolicyContribution, lambda r: (_low(r.policy_name), r.activity_date), lambda v: (_low(v["policy_name"]), v["activity_date"]), case7,
               lambda v, up: s7a5.validate(v, date.today(), False, up), s7a5.add),
    "letter": (RecommendationLetter, lambda r: (_low(r.writer_name),), lambda v: (_low(v["writer_name"]),), case5,
               lambda v, up: s8.validate(v, False, up), s8.add),
    "cv": (None, None, None, case5, lambda v, up: s2.validate_section2(v["signed_date"], False, date.today(), up),
           lambda s, uid, v, up: s2.save(s, uid, v["signed_date"], date.today(), up)),
    "conditions": (None, None, None, case5, lambda v, up: s9.validate(v["signed_date"], False, date.today(), up),
                   lambda s, uid, v, up: s9.save(s, uid, v["signed_date"], up)),
    "cover_letter": (None, None, None, case5, lambda v, up: s10.validate(v["signed_date"], False, date.today(), up),
                     lambda s, uid, v, up: s10.save(s, uid, v["signed_date"], up)),
}


def precheck(kind_key: str, drafts: list, ctx: Ctx) -> None:
    """Add the section's own validation messages to every draft that looks complete, so the preview shows them before anything is saved."""
    if kind_key not in ADDERS:                 # kinds saved by their own function (equivalency) have no form validation to run early
        return
    _, _, _, _, validate, _ = ADDERS[kind_key]
    kind = KINDS[kind_key]
    for d in drafts:
        if any(not i.startswith("check:") for i in d.issues):
            continue
        for msg in validate(kind.finalize(d.values, ctx), (d.filename, d.data)):
            if msg not in d.issues:
                d.issues.append(msg)


def _chain_ranks(drafts: list, existing_starts: list) -> None:
    """A rank ends when the next one starts: fill each missing end date from the next start date (among the drafts and the saved ranks)."""
    starts = sorted({*existing_starts, *(d.values["held_from"] for d in drafts if d.values.get("held_from"))})
    for d in drafts:
        if d.values.get("held_from") and d.values.get("held_to") is None:
            later = [x for x in starts if x > d.values["held_from"]]
            if later:
                d.values["held_to"] = later[0]


def _norm(text) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def _add_equivalency(s: Session, user_id: int, drafts: list) -> ImportReport:
    """An equivalency certificate is the second file of a degree already entered (matched by the date of award, else by the institution)."""
    case = case5(s, user_id)
    _one_import_at_a_time(s, case.id)
    degrees = list(s.scalars(select(Degree).where(Degree.case_id == case.id)))
    out = ImportReport()
    for d in drafts:
        v = d.values
        target = next((g for g in degrees if v.get("award_date") and g.graduation_date == v["award_date"]), None)
        if target is None:
            target = next((g for g in degrees if v.get("institution") and (_norm(v["institution"]) in _norm(g.university) or _norm(g.university) in _norm(v["institution"]))), None)
        if target is None:
            out.rejected.append(f"{d.filename}: no degree entered in Section 3 matches it (add the degree first)")
            continue
        if documents.current(s, case.id, "3", DocumentKind.EVIDENCE, entity_table="degree", entity_id=target.id, slot=s3.EQUIVALENCY_SLOT):
            out.skipped_existing += 1
            continue
        values = {f: getattr(target, f) for f in s3.FIELDS}
        values["equivalency_required"] = True
        s3.update(s, user_id, target.id, values, None, (d.filename, d.data))
        out.added += 1
    return out


def add_entries(s: Session, user_id: int, kind_key: str, drafts: list, ctx: Ctx) -> ImportReport:
    """Create one entry per draft (each keeping its own document as evidence). Entries that already exist are skipped."""
    if kind_key == "equivalency":
        return _add_equivalency(s, user_id, drafts)
    model, row_key, draft_key, case_fn, validate, add = ADDERS[kind_key]
    kind = KINDS[kind_key]
    case = case_fn(s, user_id)
    _one_import_at_a_time(s, case.id)
    if kind_key == "rank":
        _chain_ranks(drafts, [r.held_from for r in s.scalars(select(RankHistory).where(RankHistory.case_id == case.id))])
    have = {row_key(r) for r in s.scalars(select(model).where(model.case_id == case.id))} if model else set()
    out = ImportReport()
    for d in drafts:
        values = kind.finalize(d.values, ctx)
        upload = (d.filename, d.data)
        errors = validate(values, upload)
        if errors:
            out.rejected.append(f"{d.filename}: {errors[0]}")
            continue
        key = draft_key(values) if draft_key else None
        if key is not None and key in have:
            out.skipped_existing += 1
            continue
        add(s, user_id, values, upload)
        if key is not None:
            have.add(key)
        out.added += 1
    return out
