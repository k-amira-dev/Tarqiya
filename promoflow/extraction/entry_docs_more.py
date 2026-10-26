"""More "one evidence document = one entry" kinds, for Sections 2 to 8 (degrees, ranks, papers, awards, peer observations ...).

Same idea as entry_docs.py (read what is printed with a small schema, decide the rest with plain rules, keep every value editable in the
preview, save through the section's own validated add()), so these register themselves in `KINDS` there. What is new here:

  * documents that also need the applicant's Section 6A courses (peer observations, teaching innovation): the course is matched by its
    code and term, and left to the applicant when it is not clear;
  * documents that list SEVERAL entries (the curriculum summary): one draft per row;
  * papers: the author list gives the applicant's position and role, and the journal's ISSN and publisher come from the journal table.

A value the document does not show is never guessed: it stays empty with a "problem" (blocking), or, when only a detail is uncertain, a
"check: ..." note that does not stop the entry from being ticked.
"""
import re
from datetime import date

import pycountry
from pydantic import BaseModel, Field

from promoflow.extraction.entry_docs import (
    Col, Ctx, KINDS, Kind, _has, _lookup, _opts, parse_date, to_number,
)
from promoflow.extraction.teaching_docs import norm_code, parse_semester

LEVELS = {"department": "Department", "college": "College", "university": "University"}
YES_NO = {True: "Yes", False: "No"}


# ---- helpers -------------------------------------------------------------------------------------------------------

def country_code(name: str | None) -> str | None:
    """"United Kingdom" -> "GB"; None when the text is not a country."""
    text = (name or "").strip()
    if not text:
        return None
    if _has(text, "emirates", "uae"):
        return "AE"
    for look in (pycountry.countries.lookup, lambda t: pycountry.countries.search_fuzzy(t)[0]):
        try:
            return look(text).alpha_2
        except (LookupError, AttributeError):
            continue
    return None


def _country_options() -> dict:
    from promoflow.countries import COUNTRY_OPTIONS
    return dict(COUNTRY_OPTIONS)


def tidy(text: str | None) -> str:
    """Text printed ALL IN CAPITALS (certificates) in normal capitals; acronyms in brackets and words with digits are kept."""
    t = (text or "").strip()
    if not t or not t.isupper():
        return t
    small = {"of", "and", "on", "in", "for", "the", "at", "to"}
    words = [w if re.search(r"\d|^\(", w) else (w.lower() if i and w.lower() in small else w.title()) for i, w in enumerate(t.split(" "))]
    return " ".join(words)


def norm_name(text: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower().replace("&", "and"))


def _surname(applicant_name: str) -> str:
    words = [w for w in re.split(r"\s+", re.sub(r"^(dr|prof)\.?\s+", "", applicant_name.strip(), flags=re.I)) if w]
    return norm_name(words[-1]) if words else ""


def applicant_position(authors: list[str] | None, ctx: Ctx) -> int | None:
    """1-based position of the applicant in the author list (matched by surname), or None."""
    sur = _surname(ctx.applicant_name)
    if not sur:
        return None
    for i, a in enumerate(authors or [], 1):
        if sur in norm_name(a):
            return i
    return None


def match_course_row(code: str | None, term: str | None, ctx: Ctx) -> int | None:
    """The id of the 6A course with this code (and term, when the code alone is not enough); None if it is not clear."""
    if not code:
        return None
    same = [c for c in ctx.courses if norm_code(c.course_code) == norm_code(code)]
    if len(same) > 1 and term:
        parsed = parse_semester(term)
        if parsed:
            same = [c for c in same if c.academic_year == parsed[0] and c.semester == parsed[1]] or same
    return same[0].id if len(same) == 1 else None


def _course_options(ctx: Ctx) -> dict:
    return {c.id: f"{norm_code(c.course_code)} · {c.semester.title()} {c.academic_year}" for c in ctx.courses}


def _lookup_id(ctx: Ctx, list_code: str, code: str | None):
    return ctx.ids.get(list_code, {}).get(code)


def _year_date(year, month_text: str | None = None) -> tuple[date | None, bool]:
    """A date from a printed year (and month, when there is one). The bool says whether the month was really printed."""
    try:
        y = int(year)
    except (TypeError, ValueError):
        return None, False
    d = parse_date(f"{month_text} {y}") if month_text else None
    return (d or date(y, 1, 1)), d is not None


# ---- Section 3 and 4: degrees, equivalency, ranks, other positions -------------------------------------------------

class DegreeCert(BaseModel):
    degree_name: str | None = Field(description="the degree as printed, for example 'Doctor of Philosophy' or 'Master of Arts'")
    field_of_study: str | None = Field(description="the subject or specialization, for example 'Media and Communication'")
    university: str | None = Field(description="the university that awards the degree")
    country: str | None = Field(description="the country of the university, if printed anywhere on the page")
    conferral_date: str | None = Field(description="the date the degree was conferred or awarded")
    thesis_title: str | None = Field(description="the title of the thesis or dissertation, if printed")


def build_degree(p: DegreeCert, ctx: Ctx):
    issues, name = [], p.degree_name or ""
    level = ("phd" if _has(name, "philosophy", "ph.d", "phd") else "other_doctorate" if _has(name, "doctor") else
             "master" if _has(name, "master", "msc", "m.sc") else "bachelor" if _has(name, "bachelor", "bsc", "b.sc") else None)
    grad = parse_date(p.conferral_date)
    code = country_code(p.country)
    thesis = (p.thesis_title or "").strip() or None
    for missing, text in ((level is None, "degree level not understood"), (not (p.field_of_study or "").strip(), "specialization not found"),
                          (not (p.university or "").strip(), "university not found"), (code is None, "choose the country"),
                          (grad is None, "graduation date not found"),
                          (True, "study period start is not on the certificate: enter it"),
                          (level in ("master", "phd") and not thesis, "thesis title not found")):
        if missing:
            issues.append(text)
    return {"level": level, "specialization": tidy(p.field_of_study), "university": tidy(p.university), "country_code": code,
            "study_from": None, "study_to": grad, "graduation_date": grad, "thesis_title": thesis, "equivalency_required": False}, issues


class EquivalencyCert(BaseModel):
    qualification: str | None = Field(description="the qualification being recognised, for example 'Doctor of Philosophy in Media and Communication'")
    institution: str | None = Field(description="the awarding institution")
    date_of_award: str | None = Field(description="the date the qualification was awarded (not the date of this certificate)")


def build_equivalency(p: EquivalencyCert, ctx: Ctx):
    issues, awarded = [], parse_date(p.date_of_award)
    for missing, text in ((not p.qualification, "qualification not found"), (awarded is None, "award date not found")):
        if missing:
            issues.append(text)
    return {"qualification": (p.qualification or "").strip(), "institution": (p.institution or "").strip(), "award_date": awarded}, issues


class RankDecision(BaseModel):
    rank_title: str | None = Field(description="the academic rank the person is appointed to, for example 'Assistant Professor' or 'Lecturer'")
    institution: str | None = Field(description="the university that issued the decision")
    country: str | None = Field(description="the country printed in the letterhead, if any")
    effective_date: str | None = Field(description="the date the appointment takes effect ('with effect from')")
    decision_date: str | None = Field(description="the date of the decision itself")


def build_rank(p: RankDecision, ctx: Ctx):
    issues, title = [], p.rank_title or ""
    rank = ("assistant_professor" if _has(title, "assistant prof") else "associate_professor" if _has(title, "associate prof") else
            "professor" if _has(title, "professor") else "lecturer" if _has(title, "lecturer", "instructor") else None)
    start = parse_date(p.effective_date) or parse_date(p.decision_date)
    here = _has(p.institution, "sharjah")
    code = "AE" if here else country_code(p.country)
    for missing, text in ((rank is None, "rank not understood"), (start is None, "start date not found"),
                          (not (p.institution or "").strip(), "university not found"), (code is None, "choose the country")):
        if missing:
            issues.append(text)
    return {"rank": rank, "date_obtained": start, "university": (p.institution or "").strip(), "country_code": code,
            "held_from": start, "held_to": None, "at_this_university": here}, issues


class EmploymentDoc(BaseModel):
    position: str | None = Field(description="the job title")
    employer: str | None = Field(description="the employer (organisation)")
    country: str | None = Field(description="the country of the employer, if printed")
    date_from: str | None = Field(description="the start of the employment")
    date_to: str | None = Field(description="the end of the employment; null if open-ended")


def build_position(p: EmploymentDoc, ctx: Ctx):
    issues, d_from, d_to = [], parse_date(p.date_from), parse_date(p.date_to)
    code = country_code(p.country)
    for missing, text in ((not p.position, "position not found"), (not p.employer, "employer not found"), (code is None, "choose the country"),
                          (d_from is None, "start date not found")):
        if missing:
            issues.append(text)
    return {"position": (p.position or "").strip(), "employer": (p.employer or "").strip(), "country_code": code, "date_from": d_from, "date_to": d_to}, issues


# ---- Section 5: papers, a book chapter, conference papers, a funded project, awards, Scopus ------------------------

class PaperDoc(BaseModel):
    title: str | None = Field(description="the title of the paper, in the language it is printed")
    journal_name: str | None = Field(description="the name of the journal")
    publisher: str | None = Field(description="the publisher, if printed")
    issn: str | None = Field(description="the ISSN or eISSN, if printed")
    volume: str | None = Field(description="the volume number")
    issue: str | None = Field(description="the issue number, if printed (not the year)")
    pages: str | None = Field(description="the pages or article number")
    doi: str | None = Field(description="the DOI, without any note in brackets")
    year: int | None = Field(description="the year of publication")
    month: str | None = Field(description="the month of publication, only if printed")
    authors: list[str] = Field(description="every author, in the printed order")
    corresponding_author: str | None = Field(description="the corresponding author, if marked")
    affiliation: str | None = Field(description="the affiliation printed under the authors")


def _paper_values(title, journal_name, publisher, issn, authors, ctx: Ctx, issues):
    pos = applicant_position(authors, ctx)
    total = len(authors or [])
    known = ctx.journals.get(norm_name(journal_name)) or (None, None)
    issn = (issn or "").strip().upper() or known[0]
    if pos is None:
        issues.append("your position was not found in the author list (names in Arabic are not matched): enter your position and role")
    if not issn:
        issues.append("ISSN not found: enter it")
    others = [a for i, a in enumerate(authors or [], 1) if i != pos]
    return pos, total, issn, (publisher or "").strip() or known[1] or "", others


def _role(pos, total, corresponding, ctx: Ctx):
    if pos is None:
        return None, None
    if total == 1:
        return "sole", None
    if pos == 1:
        return "main", "first_author"
    if corresponding and _surname(ctx.applicant_name) in norm_name(corresponding):
        return "main", "corresponding_author"
    return "co_author", None


def _language(title: str | None) -> str:
    return "arabic" if re.search(r"[؀-ۿ]", title or "") else "english"


def build_paper(p: PaperDoc, ctx: Ctx):
    issues = []
    pos, total, issn, publisher, others = _paper_values(p.title, p.journal_name, p.publisher, p.issn, p.authors, ctx, issues)
    role, basis = _role(pos, total, p.corresponding_author, ctx)
    issue_date, month_printed = _year_date(p.year, p.month)
    for missing, text in ((not (p.title or "").strip(), "title not found"), (not (p.journal_name or "").strip(), "journal not found"),
                          (not (p.volume or "").strip(), "volume not found"), (not (p.issue or "").strip(), "issue number not printed: enter it"),
                          (issue_date is None, "year not found")):
        if missing:
            issues.append(text)
    if issue_date and not month_printed:
        issues.append("check: only the year is printed, the month is set to January")
    doi = re.sub(r"\(.*?\)", "", p.doi or "").strip() or None
    return {"title": (p.title or "").strip(), "journal_name": (p.journal_name or "").strip(), "issn": issn, "publisher": publisher,
            "volume": (p.volume or "").strip() or None, "issue": (p.issue or "").strip() or None, "pages": (p.pages or "").strip() or None, "doi": doi,
            "language": _language(p.title), "submit_for_promotion": True, "status": "published", "issue_date": issue_date, "acceptance_date": None,
            "new_since_rejection": None, "author_position": pos, "total_authors": total, "applicant_role": role, "main_author_basis": basis,
            "main_author_explanation": None, "with_supervised_student": False, "at_this_university": _has(p.affiliation, "sharjah", "الشارقة"),
            "from_thesis": False, "impact_factor": None, "disputes_class": False, "dispute_reason": None, "_other_authors": others, "_authors": list(p.authors or [])}, issues


class AcceptanceLetter(BaseModel):
    title: str | None = Field(description="the title of the manuscript that was accepted")
    journal_name: str | None = Field(description="the journal that accepted it")
    publisher: str | None = Field(description="the publisher named in the letterhead, if any")
    authors: list[str] = Field(description="the authors listed in the letter, in the printed order")
    acceptance_date: str | None = Field(description="the date of the letter (the acceptance)")


def build_acceptance(p: AcceptanceLetter, ctx: Ctx):
    issues = []
    pos, total, issn, publisher, others = _paper_values(p.title, p.journal_name, p.publisher, None, p.authors, ctx, issues)
    role, basis = _role(pos, total, None, ctx)
    accepted = parse_date(p.acceptance_date)
    for missing, text in ((not (p.title or "").strip(), "title not found"), (not (p.journal_name or "").strip(), "journal not found"),
                          (accepted is None, "acceptance date not found")):
        if missing:
            issues.append(text)
    if role == "co_author":
        issues.append("check: you are not the first author; confirm the authors' order")
    return {"title": (p.title or "").strip(), "journal_name": (p.journal_name or "").strip(), "issn": issn, "publisher": publisher, "volume": None, "issue": None,
            "pages": None, "doi": None, "language": _language(p.title), "submit_for_promotion": True, "status": "accepted", "issue_date": None,
            "acceptance_date": accepted, "new_since_rejection": None, "author_position": pos, "total_authors": total, "applicant_role": role,
            "main_author_basis": basis, "main_author_explanation": None, "with_supervised_student": False, "at_this_university": True, "from_thesis": False,
            "impact_factor": None, "disputes_class": False, "dispute_reason": None, "_other_authors": others, "_authors": list(p.authors or [])}, issues


class BookChapterDoc(BaseModel):
    book_title: str | None = Field(description="the title of the book")
    chapter_title: str | None = Field(description="the title of this chapter")
    publisher: str | None = Field(description="the publisher")
    publication_year: int | None = Field(description="the year the book was published")
    isbn: str | None = Field(description="the ISBN, without any note in brackets")
    authors: list[str] = Field(description="the authors of the chapter (not the editors)")


def build_book(p: BookChapterDoc, ctx: Ctx):
    issues, when = [], (date(p.publication_year, 1, 1) if p.publication_year else None)
    pos = applicant_position(p.authors, ctx)
    isbn = re.sub(r"\(.*?\)", "", p.isbn or "").strip()
    for missing, text in ((not p.book_title, "book title not found"), (not p.chapter_title, "chapter title not found"), (not p.publisher, "publisher not found"),
                          (when is None, "publication year not found"), (not isbn, "ISBN not found"), (pos is None, "your name is not in the author list: check it")):
        if missing:
            issues.append(text)
    return {"item_type": "chapter", "book_title": (p.book_title or "").strip(), "chapter_title": (p.chapter_title or "").strip(), "publisher": (p.publisher or "").strip(),
            "publication_date": when, "isbn": isbn, "main_or_sole_author": (pos == 1) if pos else None, "financial_support_by": None, "refereed": False,
            "referee_count": None, "from_thesis": False}, issues


class ConferencePaperDoc(BaseModel):
    title: str | None = Field(description="the title of the paper")
    conference_title: str | None = Field(description="the name of the conference")
    organizer: str | None = Field(description="who organised the conference")
    place: str | None = Field(description="the city and country where it was held")
    conference_date: str | None = Field(description="the date of the conference")
    pages: str | None = Field(description="the pages in the proceedings")
    doi: str | None = Field(description="the DOI, if printed")
    authors: list[str] = Field(description="the authors, in the printed order")


def build_conference(p: ConferencePaperDoc, ctx: Ctx):
    issues, d = [], parse_date(p.conference_date)
    pos = applicant_position(p.authors, ctx)
    for missing, text in ((not p.title, "title not found"), (not p.conference_title, "conference not found"), (not p.organizer, "organizer not found"),
                          (not p.place, "place not found"), (d is None, "date not found"), (pos is None, "your name is not in the author list: check it"),
                          (True, "say whether the proceedings are indexed in Scopus")):
        if missing:
            issues.append(text)
    return {"title": (p.title or "").strip(), "conference_title": (p.conference_title or "").strip(), "organizer": (p.organizer or "").strip(),
            "conference_date": d, "place": (p.place or "").strip(), "pages": (p.pages or "").strip() or None,
            "main_or_sole_author": (pos == 1) if pos else None, "scopus_indexed": None, "doi": (p.doi or "").strip() or None}, issues


class FundedProjectDoc(BaseModel):
    title: str | None = Field(description="the project title")
    funding_body: str | None = Field(description="the organisation that funds the project")
    amount: float | None = Field(description="the amount awarded, as a number")
    currency: str | None = Field(description="the 3-letter currency code, for example AED or USD")
    start_date: str | None = Field(description="the project start date")
    end_date: str | None = Field(description="the project end date")
    applicant_role: str | None = Field(description="the role of the APPLICANT in the project, as printed (principal investigator, co-investigator ...)")
    status: str | None = Field(description="the status, for example Completed or Ongoing")


def build_funded(p: FundedProjectDoc, ctx: Ctx):
    issues, body = [], p.funding_body or ""
    funder = ("internal" if _has(body, "sharjah", "internal") else "government" if _has(body, "ministry", "government", "national research", "federal") else
              "international" if _has(body, "international", "united nations", "european") else "company" if _has(body, "company", "ltd", "inc.", "corporation", "group") else
              "university" if _has(body, "universit") else None)
    role = "ci" if _has(p.applicant_role, "co-", "co ") else "pi" if _has(p.applicant_role, "principal", "pi", "lead") else None
    status = "completed" if _has(p.status, "complet", "closed", "finished") else "ongoing" if _has(p.status, "ongoing", "active", "progress") else None
    start, end = parse_date(p.start_date), parse_date(p.end_date)
    for missing, text in ((not p.title, "title not found"), (not body.strip(), "funding body not found"), (funder is None, "choose the funder type"),
                          (role is None, "your role is not clear: choose it"), (start is None, "start date not found"), (status is None, "choose the status")):
        if missing:
            issues.append(text)
    return {"title": (p.title or "").strip(), "funding_body": body.strip(), "funder_code": funder, "role": role, "amount": to_number(p.amount),
            "currency": (p.currency or "").strip().upper()[:3] or None, "start_date": start, "end_date": end, "status": status}, issues


class AwardDoc(BaseModel):
    award_name: str | None = Field(description="the name of the award or prize")
    awarding_body: str | None = Field(description="the organisation, college or association that gives the award")
    award_date: str | None = Field(description="the date or year of the award")
    context: str | None = Field(description="the event or reason the award was given for, for example a conference name, as printed")


def build_award(p: AwardDoc, ctx: Ctx):
    issues, text = [], f"{p.awarding_body or ''} {p.context or ''} {p.award_name or ''}"
    year = None
    m = re.search(r"(19|20)\d{2}", p.award_date or "")
    if m:
        year = int(m.group(0))
    scope = ("institutional" if _has(p.awarding_body, "sharjah", "college", "department", "faculty") else "international" if _has(text, "international", "world", "global") else
             "national" if _has(text, "national", "emirates", "uae", "ministry") else "regional" if _has(text, "gulf", "arab", "regional", "middle east", "gcc") else None)
    for missing, msg in ((not p.award_name, "award name not found"), (not p.awarding_body, "awarding body not found"), (year is None, "year not found"),
                         (scope is None, "choose the scope")):
        if missing:
            issues.append(msg)
    return {"name": tidy(p.award_name), "awarding_body": tidy(p.awarding_body), "year": year, "scope_code": scope}, issues


class ScopusDoc(BaseModel):
    h_index: int | None = Field(description="the h-index shown")
    total_citations: int | None = Field(description="the total number of citations shown")
    screenshot_date: str | None = Field(description="a date shown on the screenshot (for example 'as of ...'), if any")


def build_scopus(p: ScopusDoc, ctx: Ctx):
    issues, d = [], parse_date(p.screenshot_date)
    for missing, text in ((p.h_index is None, "h-index not found"), (p.total_citations is None, "citations not found"),
                          (d is None, "no date on the screenshot: enter the date it was taken")):
        if missing:
            issues.append(text)
    return {"h_index": p.h_index, "total_citations": p.total_citations, "screenshot_date": d}, issues


# ---- Section 6 and 7: peer observations, curriculum, innovation, policies; Section 8: recommendation letters -------

class PeerObservationDoc(BaseModel):
    course_code: str | None = Field(description="the code of the course observed, for example 'MCOM 325'")
    term: str | None = Field(description="the semester of the observation, for example 'Fall 2018'")
    observer_name: str | None = Field(description="the name of the observer")
    observer_role: str | None = Field(description="the role of the observer, as printed (peer faculty member, head of department ...)")
    observation_date: str | None = Field(description="the date of the observation")
    overall_score: float | None = Field(description="the overall score given")
    scale_max: float | None = Field(description="the top of the scale, for example 5 in 'out of 5'")


def build_peer_observation(p: PeerObservationDoc, ctx: Ctx):
    issues, d = [], parse_date(p.observation_date)
    course = match_course_row(p.course_code, p.term, ctx)
    role = ("hod" if _has(p.observer_role, "head", "chair") else "tl_centre" if _has(p.observer_role, "teaching", "learning", "centre", "center") else
            "peer" if _has(p.observer_role, "peer", "faculty", "colleague") else "other")
    for missing, text in ((course is None, "course not matched to your courses: choose it"), (d is None, "date not found"),
                          (p.overall_score is None, "overall score not found"), (p.scale_max is None, "scale not found")):
        if missing:
            issues.append(text)
    return {"course_taught_id": course, "observer_code": role, "observer_name": (p.observer_name or "").strip() or None, "observation_date": d,
            "rating": to_number(p.overall_score), "scale_max": to_number(p.scale_max)}, issues


class CurriculumRow(BaseModel):
    course_code: str | None = Field(description="the course code, for example 'MCOM 415'")
    course_title: str | None = Field(description="the course title")
    contribution: str | None = Field(description="the kind of contribution, as printed (proposed a new course, modified an existing course ...)")
    changes: str | None = Field(description="what was changed, as printed in the 'Contribution' column, if anything")
    approval_level: str | None = Field(description="who approved it, as printed (department / college / university level)")
    approval_date: str | None = Field(description="the approval date")
    what_was_done: str | None = Field(description="what the faculty member did, copied from the last column")


class CurriculumDoc(BaseModel):
    rows: list[CurriculumRow] = Field(description="one row per course in the table, in the printed order")


def build_curriculum_row(p: CurriculumRow, ctx: Ctx):
    issues, text = [], f"{p.contribution or ''} {p.changes or ''}"
    kind = ("new_course" if _has(p.contribution, "new") else "modified_course" if _has(p.contribution, "modif", "existing") else
            "study_plan" if _has(p.contribution, "study plan") else "program" if _has(p.contribution, "program") else None)
    changes = [c for c, words in (("textbook", ("textbook",)), ("objectives", ("objective", "outcome")), ("chapters", ("chapter",)),
                                  ("assessment", ("assessment", "exam", "evaluation")), ("other", ("content", "updated", "capstone", "other"))) if _has(text, *words)]
    if kind == "modified_course" and not changes:
        changes = ["other"]
    level = "university" if _has(p.approval_level, "universit") else "college" if _has(p.approval_level, "college") else "department" if _has(p.approval_level, "department") else None
    approved = parse_date(p.approval_date)
    title = " ".join(x for x in (norm_code(p.course_code) if p.course_code else "", (p.course_title or "").strip()) if x)
    description = (p.what_was_done or "").strip()[:2000]
    for missing, msg in ((kind is None, "contribution type not understood"), (not title, "course not found"), (level is None, "choose who approved it"),
                         (approved is None, "approval date not found"), (not description, "description not found")):
        if missing:
            issues.append(msg)
    return {"type_code": kind, "course_or_program": title, "changes": changes if kind == "modified_course" else None,
            "self_classification": ("deep" if {"textbook", "objectives"} & set(changes) else "mild") if kind == "modified_course" else None,
            "description": description, "approved_by": level, "approval_date": approved}, issues


class InnovationDoc(BaseModel):
    title: str | None = Field(description="the title of the innovation or pilot")
    course_code: str | None = Field(description="the course code")
    term: str | None = Field(description="the semester, for example 'Fall 2023'")
    what_was_done: str | None = Field(description="one or two sentences: what was done (copied or shortened from the report)")
    measured_outcome: str | None = Field(description="one or two sentences: the measured results, with the numbers as printed")


def build_innovation(p: InnovationDoc, ctx: Ctx):
    issues, text = [], f"{p.title or ''} {p.what_was_done or ''}"
    kind = ("ai_tool" if _has(text, " ai ", "ai-", "artificial", "ai tool") else "case_study" if _has(text, "versus", " vs", "compar") else
            "blended" if _has(text, "flipped", "blended") else "collaborative" if _has(text, "collaborat", "peer") else
            "active" if _has(text, "active learning", "workshop", "game") else "edtech")
    course = match_course_row(p.course_code, p.term, ctx)
    description = ": ".join(x for x in ((p.title or "").strip(), (p.what_was_done or "").strip()) if x)
    for missing, msg in ((course is None, "course not matched to your courses: choose it"), (not description, "description not found")):
        if missing:
            issues.append(msg)
    return {"type_code": kind, "course_taught_id": course, "description": description, "measured_outcome": (p.measured_outcome or "").strip() or None}, issues


class SyllabusDoc(BaseModel):
    course_code: str | None = Field(description="the course code, for example 'MCOM 201'")
    term: str | None = Field(description="the semester, for example 'Fall 2025'")


def build_course_file(p: SyllabusDoc, ctx: Ctx):
    issues, course = [], match_course_row(p.course_code, p.term, ctx)
    row = next((c for c in ctx.courses if c.id == course), None)
    if course is None:
        issues.append("course not matched to your courses: choose it")
    issues.append("choose where the course file is kept")
    return {"course_taught_id": course, "is_coordinator": (row.role == "instructor_coordinator") if row else False, "kept_in_code": None, "items": ["syllabus"]}, issues


class PolicyDoc(BaseModel):
    policy_name: str | None = Field(description="the title of the policy or regulation")
    approving_body: str | None = Field(description="the council or body that approved it, for example 'Department Council of Mass Communication'")
    effective_date: str | None = Field(description="the date it was approved or takes effect")
    applicant_role: str | None = Field(description="the role of the APPLICANT in the drafting committee, as listed (chair, member ...)")


def build_policy(p: PolicyDoc, ctx: Ctx):
    issues = []
    level = ("department" if _has(p.approving_body, "department") else "college" if _has(p.approving_body, "college", "faculty") else
             "university" if _has(p.approving_body, "universit", "senate", "board") else None)
    role = "chaired" if _has(p.applicant_role, "chair") else "reviewed" if _has(p.applicant_role, "review") else "drafted" if p.applicant_role else None
    d = parse_date(p.effective_date)
    for missing, msg in ((not p.policy_name, "policy name not found"), (level is None, "choose the level"), (role is None, "your role is not clear: choose it"),
                         (d is None, "date not found")):
        if missing:
            issues.append(msg)
    return {"policy_name": (p.policy_name or "").strip(), "level": level, "role_code": role, "activity_date": d}, issues


class LetterDoc(BaseModel):
    writer_name: str | None = Field(description="the name of the person who wrote the letter")
    writer_rank: str | None = Field(description="the writer's academic rank or job title")
    writer_institution: str | None = Field(description="the writer's institution")
    relationship: str | None = Field(description="how the writer knows the applicant, as stated in the letter (colleague, collaborator, former supervisor ...)")


def build_letter(p: LetterDoc, ctx: Ctx):
    issues, rel = [], p.relationship or ""
    code = ("former_supervisor" if _has(rel, "supervisor") else "collaborator" if _has(rel, "collaborat", "co-author", "coauthor") else
            "head_of_unit" if _has(rel, "head of", "dean", "chair") else "colleague" if _has(rel, "colleague") else "other")
    for missing, msg in ((not p.writer_name, "writer not found"), (not p.writer_rank, "rank not found"), (not p.writer_institution, "institution not found")):
        if missing:
            issues.append(msg)
    return {"writer_name": (p.writer_name or "").strip(), "writer_rank": (p.writer_rank or "").strip(), "writer_institution": (p.writer_institution or "").strip(),
            "relationship_code": code}, issues


class SignedDateDoc(BaseModel):
    signed_date: str | None = Field(description="the date the document was signed or dated")


def build_signed_date(p: SignedDateDoc, ctx: Ctx):
    d = parse_date(p.signed_date)
    return {"signed_date": d}, ([] if d else ["date not found"])


# ---- the kinds -----------------------------------------------------------------------------------------------------

def _fin_enum(*pairs, lookups=()):
    """finalize(): turn the preview's codes into what the section's add() stores: enum members, and lookup codes into ids."""
    def fin(values, ctx):
        out = dict(values)
        for key, enum_cls in pairs:
            if out.get(key) is not None:
                out[key] = enum_cls(out[key])
        for list_code, code_key, id_key in lookups:
            out[id_key] = ctx.ids.get(list_code, {}).get(out.pop(code_key, None))
        return out
    return fin


def _register():
    from promoflow.db.enums import (
        AuthorRole, BookItemType, DegreeLevel, DevelopmentDepth, InvestigatorRole, Language, MainAuthorBasis, OrgLevel, ProjectStatus, PublicationStatus, Rank,
    )
    ranks = {"lecturer": "Lecturer", "assistant_professor": "Assistant Professor", "associate_professor": "Associate Professor", "professor": "Professor"}
    levels_deg = {"bachelor": "Bachelor", "master": "Master", "phd": "PhD", "other_doctorate": "Other doctorate"}
    role_paper = {"sole": "Sole author", "main": "Main author", "co_author": "Co-author"}
    basis = {"first_author": "First author", "corresponding_author": "Corresponding author", "supervision_rule": "Supervision rule", "other": "Other"}
    paper_cols = lambda ctx: [Col("Title", "title"), Col("Journal", "journal_name"), Col("ISSN", "issn"), Col("Publisher", "publisher"), Col("Volume", "volume"),
                              Col("Issue", "issue"), Col("Pages", "pages"), Col("Issue date", "issue_date", "date"), Col("Accepted on", "acceptance_date", "date"),
                              Col("Language", "language", "select", {"english": "English", "arabic": "Arabic", "other": "Other"}),
                              Col("Your position in the authors", "author_position", "number"),
                              Col("Your role", "applicant_role", "select", role_paper), Col("Basis", "main_author_basis", "select", basis),
                              Col("At this university", "at_this_university", "select", YES_NO), Col("From your thesis", "from_thesis", "select", YES_NO)]
    paper_enums = _fin_enum(("status", PublicationStatus), ("language", Language), ("applicant_role", AuthorRole), ("main_author_basis", MainAuthorBasis))
    def paper_fin(v, ctx):
        """The author list is fixed (read from the document); the applicant's position is editable, so the other authors and the total follow it."""
        out = {**paper_enums(v, ctx), "_prev_rejected": ctx.previously_rejected}
        authors, pos = v.get("_authors") or [], v.get("author_position")
        if authors and pos:
            out["_other_authors"] = [a for i, a in enumerate(authors, 1) if i != pos]
            out["total_authors"] = len(authors)
        return out
    curriculum_enums = _fin_enum(("approved_by", OrgLevel), ("self_classification", DevelopmentDepth),
                                 lookups=(("curriculum_contribution_type", "type_code", "contribution_type_id"),))
    curriculum_fin = lambda v, ctx: {**curriculum_enums(v, ctx), "_modified": v.get("type_code") == "modified_course"}
    course_col = lambda ctx: Col("Course", "course_taught_id", "select", _course_options(ctx))
    KINDS.update({
        "degree": Kind("degree", "academic degrees", DegreeCert, build_degree,
                       lambda ctx: [Col("Level", "level", "select", levels_deg), Col("Specialization", "specialization"), Col("University", "university"),
                                    Col("Country", "country_code", "select", _country_options()), Col("Study from", "study_from", "date"),
                                    Col("Study to", "study_to", "date"), Col("Graduated", "graduation_date", "date"), Col("Thesis", "thesis_title")],
                       _fin_enum(("level", DegreeLevel))),
        "equivalency": Kind("equivalency", "equivalency certificates", EquivalencyCert, build_equivalency,
                            lambda ctx: [Col("Qualification", "qualification"), Col("Institution", "institution"), Col("Awarded on", "award_date", "date", editable=True)],
                            lambda v, ctx: dict(v)),
        "rank": Kind("rank", "academic rank decisions", RankDecision, build_rank,
                     lambda ctx: [Col("Rank", "rank", "select", ranks), Col("University", "university"), Col("Country", "country_code", "select", _country_options()),
                                  Col("From", "held_from", "date"), Col("To", "held_to", "date"), Col("At this university", "at_this_university", "select", YES_NO)],
                     _fin_enum(("rank", Rank))),
        "position": Kind("position", "non-academic positions", EmploymentDoc, build_position,
                         lambda ctx: [Col("Position", "position"), Col("Employer", "employer"), Col("Country", "country_code", "select", _country_options()),
                                      Col("From", "date_from", "date"), Col("To", "date_to", "date")], lambda v, ctx: dict(v)),
        "paper": Kind("paper", "published papers", PaperDoc, build_paper, paper_cols, paper_fin,
                      lambda ctx: f"The applicant is {ctx.applicant_name}. List every author exactly as printed, in order.", max_chars=3000),
        "acceptance": Kind("acceptance", "acceptance letters (accepted papers)", AcceptanceLetter, build_acceptance, paper_cols, paper_fin,
                           lambda ctx: f"The applicant is {ctx.applicant_name}. List every author named in the letter, in order."),
        "book": Kind("book", "book chapters", BookChapterDoc, build_book,
                     lambda ctx: [Col("Book", "book_title"), Col("Chapter", "chapter_title"), Col("Publisher", "publisher"), Col("Published", "publication_date", "date"),
                                  Col("ISBN", "isbn"), Col("Main or sole author", "main_or_sole_author", "select", YES_NO), Col("From your thesis", "from_thesis", "select", YES_NO)],
                     _fin_enum(("item_type", BookItemType)), lambda ctx: f"The applicant is {ctx.applicant_name}.", max_chars=3000),
        "conference": Kind("conference", "conference papers", ConferencePaperDoc, build_conference,
                           lambda ctx: [Col("Paper", "title"), Col("Conference", "conference_title"), Col("Organizer", "organizer"), Col("Place", "place"),
                                        Col("Date", "conference_date", "date"), Col("Pages", "pages"), Col("Main or sole author", "main_or_sole_author", "select", YES_NO),
                                        Col("Indexed in Scopus", "scopus_indexed", "select", YES_NO)],
                           lambda v, ctx: dict(v), lambda ctx: f"The applicant is {ctx.applicant_name}.", max_chars=3000),
        "funded": Kind("funded", "funded research projects", FundedProjectDoc, build_funded,
                       lambda ctx: [Col("Project", "title"), Col("Funding body", "funding_body"), Col("Funder type", "funder_code", "select", _opts(ctx, "funder_type")),
                                    Col("Your role", "role", "select", {"pi": "Principal investigator", "ci": "Co-investigator"}), Col("Amount", "amount", "number"),
                                    Col("Currency", "currency"), Col("From", "start_date", "date"), Col("To", "end_date", "date"),
                                    Col("Status", "status", "select", {"ongoing": "Ongoing", "completed": "Completed"})],
                       _fin_enum(("role", InvestigatorRole), ("status", ProjectStatus), lookups=(("funder_type", "funder_code", "funder_type_id"),)),
                       lambda ctx: f"The applicant is {ctx.applicant_name}. Give applicant_role as the role listed for THIS person."),
        "award": Kind("award", "awards", AwardDoc, build_award,
                      lambda ctx: [Col("Award", "name"), Col("Awarding body", "awarding_body"), Col("Year", "year", "number"), Col("Scope", "scope_code", "select", _opts(ctx, "award_scope"))],
                      _fin_enum(lookups=(("award_scope", "scope_code", "scope_id"),))),
        "scopus": Kind("scopus", "the Scopus profile screenshot", ScopusDoc, build_scopus,
                       lambda ctx: [Col("h-index", "h_index", "number"), Col("Total citations", "total_citations", "number"), Col("Screenshot date", "screenshot_date", "date")],
                       lambda v, ctx: dict(v)),
        "peer_observation": Kind("peer_observation", "peer observation reports", PeerObservationDoc, build_peer_observation,
                                 lambda ctx: [course_col(ctx), Col("Observer role", "observer_code", "select", _opts(ctx, "observer_role")), Col("Observer", "observer_name"),
                                              Col("Date", "observation_date", "date"), Col("Score", "rating", "number"), Col("Out of", "scale_max", "number")],
                                 _fin_enum(lookups=(("observer_role", "observer_code", "observer_role_id"),))),
        "curriculum": Kind("curriculum", "curriculum contributions", CurriculumDoc, build_curriculum_row,
                           lambda ctx: [Col("Type", "type_code", "select", _opts(ctx, "curriculum_contribution_type")), Col("Course or program", "course_or_program"),
                                        Col("What changed", "changes", "multi", _opts(ctx, "course_change")), Col("Approved by", "approved_by", "select", LEVELS),
                                        Col("Approval date", "approval_date", "date"), Col("What you did", "description")],
                           curriculum_fin, rows="rows"),
        "innovation": Kind("innovation", "teaching innovation reports", InnovationDoc, build_innovation,
                           lambda ctx: [Col("Type", "type_code", "select", _opts(ctx, "innovation_type")), course_col(ctx), Col("What was done", "description"),
                                        Col("Measured outcome", "measured_outcome")],
                           _fin_enum(lookups=(("innovation_type", "type_code", "innovation_type_id"),))),
        "course_file": Kind("course_file", "syllabi (course files)", SyllabusDoc, build_course_file,
                            lambda ctx: [course_col(ctx), Col("Course file kept in", "kept_in_code", "select", _opts(ctx, "course_file_system")),
                                         Col("You coordinate the course", "is_coordinator", "select", YES_NO), Col("Items in the file", "items", "multi", _opts(ctx, "course_file_item"))],
                            _fin_enum(lookups=(("course_file_system", "kept_in_code", "kept_in_id"),))),
        "policy": Kind("policy", "policy contributions", PolicyDoc, build_policy,
                       lambda ctx: [Col("Policy", "policy_name"), Col("Level", "level", "select", LEVELS), Col("Your role", "role_code", "select", _opts(ctx, "policy_role")),
                                    Col("Date", "activity_date", "date")],
                       _fin_enum(("level", OrgLevel), lookups=(("policy_role", "role_code", "role_id"),)),
                       lambda ctx: f"The applicant is {ctx.applicant_name}. Give applicant_role as the role listed for THIS person."),
        "letter": Kind("letter", "recommendation letters", LetterDoc, build_letter,
                       lambda ctx: [Col("Writer", "writer_name"), Col("Rank / title", "writer_rank"), Col("Institution", "writer_institution"),
                                    Col("Relationship", "relationship_code", "select", _opts(ctx, "recommendation_relationship"))],
                       _fin_enum(lookups=(("recommendation_relationship", "relationship_code", "relationship_id"),))),
        "cv": Kind("cv", "your CV", SignedDateDoc, build_signed_date, lambda ctx: [Col("Last updated", "signed_date", "date")], lambda v, ctx: dict(v),
                   lambda ctx: "signed_date is the date the CV was last updated (printed in the header or footer), if any."),
        "conditions": Kind("conditions", "the signed conditions form", SignedDateDoc, build_signed_date, lambda ctx: [Col("Signed on", "signed_date", "date")], lambda v, ctx: dict(v)),
        "cover_letter": Kind("cover_letter", "the signed cover letter", SignedDateDoc, build_signed_date, lambda ctx: [Col("Signed on", "signed_date", "date")], lambda v, ctx: dict(v)),
    })


_register()


# ---- study years from the CV (a degree certificate does not print them) --------------------------------------------

class CvDegreeRow(BaseModel):
    degree: str | None = Field(description="the degree, as printed in the Education table")
    institution: str | None = Field(description="the university")
    years: str | None = Field(description="the years of study as printed, for example '2012-2016'")


class CvEducation(BaseModel):
    rows: list[CvDegreeRow] = Field(description="one row per degree in the Education table")


def cv_education_text(cv_text: str) -> str:
    """The part of the CV text that holds the Education table (the whole CV is long and the rest is not needed)."""
    m = re.search(r"\n\s*Education\s*\n\s*Degree", cv_text)
    start = m.start() if m else 0
    return cv_text[start:start + 2500]


def fill_study_years(drafts: list, rows: list[CvDegreeRow]) -> None:
    """Fill the study start of degree drafts from the CV's Education table. The CV gives only years, so the start is set to 1 September and a
    "check:" note says so; the applicant can change it in the table."""
    for d in drafts:
        v = d.values
        if v.get("study_from") or not v.get("university"):
            continue
        row = next((r for r in rows if norm_name(r.institution) and (norm_name(r.institution) in norm_name(v["university"]) or norm_name(v["university"]) in norm_name(r.institution))
                    and (not v.get("graduation_date") or str(v["graduation_date"].year) in (r.years or ""))), None)
        years = re.findall(r"(?:19|20)\d{2}", row.years or "") if row else []
        if not years:
            continue
        v["study_from"] = date(int(years[0]), 9, 1)
        d.issues[:] = [i for i in d.issues if not i.startswith("study period start")]
        d.issues.append(f"check: the study start comes from your CV, which gives only the year; set to 1 September {years[0]}")
