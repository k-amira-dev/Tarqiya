"""Eligibility Checker (rule-based, no LLM). Owner: Amira.

Runs on a submitted case and answers one question: can this dossier go on to the evaluating agents?
- Section 0 rules (time in rank, years at the university, early/exceptional, reapplication) come from
  promoflow/rules/eligibility.py, the same code the applicant's live preview uses.
- Added here: submission window on the actual submission date, rank history (§4) consistent with Section 0,
  a doctorate degree, the Scopus screenshot no older than 30 days, and every required document present.
- "Exceptional research volume" is never decided here: it becomes a needs_human flag for the HoD.
Every failed check produces a fixed guidance message (plus the policy page where the policy gives one).
Verdicts: PASS | NEEDS_HUMAN (still goes on) | INCOMPLETE (something to upload/enter) | FAIL (not eligible).
"""
import math
import re
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.db import session as db_session
from promoflow.db.enums import Component, Confidence, DocumentKind, FlagSeverity, Verdict
from promoflow.db.models import CaseDocument, Degree, PromotionCase, PromotionCriteria, RankHistory, ScopusEvidence
from promoflow.dossier import section3, section4, section9, section10
from promoflow.dossier.section6 import courses as courses_mod
from promoflow.rules.eligibility import (
    Criteria, in_submission_window, section0_checks, years_between,
)
from promoflow.workflow.nodes import stub_result, use_stubs
from promoflow.workflow.persist import save_output
from promoflow.workflow.schemas import AgentOutput, CaseState, CriterionOut, FlagOut


# (section, kind, slot, name shown to the applicant, where to upload it)
REQUIRED_DOCUMENTS = [
    ("1", DocumentKind.SIGNED_FORM, None, "Signed application form", "Section 1"),
    ("2", DocumentKind.CV, None, "Curriculum Vitae", "Section 2"),
    ("6A", DocumentKind.EVIDENCE, courses_mod.REPORT_SLOT, "Registrar teaching-load report", "Section 6A"),
    ("9", DocumentKind.SIGNED_FORM, section9.FORM_SLOT, "Signed Conditions Form", "Section 9"),
    ("10", DocumentKind.SIGNED_FORM, section10.LETTER_SLOT, "Signed cover letter", "Section 10"),
]
SCOPUS_MAX_AGE_DAYS = 30
# A failed check with one of these keys means "something is missing" (INCOMPLETE), not "not eligible" (FAIL).
COMPLETENESS_PREFIXES = ("doc_", "doctorate", "rank_history", "scopus_")


# Turn a label such as "Time in current rank" into a short key, "time_in_current_rank".
def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


# True when the date is the 1st-7th of January, April or October: the only days applications are accepted.
def _in_window(d: date) -> bool:
    return in_submission_window(d)


# The heart of the agent: every eligibility rule, evaluated for one case. It only READS the database; run() below
# saves the result.
def check_case(s: Session, case_id: int, today: date) -> AgentOutput:
    """All the eligibility checks for one case. Reads the database, writes nothing."""
    case = s.get(PromotionCase, case_id)
    if case is None:
        raise ValueError(f"No case with id {case_id}.")
    # `on` is the date the rules are applied on: the day the applicant actually submitted (or today, if not yet
    # submitted).
    on = case.submitted_at.date() if case.submitted_at else today
    # The numbers (minimum years in rank, and so on) come from the database, not from the code, so the policy can
    # change without anyone editing Python.
    crit_row = s.scalar(select(PromotionCriteria).where(
        PromotionCriteria.policy_version_id == case.policy_version_id, PromotionCriteria.track == case.track))
    if crit_row is None:
        return AgentOutput(
            component=Component.ELIGIBILITY, verdict=Verdict.INCOMPLETE, confidence=Confidence.HIGH,
            narrative="No promotion criteria are loaded for this track and policy version.",
            flags=[FlagOut(severity=FlagSeverity.NEEDS_HUMAN, code="criteria_missing",
                           message="No promotion criteria found for this case's policy version. Ask the admin.")])

    # Two lists are filled in as we go: `criteria` = the rows of the report table (one per check); `flags` = the
    # messages for anything that did not pass.
    criteria: list[CriterionOut] = []
    flags: list[FlagOut] = []

    # Helper used by every check below: it records the table row and, when the check did not pass, a flag carrying
    # the guidance message.
    def add(key: str, label: str, passed: bool | None, *, message: str = "", ref: str | None = None,
            required: float | None = None, actual: float | None = None,
            severity: FlagSeverity = FlagSeverity.WARNING, code: str | None = None) -> None:
        criteria.append(CriterionOut(key=key, label=label, required=required, actual=actual, passed=passed,
                                     policy_ref=ref))
        if passed is not True and message:
            text = message + (f" (Policy {ref})" if ref else "")
            flags.append(FlagOut(severity=severity, code=code or f"eligibility_{key}", message=text))

    # 1. Section 0 rules, shared with the applicant's live preview.
    rules = Criteria(crit_row.min_years_in_rank, crit_row.min_years_at_institution, crit_row.early_application_months,
                     crit_row.exceptional_min_years, crit_row.reapply_min_years, crit_row.reapply_new_publications,
                     crit_row.reapply_new_class_a, crit_row.reapply_new_main_author)
    # The Section 0 rules are written once, in rules/eligibility.py, and shared with the applicant's live preview.
    # Each result has a status: ok, warn, fail or info.
    for chk in section0_checks(
            track=case.track, current_rank_date=case.current_rank_date, appointment_date=case.appointment_date,
            early_application=case.early_application, exceptional_case=case.exceptional_case,
            previously_rejected=case.previously_rejected, rejection_date=case.rejection_date, criteria=rules, today=on):
        if chk.status == "info":
            continue
        key = _slug(chk.label)
        required = actual = None
        if key == "time_in_current_rank" and case.current_rank_date:
            # rounded down, so a shortfall never displays as the full minimum (4.997 years is shown as 4.99)
            required = float(rules.min_years_in_rank)
            actual = math.floor(years_between(case.current_rank_date, on) * 100) / 100
        if chk.status == "warn":      # exceptional-case request: the HoD decides, not the system
            add(key, chk.label, None, message=f"{chk.label}: {chk.detail}", ref=chk.policy_ref or None,
                required=required, actual=actual, severity=FlagSeverity.NEEDS_HUMAN, code="exceptional_case")
        else:
            add(key, chk.label, chk.status == "ok", message=f"{chk.label}: {chk.detail}",
                ref=chk.policy_ref or None, required=required, actual=actual)

    # 2. The dossier was submitted inside a window (first week of Jan / Apr / Oct).
    if case.submitted_at:
        add("submission_window", "Submitted inside a submission window", _in_window(on),
            message=f"Submitted on {on:%d %b %Y}. Applications are accepted only in the first week of January, "
                    f"April and October.", ref="Conditions §8")

    # 3. Rank history (§4) agrees with Section 0.
    # The rank history typed in Section 4 must agree with the date typed in Section 0.
    ranks = list(s.scalars(select(RankHistory).where(RankHistory.case_id == case_id)))
    if not ranks:
        add("rank_history", "Rank history entered", False, message="No rank history entered. Complete Section 4A.")
    else:
        problems = section4.rank_entry_checks(ranks, case.current_rank)
        add("rank_history", "Rank history is consistent", not problems,
            message="Rank history problems: " + " ".join(problems))
        current = [r for r in ranks if r.held_to is None]
        if current and case.current_rank_date and current[0].date_obtained != case.current_rank_date:
            add("rank_dates_consistent", "Current rank date matches Section 4", None,
                message=f"Section 0 says the current rank was obtained on {case.current_rank_date:%d %b %Y}, "
                        f"Section 4 says {current[0].date_obtained:%d %b %Y}. The HoD should confirm which is right.",
                severity=FlagSeverity.NEEDS_HUMAN, code="rank_date_mismatch")

    # 4. Doctorate degree.
    levels = list(s.scalars(select(Degree.level).where(Degree.case_id == case_id)))
    add("doctorate_degree", "Doctorate degree entered", any(l in section3.DOCTORATE_LEVELS for l in levels),
        message="At least one PhD/doctorate degree is required. Complete Section 3.")

    # 5. Scopus evidence, not older than 30 days at submission.
    scopus = s.scalar(select(ScopusEvidence).where(ScopusEvidence.case_id == case_id))
    if scopus is None:
        add("scopus_evidence", "Scopus evidence entered", False,
            message="Scopus evidence is missing. Complete Section 5F.")
    else:
        age = (on - scopus.screenshot_date).days
        add("scopus_screenshot_recent", "Scopus screenshot is recent", 0 <= age <= SCOPUS_MAX_AGE_DAYS,
            required=float(SCOPUS_MAX_AGE_DAYS), actual=float(age),
            message=f"The Scopus screenshot is dated {scopus.screenshot_date:%d %b %Y} ({age} days before "
                    f"submission). It must be no more than {SCOPUS_MAX_AGE_DAYS} days old. Replace it in Section 5F.")

    # 6. Required documents present (current version only, not superseded).
    present = {(code, kind, slot) for code, kind, slot in s.execute(
        select(CaseDocument.section_code, CaseDocument.kind, CaseDocument.slot).where(
            CaseDocument.case_id == case_id, CaseDocument.superseded_by_id.is_(None),
            CaseDocument.entity_table.is_(None)))}
    for code, kind, slot, name, where in REQUIRED_DOCUMENTS:
        add(f"doc_{code}{'_' + slot if slot else ''}", f"{name} uploaded", (code, kind, slot) in present,
            message=f"{name} is missing. Upload it in {where}.", code="document_missing")

    # Turn all the checks into ONE verdict. A real rule failing = FAIL (not eligible). Only missing items =
    # INCOMPLETE (the applicant can fix it). Anything needing a person = NEEDS_HUMAN. Otherwise PASS.
    failed = [c for c in criteria if c.passed is False]
    if any(not c.key.startswith(COMPLETENESS_PREFIXES) for c in failed):
        verdict = Verdict.FAIL
    elif failed:
        verdict = Verdict.INCOMPLETE
    elif any(c.passed is None for c in criteria) or any(f.severity == FlagSeverity.NEEDS_HUMAN for f in flags):
        verdict = Verdict.NEEDS_HUMAN
    else:
        verdict = Verdict.PASS

    passed = sum(1 for c in criteria if c.passed is True)
    narrative = f"{passed} of {len(criteria)} eligibility checks passed."
    if failed:
        narrative += " Not met: " + "; ".join(c.label for c in failed) + "."
    return AgentOutput(component=Component.ELIGIBILITY, verdict=verdict, narrative=narrative, criteria=criteria,
                       flags=flags, confidence=Confidence.HIGH)


# The graph calls this. For tests it can return placeholder output; otherwise it reads the case, checks it, saves
# the result and tells the graph whether to carry on (`eligible`).
def run(state: CaseState) -> dict:
    if use_stubs(state):               # tests and demos of the graph's flow only; no database needed
        eligible = bool(state["options"].get("stub_eligible", True))
        update = stub_result(Component.ELIGIBILITY, Verdict.PASS if eligible else Verdict.FAIL)
        update["eligible"] = eligible
        return update
    # session_scope() opens a database session, commits when the block ends and rolls back if there was an error.
    with db_session.session_scope() as s:
        out = check_case(s, state["case_id"], date.today())
        save_output(s, state["case_id"], out)
    return {"results": {"eligibility": out.model_dump(mode="json")},
            "eligible": out.verdict in (Verdict.PASS, Verdict.NEEDS_HUMAN)}
