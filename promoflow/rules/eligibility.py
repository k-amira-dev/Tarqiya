"""Deterministic eligibility checks for Section 0 (no LLM). Pure functions: easy to test and to explain.

The applicant sees these as a *preview* while filling in the form; the Eligibility Checker re-runs them on
submission with the full dossier (e.g. rank history from §4).
"""
import re
from dataclasses import dataclass
from datetime import date

from promoflow.db.enums import PromotionTrack, Rank

RANK_ORDER = [Rank.LECTURER, Rank.ASSISTANT_PROFESSOR, Rank.ASSOCIATE_PROFESSOR, Rank.PROFESSOR]
CURRENT_RANK_FOR = {PromotionTrack.TO_ASSOCIATE: Rank.ASSISTANT_PROFESSOR,
                    PromotionTrack.TO_FULL: Rank.ASSOCIATE_PROFESSOR}
TARGET_RANK_FOR = {PromotionTrack.TO_ASSOCIATE: Rank.ASSOCIATE_PROFESSOR, PromotionTrack.TO_FULL: Rank.PROFESSOR}
WINDOW_MONTHS = (1, 4, 10)  # submissions only in the first week of January, April and October
WINDOW_LAST_DAY = 7
MAX_JUSTIFICATION = 3000


@dataclass(frozen=True)
class Criteria:
    min_years_in_rank: int
    min_years_at_institution: int
    early_application_months: int
    exceptional_min_years: int
    reapply_min_years: int
    reapply_new_publications: int
    reapply_new_class_a: int
    reapply_new_main_author: int


@dataclass(frozen=True)
class Check:
    label: str
    status: str  # "ok" | "warn" | "fail" | "info"
    detail: str
    policy_ref: str = ""


@dataclass(frozen=True)
class Window:
    start: date
    end: date
    open_now: bool


def years_between(start: date, end: date) -> float:
    return (end - start).days / 365.25


def next_submission_window(today: date) -> Window:
    for year in (today.year, today.year + 1):
        for month in WINDOW_MONTHS:
            start, end = date(year, month, 1), date(year, month, WINDOW_LAST_DAY)
            if end >= today:
                return Window(start, end, start <= today)
    raise AssertionError("unreachable")


def assumed_submission_date(today: date) -> date:
    """Checks are evaluated on the day the dossier could be submitted: today if a window is open, else its start."""
    w = next_submission_window(today)
    return today if w.open_now else w.start


def section0_checks(*, track: PromotionTrack | None, current_rank_date: date | None, appointment_date: date | None,
                    early_application: bool, exceptional_case: bool, previously_rejected: bool,
                    rejection_date: date | None, criteria: Criteria | None, today: date) -> list[Check]:
    on = assumed_submission_date(today)
    w = next_submission_window(today)
    window = Check(
        "Submission window",
        "info",
        (f"Open now, until {w.end:%d %b %Y}." if w.open_now
         else f"Next window: {w.start:%d}–{w.end:%d %b %Y}. Checks below are calculated for {on:%d %b %Y}."),
        "Conditions §8",
    )
    if track is None or criteria is None:
        return [Check("Promotion track", "info", "Choose your promotion track to see the requirements.")] + [window]

    checks = []
    need = criteria.min_years_in_rank
    if current_rank_date is None:
        checks.append(Check("Time in current rank", "info", "Enter the date you obtained your current rank."))
    else:
        yrs = years_between(current_rank_date, on)
        short_months = (need - yrs) * 12
        if yrs >= need:
            checks.append(Check("Time in current rank", "ok", f"{yrs:.1f} years (minimum {need}).", "p.13–14"))
        elif early_application and short_months <= criteria.early_application_months:
            checks.append(Check("Time in current rank", "ok",
                                f"{yrs:.1f} years: early application, completes {need} years within "
                                f"{criteria.early_application_months} months.", "p.24"))
        elif exceptional_case and yrs >= criteria.exceptional_min_years:
            checks.append(Check("Time in current rank", "warn",
                                f"{yrs:.1f} years: exceptional-case request. The Head of Department decides.", "p.24"))
        elif early_application:
            checks.append(Check("Time in current rank", "fail",
                                f"{yrs:.1f} years: an early application must complete {need} years within "
                                f"{criteria.early_application_months} months of submission.", "p.24"))
        else:
            checks.append(Check("Time in current rank", "fail",
                                f"{yrs:.1f} years; the minimum is {need}. Consider a later window.", "p.13–14"))

    if current_rank_date and appointment_date:
        start = max(current_rank_date, appointment_date)
        yrs_here = years_between(start, on)
        need_here = criteria.min_years_at_institution
        checks.append(Check(
            "Years at this university in current rank",
            "ok" if yrs_here >= need_here else "fail",
            f"{yrs_here:.1f} years (minimum {need_here}). Confirmed later against your rank history (§4).",
            "p.13–14",
        ))

    if previously_rejected:
        if rejection_date is None:
            checks.append(Check("Reapplication", "info", "Enter the date of the rejection decision."))
        else:
            gap = years_between(rejection_date, on)
            ok = gap >= criteria.reapply_min_years
            checks.append(Check(
                "Reapplication",
                "ok" if ok else "fail",
                (f"{gap:.1f} years since the decision (minimum {criteria.reapply_min_years}). You also need "
                 f"{criteria.reapply_new_publications} new publications (≥{criteria.reapply_new_class_a} Class A, "
                 f"≥{criteria.reapply_new_main_author} main-author), checked in §5A."),
                "p.12, p.24",
            ))
    checks.append(window)
    return checks


_ORCID = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")


def orcid_is_valid(orcid: str) -> bool:
    """Format 0000-0000-0000-000X plus the ISO 7064 MOD 11-2 check digit."""
    if not _ORCID.match(orcid):
        return False
    digits = orcid.replace("-", "")
    total = 0
    for ch in digits[:-1]:
        total = (total + int(ch)) * 2
    check = (12 - total % 11) % 11
    return digits[-1] == ("X" if check == 10 else str(check))


def validate_section0(v: dict, today: date) -> list[str]:
    """Blocking errors for saving Section 0. `v` holds the form values (see dossier.section0.FIELDS)."""
    errors = []
    required = {
        "academic_year": "Academic year", "track": "Promotion track", "specialization": "Specialization",
        "fine_specialization": "Fine specialization", "appointment_date": "Date of appointment at the University",
        "rank_on_appointment": "Academic rank on appointment", "current_rank_date": "Date current rank obtained",
        "scopus_author_id": "Scopus Author ID",
    }
    for key, label in required.items():
        if v.get(key) in (None, "", []):
            errors.append(f"{label} is required.")
    for key, label in [("appointment_date", "Date of appointment"), ("current_rank_date", "Date current rank obtained"),
                       ("rejection_date", "Date of the rejection decision")]:
        if v.get(key) and v[key] > today:
            errors.append(f"{label} cannot be in the future.")
    track, appointed_as = v.get("track"), v.get("rank_on_appointment")
    if track and appointed_as and RANK_ORDER.index(appointed_as) > RANK_ORDER.index(CURRENT_RANK_FOR[track]):
        errors.append("Your rank on appointment cannot be higher than your current rank.")
    scopus = (v.get("scopus_author_id") or "").strip()
    if scopus and not (scopus.isdigit() and 5 <= len(scopus) <= 15):
        errors.append("Scopus Author ID should be the number shown on your Scopus profile (digits only).")
    orcid = (v.get("orcid") or "").strip().upper()
    if orcid and not orcid_is_valid(orcid):
        errors.append("ORCID iD is not valid (format 0000-0000-0000-000X; check the last digit).")
    if v.get("early_application") and v.get("exceptional_case"):
        errors.append("Choose either an early application or an exceptional-case request, not both.")
    if v.get("exceptional_case"):
        text = (v.get("exceptional_justification") or "").strip()
        if not text:
            errors.append("Please justify the exceptional-case request.")
        elif len(text) > MAX_JUSTIFICATION:
            errors.append(f"The justification is limited to {MAX_JUSTIFICATION} characters.")
    if v.get("previously_rejected") and not v.get("rejection_date"):
        errors.append("Enter the date of the previous rejection decision.")
    if len(v.get("research_keywords") or []) > 8:
        errors.append("Choose at most 8 research keywords.")
    return errors
