"""The registrar, student-evaluation and advisee reports, the CV's education table and the classification form, read from a text PDF with pdfplumber
tables and plain rules: no model, and a student's name is never read. The tables below are what pdfplumber returned for the pilot dossier's PDFs."""
import pytest

from promoflow.extraction import local_read, rule_reports as RR, teaching_docs as T
from promoflow.extraction.local_read import ReadFailed

REGISTRAR_TABLES = [
    [["Semester", "Course", "CRN", "Number of students"],
     ["Fall 2019", "CS 110 Programming Fundamentals", "10248", "52"],
     ["", "CS 220 Data Structures and Algorithms", "10259", "44"],
     ["Spring 2020", "CS 325 Network Security", "10290", "49"]],
    [["", "CS 340 Machine Learning", "10294", "27"]],                       # the next page: no header, no semester
]
REGISTRAR_TEXT = "Faculty Teaching Load Report\nTotal: 4 course sections in 2 semesters; 172 student enrolments.\nOFFICIAL"

EVAL_TABLES = [[["Semester", "Course", "CRN", "Students", "Responses", "Instructor", "Department average", "College average", "University average",
                 "Difference (instructor - university)"],
                ["Fall 2019", "CS 110 Programming Fundamentals", "10248", "52", "41", "4.26", "4.09", "4.19", "4.08", "+0.18"],
                ["", "CS 310 Computer Networks", "10262", "50", "45", "4.08", "4.10", "4.06", "4.10", "-0.02"]]]
EVAL_TEXT = "Scores are the mean of student ratings on a scale from 1 to 5."

SECRET = "Nasser Hassan"
ADVISEE_TABLES = [[["#", "Student ID", "Name", "College", "Department", "CGPA", "Hours completed", "Academic status"],
                   ["1", "U20195952", SECRET, "College of Computing and Informatics", "Computer Science", "3.45", "60", "Good standing"],
                   ["2", "U20195970", "Reem Al-Suwaidi", "College of Computing and Informatics", "Information Systems", "1.99", "30", "Academic probation"]]]
ADVISEE_TEXT = "Academic Advising - Advisee List - Spring 2020\nAdvisees this semester: 2 | Advising meetings recorded: 30"

CV_TABLES = [[["Degree", "Field", "Institution", "Years", "Thesis"],
              ["Doctor of Philosophy", "Computer Science", "Westmarch University, Australia", "2012- 2016", "Learning-Based Anomaly Detection"],
              ["Master of Science", "Computer Science (Networking)", "Northfield Institute of Technology, Canada", "2008- 2010", "Adaptive Congestion Control"]],
             [["Role", "Grant", "Years", "Amount"], ["PI", "A grant", "2020", "100"]]]          # a later table of the CV must not be mixed in

FORM_TABLES = [[["Notes", "Classification", "Impact Factor", "Criteria", "Publisher", "Journal's Name"],
                ["garbled arabic header cells", "", "", "", "", ""],
                ["https://meridian.example/jnis", "Q1", "SJR 1.214", "✓", "Meridian Academic Publishers", "Journal of Network and Intelligent Systems"],
                ["https://x.example/y", "Q3-B", "SJR 0.2", "✓", "Brightwater", "Computer Networks and Security Letters"]]]


@pytest.fixture
def pdf(monkeypatch):
    def feed(tables, text=""):
        monkeypatch.setattr(local_read, "tables", lambda data, max_pages=40: tables)
        monkeypatch.setattr(local_read, "layout_text", lambda data, max_pages=40: text)
    return feed


def test_registrar_rows_are_joined_across_pages_with_the_semester_carried_down(pdf):
    pdf(REGISTRAR_TABLES, REGISTRAR_TEXT)
    r = RR.registrar(b"x")
    assert [(x.semester, x.course_code, x.crn, x.students) for x in r.rows] == [
        ("Fall 2019", "CS 110", 10248, 52), ("Fall 2019", "CS 220", 10259, 44), ("Spring 2020", "CS 325", 10290, 49), ("Spring 2020", "CS 340", 10294, 27)]
    assert r.rows[1].course_title == "Data Structures and Algorithms" and (r.stated_sections, r.stated_enrolments) == (4, 172)


def test_the_documents_own_totals_check_the_read(pdf):
    pdf(REGISTRAR_TABLES, REGISTRAR_TEXT)
    res = T.read_registrar_report(b"x")
    assert len(res.drafts) == 4 and res.notes == []                                      # 4 sections and 172 enrolments, as printed
    pdf(REGISTRAR_TABLES, REGISTRAR_TEXT.replace("172", "180"))
    assert "172" in " ".join(T.read_registrar_report(b"x").notes)


def test_evaluation_rows_and_scale(pdf):
    pdf(EVAL_TABLES, EVAL_TEXT)
    e = RR.evaluations(b"x")
    assert e.scale_max == 5 and [(x.semester, x.course_code, x.instructor, x.difference) for x in e.rows] == [
        ("Fall 2019", "CS 110", 4.26, 0.18), ("Fall 2019", "CS 310", 4.08, -0.02)]
    assert len(T.read_student_evaluations([], b"x").drafts) == 2


def test_advisee_lists_never_carry_a_student_name_or_id(pdf):
    pdf(ADVISEE_TABLES, ADVISEE_TEXT)
    a = RR.advisees(b"x")
    assert (a.semester, a.stated_advisees, a.advising_meetings, len(a.rows)) == ("Spring 2020", 2, 30, 2)
    assert [(r.cgpa, r.hours, r.status) for r in a.rows] == [(3.45, 60, "Good standing"), (1.99, 30, "Academic probation")]
    dumped = a.model_dump_json()
    assert SECRET not in dumped and "Reem" not in dumped and "U2019" not in dumped        # only anonymous codes (ID-xxxxxxxx) remain
    assert all(r.student_id.startswith("ID-") for r in a.rows)
    name, data, parsed = T.read_advisee_list("a.pdf", b"x")
    assert parsed.stated_advisees == 2


def test_the_cv_education_table_is_the_first_table_only(pdf):
    pdf(CV_TABLES)
    rows = RR.cv_education(b"x")
    assert [(r.degree, r.institution.split(",")[0], r.years) for r in rows] == [
        ("Doctor of Philosophy", "Westmarch University", "2012- 2016"), ("Master of Science", "Northfield Institute of Technology", "2008- 2010")]


def test_the_classification_form_gives_name_and_class_per_journal(pdf):
    pdf(FORM_TABLES)
    form = RR.classification_form(b"x")
    assert [(j.journal_name, j.classification) for j in form.journals] == [
        ("Journal of Network and Intelligent Systems", "Q1"), ("Computer Networks and Security Letters", "Q3-B")]


def test_a_report_with_no_known_table_is_left_to_the_applicant(pdf):
    pdf([], "")
    for call in (lambda: T.read_registrar_report(b"x"), lambda: T.read_student_evaluations([], b"x"), lambda: T.read_advisee_list("a.pdf", b"x")):
        with pytest.raises(ReadFailed, match="enter the values by hand"):
            call()
    assert RR.cv_education(b"x") is None and RR.classification_form(b"x") is None
