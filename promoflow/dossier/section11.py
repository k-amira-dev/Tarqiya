"""Section 11 – Review & Submit (spec chapter 13).

Completeness here is a lightweight presence check per section (required file/field present, at least one
entry where the spec calls the section required) — not the full Eligibility Checker or Research/Teaching/
Service Agent logic, which don't exist yet. The research snapshot below is the same kind of preview: real
counts from what's entered, compared against the policy's thresholds, but without the caps and cross-checks
the Research Agent will eventually apply.
"""
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.db.enums import AuthorRole, CaseStatus, JournalClass, PublicationStatus
from promoflow.db.models import CaseStatusHistory, PromotionCase, PromotionCriteria
from promoflow.dossier import audit
from promoflow.dossier import section0, section1, section2, section3, section4, section5, section6, section7
from promoflow.dossier import section9, section10
from promoflow.dossier.section0 import EDITABLE, CaseLocked, active_case, current_policy
from promoflow.rules.eligibility import Check, next_submission_window, section0_checks


@dataclass(frozen=True)
class SectionStatus:
    code: str
    title: str
    complete: bool
    note: str


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


def _research_snapshot(s: Session, case: PromotionCase, today: date) -> ResearchSnapshot | None:
    policy = current_policy(s, today)
    criteria = s.scalar(select(PromotionCriteria).where(PromotionCriteria.policy_version_id == policy.id,
                                                        PromotionCriteria.track == case.track))
    if criteria is None:
        return None
    paper_rows = [row for row in section5.papers.load(s, case.id) if row.publication.submit_for_promotion]
    papers = [row.publication for row in paper_rows]
    class_by_id = {row.publication.id: row.classification.journal_class for row in paper_rows}
    sole_or_main = sum(1 for p in papers if p.applicant_role in (AuthorRole.SOLE, AuthorRole.MAIN))
    published = sum(1 for p in papers if p.status == PublicationStatus.PUBLISHED)
    at_institution = sum(1 for p in papers if p.at_this_university)
    class_a_sole_or_main = sum(1 for p in papers if p.applicant_role in (AuthorRole.SOLE, AuthorRole.MAIN)
                              and class_by_id.get(p.id) == JournalClass.CLASS_A)
    return ResearchSnapshot(
        len(papers), sole_or_main, published, at_institution, class_a_sole_or_main,
        criteria.min_total_publications, criteria.min_sole_main_author, criteria.min_published,
        criteria.min_at_institution, criteria.min_class_a_main_author,
    )


def _degrees_note(degrees: list) -> str:
    if not degrees:
        return "No degrees entered."
    if not section3.has_doctorate(degrees):
        return "At least one PhD/doctorate degree is required."
    return ""


def load(s: Session, user_id: int, today: date) -> Section11Context:
    case = active_case(s, user_id)
    if case is None:
        return Section11Context(None, None, [], 0, [], None, False, "", False)

    s1 = section1.load(s, user_id, today)
    s2 = section2.load(s, user_id, today)
    s3 = section3.load(s, user_id, today)
    s4 = section4.load(s, user_id, today)
    s5 = section5.load(s, user_id, today)
    s6 = section6.load(s, user_id)
    s7 = section7.load(s, user_id)
    s9 = section9.load(s, user_id)
    s10 = section10.load(s, user_id)

    sections = [
        SectionStatus("0", "Applicant Details & Promotion Track",
                     bool(case.track and case.specialization and case.appointment_date and case.rank_on_appointment
                          and case.current_rank_date and case.scopus_author_id), ""),
        SectionStatus("1", "Application Form",
                     bool(case.decl_not_from_thesis and case.decl_after_current_rank and s1.signed_document),
                     "" if s1.signed_document else "Signed application form missing."),
        SectionStatus("2", "Curriculum Vitae", bool(case.cv_last_updated and s2.cv_document),
                     "" if s2.cv_document else "CV missing."),
        SectionStatus("3", "Degrees & Equivalency", bool(s3.degrees) and section3.has_doctorate(s3.degrees),
                     _degrees_note(s3.degrees)),
        SectionStatus("4", "Ranks & Experience", bool(s4.ranks) and not section4.section_checks(s4.ranks, s4.current_rank),
                     "" if s4.ranks else "No rank history entered."),
        SectionStatus("5", "Research", bool(s5.scopus.evidence) and any(row.publication.submit_for_promotion
                                                                       for row in s5.papers),
                     "" if s5.scopus.evidence else "Scopus evidence (5F) missing."),
        SectionStatus("6", "Teaching & Academic Advising", bool(s6.courses) and s6.registrar_report is not None,
                     "" if s6.registrar_report else "Registrar teaching-load report missing."),
        SectionStatus("7", "University & Community Service", bool(s7.committees),
                     "" if s7.committees else "At least one committee membership is required."),
        SectionStatus("8", "Recommendation Letters (optional)", True, ""),
        SectionStatus("9", "Conditions Form", bool(case.conditions_signed_date and s9.document),
                     "" if s9.document else "Signed Conditions Form missing."),
        SectionStatus("10", "Cover Letter", bool(case.cover_letter_signed_date and s10.document),
                     "" if s10.document else "Signed cover letter missing."),
    ]
    completed_count = sum(1 for row in sections if row.complete)

    checks = section0_checks(
        track=case.track, current_rank_date=case.current_rank_date, appointment_date=case.appointment_date,
        early_application=case.early_application, exceptional_case=case.exceptional_case,
        previously_rejected=case.previously_rejected, rejection_date=case.rejection_date,
        criteria=section0.load(s, user_id, today).criteria.get(case.track), today=today,
    )
    window = next_submission_window(today)
    research = _research_snapshot(s, case, today)
    can_submit = (case.status in EDITABLE and window.open_now and completed_count == len(sections))

    return Section11Context(
        case.id, case.status, sections, completed_count, checks, research, window.open_now,
        f"{window.start:%d}–{window.end:%d %b %Y}" + ("" if window.open_now else " (not open yet)"),
        can_submit,
    )


def submit(s: Session, user_id: int, today: date) -> None:
    case = active_case(s, user_id)
    if case is None:
        raise CaseLocked("Save Section 0 first to start your application.")
    if case.status not in EDITABLE:
        raise CaseLocked("This application has already been submitted.")
    window = next_submission_window(today)
    if not window.open_now:
        raise CaseLocked("Submissions are only accepted in the first week of January, April or October.")

    previous_status = case.status
    case.status = CaseStatus.SUBMITTED
    case.submitted_at = datetime.now(timezone.utc)
    case.updated_at = datetime.now(timezone.utc)
    s.add(CaseStatusHistory(case_id=case.id, from_status=previous_status, to_status=CaseStatus.SUBMITTED,
                            changed_by=user_id, note="Submitted by applicant"))
    s.flush()
    audit.log(s, user_id=user_id, case_id=case.id, action="case_submitted", entity_table="promotion_case",
             entity_id=case.id, before={"status": previous_status.value}, after={"status": case.status.value})
