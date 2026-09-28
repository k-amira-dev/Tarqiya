"""Section 5 – Academic Research (spec chapter 9). Split into one module per entry type (5A, 5A-2, 5B, ...)
since this is the largest dossier section; `load` bundles them for the UI in one call.
"""
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from promoflow.db.enums import CaseStatus
from promoflow.dossier.section0 import active_case
from promoflow.dossier.section5 import awards, books, classification, conference, creative, funded, papers, patents, scopus


@dataclass(frozen=True)
class Section5Context:
    case_id: int | None
    status: CaseStatus | None
    current_rank_date: date | None
    previously_rejected: bool
    papers: list["papers.PublicationRow"]
    creative_works: list["creative.CreativeWorkRow"]
    books: list["books.BookRow"]
    conference_papers: list["conference.ConferencePaperRow"]
    funded_projects: list["funded.FundedProjectRow"]
    patents: list["patents.PatentRow"]
    awards: list["awards.AwardRow"]
    scopus: "scopus.Section5FContext"


def load(s: Session, user_id: int, today: date) -> Section5Context:
    case = active_case(s, user_id)
    if case is None:
        return Section5Context(None, None, None, False, [], [], [], [], [], [], [], scopus.Section5FContext(None, None))
    return Section5Context(
        case.id, case.status, case.current_rank_date, bool(case.previously_rejected),
        papers.load(s, case.id), creative.load(s, case.id), books.load(s, case.id),
        conference.load(s, case.id), funded.load(s, case.id), patents.load(s, case.id),
        awards.load(s, case.id), scopus.load(s, case.id),
    )
