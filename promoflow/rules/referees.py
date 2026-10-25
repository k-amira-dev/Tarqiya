"""Deterministic referee rules (no LLM), used by the Chancellor's Office Agent and the Reviewer Outreach worker.

- conflict of interest: co-authorship, shared institution, used on any case in the last 5 years;
- eligibility: outside the UAE, citations / h-index comparable to or higher than the applicant's, no conflict;
- outreach timing: a reminder every 2 weeks, a replacement after 3 months without a report (spec);
- returned reports: per-referee average grade, the minimum number of reports, and the pass mark
  (PromotionCriteria.min_referee_average_pct: 75% for Associate, 80% for Full).

Plain functions: same inputs, same answer, no database, no network.
"""
"""
FUTURE ADDITION: ORCHID FOR SAMESCHOOL COMPARE
"""
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta

MAX_SHORTLIST = 10                          #max candidates in the shortlist
REUSE_YEARS = 5
REMINDER_EVERY = timedelta(days=14)          # flowchart: "2 weeks no response, send a reminder"
NO_RESPONSE_LIMIT = timedelta(days=90)       # spec: 3 months without a report -> replacement referee
METRIC_RATIO = 0.9                           # "comparable": at least 90% of the applicant's (ASSUMPTION outreach-v1)
UAE = "AE"


def name_key(name: str | None) -> str | None:
    """A rough key for matching author names written differently: "Saleh, Jamal A." / "J. A. Saleh" -> "smith j".
    Used only to spot possible co-authors; a match is a conflict to be checked"""
    if not name:
        return None
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    if "," in text:                                        # "Saleh, Jamal A." / "J. A. Saleh" 
        last, first = text.split(",", 1)
        text = f"{first} {last}"
    parts = [p for p in re.split(r"[^a-z]+", text) if p]
    if not parts:
        return None
    return f"{parts[-1]} {parts[0][0]}" if len(parts) > 1 else parts[0]


def _norm_inst(name: str | None) -> str:
    """"The University of Jordan" and "university-of-jordan" -> "university of jordan"."""
    text = re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()
    return text[4:] if text.startswith("the ") else text
  
#card for possible candidates 
@dataclass(frozen=True)
class Candidate:
    key: str                                   # OpenAlex author id, e.g. "A5023888391"
    name: str | None
    country: str | None
    institution_ids: frozenset[str] = frozenset()
    institution_names: frozenset[str] = frozenset()
    h_index: int | None = None
    citations: int | None = None
    works: int | None = None
    topics: tuple[str, ...] = ()


@dataclass(frozen=True)
class ApplicantSide:
    coauthor_ids: frozenset[str] = frozenset()        # OpenAlex ids of recent co-authors
    coauthor_name_keys: frozenset[str] = frozenset()  # from the dossier's author lists
    institution_ids: frozenset[str] = frozenset()
    institution_names: frozenset[str] = frozenset()
    h_index: int | None = None
    citations: int | None = None

#conflict of interest , note that 5 years rules is subejected to removel soon due to its unnecessity 
@dataclass(frozen=True)
class Conflict:
    coauthor: bool
    same_institution: bool
    used_within_5_years: bool

    @property #confirm not a single conflict was found
    def clear(self) -> bool:
        return not (self.coauthor or self.same_institution or self.used_within_5_years)


def conflicts(c: Candidate, a: ApplicantSide, recently_used: set[str]) -> Conflict:
    coauthor = c.key in a.coauthor_ids or (name_key(c.name) in a.coauthor_name_keys if c.name else False) #is the candidate a coauthor with the applicant? via checking if the coauthor key is found in the applicant coauthors
  #comparison using the instituation ID or name after rewriting it for searching purpose
    same_inst = bool(c.institution_ids & a.institution_ids) or bool(
        {_norm_inst(n) for n in c.institution_names} & {_norm_inst(n) for n in a.institution_names} - {""})
    return Conflict(coauthor, same_inst, c.key in recently_used)

#note: if country is not clear then it's rejected since we can not prove it is not in the UAE
def eligibility(c: Candidate, a: ApplicantSide, conflict: Conflict) -> tuple[bool, list[str]]:
    """(eligible, reasons it is not). Rank (Full Professor) cannot be checked from OpenAlex: a person confirms it."""
    reasons = []
     if not conflict.clear:
        if conflict.coauthor:
            reasons.append("co-authored with the applicant")
        if conflict.same_institution:
            reasons.append("shares an institution with the applicant")
        if conflict.used_within_5_years:
            reasons.append("was a referee in the last 5 years")
    if not c.country:
        reasons.append("country unknown (must be outside the UAE)")
    elif c.country.upper() == UAE:
        reasons.append("based in the UAE")
    if a.h_index is not None and (c.h_index is None or c.h_index < METRIC_RATIO * a.h_index):
        reasons.append(f"h-index {c.h_index} is below the applicant's {a.h_index}")
    if a.citations is not None and (c.citations is None or c.citations < METRIC_RATIO * a.citations):
        reasons.append(f"{c.citations} citations is below the applicant's {a.citations}")
    return not reasons, reasons
    #if conflict.same_school:
            #reasons.append("studied or worked at a university where the applicant studied")#

def reachable(email: str | None) -> bool:
    """Can this referee be contacted? Yes if there is an email address, no if there is not. OpenAlex never gives
    emails, so a new candidate is unreachable until the Chancellor's office enters one."""
    text = (email or "").strip()
    return "@" in text and not text.startswith("@") and not text.endswith("@")
 
#HIGHLY UNLIKELY TO BE APPLIED DUE TO THE NATURE OF THE PROJECT WHICH IS AGENTIC: 
#iff llm is not reachable then we use hardcoded rules
def topic_overlap(candidate_topics: tuple[str, ...] | list[str], applicant_terms: list[str]) -> float:
    """Fallback match score (0-1) when no language model is available: the share of the applicant's words found in
    the candidate's topics."""
    words = {w for t in applicant_terms for w in re.findall(r"[a-z]{4,}", (t or "").lower())}
    if not words:
        return 0.0
    theirs = {w for t in candidate_topics for w in re.findall(r"[a-z]{4,}", (t or "").lower())}
    return round(len(words & theirs) / len(words), 3)
  
#reachability
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.IGNORECASE)
 
 
def reachable(email: str | None) -> bool:
    """Yes only if we hold a well-formed email address for the referee. Without one nobody can be invited, so the
    outreach worker blocks the invitation and asks a person to find the address."""
    return bool(email and _EMAIL.match(email.strip()))
 
 
def contact_search_links(name: str | None, institution: str | None) -> dict[str, str]:
    """Ready-made search links for the person who looks up a referee's email by hand. Google Scholar and LinkedIn
    cannot be searched automatically (no public API; scraping breaks their terms), so these are for a human."""
    if not name:
        return {}
    q = quote_plus(" ".join(x for x in (name, institution) if x))
    return {"google_scholar": f"https://scholar.google.com/scholar?q={q}",
            "linkedin": f"https://www.linkedin.com/search/results/people/?keywords={q}",
            "web": f"https://www.google.com/search?q={q}+email"}
 
 
# ---- outreach timing -----------------------------------------------------------------------------------------------

REMIND = "remind"
REPLACE = "replace


def next_action(waiting: bool, invited_at: datetime, last_reminder_at: datetime | None, now: datetime) -> str | None:
    """What to do today for one contacted referee. `waiting` = invited/reminded/accepted with no report yet."""
    if not waiting:
        return None
    if now - invited_at >= NO_RESPONSE_LIMIT:
        return REPLACE #with another candidate
    if now - (last_reminder_at or invited_at) >= REMINDER_EVERY:
        return REMIND
    return None


# ---- returned reports ----------------------------------------------------------------------------------------------

@dataclass
class RefereeOutcome:
    report_averages: dict[int, float] = field(default_factory=dict)   # report id -> mean of its paper grades
    overall_average: float | None = None
    reports: int = 0
    enough_reports: bool = False
    passed: bool | None = None            # None until the minimum number of reports is in


def referee_outcome(grades_by_report: dict[int, list[float]], min_reports: int, min_average_pct: float
                    ) -> RefereeOutcome:
    out = RefereeOutcome()
    exact = {rid: sum(g) / len(g) for rid, g in grades_by_report.items() if g}
    out.report_averages = {rid: round(v, 2) for rid, v in exact.items()}   # rounded for display only
    out.reports = len(exact)
    out.enough_reports = out.reports >= min_reports
    exact_overall = sum(exact.values()) / out.reports if exact else None
    if exact_overall is not None:
        out.overall_average = round(exact_overall, 2)                      # rounded for display only
    if out.enough_reports:
        out.passed = exact_overall >= min_average_pct                      # the decision uses the exact value
    return out
