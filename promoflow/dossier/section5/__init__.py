"""Section 5 – Academic Research (spec chapter 9). Split into one module per entry type (5A, 5A-2, 5B, ...)
since this is the largest dossier section; `load` bundles them for the UI in one call.
"""
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from promoflow.db.enums import CaseStatus
from promoflow.db.session import parallel
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
    cid = case.id
    (paper_rows, creative_rows, book_rows, conference_rows, funded_rows, patent_rows, award_rows,
     scopus_ctx) = parallel(
        lambda sess: papers.load(sess, cid), lambda sess: creative.load(sess, cid),
        lambda sess: books.load(sess, cid), lambda sess: conference.load(sess, cid),
        lambda sess: funded.load(sess, cid), lambda sess: patents.load(sess, cid),
        lambda sess: awards.load(sess, cid), lambda sess: scopus.load(sess, cid))
    return Section5Context(case.id, case.status, case.current_rank_date, bool(case.previously_rejected),
                           paper_rows, creative_rows, book_rows, conference_rows, funded_rows, patent_rows,
                           award_rows, scopus_ctx)
