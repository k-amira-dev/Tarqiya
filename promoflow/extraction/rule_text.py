"""Text documents read by plain rules (no model, no tokens, nothing leaves the machine): published papers, acceptance letters, book chapters,
conference papers, funded projects, peer observation reports, equivalency certificates, employment contracts, recommendation letters, syllabi,
signed documents (CV, conditions form, cover letter) and the Scopus screenshot.

Same contract as rule_letters.py and rule_docs.py: each function takes the text of the document (its text layer, or OCR text for a scan or a
screenshot) and returns a dict with the keys of the matching schema in entry_docs_more.py, None for anything not found. Nothing is guessed: a
paper whose first page is laid out differently simply gives None for the fields it does not match, and the applicant completes them.
The first page of a paper carries everything that is needed (journal line, publisher and DOI, title, authors, affiliation), so only the start of the
text is looked at. Registers itself in rule_letters.RULES / REQUIRED / rule_docs.NEEDS_APPLICANT (rule_letters imports this at its end).
"""
import re

from promoflow.extraction import rule_letters as RL
from promoflow.extraction.rule_letters import DATE, _clean, _date, _flat, _junk, _lines, _titlecase

_AFFILIATION = r"(?:Department|Dept\.|School|Faculty|College|Institute|University|Centre|Center|Laboratory|Division)\b"


def _authors(line: str | None) -> list[str]:
    parts = re.split(r",\s*|;\s*|\s+and\s+|\s*&\s*", line or "")
    return [p.strip(" *†‡") for p in parts if p.strip(" *†‡") and not re.search(r"\d", p)]


def _clean_lines(text: str) -> list[str]:
    return [x for x in _lines(text) if not _junk(x)]


# ---- a published paper ----------------------------------------------------------------------------------------------------

def paper_doc(text: str, applicant: str = "") -> dict:
    lines = _clean_lines(text)
    journal = volume = issue = year = pages = publisher = doi = None
    pub_at = -1
    for i, line in enumerate(lines[:8]):
        m = re.match(r"^(?P<j>.+?)\s+Vol(?:ume)?\.?\s*(?P<v>\d+)(?:,\s*(?:No|Issue)\.?\s*(?P<i>\d+))?,\s*(?P<y>\d{4})(?:,\s*(?:pp?|art)\.?\s*(?P<p>[\w\-–]+))?", line)
        if m and journal is None:
            journal, volume, issue, year, pages = _clean(m.group("j")), m.group("v"), m.group("i"), int(m.group("y")), m.group("p")
            continue
        m = re.match(r"^(?P<j>.+?)\s+(?:Accepted manuscript|In press|Advance online|Early access)\b", line, re.I)
        if m and journal is None:
            journal = _clean(m.group("j"))
            continue
        m = re.match(r"^(?P<pub>.+?)\s+DOI:\s*(?P<doi>10\.\S+)", line)
        if m and doi is None:
            publisher, doi, pub_at = _clean(m.group("pub")), m.group("doi").rstrip(".,;"), i
    head = " ".join(lines[:8])
    issn = re.search(r"ISSN[:\s]*([0-9]{4}-[0-9]{3}[0-9Xx])", head)
    aff_at = next((i for i in range(max(pub_at, 0) + 2, min(len(lines), 14)) if re.match(_AFFILIATION, lines[i])), None)
    title = authors = affiliation = None
    if aff_at is not None and pub_at >= 0 and aff_at - 1 > pub_at + 1:
        title = _clean(" ".join(lines[pub_at + 1:aff_at - 1]))
        authors = _authors(lines[aff_at - 1])
        affiliation = _clean(lines[aff_at])
    corresponding = re.search(r"[Cc]orresponding author[:\s]+([^\n.;]+)", " ".join(lines[:20]))
    return {"title": title, "journal_name": journal, "publisher": publisher, "issn": issn.group(1) if issn else None, "volume": volume, "issue": issue,
            "pages": pages, "doi": doi, "year": year, "month": None, "authors": authors or [],
            "corresponding_author": _clean(corresponding.group(1)) if corresponding else None, "affiliation": affiliation}


# ---- an acceptance letter -------------------------------------------------------------------------------------------------

def acceptance_letter(text: str, applicant: str = "") -> dict:
    lines = _clean_lines(text)
    flat = _flat(text)
    q = re.search(r'["“”]\s*(.+?)\s*["“”]', flat)
    j = re.search(r"accepted for publication in (.+?)\.(?:\s|$)", flat)
    a = re.search(r"\(authors?:\s*([^)]+)\)", flat)
    d = re.search(rf"Date:\s*({DATE})", flat)
    journal = _clean(j.group(1)) if j else None
    publisher = None
    for i, line in enumerate(lines[:6]):                                # the letterhead: office, journal, publisher
        if journal and line.casefold() == journal.casefold() and i + 1 < len(lines) and not re.match(r"(date|manuscript|dear)", lines[i + 1], re.I):
            publisher = _clean(lines[i + 1])
            break
    return {"title": _clean(q.group(1)) if q else None, "journal_name": journal, "publisher": publisher, "authors": _authors(a.group(1)) if a else [],
            "acceptance_date": _date(d.group(1)) if d else None}


# ---- a book chapter (page 1 is the book's title page, page 2 starts the chapter) -----------------------------------------

def book_chapter(text: str, applicant: str = "") -> dict:
    lines = _clean_lines(text)
    flat = _flat(text)
    edited = next((i for i, x in enumerate(lines) if re.match(r"edited by", x, re.I)), None)
    book = _clean(" ".join(lines[1:edited])) if edited and edited > 1 else None
    publisher = _titlecase(lines[0]) if lines else None
    year = re.search(r"(?:First published|Published|©|\(c\))\s*(\d{4})", flat)
    isbn = re.search(r"ISBN[:\s]*([\d\-Xx]{10,17})", flat)
    contents = next((i for i, x in enumerate(lines) if re.match(r"contents:", x, re.I)), None)
    chapter = authors = None
    if contents is not None and contents + 2 < len(lines):
        chapter, authors = _clean(lines[contents + 1]), _authors(lines[contents + 2])
    return {"book_title": book, "chapter_title": chapter, "publisher": publisher, "publication_year": int(year.group(1)) if year else None,
            "isbn": isbn.group(1) if isbn else None, "authors": authors or []}


# ---- a conference paper ---------------------------------------------------------------------------------------------------

def conference_paper(text: str, applicant: str = "") -> dict:
    lines = _clean_lines(text)
    flat = _flat(" ".join(lines[:12]))
    org_at = next((i for i, x in enumerate(lines[:12]) if re.match(r"organi[sz]ed by", x, re.I)), None)
    organizer = None
    if org_at is not None:
        organizer = re.sub(r"(?i)^organi[sz]ed by", "", lines[org_at])
        organizer = _clean(re.split(rf"\s+(?:{DATE}|[·•|]|Proceedings)", organizer)[0])
    title = authors = None
    if org_at is not None and org_at + 2 < len(lines):
        title, authors = _clean(lines[org_at + 1]), _authors(lines[org_at + 2])
    first = lines[0] if lines else ""
    place = re.search(r"\s([A-Z][a-z]+,\s*[A-Z][A-Za-z]+(?:\s[A-Z][a-z]+)?)$", first)                 # "... Security Dubai, UAE" (a one-word city)
    name = _clean(first[:place.start(1)]) if place else _clean(first)
    acronym = next((m for m in (re.match(r"^\(([A-Z][A-Z0-9 ]+\d{4})\)", x) for x in lines[1:4]) if m), None)
    if name and acronym:
        name = f"{name} ({acronym.group(1)})"
    when = re.search(rf"({DATE})", flat)
    pages = re.search(r"pp\.?\s*(\d+\s*[-–]\s*\d+)", flat) or re.search(r"Proceedings,\s*pp\.?\s*(\d+)\s*(\d+\s*[-–]\s*\d+)?", flat)
    page_text = None
    if pages:
        page_text = pages.group(1) if pages.lastindex == 1 and "-" in pages.group(1) or "–" in pages.group(1) else None
    if page_text is None:
        loose = re.search(r"\b(\d{1,4}\s*[-–]\s*\d{1,4})\b", " ".join(lines[1:4]))
        page_text = loose.group(1) if loose else None
    return {"title": title, "conference_title": name, "organizer": organizer, "place": _clean(place.group(1)) if place else None,
            "conference_date": _date(when.group(1)) if when else None, "pages": re.sub(r"\s", "", page_text) if page_text else None,
            "doi": (re.search(r"(10\.\d{4,}/\S+)", flat) or [None, None])[1], "authors": authors or []}


# ---- a funded project -----------------------------------------------------------------------------------------------------

def funded_project(text: str, applicant: str = "") -> dict:
    flat = _flat(text)
    last = (applicant or "").replace(".", " ").split()[-1].casefold() if (applicant or "").strip() else ""
    title = re.search(r"Project title\s+(.+?)\s+Funding body", flat)
    body = re.search(r"Funding body\s+(.+?)\s+Amount awarded", flat)
    money = re.search(r"Amount awarded\s+([A-Z]{3})\s*([\d,]+(?:\.\d+)?)", flat)
    period = re.search(rf"Project period\s+({DATE})\s*[^\w\s]{{1,3}}\s*({DATE})", flat)
    pi = re.search(r"Principal Investigator\s+(.+?)(?=\s+Co-investigators|\s+Status|\s+Summary|$)", flat)
    co = re.search(r"Co-investigators?\s+(.+?)(?=\s+Status|\s+Summary|$)", flat)
    role = None
    if last and pi and last in pi.group(1).casefold():
        role = "Principal Investigator"
    elif last and co and last in co.group(1).casefold():
        role = "Co-investigator"
    status = re.search(r"Status\s+(Completed|Ongoing|Active|Approved|Terminated|Pending)\b", flat)
    return {"title": _clean(title.group(1)) if title else None, "funding_body": _clean(body.group(1)) if body else None,
            "amount": float(money.group(2).replace(",", "")) if money else None, "currency": money.group(1) if money else None,
            "start_date": _date(period.group(1)) if period else None, "end_date": _date(period.group(2)) if period else None,
            "applicant_role": role, "status": status.group(1) if status else None}


# ---- a peer observation report --------------------------------------------------------------------------------------------

def peer_observation(text: str, applicant: str = "") -> dict:
    flat = _flat(text)
    course = re.search(r"Course\s+([A-Z]{2,5}\s?\d{3})\b", flat)
    term = re.search(r"Semester\s+((?:Fall|Spring|Summer)\s*\d{4})", flat)
    observer = re.search(r"Observer\s+(.+?)\s+Observer role\s+(.+?)\s+Evaluation criteria", flat)
    when = re.search(rf"Date of\s+(?:observation\s+)?({DATE})|\b({DATE})\b", flat)
    score = re.search(r"Overall score \(out of (\d+(?:\.\d+)?)\)\s*(\d+(?:\.\d+)?)", flat, re.I)
    return {"course_code": _clean(course.group(1)) if course else None, "term": _clean(term.group(1)) if term else None,
            "observer_name": _clean(observer.group(1)) if observer else None, "observer_role": _clean(observer.group(2)) if observer else None,
            "observation_date": _date(when.group(1) or when.group(2)) if when else None,
            "overall_score": float(score.group(2)) if score else None, "scale_max": float(score.group(1)) if score else None}


# ---- an equivalency certificate -------------------------------------------------------------------------------------------

def equivalency_cert(text: str, applicant: str = "") -> dict:
    flat = _flat(text)
    q = re.search(r"Qualification\s+(.+?)\s+Awarding institution", flat)
    i = re.search(r"Awarding institution\s+(.+?)\s+Date of award", flat)
    d = re.search(rf"Date of award\s+({DATE})", flat)
    return {"qualification": _clean(q.group(1)) if q else None, "institution": _clean(i.group(1)) if i else None,
            "date_of_award": _date(d.group(1)) if d else None}


# ---- an employment contract -----------------------------------------------------------------------------------------------

def employment_doc(text: str, applicant: str = "") -> dict:
    lines = _clean_lines(text)
    flat = _flat(text)
    pos = re.search(r"employed as (.+?) in the", flat)
    emp = re.search(r'between (.+?) \(the\s*["“”]?Employer["“”]?\)', flat)
    employer_name = _clean(emp.group(1)) if emp else None
    country = next((x for x in lines[:3] if re.fullmatch(r"[A-Za-z ]{3,30}", x) and len(x.split()) <= 3
                    and (not employer_name or x.casefold() != employer_name.casefold())), None)
    start = re.search(rf"starts on ({DATE})", flat, re.I)
    end = re.search(rf"ends on ({DATE})", flat, re.I)
    return {"position": _clean(pos.group(1)) if pos else None, "employer": _clean(emp.group(1)) if emp else None, "country": _clean(country),
            "date_from": _date(start.group(1)) if start else None, "date_to": _date(end.group(1)) if end else None}


# ---- a recommendation letter ----------------------------------------------------------------------------------------------

def recommendation_letter(text: str, applicant: str = "") -> dict:
    lines = _clean_lines(text)
    flat = _flat(text)
    rel = next((s for s in re.split(r"(?<!\bDr\.)(?<!\bProf\.)(?<!\bMr\.)(?<!\bMrs\.)(?<!\bMs\.)(?<=[.!?])\s+", flat)
                if re.search(r"\bI\b.*\b(supervis|collaborat|colleague|co-author|mentor|worked|known|taught)", s)), None)
    return {"writer_name": _clean(lines[0]) if lines else None, "writer_institution": _clean(lines[1]) if len(lines) > 1 else None,
            "writer_rank": _clean(lines[2]) if len(lines) > 2 else None, "relationship": _clean(rel)}


# ---- a syllabus -----------------------------------------------------------------------------------------------------------

def syllabus(text: str, applicant: str = "") -> dict:
    flat = _flat(text)
    code = re.search(r"Course Syllabus\s*[-–]\s*([A-Z]{2,5}\s?\d{3})", flat) or re.search(r"\bCourse\s+([A-Z]{2,5}\s?\d{3})\b", flat)
    term = re.search(r"Semester\s+((?:Fall|Spring|Summer)\s*\d{4})", flat)
    return {"course_code": _clean(code.group(1)) if code else None, "term": _clean(term.group(1)) if term else None}


# ---- signed documents (CV, conditions form, cover letter) -----------------------------------------------------------------

def signed_date(text: str, applicant: str = "") -> dict:
    flat = _flat(text)
    labelled = re.search(rf"(?:Last updated|Date|Dated|Signed on|Signed)[:\s]+({DATE})", flat, re.I)
    if labelled:
        return {"signed_date": _date(labelled.group(1))}
    first = re.search(rf"({DATE})", flat[:1200])
    return {"signed_date": _date(first.group(1)) if first else None}


# ---- the Scopus profile screenshot (OCR text) -----------------------------------------------------------------------------

def scopus_profile(text: str, applicant: str = "") -> dict:
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    flat = _flat(text)
    values: dict[str, int] = {}
    # A profile page shows its tiles as a row of labels followed by a row of numbers ("Documents", "Citations", "h-index", then 24, 468, 12):
    # the first run of label lines owns the next run of number lines, in the same order.
    label = re.compile(r"(documents|citations|h[- ]?index|co-?authors)", re.I)
    start = next((i for i, x in enumerate(lines) if label.fullmatch(x)), None)
    if start is not None:
        run = []
        for x in lines[start:]:
            if not label.fullmatch(x):
                break
            run.append("h_index" if x.lower().startswith("h") else x.lower().replace("-", ""))
        numbers = [x for x in lines[start + len(run):start + len(run) + 3 * len(run)] if re.fullmatch(r"[\d,]+", x)][:len(run)]
        values = {k: int(v.replace(",", "")) for k, v in zip(run, numbers)}
    if "h_index" not in values:                                               # the label and its number on one line
        h = re.search(r"h[- ]?index\D{0,12}(\d{1,3})", flat, re.I) or re.search(r"(\d{1,3})\s*h[- ]?index", flat, re.I)
        values.update({"h_index": int(h.group(1))} if h else {})
    if "citations" not in values:
        c = re.search(r"citations?\D{0,12}([\d,]{1,7})", flat, re.I) or re.search(r"([\d,]{1,7})\s*citations?", flat, re.I)
        values.update({"citations": int(c.group(1).replace(",", ""))} if c else {})
    when = re.search(rf"as of\s+({DATE})", flat, re.I) or re.search(rf"({DATE})", " ".join(lines[:6]))
    return {"h_index": values.get("h_index"), "total_citations": values.get("citations"), "screenshot_date": _date(when.group(1)) if when else None}


# ---- a patent grant certificate -------------------------------------------------------------------------------------------------------

_OFFICES = (r"United States Patent and Trademark Office", r"\bUSPTO\b", r"European Patent Office", r"\bEPO\b", r"Ministry of Economy",
            r"World Intellectual Property Organi[sz]ation", r"\bWIPO\b", r"Patent Cooperation Treaty", r"UK Intellectual Property Office",
            r"Intellectual Property Office[^.,;]{0,30}", r"Patent Office[^.,;]{0,30}")
_NEXT_LABEL = r"(?=\s+(?:(?:Inventors?|Applicants?|Assignee|Appl\.?|Application|Filed|Patent(?: No| Number)?|Date of|Grant(?:ed)?|Issue[d]?|Title|Abstract|Priority|Examiner)\b|\(\d{2}\))|$)"


def patent_doc(text: str, applicant: str = "") -> dict:
    flat = _flat(text)
    number = (re.search(r"(?:Patent|Pat\.)\s*(?:No\.?|Number|#)\s*[:\-]?\s*([A-Z]{0,3}\s?\d[\d,.\-/]{3,}(?:\s?[A-Z]\d)?)", flat)
              or re.search(r"\b((?:US|EP|WO|AE|GB|CN|JP|KR)\s?[\d,.\-]{5,}\s?[A-Z]\d?)\b", flat))
    title = (re.search(rf"\(54\)\s*(?:Title\s*[:\-]?\s*)?(.+?){_NEXT_LABEL}", flat)
             or re.search(rf"Title(?: of (?:the )?invention)?\s*[:\-]\s*(.+?){_NEXT_LABEL}", flat, re.I))
    inventors = re.search(rf"Inventors?(?:\s*\(s\))?\s*[:\-]?\s*(.+?){_NEXT_LABEL}", flat)
    granted = re.search(rf"(?:Date of Patent|Grant(?:ed)? date|Date of grant|Granted on|Date of issue|Issue date|Issued on)\s*[:\-]?\s*({DATE})", flat, re.I)
    office = next((m.group(0) for p in _OFFICES if (m := re.search(p, flat, re.I))), None)
    status = "granted" if granted or re.search(r"\b(?:letters patent|patent certificate|is hereby granted|has been granted|granted)\b", flat, re.I) \
        else "filed" if re.search(r"\b(?:application|filed|pending)\b", flat, re.I) else None
    names = re.split(r"\s*;\s*|\s+and\s+", inventors.group(1)) if inventors else []
    if inventors and len(names) == 1:                                           # "A. Name, B. Name" with no semicolon
        names = re.split(r"\s*,\s*(?=[A-Z][a-z]+ [A-Z])", inventors.group(1))
    names = [re.sub(r",\s*[A-Za-z .\-]+\s*\([A-Z]{2}\)\s*$", "", n) for n in names]        # "Nadia Karimi, Sharjah (AE)" -> "Nadia Karimi"
    return {"title": _clean(title.group(1)) if title else None, "patent_number": _clean(number.group(1)) if number else None,
            "office": _clean(office), "status": status, "grant_date": _date(granted.group(1)) if granted else None,
            "inventors": [n.strip(" ,;.") for n in names if n.strip(" ,;.")]}


# ---- a creative or studio work: catalogue, programme or approval letter ----------------------------------------------------------------

def creative_doc(text: str, applicant: str = "") -> dict:
    flat = _flat(text)
    quoted = re.search(r'["“”]\s*(.+?)\s*["“”]', flat)
    days = re.search(rf"(?:from|between)\s+(\d{{1,2}})(?:st|nd|rd|th)?\s*(?:to|-|–|until|and)\s*({DATE})", flat, re.I)
    span = re.search(rf"(?:from|between)\s+({DATE})\s*(?:to|-|–|until|and)\s*({DATE})", flat, re.I)
    single = re.search(rf"(?:held|performed|screened|opened|exhibited|displayed|presented)\s+(?:on\s+)?({DATE})", flat, re.I) or re.search(rf"\b({DATE})\b", flat)
    if span:
        date_from, date_to = _date(span.group(1)), _date(span.group(2))
    elif days:
        end = _date(days.group(2))
        month_year = re.search(r"([A-Za-z]+\.?\s*\d{4})$", end or "")
        date_from, date_to = (f"{days.group(1)} {month_year.group(1)}" if month_year else None), end
    else:
        date_from, date_to = (_date(single.group(1)) if single else None), None
    unquoted = re.sub(r'["“”].+?["“”]', " ", flat)
    venue = re.search(r"(?:held|performed|exhibited|shown|screened|displayed|presented|staged)\s+(?:\w+\s+){0,3}?(?:at|in)\s+(?:the\s+)?(.+?)"
                      r"(?=,?\s+(?:from|between|on|during|organi[sz]ed|curated|and\b)|[.;]|$)", unquoted, re.I)
    organiser = re.search(r"(?:organi[sz]ed|curated|hosted|presented|produced)\s+by\s+(.+?)(?=\s*(?:[.;]|,\s+(?:from|between|on)|\s+(?:from|between|on)\b)|$)", flat, re.I)
    approved = True if re.search(r"approved\s+(?:\w+\s+){0,4}as\s+(?:an?\s+)?(?:\w+\s+){0,2}(?:creative|artistic|original|studio)", flat, re.I) else None
    kind = next((name for name, words in (("exhibition", r"exhibition|exhibited|gallery|biennial"), ("performance", r"perform|concert|theatre|theater|recital|staged"),
                                         ("design", r"design"), ("media", r"film|video|documentary|broadcast|screened|media production")) if re.search(words, flat, re.I)), None)
    return {"title": _clean(quoted.group(1)) if quoted else None, "form": kind, "venue": _clean(re.sub(r"(?i)^the\s+", "", venue.group(1))) if venue else None,
            "organizing_institution": _clean(re.sub(r"(?i)^the\s+", "", organiser.group(1))) if organiser else None, "date_from": date_from, "date_to": date_to, "approved": approved}


RULES = {"paper": paper_doc, "acceptance": acceptance_letter, "book": book_chapter, "conference": conference_paper, "funded": funded_project,
         "peer": peer_observation, "equivalency": equivalency_cert, "position": employment_doc, "letter": recommendation_letter,
         "syllabus": syllabus, "signed": signed_date, "scopus": scopus_profile, "patent": patent_doc, "creative": creative_doc}
REQUIRED = {"paper": ("title", "journal_name"), "acceptance": ("title", "journal_name", "acceptance_date"), "book": ("book_title", "chapter_title"),
            "conference": ("title", "conference_title", "conference_date"), "funded": ("title", "funding_body", "start_date"),
            "peer": ("course_code", "observation_date"), "equivalency": ("qualification", "date_of_award"), "position": ("position", "employer", "date_from"),
            "letter": ("writer_name",), "syllabus": ("course_code", "term"), "signed": ("signed_date",), "scopus": ("h_index",), "patent": ("title", "patent_number"), "creative": ("title", "date_from")}

RL.RULES.update(RULES)
RL.REQUIRED.update(REQUIRED)
RL.NEEDS_APPLICANT.update({"funded"})
