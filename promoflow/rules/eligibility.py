"""Deterministic eligibility checks for Section 0 (no LLM). Pure functions: easy to test and to explain.

The applicant sees these as a *preview* while filling in the form; the Eligibility Checker re-runs them on
submission with the full dossier (e.g. rank history from §4).

HOW TO READ THIS FILE: the functions are "pure": give them dates and flags, get results back, with no database and no
language model. That is why the rules are easy to test (see tests/test_eligibility.py) and easy to explain.
"""
import math
import re
from dataclasses import dataclass
from datetime import date

from promoflow.config import DEV_IGNORE_SUBMISSION_WINDOW
from promoflow.db.enums import PromotionTrack, Rank

# The ranks from lowest to highest. A position in this list lets us compare ranks.
RANK_ORDER = [Rank.LECTURER, Rank.ASSISTANT_PROFESSOR, Rank.ASSOCIATE_PROFESSOR, Rank.PROFESSOR]
# Which rank someone must hold NOW to apply for each track, and which rank they are applying FOR.
CURRENT_RANK_FOR = {PromotionTrack.TO_ASSOCIATE: Rank.ASSISTANT_PROFESSOR,
                    PromotionTrack.TO_FULL: Rank.ASSOCIATE_PROFESSOR}
TARGET_RANK_FOR = {PromotionTrack.TO_ASSOCIATE: Rank.ASSOCIATE_PROFESSOR, PromotionTrack.TO_FULL: Rank.PROFESSOR}
# Applications are only accepted in the first week (days 1-7) of these months: January, April and October.
WINDOW_MONTHS = (1, 4, 10)  # submissions only in the first week of January, April and October
WINDOW_LAST_DAY = 7
MAX_JUSTIFICATION = 3000


# The numeric thresholds for one promotion track. They are read from the database (promotion_criteria table), not
# hard-coded.
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


# The result of one eligibility check: a status (ok / warn / fail / info), a message for the applicant and the
# policy page it comes from.
@dataclass(frozen=True)
class Check:
    label: str
    status: str  # "ok" | "warn" | "fail" | "info"
    detail: str
    policy_ref: str = ""


# A submission window: when it opens, when it closes, and whether it is open today.
@dataclass(frozen=True)
class Window:
    start: date
    end: date
    open_now: bool


def _add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # 29 February in a non-leap year
        return d.replace(year=d.year + years, day=28)


# Time between two dates, in years.
def years_between(start: date, end: date) -> float:
    """Whole calendar years plus the fraction of the current year. Exactly five years after a date is 5.0, whatever
    the leap days in between (dividing days by 365.25 made five full years come out as 4.9993 and fail the minimum)."""
    if end < start:
        return -years_between(end, start)
    whole = end.year - start.year - ((end.month, end.day) < (start.month, start.day))
    anniversary, next_anniversary = _add_years(start, whole), _add_years(start, whole + 1)
    return whole + (end - anniversary).days / (next_anniversary - anniversary).days


def _fmt(years: float) -> str:
    """One decimal, rounded down, so 4.997 years reads '4.9' and never '5.0' next to a minimum of 5."""
    return f"{math.floor(years * 10) / 10:.1f}"


# True when `d` falls on days 1-7 of January, April or October (or always, in development mode).
def in_submission_window(d: date) -> bool:
    return DEV_IGNORE_SUBMISSION_WINDOW or (d.month in WINDOW_MONTHS and d.day <= WINDOW_LAST_DAY)


# The submission window that is open today, or else the next one to open.
def next_submission_window(today: date) -> Window:
    if DEV_IGNORE_SUBMISSION_WINDOW:      # development only: pretend a window is open today (see config.py)
        return Window(today, today, True)
    for year in (today.year, today.year + 1):
        for month in WINDOW_MONTHS:
            start, end = date(year, month, 1), date(year, month, WINDOW_LAST_DAY)
            if end >= today:
                return Window(start, end, start <= today)
    raise AssertionError("unreachable")


# The date to calculate the rules on: today if a window is open, otherwise the day the next one opens (so the
# applicant sees how they will stand then).
def assumed_submission_date(today: date) -> date:
    """Checks are evaluated on the day the dossier could be submitted: today if a window is open, else its start."""
    w = next_submission_window(today)
    return today if w.open_now else w.start


# All the rules that can be checked from Section 0 alone. Returns a list of Check results. The applicant's live
# preview and the Eligibility Checker agent both call this, so they always agree.
def section0_checks(*, track: PromotionTrack | None, current_rank_date: date | None, appointment_date: date | None,
                    early_application: bool, exceptional_case: bool, previously_rejected: bool,
                    rejection_date: date | None, criteria: Criteria | None, today: date) -> list[Check]:
    # `on` = the date the rules are applied on.
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

    # Everything below adds results to this list, one rule at a time.
    checks = []
    need = criteria.min_years_in_rank
    if current_rank_date is None:
        checks.append(Check("Time in current rank", "info", "Enter the date you obtained your current rank."))
    else:
        yrs = years_between(current_rank_date, on)
        short_months = (need - yrs) * 12
        if yrs >= need:
            checks.append(Check("Time in current rank", "ok", f"{_fmt(yrs)} years (minimum {need}).", "p.13–14"))
        elif early_application and short_months <= criteria.early_application_months:
            checks.append(Check("Time in current rank", "ok",
                                f"{_fmt(yrs)} years: early application, completes {need} years within "
                                f"{criteria.early_application_months} months.", "p.24"))
        elif exceptional_case and yrs >= criteria.exceptional_min_years:
            checks.append(Check("Time in current rank", "warn",
                                f"{_fmt(yrs)} years: exceptional-case request. The Head of Department decides.", "p.24"))
        elif early_application:
            checks.append(Check("Time in current rank", "fail",
                                f"{_fmt(yrs)} years: an early application must complete {need} years within "
                                f"{criteria.early_application_months} months of submission.", "p.24"))
        else:
            checks.append(Check("Time in current rank", "fail",
                                f"{_fmt(yrs)} years; the minimum is {need}. Consider a later window.", "p.13–14"))

    if current_rank_date and appointment_date:
        start = max(current_rank_date, appointment_date)
        yrs_here = years_between(start, on)
        need_here = criteria.min_years_at_institution
        checks.append(Check(
            "Years at this university in current rank",
            "ok" if yrs_here >= need_here else "fail",
            f"{_fmt(yrs_here)} years (minimum {need_here}). Confirmed later against your rank history (§4).",
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
                (f"{_fmt(gap)} years since the decision (minimum {criteria.reapply_min_years}). You also need "
                 f"{criteria.reapply_new_publications} new publications (≥{criteria.reapply_new_class_a} Class A, "
                 f"≥{criteria.reapply_new_main_author} main-author), checked in §5A."),
                "p.12, p.24",
            ))
    checks.append(window)
    return checks


# An ORCID iD looks like 0000-0000-0000-000X: four groups of four characters, the last one a digit or X.
_ORCID = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")


# Check an ORCID's shape AND its last (check) character, which catches most typing mistakes.
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


# Blocking errors for Section 0: a list of messages to show the applicant (empty list = valid).
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
