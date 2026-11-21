"""Reading three kinds of Section 6 documents (pdfplumber tables and plain rules, see rule_reports.py) and CHECKING what comes back:

  * the registrar teaching-load report  -> the course list of 6A
  * the student evaluation report       -> the student satisfaction entries of 6C
  * the academic advisee lists          -> the advising semesters of 6E (a student's name is never read: only an anonymous code, the CGPA,
                                           the hours and the status)

Everything that decides whether a row can be trusted is plain code here: the document's own printed totals, impossible values, duplicates, and
matching to courses the applicant already entered. A row with a problem is shown to the applicant with the reason, and is not saved unless the
applicant fixes it. Nothing here touches the database.
"""
import hashlib
import re
from dataclasses import dataclass, field

from pydantic import BaseModel

from promoflow.extraction import rule_reports
from promoflow.extraction.local_read import ReadFailed

SEMESTER = re.compile(r"(fall|spring|summer)\s*(\d{4})", re.I)


# ---- small helpers -------------------------------------------------------------------------------------------------

def parse_semester(label: str | None) -> tuple[str, str] | None:
    """"Fall 2018" -> ("2018/2019", "fall"); "Spring 2019" -> ("2018/2019", "spring"). None if it cannot be read."""
    m = SEMESTER.search(label or "")
    if not m:
        return None
    term, year = m.group(1).lower(), int(m.group(2))
    return (f"{year}/{year + 1}" if term == "fall" else f"{year - 1}/{year}"), term


def term_index(academic_year: str, semester: str) -> int | None:
    """A number that grows by 1 from one teaching term to the next (spring Y comes just before fall Y). Summer is not supported."""
    start = int(academic_year[:4])
    return {"fall": 2 * start, "spring": 2 * (start + 1) - 1}.get(semester)


def norm_code(code: str | None) -> str:
    """"mcom201" / "MCOM  201" -> "MCOM 201" (letters, one space, digits)."""
    c = re.sub(r"\s+", "", code or "").upper()
    m = re.match(r"^([A-Z]+)(\d.*)$", c)
    return f"{m.group(1)} {m.group(2)}" if m else c


def level_for(code: str) -> str:
    """Course numbers of 500 and above are graduate courses (an assumption the applicant can change after import)."""
    m = re.search(r"(\d)\d{2,3}", code or "")
    return "graduate" if m and int(m.group(1)) >= 5 else "undergraduate"


def _status_is_warning(status: str) -> bool:
    s = status.lower()
    return "probation" in s or "warning" in s


# ===== 17: registrar teaching-load report ===========================================================================

class RegRow(BaseModel):
    semester: str                 # as printed, e.g. "Fall 2018"
    course_code: str
    course_title: str
    crn: int | None
    students: int | None


class RegistrarReport(BaseModel):
    stated_sections: int | None   # "Total: 64 course sections ..."
    stated_enrolments: int | None
    rows: list[RegRow]


@dataclass
class CourseDraft:
    academic_year: str | None
    semester: str | None
    course_code: str
    course_title: str
    level: str
    students: int | None
    crn: int | None
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


@dataclass
class ReadResult:
    drafts: list
    notes: list[str]              # problems with the whole document (a total that does not match, ...)


def build_course_drafts(parsed: RegistrarReport) -> tuple[list[CourseDraft], list[str]]:
    drafts, notes, seen = [], [], set()
    for r in parsed.rows:
        sem = parse_semester(r.semester)
        d = CourseDraft(sem[0] if sem else None, sem[1] if sem else None, norm_code(r.course_code), r.course_title.strip(),
                        level_for(r.course_code), r.students, r.crn)
        if sem is None:
            d.issues.append(f"semester '{r.semester}' not understood")
        if r.students is None or r.students < 0:
            d.issues.append("number of students missing")
        key = (d.academic_year, d.semester, d.course_code)
        if key in seen:
            d.issues.append("the same course appears twice in the same semester")
        seen.add(key)
        drafts.append(d)
    if parsed.stated_sections is not None and parsed.stated_sections != len(parsed.rows):
        notes.append(f"The report says {parsed.stated_sections} course sections, but {len(parsed.rows)} rows were read. Check that none is missing.")
    total = sum(r.students or 0 for r in parsed.rows)
    if parsed.stated_enrolments is not None and parsed.stated_enrolments != total:
        notes.append(f"The report says {parsed.stated_enrolments} student enrolments, but the rows add up to {total}. Check the numbers.")
    return drafts, notes


RULES_FAILED = ("The table in this report could not be read (its layout is not one the reader knows, or the file is a scan). "
                "Please enter the values by hand.")


def read_registrar_report(data: bytes) -> ReadResult:
    """Read the report with pdfplumber's tables and plain rules."""
    parsed = rule_reports.registrar(data)
    if parsed is None:
        raise ReadFailed(RULES_FAILED)
    drafts, notes = build_course_drafts(parsed)
    return ReadResult(drafts, notes)


# ===== 19: student evaluation report ================================================================================

class EvalRow(BaseModel):
    semester: str
    course_code: str
    crn: int | None
    students: int | None
    responses: int | None         # number of students who answered, if the report shows it
    instructor: float | None      # the instructor's mean score
    department: float | None
    college: float | None
    university: float | None
    difference: float | None


class StudentEvaluations(BaseModel):
    scale_max: float | None       # "on a scale from 1 to 5" -> 5
    rows: list[EvalRow]


SCALE = re.compile(r"scale\s+(?:of|from)\s+(?:\d+(?:\.\d+)?\s+to\s+)?(\d+(?:\.\d+)?)|out\s+of\s+(\d+(?:\.\d+)?)", re.I)


def scale_from_text(text: str) -> float | None:
    """The top of the scale when the document states it in words ("on a scale from 1 to 5", "out of 5"). A safety net for the model's answer."""
    m = SCALE.search(text)
    return float(m.group(1) or m.group(2)) if m else None


@dataclass
class SatDraft:
    course_taught_id: int | None
    label: str                    # the course as shown to the applicant
    academic_year: str | None
    semester: str | None
    course_code: str
    students: int | None
    respondents: int | None
    average_score: float | None
    scale_max: float | None
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def build_sat_drafts(parsed: StudentEvaluations, courses: list, scale_override: float | None = None) -> tuple[list[SatDraft], list[str]]:
    """`courses` = the applicant's 6A courses (anything with .id, .academic_year, .semester, .course_code, .students)."""
    index = {}
    for c in courses:
        sem = getattr(c.semester, "value", c.semester)
        index.setdefault((c.academic_year, sem, norm_code(c.course_code)), c)
    scale = scale_override or parsed.scale_max
    drafts, notes = [], []
    if scale is None:
        notes.append("The report does not state the scale of the scores (for example 1 to 5). Enter it below.")
    for r in parsed.rows:
        sem = parse_semester(r.semester)
        code = norm_code(r.course_code)
        course = index.get((sem[0], sem[1], code)) if sem else None
        d = SatDraft(course.id if course else None, f"{code} - {r.semester}", sem[0] if sem else None, sem[1] if sem else None, code,
                     course.students if course else r.students, r.responses, r.instructor, scale)
        if sem is None:
            d.issues.append(f"semester '{r.semester}' not understood")
        elif course is None:
            d.issues.append("this course is not in your list yet (add it in 6A first)")
        if r.instructor is None:
            d.issues.append("no instructor score")
        if r.responses is None:
            d.issues.append("the report does not show how many students answered")
        elif d.students is not None and r.responses > d.students:
            d.issues.append(f"more responses ({r.responses}) than students ({d.students})")
        if scale is not None and r.instructor is not None and not (0 <= r.instructor <= scale):
            d.issues.append(f"score {r.instructor:g} is outside the scale 0-{scale:g}")
        if None not in (r.instructor, r.university, r.difference) and abs((r.instructor - r.university) - r.difference) > 0.011:
            d.issues.append("the difference column does not match instructor minus university: check the row")
        drafts.append(d)
    return drafts, notes


def read_student_evaluations(courses: list, data: bytes, scale_override: float | None = None) -> ReadResult:
    parsed = rule_reports.evaluations(data)              # pdfplumber tables and plain rules
    if parsed is None:
        raise ReadFailed(RULES_FAILED)
    drafts, notes = build_sat_drafts(parsed, courses, scale_override)
    return ReadResult(drafts, notes)


# ===== 21: advisee lists (names and IDs are removed before reading) ==================================================

def pseudonym(student_id: str) -> str:
    """The same student always gets the same code, so a student can be followed from one semester's list to the next."""
    return "ID-" + hashlib.sha256(("promoflow-advisees:" + student_id).encode()).hexdigest()[:8]


class AdvRow(BaseModel):
    student_id: str               # the anonymous code
    cgpa: float | None
    hours: int | None
    status: str


class AdviseeList(BaseModel):
    semester: str
    stated_advisees: int | None   # "Advisees this semester: 21"
    advising_meetings: int | None
    rows: list[AdvRow]


@dataclass
class AdvisingDraft:
    filename: str
    data: bytes
    label: str
    academic_year: str | None
    semester: str | None
    advisees: int
    meetings_held: int | None
    on_warning_at_start: int | None
    cleared_warning: int | None
    improved_gpa: int | None
    on_probation_now: int
    issues: list[str] = field(default_factory=list)
    rows: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def build_advising_drafts(items: list[tuple[str, bytes, AdviseeList]]) -> list[AdvisingDraft]:
    """One draft per list, in time order. The three warning figures come from comparing a semester's list with the PREVIOUS semester's
    (same students, followed by their anonymous codes), using the app's definitions:
    on warning at the start = on probation in the previous list and still an advisee; cleared = no longer on probation;
    improved GPA = still on probation but with a higher CGPA than before."""
    drafts = []
    for filename, data, lst in items:
        sem = parse_semester(lst.semester)
        d = AdvisingDraft(filename, data, lst.semester, sem[0] if sem else None, sem[1] if sem else None, len(lst.rows), lst.advising_meetings,
                          None, None, None, sum(1 for r in lst.rows if _status_is_warning(r.status)), rows=lst.rows)
        if sem is None or term_index(*sem) is None:
            d.issues.append(f"semester '{lst.semester}' not understood (only Fall and Spring lists are supported)")
        if lst.stated_advisees is not None and lst.stated_advisees != len(lst.rows):
            d.issues.append(f"the list says {lst.stated_advisees} advisees, but {len(lst.rows)} rows were read")
        if lst.advising_meetings is None:
            d.issues.append("the number of advising meetings is not shown: enter it")
        drafts.append(d)
    by_term = {term_index(d.academic_year, d.semester): d for d in drafts if d.academic_year and term_index(d.academic_year, d.semester) is not None}
    for d in drafts:
        idx = term_index(d.academic_year, d.semester) if d.academic_year else None
        prev = by_term.get(idx - 1) if idx is not None else None
        if prev is None:
            d.issues.append("the previous semester's list was not uploaded with this one, so the warning figures cannot be worked out: enter them "
                            "(use 0 if this is your first semester)")
            continue
        before = {r.student_id: r for r in prev.rows}
        warned = [r for r in d.rows if r.student_id in before and _status_is_warning(before[r.student_id].status)]
        d.on_warning_at_start = len(warned)
        d.cleared_warning = sum(1 for r in warned if not _status_is_warning(r.status))
        d.improved_gpa = sum(1 for r in warned if _status_is_warning(r.status) and r.cgpa is not None
                             and before[r.student_id].cgpa is not None and r.cgpa > before[r.student_id].cgpa)
    return sorted(drafts, key=lambda d: (term_index(d.academic_year, d.semester) if d.academic_year and term_index(d.academic_year, d.semester) is not None else 10 ** 9))


def read_advisee_list(filename: str, data: bytes) -> tuple[str, bytes, AdviseeList]:
    """Read one list with pdfplumber's table and return it ready for build_advising_drafts(). The student's name is never read: only an anonymous
    code, the CGPA, the hours and the status are kept."""
    parsed = rule_reports.advisees(data)
    if parsed is None:
        raise ReadFailed(RULES_FAILED)
    return filename, data, parsed
