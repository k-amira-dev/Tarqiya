"""5A – Journal paper entry (spec §9). DOI / OpenAlex auto-lookup is not built yet: every field is typed
manually (`lookup_source` stays MANUAL) until that integration lands.
"""
import re
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from promoflow.db.enums import AuthorRole, DocumentKind, JournalClass, LookupSource, MainAuthorBasis, PublicationStatus
from promoflow.db.models import CaseDocument, Journal, JournalRanking, Publication, PublicationAuthor, User
from promoflow.dossier import audit, documents
from promoflow.dossier.section5.common import CaseLocked, case_for_entity, case_for_new_entry
from promoflow.rules.research import classify_journal

FIELDS = [
    "doi", "title", "journal_name", "issn", "publisher", "volume", "issue", "pages", "language",
    "submit_for_promotion", "status", "issue_date", "acceptance_date", "new_since_rejection",
    "author_position", "total_authors", "applicant_role", "main_author_basis", "main_author_explanation",
    "with_supervised_student", "at_this_university", "from_thesis", "impact_factor", "disputes_class",
    "dispute_reason",
]
_ISSN = re.compile(r"^\d{4}-\d{3}[\dX]$")
PAPER_SLOT = "paper"
ACCEPTANCE_SLOT = "acceptance_letter"


@dataclass(frozen=True)
class Classification:
    journal: Journal | None
    ranking: JournalRanking | None
    journal_class: JournalClass


@dataclass(frozen=True)
class PublicationRow:
    publication: Publication
    authors: list[PublicationAuthor]
    classification: Classification
    paper_file: CaseDocument | None
    acceptance_letter: CaseDocument | None


def _lookup_journal(s: Session, issn: str | None) -> Journal | None:
    if not issn:
        return None
    return s.scalar(select(Journal).where((Journal.issn == issn) | (Journal.eissn == issn)))


def _latest_ranking(s: Session, journal_id: int | None) -> JournalRanking | None:
    if journal_id is None:
        return None
    return s.scalar(select(JournalRanking).where(JournalRanking.journal_id == journal_id)
                    .order_by(JournalRanking.year.desc()))


def _classification(journal: Journal | None, ranking: JournalRanking | None, p: Publication) -> Classification:
    if ranking is None:
        return Classification(journal, None, JournalClass.NOT_COUNTED)
    cls = classify_journal(scopus_indexed=ranking.scopus_indexed, sjr_percentile=ranking.sjr_percentile,
                           isi_listed=bool(journal and journal.isi_listed), has_impact_factor=p.impact_factor is not None)
    return Classification(journal, ranking, cls)


def classify(s: Session, p: Publication) -> Classification:
    journal = _lookup_journal(s, p.issn)
    return _classification(journal, _latest_ranking(s, journal.id if journal else None), p)


def classify_many(s: Session, pubs: list[Publication]) -> dict[int, Classification]:
    """Same result as `classify` for each paper, but with two queries in total instead of two per paper."""
    issns = {p.issn for p in pubs if p.issn}
    journals = s.scalars(select(Journal).where(Journal.issn.in_(issns) | Journal.eissn.in_(issns))).all() if issns else []
    by_issn = {}
    for j in journals:
        for key in (j.issn, j.eissn):
            if key:
                by_issn[key] = j
    latest: dict[int, JournalRanking] = {}
    if journals:
        for r in s.scalars(select(JournalRanking).where(JournalRanking.journal_id.in_([j.id for j in journals]))
                           .order_by(JournalRanking.year)):
            latest[r.journal_id] = r  # ascending year, so the last one wins
    out = {}
    for p in pubs:
        journal = by_issn.get(p.issn)
        out[p.id] = _classification(journal, latest.get(journal.id) if journal else None, p)
    return out


def _row(s: Session, p: Publication, classification: Classification) -> PublicationRow:
    return PublicationRow(
        p, list(p.authors), classification,
        documents.current(s, p.case_id, "5A", DocumentKind.EVIDENCE, entity_table="publication", entity_id=p.id,
                          slot=PAPER_SLOT),
        documents.current(s, p.case_id, "5A", DocumentKind.EVIDENCE, entity_table="publication", entity_id=p.id,
                          slot=ACCEPTANCE_SLOT),
    )


def load(s: Session, case_id: int) -> list[PublicationRow]:
    papers = s.scalars(select(Publication).options(selectinload(Publication.authors))
                       .where(Publication.case_id == case_id).order_by(Publication.id)).all()
    classes = classify_many(s, list(papers))
    return [_row(s, p, classes[p.id]) for p in papers]


def _is_empty(v) -> bool:
    return (not v.strip()) if isinstance(v, str) else v is None


def validate(values: dict, today: date, previously_rejected: bool, other_authors: list[str],
            has_paper_file: bool, has_acceptance_letter: bool, paper_upload=None, acceptance_upload=None
            ) -> list[str]:
    errors = []
    required = {"title": "Paper title", "journal_name": "Journal name", "issn": "ISSN / eISSN",
               "publisher": "Publisher", "language": "Language", "status": "Publication status"}
    for key, label in required.items():
        if _is_empty(values.get(key)):
            errors.append(f"{label} is required.")
    issn = (values.get("issn") or "").strip()
    if issn and not _ISSN.match(issn):
        errors.append("ISSN / eISSN should look like NNNN-NNNX.")
    status = values.get("status")
    if status == PublicationStatus.PUBLISHED:
        for key, label in [("volume", "Volume"), ("issue", "Issue"), ("issue_date", "Date of issue")]:
            if not values.get(key):
                errors.append(f"{label} is required for a published paper.")
        if not has_paper_file and paper_upload is None:
            errors.append("Upload the paper (or its first page + DOI page).")
        if values.get("issue_date") and values["issue_date"] > today:
            errors.append("Date of issue cannot be in the future.")
    if status == PublicationStatus.ACCEPTED:
        if not values.get("acceptance_date"):
            errors.append("Acceptance date is required for an accepted paper.")
        elif values["acceptance_date"] > today:
            errors.append("Acceptance date cannot be in the future.")
        if not has_acceptance_letter and acceptance_upload is None:
            errors.append("Upload the acceptance letter.")
    if previously_rejected and values.get("new_since_rejection") is None:
        errors.append("State whether this paper is new since your previous rejected application.")
    total_authors, author_position = values.get("total_authors"), values.get("author_position")
    if not total_authors or total_authors < 1:
        errors.append("Total number of authors is required.")
    elif not author_position or not (1 <= author_position <= total_authors):
        errors.append("Your position in the author list must be between 1 and the total number of authors.")
    elif len(other_authors) != total_authors - 1:
        errors.append(f"Enter the other {total_authors - 1} author name(s), one per line.")
    if values.get("applicant_role") is None:
        errors.append("Applicant's role is required.")
    if values.get("applicant_role") == AuthorRole.MAIN and values.get("main_author_basis") is None:
        errors.append("State the basis for your main-author claim.")
    if values.get("main_author_basis") == MainAuthorBasis.OTHER and not (values.get("main_author_explanation") or "").strip():
        errors.append("Explain the basis for your main-author claim.")
    if values.get("at_this_university") is None:
        errors.append("State whether this was produced while at this university.")
    if values.get("from_thesis") is None:
        errors.append("State whether this is derived from your thesis.")
    return errors


def add(s: Session, user_id: int, values: dict, other_authors: list[str],
       paper_upload: tuple[str, bytes] | None, acceptance_upload: tuple[str, bytes] | None) -> int:
    case = case_for_new_entry(s, user_id)
    journal = _lookup_journal(s, values.get("issn"))
    p = Publication(case_id=case.id, lookup_source=LookupSource.MANUAL,
                    journal_id=journal.id if journal else None, **{f: values.get(f) for f in FIELDS})
    s.add(p)
    s.flush()
    _save_authors(s, p, user_id, values["author_position"], values["total_authors"], other_authors)
    if paper_upload is not None:
        filename, data = paper_upload
        documents.replace(s, case.id, user_id, "5A", DocumentKind.EVIDENCE, filename, data,
                          entity_table="publication", entity_id=p.id, slot=PAPER_SLOT)
    if acceptance_upload is not None:
        filename, data = acceptance_upload
        documents.replace(s, case.id, user_id, "5A", DocumentKind.EVIDENCE, filename, data,
                          entity_table="publication", entity_id=p.id, slot=ACCEPTANCE_SLOT)
    audit.log(s, user_id=user_id, case_id=case.id, action="section5_paper_added", entity_table="publication",
             entity_id=p.id, before=None, after=audit.snapshot(p, FIELDS))
    return p.id


def _save_authors(s: Session, p: Publication, user_id: int, author_position: int, total_authors: int,
                  other_authors: list[str]) -> None:
    for a in list(p.authors):
        s.delete(a)
    s.flush()
    applicant_name = s.get(User, user_id).full_name or "Me"
    others = iter(other_authors)
    for position in range(1, total_authors + 1):
        name = applicant_name if position == author_position else next(others, "")
        s.add(PublicationAuthor(publication_id=p.id, position=position, display_name=name,
                                is_applicant=(position == author_position)))


def update(s: Session, user_id: int, publication_id: int, values: dict, other_authors: list[str],
          paper_upload: tuple[str, bytes] | None = None, acceptance_upload: tuple[str, bytes] | None = None) -> None:
    p = s.get(Publication, publication_id)
    case = case_for_entity(s, p.case_id)
    before = audit.snapshot(p, FIELDS)
    journal = _lookup_journal(s, values.get("issn"))
    p.journal_id = journal.id if journal else None
    for f in FIELDS:
        setattr(p, f, values.get(f))
    _save_authors(s, p, user_id, values["author_position"], values["total_authors"], other_authors)
    if paper_upload is not None:
        filename, data = paper_upload
        documents.replace(s, case.id, user_id, "5A", DocumentKind.EVIDENCE, filename, data,
                          entity_table="publication", entity_id=p.id, slot=PAPER_SLOT)
    if acceptance_upload is not None:
        filename, data = acceptance_upload
        documents.replace(s, case.id, user_id, "5A", DocumentKind.EVIDENCE, filename, data,
                          entity_table="publication", entity_id=p.id, slot=ACCEPTANCE_SLOT)
    s.flush()
    audit.log(s, user_id=user_id, case_id=case.id, action="section5_paper_updated", entity_table="publication",
             entity_id=p.id, before=before, after=audit.snapshot(p, FIELDS))


def delete(s: Session, user_id: int, publication_id: int) -> None:
    p = s.get(Publication, publication_id)
    case = case_for_entity(s, p.case_id)
    audit.log(s, user_id=user_id, case_id=case.id, action="section5_paper_deleted", entity_table="publication",
             entity_id=p.id, before=audit.snapshot(p, FIELDS), after=None)
    s.delete(p)
