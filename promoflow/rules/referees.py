"""Deterministic referee rules (no LLM), used by the Chancellor's Office Agent and the Reviewer Outreach worker.

- conflict of interest: co-authorship, shared institution, used on any case in the last 5 years;
- eligibility: outside the UAE, citations / h-index comparable to or higher than the applicant's, no conflict;
- outreach timing: a reminder every 2 weeks, a replacement after 3 months without a report (spec);
- returned reports: per-referee average grade, the minimum number of reports, and the pass mark
  (PromotionCriteria.min_referee_average_pct: 75% for Associate, 80% for Full).

Plain functions: same inputs, same answer, no database, no network.
"""
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta

MAX_SHORTLIST = 10
REUSE_YEARS = 5
REMINDER_EVERY = timedelta(days=14)          # flowchart: "2 weeks no response, send a reminder"
NO_RESPONSE_LIMIT = timedelta(days=90)       # spec: 3 months without a report -> replacement referee
METRIC_RATIO = 0.9                           # "comparable": at least 90% of the applicant's (ASSUMPTION outreach-v1)
UAE = "AE"


def name_key(name: str | None) -> str | None:
    """A rough key for matching author names written differently: "Smith, John A." / "J. A. Smith" -> "smith j".
    Used only to spot possible co-authors; a match is a conflict to be checked, never proof."""
    if not name:
        return None
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    if "," in text:                                        # "Smith, John" -> "John Smith"
        last, first = text.split(",", 1)
        text = f"{first} {last}"
    parts = [p for p in re.split(r"[^a-z]+", text) if p]
    if not parts:
        return None
    return f"{parts[-1]} {parts[0][0]}" if len(parts) > 1 else parts[0]


def _norm_inst(name: str | None) -> str:
    return re.sub(r"[^a-z]+", " ", (name or "").lower()).strip()


@dataclass(frozen=True)
