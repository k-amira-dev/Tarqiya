"""Section 11 – Review & Submit (spec chapter 13).

Completeness here is a lightweight presence check per section (required file/field present, at least one
entry where the spec calls the section required) — not the full Eligibility Checker or Research/Teaching/
Service Agent logic, which don't exist yet. The research snapshot below is the same kind of preview: real
counts from what's entered, compared against the policy's thresholds, but without the caps and cross-checks
the Research Agent will eventually apply.
"""
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from promoflow.db.enums import AuthorRole, CaseStatus, DocumentKind, JournalClass, PublicationStatus
from promoflow.db.models import (
    CaseDocument, CaseStatusHistory, CommitteeMembership, CourseTaught, Degree, Publication, PromotionCriteria,
    RankHistory, ScopusEvidence,
)
from promoflow.dossier import audit, section3, section4, section9, section10
from promoflow.dossier.section0 import EDITABLE, CaseLocked, active_case, current_policy
from promoflow.dossier.section5 import papers as papers_mod
from promoflow.dossier.section6 import courses as courses_mod
from promoflow.rules.eligibility import Check, Criteria, next_submission_window, section0_checks


# One row of the completeness checklist: a section, whether it is complete, and a note saying what is missing.
@dataclass(frozen=True)
class SectionStatus:
    code: str
    title: str
    complete: bool
    note: str


# The research counts shown next to the policy minimums, so the applicant sees roughly where they stand BEFORE
# submitting.
@dataclass(frozen=True)
class ResearchSnapshot:
    total_papers: int
    sole_or_main: int
    published: int
    at_institution: int
    class_a_sole_or_main: int
    min_total_publications: int
    min_sole_main_author: int
    min_published: int
    min_at_institution: int
    min_class_a_main_author: int


# Everything the Review & Submit page needs, gathered by load().
@dataclass(frozen=True)
class Section11Context:
    case_id: int | None
    status: CaseStatus | None
    sections: list[SectionStatus]
    completed_count: int
    eligibility_checks: list[Check]
    research: ResearchSnapshot | None
    window_open: bool
    window_label: str
    can_submit: bool


# Simple counts from Section 5 compared with the thresholds. It is only a preview: the real checks (caps,
# classification, cross-checks) are the Research Agent's job.
def _research_snapshot(papers: list[Publication], classes: dict, criteria: PromotionCriteria) -> ResearchSnapshot:
    sole_or_main = sum(1 for p in papers if p.applicant_role in (AuthorRole.SOLE, AuthorRole.MAIN))
    published = sum(1 for p in papers if p.status == PublicationStatus.PUBLISHED)
    at_institution = sum(1 for p in papers if p.at_this_university)
    class_a_sole_or_main = sum(1 for p in papers if p.applicant_role in (AuthorRole.SOLE, AuthorRole.MAIN)
                              and classes[p.id].journal_class == JournalClass.CLASS_A)
    return ResearchSnapshot(
        len(papers), sole_or_main, published, at_institution, class_a_sole_or_main,
        criteria.min_total_publications, criteria.min_sole_main_author, criteria.min_published,
        criteria.min_at_institution, criteria.min_class_a_main_author,
    )


# The message to show when the degrees section is incomplete (none entered, or no doctorate).
def _degrees_note(levels: list) -> str:
    if not levels:
        return "No degrees entered."
    if not any(level in section3.DOCTORATE_LEVELS for level in levels):
        return "At least one PhD/doctorate degree is required."
    return ""


# Everything the page shows, in about ten queries: which sections are complete, the preliminary eligibility checks,
# the research counts and whether Submit is allowed.
def load(s: Session, user_id: int, today: date) -> Section11Context:
    """About ten queries in total: this page only needs presence checks and counts, not every entry in full."""
    case = active_case(s, user_id)
    if case is None:
        return Section11Context(None, None, [], 0, [], None, False, "", False)

    section_docs = {(code, kind, slot) for code, kind, slot in s.execute(
        select(CaseDocument.section_code, CaseDocument.kind, CaseDocument.slot).where(
            CaseDocument.case_id == case.id, CaseDocument.superseded_by_id.is_(None),
            CaseDocument.entity_table.is_(None)))}
    levels = list(s.scalars(select(Degree.level).where(Degree.case_id == case.id)))
    ranks = list(s.scalars(select(RankHistory).where(RankHistory.case_id == case.id)))
    has_scopus, course_count, committee_count = s.execute(select(
        select(func.count()).select_from(ScopusEvidence).where(ScopusEvidence.case_id == case.id).scalar_subquery(),
        select(func.count()).select_from(CourseTaught).where(CourseTaught.case_id == case.id).scalar_subquery(),
        select(func.count()).select_from(CommitteeMembership).where(CommitteeMembership.case_id == case.id)
        .scalar_subquery(),
    )).one()
    submitted_papers = list(s.scalars(select(Publication).where(Publication.case_id == case.id,
                                                                Publication.submit_for_promotion.is_(True))))
    classes = papers_mod.classify_many(s, submitted_papers)
    policy = current_policy(s, today)
    criteria_row = s.scalar(select(PromotionCriteria).where(PromotionCriteria.policy_version_id == policy.id,
                                                            PromotionCriteria.track == case.track))

    # True if the required file exists in that section, kind and slot.
    def has(code: str, kind: DocumentKind, slot: str | None = None) -> bool:
        return (code, kind, slot) in section_docs

    # One entry per section, each with its own definition of 'complete'. Completeness is a presence check only:
    # whether the content is right is for the agents to judge.
    sections = [
        SectionStatus("0", "Applicant Details & Promotion Track",
                     bool(case.track and case.specialization and case.appointment_date and case.rank_on_appointment
                          and case.current_rank_date and case.scopus_author_id), ""),
        SectionStatus("1", "Application Form",
                     bool(case.decl_not_from_thesis and case.decl_after_current_rank
                          and has("1", DocumentKind.SIGNED_FORM)),
                     "" if has("1", DocumentKind.SIGNED_FORM) else "Signed application form missing."),
        SectionStatus("2", "Curriculum Vitae", bool(case.cv_last_updated and has("2", DocumentKind.CV)),
                     "" if has("2", DocumentKind.CV) else "CV missing."),
        SectionStatus("3", "Degrees & Equivalency",
                     bool(levels) and any(level in section3.DOCTORATE_LEVELS for level in levels),
                     _degrees_note(levels)),
        SectionStatus("4", "Ranks & Experience",
                     bool(ranks) and not section4.rank_entry_checks(ranks, case.current_rank),
                     "" if ranks else "No rank history entered."),
        SectionStatus("5", "Research", bool(has_scopus) and bool(submitted_papers),
                     "" if has_scopus else "Scopus evidence (5F) missing."),
        SectionStatus("6", "Teaching & Academic Advising",
                     bool(course_count) and has("6A", DocumentKind.EVIDENCE, courses_mod.REPORT_SLOT),
                     "" if has("6A", DocumentKind.EVIDENCE, courses_mod.REPORT_SLOT)
                     else "Registrar teaching-load report missing."),
        SectionStatus("7", "University & Community Service", bool(committee_count),
                     "" if committee_count else "At least one committee membership is required."),
        SectionStatus("8", "Recommendation Letters (optional)", True, ""),
        SectionStatus("9", "Conditions Form",
                     bool(case.conditions_signed_date and has("9", DocumentKind.SIGNED_FORM, section9.FORM_SLOT)),
                     "" if has("9", DocumentKind.SIGNED_FORM, section9.FORM_SLOT)
                     else "Signed Conditions Form missing."),
        SectionStatus("10", "Cover Letter",
                     bool(case.cover_letter_signed_date
                          and has("10", DocumentKind.SIGNED_FORM, section10.LETTER_SLOT)),
                     "" if has("10", DocumentKind.SIGNED_FORM, section10.LETTER_SLOT)
                     else "Signed cover letter missing."),
    ]
    completed_count = sum(1 for row in sections if row.complete)

    eligibility_criteria = None if criteria_row is None else Criteria(
        criteria_row.min_years_in_rank, criteria_row.min_years_at_institution, criteria_row.early_application_months,
        criteria_row.exceptional_min_years, criteria_row.reapply_min_years, criteria_row.reapply_new_publications,
        criteria_row.reapply_new_class_a, criteria_row.reapply_new_main_author)
    checks = section0_checks(
        track=case.track, current_rank_date=case.current_rank_date, appointment_date=case.appointment_date,
        early_application=case.early_application, exceptional_case=case.exceptional_case,
        previously_rejected=case.previously_rejected, rejection_date=case.rejection_date,
        criteria=eligibility_criteria, today=today,
    )
    window = next_submission_window(today)
    research = _research_snapshot(submitted_papers, classes, criteria_row) if criteria_row else None
    # Submit is allowed only while the case is editable, a submission window is open and every section is complete.
    can_submit = (case.status in EDITABLE and window.open_now and completed_count == len(sections))

    return Section11Context(
        case.id, case.status, sections, completed_count, checks, research, window.open_now,
        f"{window.start:%d}–{window.end:%d %b %Y}" + ("" if window.open_now else " (not open yet)"),
        can_submit,
    )


# The Submit button. It locks the dossier by changing the status to 'submitted', records who and when, and leaves an
# audit entry. The page then hands the case to the agents (review_service.start_review).
def submit(s: Session, user_id: int, today: date) -> None:
    case = active_case(s, user_id)
    if case is None:
        raise CaseLocked("Save Section 0 first to start your application.")
    if case.status not in EDITABLE:
        raise CaseLocked("This application has already been submitted.")
    window = next_submission_window(today)
    if not window.open_now:
        raise CaseLocked("Submissions are only accepted in the first week of January, April or October.")

    # Do the actual submission: new status, timestamp, history row, audit entry.
    previous_status = case.status
    case.status = CaseStatus.SUBMITTED
    case.submitted_at = datetime.now(timezone.utc)
    case.updated_at = datetime.now(timezone.utc)
    s.add(CaseStatusHistory(case_id=case.id, from_status=previous_status, to_status=CaseStatus.SUBMITTED,
                            changed_by=user_id, note="Submitted by applicant"))
    s.flush()
    audit.log(s, user_id=user_id, case_id=case.id, action="case_submitted", entity_table="promotion_case",
             entity_id=case.id, before={"status": previous_status.value}, after={"status": case.status.value})
