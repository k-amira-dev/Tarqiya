"""Read the three Section 6 reports from a text PDF with pdfplumber's tables and plain rules: NO model, no tokens, and nothing leaves the machine.

  * registrar teaching-load report -> RegistrarReport     (course list, 6A)
  * student evaluation report      -> StudentEvaluations  (satisfaction scores, 6C)
  * academic advisee lists         -> AdviseeList         (advising, 6E; the student's name is never even read: only an anonymous code,
                                                           the CGPA, the hours and the status are kept)

Each function returns the SAME object the language model used to return (the schemas in teaching_docs.py), or None when the document has no
table it recognises. teaching_docs.py then runs the same checks as before (the report's own printed totals, the difference column, the advisee
count), so a wrong read shows up as a note for the applicant rather than as a silent error.
"""
import re

from promoflow.extraction import local_read

_COURSE = re.compile(r"^([A-Za-z]{2,5})\s?(\d{3,4}[A-Za-z]?)\s+(.+)$")
_ID = re.compile(r"^[A-Z]{1,2}\d{7,9}$")


def _num(cell: str | None, as_int: bool = False):
    cell = (cell or "").replace(",", "").replace("+", "").strip()
    try:
        return int(float(cell)) if as_int else float(cell)
    except ValueError:
        return None


def _header_index(rows: list[list[str]], *names: str) -> int | None:
    """Where the header row is: the first row whose cells contain all the given words (case-insensitive)."""
    for i, row in enumerate(rows):
        joined = " ".join(row).lower()
        if all(n in joined for n in names):
            return i
    return None


def _data_rows(data: bytes, *header_words: str) -> list[list[str]]:
    """Every data row of every table whose header contains `header_words`, across pages. A table that continues on the next page (with or
    without a repeated header) is joined; header rows are dropped."""
    out = []
    for table in local_read.tables(data):
        i = _header_index(table, *header_words)
        if i is not None:
            out += [r for r in table[i + 1:] if any(c for c in r)]
        elif out:                                          # a continuation page without its own header
            out += [r for r in table if any(c for c in r)]
    return [r for r in out if not _header_index([r], *header_words)]


def _stated(text: str, pattern: str) -> int | None:
    m = re.search(pattern, text, re.I)
    return int(m.group(1).replace(",", "")) if m else None


# ---- 17: registrar teaching-load report --------------------------------------------------------------------------------

def registrar(data: bytes):
    from promoflow.extraction.teaching_docs import RegistrarReport, RegRow

    rows, semester = [], ""
    for r in _data_rows(data, "semester", "course", "crn"):
        if len(r) < 4:
            continue
        semester = r[0] or semester                          # the semester is printed only on the first row of its group
        m = _COURSE.match(r[1])
        if not m or not semester:
            continue
        rows.append(RegRow(semester=semester, course_code=f"{m.group(1).upper()} {m.group(2)}", course_title=m.group(3).strip(),
                           crn=_num(r[2], True), students=_num(r[3], True)))
    if not rows:
        return None
    text = local_read.layout_text(data)
    return RegistrarReport(stated_sections=_stated(text, r"total:?\s*(\d+)\s+course sections"),
                           stated_enrolments=_stated(text, r"([\d,]+)\s+student enrolments"), rows=rows)


# ---- 19: student evaluation report -------------------------------------------------------------------------------------

def evaluations(data: bytes):
    from promoflow.extraction.teaching_docs import EvalRow, StudentEvaluations, scale_from_text

    rows, semester = [], ""
    for r in _data_rows(data, "semester", "course", "instructor"):
        if len(r) < 10:
            continue
        semester = r[0] or semester
        m = _COURSE.match(r[1])
        if not m or not semester:
            continue
        rows.append(EvalRow(semester=semester, course_code=f"{m.group(1).upper()} {m.group(2)}", crn=_num(r[2], True), students=_num(r[3], True),
                            responses=_num(r[4], True), instructor=_num(r[5]), department=_num(r[6]), college=_num(r[7]),
                            university=_num(r[8]), difference=_num(r[9])))
    if not rows:
        return None
    return StudentEvaluations(scale_max=scale_from_text(local_read.layout_text(data)), rows=rows)


# ---- 21: advisee list ---------------------------------------------------------------------------------------------------

def advisees(data: bytes):
    from promoflow.extraction.teaching_docs import AdviseeList, AdvRow, pseudonym

    rows = []
    for r in _data_rows(data, "student", "cgpa"):
        if len(r) < 7 or not _ID.match(r[1].replace(" ", "")):
            continue
        # The student's name (column 2) is deliberately not used. Only an anonymous code, the CGPA, the hours and the status are kept.
        rows.append(AdvRow(student_id=pseudonym(r[1].replace(" ", "")), cgpa=_num(r[-3]), hours=_num(r[-2], True), status=r[-1]))
    if not rows:
        return None
    text = local_read.layout_text(data)
    sem = re.search(r"(fall|spring|summer)\s*(\d{4})", text, re.I)
    return AdviseeList(semester=f"{sem.group(1).capitalize()} {sem.group(2)}" if sem else "",
                       stated_advisees=_stated(text, r"advisees this semester:?\s*(\d+)"),
                       advising_meetings=_stated(text, r"advising meetings recorded:?\s*(\d+)"), rows=rows)


# ---- 20: curriculum development summary (one entry per table row) ---------------------------------------------------------

def _join_split_row(data: bytes, frag: list[str]) -> list[str]:
    """A table row that runs over a page break comes back as two pieces: its first lines are page text outside any table, and its last
    lines are the first row of the next page's table. Put them together from the last course line of the previous page's text."""
    import io

    import pdfplumber
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages[:-1]:
                lines = (page.extract_text() or "").splitlines()
            tail = [ln for ln in lines if re.match(r"[A-Za-z]{2,5}\s?\d{3,4}[A-Za-z]?\s+(?:Modified|New)", ln)]
            if not tail:
                return frag
            first = tail[-1]
            code = re.match(r"([A-Za-z]{2,5}\s?\d{3,4}[A-Za-z]?)\s+(?:Modified|New)", first).group(1)
            year = re.search(r"\b(19|20)\d{2}\b", first)
            nxt = lines[lines.index(first) + 1] if first in lines and lines.index(first) + 1 < len(lines) else ""
            title = re.match(r"([A-Za-z][A-Za-z ]*?)\s+course\b", nxt)
            what = re.search(r"\d{4}\s+(?:Department|College|University)\s+(?:level\s+)?(.+)$", first)
            level = re.search(r"(Department|College|University)", first)
            return [f"{code} {title.group(1) if title else ''} {frag[0]}".replace("  ", " ").strip(),
                    f"Modified an existing course {frag[1]}".strip(), year.group(0) if year else "",
                    f"{level.group(1) + ' level ' if level else ''}{frag[3]}".strip(), f"{what.group(1) if what else ''} {frag[4]}".strip()]
    except Exception:
        return frag


def curriculum(data: bytes):
    from promoflow.extraction.entry_docs_more import CurriculumDoc, CurriculumRow
    from promoflow.extraction.rule_letters import DATE, _date

    rows = []
    for r in _data_rows(data, "course", "contribution", "year"):
        if len(r) < 5:
            continue
        if not _COURSE.match(r[0]) and not (r[2] or "").strip():            # the second half of a row the page break cut in two
            r = _join_split_row(data, r)
        m = _COURSE.match(r[0])
        approved = re.search(rf"({DATE})", r[3])
        level = re.match(r"\s*(\w+)\s+level", r[3], re.I)
        rows.append(CurriculumRow(course_code=f"{m.group(1).upper()} {m.group(2)}" if m else None, course_title=m.group(3).strip() if m else r[0],
                                  contribution=r[1], changes=None, approval_level=f"{level.group(1)} level" if level else r[3],
                                  approval_date=_date(approved.group(1)) if approved else None, what_was_done=r[4]))
    return CurriculumDoc(rows=rows) if rows else None


# ---- the CV's Education table (the study years a degree certificate does not print) -----------------------------------------

def cv_education(data: bytes):
    """The CV's Education table as rows of (degree, institution, years), or None when there is no such table. Only the FIRST table that carries
    the Education header is read: a CV has many other tables (grants, courses taught) that must not be mixed in."""
    from promoflow.extraction.entry_docs_more import CvDegreeRow

    for table in local_read.tables(data):
        i = _header_index(table, "degree", "institution", "years")
        if i is not None:
            rows = [CvDegreeRow(degree=r[0], institution=r[2], years=r[3]) for r in table[i + 1:] if len(r) >= 4 and any(r)]
            return rows or None
    return None


# ---- the signed Journals Classification Form -------------------------------------------------------------------------------

_CLASS = re.compile(r"^(Q[1-4](?:\s*-?\s*[AB])?|A|B)\b", re.I)


def classification_form(data: bytes):
    """The journals of the signed classification form (name and class per row) from its table, or None when no row is found. The class is the cell
    that reads Q1, Q3-B, A or B; the English name is the last filled cell of the row."""
    from promoflow.dossier.section5.classification import ClassificationForm, FormJournal

    journals = []
    for r in _data_rows(data, "classification", "journal"):
        cls = next((c for c in r[:3] if _CLASS.match(c.strip())), None)
        name = next((c for c in reversed(r) if c.strip() and not _CLASS.match(c.strip()) and c.strip() not in ("✓", "✔")), None)
        if cls and name:
            journals.append(FormJournal(journal_name=name, journal_name_arabic=None, classification=cls.strip()))
    return ClassificationForm(journals=journals) if journals else None
