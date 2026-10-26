"""One evidence document = one entry: appointment letters, certificates, decisions (scanned or digital).

For each kind of document this file defines (1) what to read from it, as a small schema, (2) how to turn the answer into the values of
a Section 6 / 7 entry, with a problem list for anything missing or doubtful, and (3) which entry function saves it. The reading itself
is in picture_doc.py. Nothing here touches the database except through `Kind.add`, called by dossier/doc_entries.py.

The model only COPIES what is printed on the page. The decisions that matter (which role, which level, whether it is inside the
university, whether the student graduated) are plain rules below, and every value stays editable in the preview before anything is saved.
"""
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Callable

from pydantic import BaseModel, Field

from promoflow.extraction.doc_llm import ReadFailed, Usage
from promoflow.extraction.picture_doc import read_entry_file


# ---- small helpers -------------------------------------------------------------------------------------------------

_DATE_FORMATS = ("%Y-%m-%d", "%Y-%m", "%d/%m/%Y", "%d.%m.%Y", "%d %B %Y", "%d %b %Y", "%B %d, %Y", "%B %Y", "%b %Y")


def parse_date(text) -> date | None:
    """A date written in any of the common ways ("2022-09-01", "1 September 2022", "14th of November 2022", "11/06/2022")."""
    if isinstance(text, date):
        return text
    if not text or not str(text).strip():
        return None
    cleaned = re.sub(r"(?<=\d)(st|nd|rd|th)\b", "", str(text).strip(), flags=re.I)
    cleaned = re.sub(r"\bof\b", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.")
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def to_number(x, as_int: bool = False):
    try:
        v = Decimal(str(x).replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        return None
    return int(v) if as_int else float(v)


def _has(text: str | None, *words: str) -> bool:
    t = (text or "").lower()
    return any(w in t for w in words)


@dataclass
class Ctx:
    """What the builders need besides the document: who the applicant is, and the dropdown lists (code -> database id, code -> label)."""
    applicant_name: str = ""
    ids: dict = field(default_factory=dict)          # list_code -> {code: id}
    labels: dict = field(default_factory=dict)       # list_code -> {code: label}
    courses: list = field(default_factory=list)      # the applicant's Section 6A courses (id, course_code, academic_year, semester as text)
    journals: dict = field(default_factory=dict)     # normalised journal name -> (issn, publisher), from the journal table
    previously_rejected: bool = False


@dataclass
class EntryDraft:
    kind: str
    filename: str
    data: bytes
    values: dict
    issues: list[str]
    route: str                                        # "text" or "picture": how the document was read

    @property
    def ok(self) -> bool:
        """Ready to add. A note starting with "check:" asks the applicant to look at something but does not block."""
        return not any(not i.startswith("check:") for i in self.issues)


@dataclass
class Col:
    """A column of the preview table. `options` (code -> label) makes it a dropdown; `kind` is text, date, number or select."""
    label: str
    key: str
    kind: str = "text"
    options: dict | None = None
    editable: bool = True


# ---- what to read, per kind of document ----------------------------------------------------------------------------

class CommitteeLetter(BaseModel):
    committee_name: str | None = Field(description="the name of the committee")
    role: str | None = Field(description="the role given to the applicant: member, chair, secretary, rapporteur ...")
    date_from: str | None = Field(description="start of the appointment")
    date_to: str | None = Field(description="end of the appointment; null when it says 'until further notice' or gives no end")
    signer_title: str | None = Field(description="the job title of the person who signed or issued the letter, for example 'Dean, College of Communication'")


class AdminLetter(BaseModel):
    position_title: str | None = Field(description="the administrative position, for example 'Deputy Head of Department'")
    unit: str | None = Field(description="the department, programme or unit the position is in")
    date_from: str | None = Field(description="start of the assignment")
    date_to: str | None = Field(description="end of the assignment; null if open-ended")


class WorkshopCert(BaseModel):
    title: str | None = Field(description="the title of the workshop or event")
    organized_by: str | None = Field(description="the college, centre or organisation that issued the certificate or hosted the event")
    role: str | None = Field(description="the applicant's role, copied as printed, for example 'organiser' or 'organiser and lecturer'")
    activity_date: str | None = Field(description="the date of the event")
    attendees: int | None = Field(description="number of participants, if shown")


class TrainingCert(BaseModel):
    title: str | None = Field(description="the title of the training")
    host_organisation: str | None = Field(description="the organisation that issued the certificate (the host of the training)")
    hours: float | None = Field(description="the length of the training in hours")
    activity_date: str | None = Field(description="the date of the training")


class CommunityLetter(BaseModel):
    organisation: str | None = Field(description="the organisation that issued the letter (the beneficiary)")
    activity_title: str | None = Field(description="the title or name of the activity")
    role: str | None = Field(description="the applicant's role in the activity")
    date_from: str | None = Field(description="start of the activity or period")
    date_to: str | None = Field(description="end of the activity or period (same as the start for a single day)")
    outputs: str | None = Field(description="what was delivered or achieved (sessions, attendees, products), as printed")


class AttendanceCert(BaseModel):
    title: str | None = Field(description="the title of the workshop, seminar or conference attended")
    organiser: str | None = Field(description="who organised it or issued the certificate")
    activity_date: str | None = Field(description="the date it took place")
    hours: float | None = Field(description="training hours, if shown")
    event_type: str | None = Field(description="workshop, seminar or conference, as printed or implied")


class SupervisionDoc(BaseModel):
    student_name: str | None = Field(description="the name of the student (candidate)")
    thesis_title: str | None = Field(description="the title of the thesis")
    degree: str | None = Field(description="the degree, for example Master of Arts or PhD")
    applicant_role: str | None = Field(description="the role the APPLICANT has, as listed (supervisor, chair, co-supervisor ...)")
    studies_began: str | None = Field(description="the date the student's studies began")
    defence_date: str | None = Field(description="the date of the thesis defence, if there was one")
    conferral_date: str | None = Field(description="the date the degree is conferred, if stated")
    outcome: str | None = Field(description="the result, for example PASS, or approved proposal")


# ---- turning the answer into entry values --------------------------------------------------------------------------

def build_committee(p: CommitteeLetter, ctx: Ctx):
    issues, name = [], (p.committee_name or "").strip()
    # The committee's level comes from its name; when the name does not say, from who appointed the member (a Head -> department, a Dean -> college,
    # a Vice President or President -> university).
    level = ("department" if _has(name, "department") else "college" if _has(name, "college") else "university" if _has(name, "university") else
             "department" if _has(p.signer_title, "head of", "department head") else "college" if _has(p.signer_title, "dean") else
             "university" if _has(p.signer_title, "president", "rector", "chancellor", "provost") else None)
    role = "chair" if _has(p.role, "chair") else "secretary" if _has(p.role, "secretar") else "rapporteur" if _has(p.role, "rapporteur") else "member" if _has(p.role, "member") else None
    d_from, d_to = parse_date(p.date_from), parse_date(p.date_to)
    if not name:
        issues.append("committee name not found")
    if level is None:
        issues.append("choose the level (department, college or university)")
    if role is None:
        issues.append("role not understood")
    if d_from is None:
        issues.append("start date not found")
    return {"committee_name": name, "level": level, "role_code": role, "date_from": d_from, "date_to": d_to, "contribution_summary": None}, issues


def build_admin(p: AdminLetter, ctx: Ctx):
    issues, title = [], (p.position_title or "").strip()
    code = ("other" if _has(title, "deputy") else "hod" if _has(title, "head of department", "department head", "chair of department")
            else "vice_dean" if _has(title, "vice dean", "assistant dean") else "dean" if _has(title, "dean")
            else "program_coordinator" if _has(title, "coordinator") else "unit_director" if _has(title, "director") else "other")
    unit = (p.unit or (title.split(",", 1)[1].strip() if "," in title else "")).strip()
    d_from, d_to = parse_date(p.date_from), parse_date(p.date_to)
    if not title:
        issues.append("position not found")
    if not unit:
        issues.append("unit not found")
    if d_from is None:
        issues.append("start date not found")
    return {"position_code": code, "unit": unit, "date_from": d_from, "date_to": d_to}, issues


def build_workshop(p: WorkshopCert, ctx: Ctx):
    issues = []
    both = _has(p.role, "both") or (_has(p.role, "organi") and _has(p.role, "lectur"))
    role = "organiser_and_lecturer" if both else "organiser" if _has(p.role, "organi") else "lecturer" if _has(p.role, "lectur", "speaker", "present") else None
    d = parse_date(p.activity_date)
    # In the app "organised by" is the LEVEL of the organiser: department, college or university.
    level = "department" if _has(p.organized_by, "department") else "college" if _has(p.organized_by, "college", "faculty") else "university" if _has(p.organized_by, "university") else None
    for missing, text in ((not p.title, "title not found"), (level is None, "choose who organised it (department, college or university)"),
                          (role is None, "role not understood"), (d is None, "date not found")):
        if missing:
            issues.append(text)
    return {"title": (p.title or "").strip(), "organized_by": level, "role": role, "activity_date": d,
            "attendees": to_number(p.attendees, True)}, issues


def build_training(p: TrainingCert, ctx: Ctx):
    issues, d = [], parse_date(p.activity_date)
    host = (p.host_organisation or "").strip()
    for missing, text in ((not p.title, "title not found"), (not host, "host not found"), (d is None, "date not found")):
        if missing:
            issues.append(text)
    return {"title": (p.title or "").strip(), "inside_university": _has(host, "sharjah"), "host_organisation": host, "activity_date": d,
            "hours": to_number(p.hours), "participants": None}, issues


def build_community(p: CommunityLetter, ctx: Ctx):
    issues, text = [], f"{p.activity_title or ''} {p.role or ''}"
    code = ("school" if _has(text, "school") else "library" if _has(text, "library") else
            "volunteering" if _has(text, "volunteer") else "public_lecture" if _has(text, "lecture") else
            "media_tv" if _has(text, "television", " tv") else "media_radio" if _has(text, "radio") else "media_press" if _has(text, "interview", "press") else "other")
    d_from = parse_date(p.date_from)
    d_to = parse_date(p.date_to) or d_from
    for missing, msg in ((not p.activity_title, "activity not found"), (not p.organisation, "organisation not found"), (not p.role, "role not found"),
                         (d_from is None, "start date not found"), (not (p.outputs or "").strip(), "nothing delivered is stated: describe it")):
        if missing:
            issues.append(msg)
    return {"activity_type_code": code, "title": (p.activity_title or "").strip(), "beneficiary_organisation": (p.organisation or "").strip(),
            "applicant_role": (p.role or "").strip(), "date_from": d_from, "date_to": d_to, "beneficiaries": None, "deliverables": (p.outputs or "").strip(),
            "measurable_outcome": None, "funded_project_id": None}, issues


def build_development(p: AttendanceCert, ctx: Ctx):
    issues, d = [], parse_date(p.activity_date)
    fmt = "conference" if _has(p.event_type, "conference") or _has(p.title, "conference") else "seminar" if _has(p.event_type, "seminar") else "workshop"
    title = p.title or ""
    topic = ("ai" if _has(title, " ai ", "ai-", "artificial", "ai tools") or title.lower().startswith("ai ") else "assessment" if _has(title, "assess", "rubric")
             else "lms" if _has(title, "blackboard", "lms") else "taskstream" if _has(title, "taskstream") else
             "methods" if _has(title, "teach", "learning", "pedagog", "classroom", "instruction") else "other")
    for missing, msg in ((not p.title, "title not found"), (not p.organiser, "organiser not found"), (d is None, "date not found")):
        if missing:
            issues.append(msg)
    return {"title": title.strip(), "format": fmt, "topic_code": topic, "organizer": (p.organiser or "").strip(), "activity_date": d, "hours": to_number(p.hours)}, issues


def build_supervision(p: SupervisionDoc, ctx: Ctx):
    issues = []
    degree = "phd" if _has(p.degree, "phd", "doctor") else "msc" if _has(p.degree, "master", "msc", "m.a", "m.sc") else None
    role = "associate" if _has(p.applicant_role, "co-", "co ", "associate", "second") else "main" if _has(p.applicant_role, "supervis", "chair", "main", "principal") else None
    started, defence, conferral = parse_date(p.studies_began), parse_date(p.defence_date), parse_date(p.conferral_date)
    graduated = defence is not None and not _has(p.outcome, "fail", "not pass")
    for missing, msg in ((not p.student_name, "student not found"), (not p.thesis_title, "thesis title not found"), (degree is None, "degree not understood"),
                         (role is None, "your role is not clear: choose it"), (started is None, "start date not found")):
        if missing:
            issues.append(msg)
    return {"student_name": (p.student_name or "").strip(), "degree": degree, "role": role, "thesis_title": (p.thesis_title or "").strip(), "start_date": started,
            "status": "graduated" if graduated else "in_progress", "graduation_date": (conferral or defence) if graduated else None}, issues


# ---- the kinds -----------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Kind:
    key: str
    noun: str                                         # "committee appointments"
    schema: type
    build: Callable                                   # (parsed, ctx) -> (values, issues)
    columns: Callable                                 # (ctx) -> list[Col]
    finalize: Callable                                # (values, ctx) -> the values the section's add() expects (codes -> ids)
    hint: Callable = lambda ctx: ""
    max_chars: int | None = None                      # read only the start of a long document (a paper's first page has everything needed)
    rows: str | None = None                           # name of the list in `schema` when ONE document holds SEVERAL entries (build then takes one row)


def _lookup(list_code: str, code_key: str, id_key: str):
    def fin(values, ctx):
        out = {k: v for k, v in values.items() if k != code_key}
        out[id_key] = ctx.ids.get(list_code, {}).get(values.get(code_key))
        return out
    return fin


def _opts(ctx, list_code):
    return dict(ctx.labels.get(list_code, {}))


KINDS: dict[str, Kind] = {
    "committee": Kind("committee", "committee appointments", CommitteeLetter, build_committee,
                      lambda ctx: [Col("Committee", "committee_name"), Col("Level", "level", "select", {"department": "Department", "college": "College", "university": "University"}),
                                   Col("Role", "role_code", "select", _opts(ctx, "committee_role")), Col("From", "date_from", "date"), Col("To", "date_to", "date")],
                      _lookup("committee_role", "role_code", "role_id")),
    "admin": Kind("admin", "administrative appointments", AdminLetter, build_admin,
                  lambda ctx: [Col("Position", "position_code", "select", _opts(ctx, "admin_position")), Col("Unit", "unit"), Col("From", "date_from", "date"), Col("To", "date_to", "date")],
                  _lookup("admin_position", "position_code", "position_id")),
    "workshop": Kind("workshop", "workshops you organised or gave", WorkshopCert, build_workshop,
                     lambda ctx: [Col("Title", "title"), Col("Organised by", "organized_by", "select", {"department": "Department", "college": "College", "university": "University"}),
                                  Col("Your role", "role", "select", {"organiser": "Organiser", "lecturer": "Lecturer", "organiser_and_lecturer": "Organiser and lecturer"}),
                                  Col("Date", "activity_date", "date"), Col("Attendees", "attendees", "number")],
                     lambda v, ctx: dict(v)),
    "training": Kind("training", "trainings you delivered", TrainingCert, build_training,
                     lambda ctx: [Col("Title", "title"), Col("Host", "host_organisation"), Col("Inside the university", "inside_university", "select", {True: "Yes", False: "No"}),
                                  Col("Date", "activity_date", "date"), Col("Hours", "hours", "number")],
                     lambda v, ctx: dict(v)),
    "community": Kind("community", "community activities", CommunityLetter, build_community,
                      lambda ctx: [Col("Type", "activity_type_code", "select", _opts(ctx, "community_activity_type")), Col("Activity", "title"), Col("Organisation", "beneficiary_organisation"),
                                   Col("Your role", "applicant_role"), Col("From", "date_from", "date"), Col("To", "date_to", "date"), Col("What was delivered", "deliverables")],
                      _lookup("community_activity_type", "activity_type_code", "activity_type_id")),
    "development": Kind("development", "workshops and seminars you attended", AttendanceCert, build_development,
                        lambda ctx: [Col("Title", "title"), Col("Type", "format", "select", {"workshop": "Workshop", "seminar": "Seminar", "conference": "Conference"}),
                                     Col("Topic", "topic_code", "select", _opts(ctx, "development_topic")), Col("Organiser", "organizer"), Col("Date", "activity_date", "date"), Col("Hours", "hours", "number")],
                        _lookup("development_topic", "topic_code", "topic_id")),
    "supervision": Kind("supervision", "thesis supervision records", SupervisionDoc, build_supervision,
                        lambda ctx: [Col("Student", "student_name"), Col("Thesis", "thesis_title"), Col("Degree", "degree", "select", {"msc": "MSc", "phd": "PhD"}),
                                     Col("Your role", "role", "select", {"main": "Main supervisor", "associate": "Co-supervisor"}),
                                     Col("Started", "start_date", "date"), Col("Status", "status", "select", {"in_progress": "In progress", "graduated": "Graduated"}),
                                     Col("Graduated", "graduation_date", "date")],
                        lambda v, ctx: dict(v),
                        lambda ctx: f"The applicant is {ctx.applicant_name}. Give applicant_role as the role listed for THIS person."),
}


def read_entries(kind: Kind, filename: str, data: bytes, ctx: Ctx, text_llm, vision_llm) -> tuple[list[EntryDraft], Usage]:
    """Read one file and return its draft entries (one, or one per row for documents that list several). Raises ReadFailed with a plain message."""
    parsed, usage, route = read_entry_file(data, kind.schema, text_llm, vision_llm, kind.hint(ctx), kind.max_chars)
    if kind.rows:
        built = [kind.build(row, ctx) for row in getattr(parsed, kind.rows)]
        if not built:
            raise ReadFailed("No entries were found in this document.")
    else:
        built = [kind.build(parsed, ctx)]
    return [EntryDraft(kind.key, filename, data, values, issues, route) for values, issues in built], usage


def read_entry(kind: Kind, filename: str, data: bytes, ctx: Ctx, text_llm, vision_llm) -> tuple[EntryDraft, Usage]:
    """Read one file that holds exactly one entry."""
    drafts, usage = read_entries(kind, filename, data, ctx, text_llm, vision_llm)
    return drafts[0], usage


from promoflow.extraction import entry_docs_more  # noqa: E402,F401  (registers the Section 2-8 kinds in KINDS; must come after the definitions above)
