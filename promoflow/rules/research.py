"""Deterministic Research Agent rules that don't need an LLM (spec §9).

- journal classification (Class A / B / not counted) and the ISBN checksum (already used by Section 5);
- which papers count, and with which credit (thesis, current-rank date, journal class, supervision rule + its cap);
- the five publication counts compared with the PromotionCriteria minimums;
- the caps on books, patents and creative works;
- the cross-check of the applicant's self-reported h-index / citations against a verified record.

These are plain functions: the same inputs always give the same answer, with no database and no language model. That
makes them easy to test and easy to explain to a committee. The Research Agent (workflow/nodes/research.py) reads the
database, turns rows into the small dataclasses below, and calls these functions.
"""
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from promoflow.db.enums import AuthorRole, JournalClass, MainAuthorBasis, PublicationStatus

# Class A needs the journal to be in the top 20% of its category, which is a percentile of 80 or more.
CLASS_A_MIN_PERCENTILE = Decimal("80")


# Decide a journal's class from facts about it. Not in Scopus = not counted; Scopus top-20% AND listed in ISI AND
# has an impact factor = Class A; any other Scopus journal = Class B.
def classify_journal(*, scopus_indexed: bool, sjr_percentile: Decimal | None, isi_listed: bool,
                     has_impact_factor: bool) -> JournalClass:
    """Class A = Scopus top-20% SJR and listed in ISI with an impact factor (spec §5A, policy §4 p.9)."""
    if not scopus_indexed:
        return JournalClass.NOT_COUNTED
    if isi_listed and has_impact_factor and sjr_percentile is not None and sjr_percentile >= CLASS_A_MIN_PERCENTILE:
        return JournalClass.CLASS_A
    return JournalClass.CLASS_B


# An ISBN may contain only digits, hyphens and an X.
_ISBN_CHARS = re.compile(r"^[\dXx-]+$")


# Check an ISBN's built-in check digit, which catches most typing mistakes.
def isbn_is_valid(isbn: str) -> bool:
    """ISBN-10 (MOD 11) or ISBN-13 (EAN-13 MOD 10) checksum, ignoring hyphens."""
    if not _ISBN_CHARS.match(isbn):
        return False
    digits = isbn.replace("-", "").upper()
    if len(digits) == 10:
        if not digits[:-1].isdigit() or digits[-1] not in "0123456789X":
            return False
        # ISBN-10: weight the digits 10, 9, 8 ... 1 (an X counts as 10); the total must divide evenly by 11.
        total = sum((10 - i) * (10 if ch == "X" else int(ch)) for i, ch in enumerate(digits))
        return total % 11 == 0
    if len(digits) == 13:
        if not digits.isdigit():
            return False
        # ISBN-13: weight the digits 1, 3, 1, 3 ...; the total must divide evenly by 10.
        total = sum(int(ch) * (1 if i % 2 == 0 else 3) for i, ch in enumerate(digits))
        return total % 10 == 0
    return False


# Which papers count
# Where a dated item sits relative to the date the applicant obtained the current rank.
AFTER, BEFORE, SAME_MONTH, UNKNOWN = "after", "before", "same_month", "unknown"


def period_status(item_date: date | None, rank_date: date | None) -> str:
    if item_date is None or rank_date is None:
        return UNKNOWN
    if (item_date.year, item_date.month) == (rank_date.year, rank_date.month):
        return SAME_MONTH
    return AFTER if item_date > rank_date else BEFORE


@dataclass(frozen=True)
class PaperFacts:
    """One §5A paper, reduced to the facts the rules need (built from a `publication` row)."""
    id: int
    status: PublicationStatus
    paper_date: date              # issue date if published, acceptance date if accepted
    role: AuthorRole
    main_basis: MainAuthorBasis | None
    with_supervised_student: bool
    at_this_university: bool
    from_thesis: bool
    journal_class: JournalClass
    journal_in_table: bool = True        # False = no ranking on file yet (as opposed to "not Scopus-indexed")


@dataclass
class PaperVerdict:
    """The rule's decision on one paper."""
    id: int
    counted: bool
    journal_class: JournalClass
    credited_main: bool                  # counts as sole/main author
    via_supervision: bool = False        # main-author credit came from the supervision rule
    reasons: list[str] = field(default_factory=list)   # why, in plain words (shown in the report)
    needs_check: str | None = None       # a question for a person; the paper is still counted

#Sole author, or main author for a reason other than supervision, gets main-author credit. Co-written with a supervised student also gets it. Claiming supervision with no student linked gets co-author credit plus a question. .
def classify_papers(papers: list[PaperFacts], rank_date: date | None, max_supervision_papers: int
                    ) -> list[PaperVerdict]:
    """Decide, paper by paper, whether it counts and how it is credited. Papers are processed in id order, so the
    supervision-rule cap always keeps the same papers."""
    verdicts = []
    supervision_used = 0
    for p in sorted(papers, key=lambda x: x.id):
        v = PaperVerdict(id=p.id, counted=True, journal_class=p.journal_class, credited_main=False)
        # 1. Exclusions.
        if p.from_thesis:
            v.counted = False
            v.reasons.append("derived from the applicant's thesis, so it does not count")
        if p.journal_class == JournalClass.NOT_COUNTED:
            v.counted = False
            v.reasons.append("the journal has no ranking on file yet" if not p.journal_in_table
                             else "the journal is not Scopus-indexed")
        period = period_status(p.paper_date, rank_date)
        if period == BEFORE:
            v.counted = False
            v.reasons.append("dated before the current rank was obtained")
        elif period == SAME_MONTH:
            v.needs_check = "dated in the same month as the current rank; confirm it came after the rank date"
        elif period == UNKNOWN:
            v.needs_check = "the paper date or the current-rank date is missing; confirm it came after the rank"

        # 2. Author credit.
        own_main = p.role == AuthorRole.SOLE or (p.role == AuthorRole.MAIN
                                                  and p.main_basis != MainAuthorBasis.SUPERVISION_RULE)
        if own_main:
            v.credited_main = True
            v.reasons.append(f"credited as {p.role.value} author")
        elif p.with_supervised_student:
            # Co-authored with a student the applicant supervised: counts as main author whatever the order,
            # up to the cap. Only papers that otherwise count use up the cap.
            if v.counted and supervision_used >= max_supervision_papers:
                v.reasons.append(f"supervision rule cap of {max_supervision_papers} already used: credited as "
                                 "co-author")
            else:
                v.credited_main = True
                v.via_supervision = True
                if v.counted:
                    supervision_used += 1
                v.reasons.append("credited as main author under the supervision rule")
        elif p.main_basis == MainAuthorBasis.SUPERVISION_RULE:
            v.reasons.append("main author claimed under the supervision rule, but no supervised student is linked: "
                             "credited as co-author")
            v.needs_check = v.needs_check or "supervision-rule claim without a linked supervised student"
        else:
            v.reasons.append("credited as co-author")
        verdicts.append(v)
    return verdicts


# Books, patents, creative works (counted towards the total, within caps)
@dataclass(frozen=True)
class OtherItem:
    """A book / chapter, granted patent or approved creative work, reduced to what the caps need."""
    table: str                           # "book", "patent" or "creative_work"
    id: int
    kind: str                            # book: BookItemType value; patent: "patent"; creative: "creative_work"
    item_date: date | None
    eligible: bool                       # granted patent / approved creative work / not from thesis
    main_author: bool = False


@dataclass
class OtherResult:
    counted: list[OtherItem] = field(default_factory=list)
    excluded: list[tuple[OtherItem, str]] = field(default_factory=list)


def apply_caps(items: list[OtherItem], rank_date: date | None, *, per_book_type: dict[str, int],
               max_books_total: int, max_patents: int, max_creative_works: int) -> OtherResult:
    """Keep the items that may count, within the policy caps (p.6). ASSUMPTION research-v1: kept items count towards
    the total-publications minimum only, not towards the main-author, published or Class A minimums."""
    res = OtherResult()
    books = patents = creative = 0
    per_type: dict[str, int] = {}
    for it in sorted(items, key=lambda x: (x.table, x.id)):
        if not it.eligible:
            res.excluded.append((it, "not eligible (patent not granted, work not approved, or from a thesis)"))
            continue
        if period_status(it.item_date, rank_date) == BEFORE:
            res.excluded.append((it, "dated before the current rank was obtained"))
            continue
        if it.table == "book":
            type_cap = per_book_type.get(it.kind)
            if type_cap is not None and per_type.get(it.kind, 0) >= type_cap:
                res.excluded.append((it, f"cap of {type_cap} for {it.kind.replace('_', ' ')} items reached"))
                continue
            if books >= max_books_total:
                res.excluded.append((it, f"cap of {max_books_total} books in total reached"))
                continue
            books += 1
            per_type[it.kind] = per_type.get(it.kind, 0) + 1
        elif it.table == "patent":
            if patents >= max_patents:
                res.excluded.append((it, f"cap of {max_patents} patents reached"))
                continue
            patents += 1
        else:
            if creative >= max_creative_works:
                res.excluded.append((it, f"cap of {max_creative_works} creative works reached"))
                continue
            creative += 1
        res.counted.append(it)
    return res


# The five counts against the minimums
@dataclass(frozen=True)
class Requirement:
    key: str                  # the PromotionCriteria column, e.g. "min_class_a_main_author"
    label: str
    required: int
    actual: int
    ids: tuple[int, ...]      # the publication ids behind the count

    @property
    def passed(self) -> bool:
        return self.actual >= self.required


def requirements(verdicts: list[PaperVerdict], facts: dict[int, PaperFacts], minimums: dict[str, int],
                 extra_for_total: int = 0) -> list[Requirement]:
    """The five numeric checks. `minimums` holds the PromotionCriteria values; `extra_for_total` is the number of
    books / patents / creative works kept by apply_caps()."""
    counted = [v for v in verdicts if v.counted]

    def ids(pred) -> tuple[int, ...]:
        return tuple(v.id for v in counted if pred(v))

    total = ids(lambda v: True)
    main = ids(lambda v: v.credited_main)
    published = ids(lambda v: facts[v.id].status == PublicationStatus.PUBLISHED)
    at_inst = ids(lambda v: facts[v.id].at_this_university)
    class_a_main = ids(lambda v: v.credited_main and v.journal_class == JournalClass.CLASS_A)
    rows = [
        ("min_total_publications", "Total counted publications", total, len(total) + extra_for_total),
        ("min_sole_main_author", "Sole or main-author papers", main, len(main)),
        ("min_published", "Published papers (not only accepted)", published, len(published)),
        ("min_at_institution", "Papers produced at this university", at_inst, len(at_inst)),
        ("min_class_a_main_author", "Class A papers as sole/main author", class_a_main, len(class_a_main)),
    ]
    return [Requirement(key, label, int(minimums[key]), actual, paper_ids) for key, label, paper_ids, actual in rows]


# Self-reported vs verified metrics
H_INDEX_TOLERANCE = 2          # points of h-index difference accepted before flagging (ASSUMPTION research-v1)
CITATION_TOLERANCE = 0.15      # relative citation difference accepted before flagging (ASSUMPTION research-v1)


def metric_differences(reported_h: int | None, reported_citations: int | None,
                       verified_h: int | None, verified_citations: int | None) -> list[str]:
    """Plain-language differences larger than the tolerances. Empty list = consistent (or nothing to compare).
    Only a claim HIGHER than the verified record is reported: claiming less gains the applicant nothing, and OpenAlex
    usually counts more than Scopus, so flagging it would only put honest applicants under suspicion."""
    out = []
    if reported_h is not None and verified_h is not None and reported_h - verified_h > H_INDEX_TOLERANCE:
        out.append(f"h-index reported {reported_h}, higher than the verified {verified_h}")
    if reported_citations is not None and verified_citations is not None:
        base = max(verified_citations, 1)
        if (reported_citations - verified_citations) / base > CITATION_TOLERANCE:
            out.append(f"citations reported {reported_citations}, higher than the verified {verified_citations}")
    return out
