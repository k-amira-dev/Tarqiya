"""Reading whole documents with the model: the reader, the checks on its answer, the privacy step, and saving as entries.
A fake model stands in for Groq, so nothing here costs money or needs a key."""
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from promoflow.db.models import User
from promoflow.dossier import section0 as s0
from promoflow.dossier.section6 import advising as s6e
from promoflow.dossier.section6 import courses as s6a
from promoflow.dossier.section6 import imports, satisfaction as s6c
from promoflow.extraction import doc_llm, teaching_docs as T
from tests.test_eligibility_checker import ON, S0_VALUES


class FakeLLM:
    """Looks like the real model: .with_structured_output(...).invoke(...) -> {"raw", "parsed"}. `answers` are returned or raised in turn."""
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), 0

    def with_structured_output(self, schema, method=None, include_raw=False):
        return self

    def invoke(self, messages):
        self.calls += 1
        a = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(a, Exception):
            raise a
        return {"raw": SimpleNamespace(usage_metadata={"input_tokens": 1000, "output_tokens": 500}), "parsed": a, "parsing_error": None}


# ---- helpers ---------------------------------------------------------------------------------------------------------

def test_semester_and_course_helpers():
    assert T.parse_semester("Fall 2018") == ("2018/2019", "fall")
    assert T.parse_semester("Spring\n2019") == ("2018/2019", "spring")
    assert T.parse_semester("nonsense") is None
    assert T.term_index("2018/2019", "fall") + 1 == T.term_index("2018/2019", "spring")      # spring follows fall
    assert T.term_index("2018/2019", "spring") + 1 == T.term_index("2019/2020", "fall")
    assert T.norm_code("mcom201") == "MCOM 201" and T.norm_code("MCOM   310") == "MCOM 310"
    assert (T.level_for("MCOM 201"), T.level_for("MCOM 520")) == ("undergraduate", "graduate")


# ---- the reader ------------------------------------------------------------------------------------------------------

def test_reader_returns_the_answer_and_the_tokens_used():
    answer = T.RegistrarReport(stated_sections=1, stated_enrolments=26, rows=[T.RegRow(semester="Fall 2018", course_code="MCOM 201", course_title="Intro", crn=10247, students=26)])
    parsed, usage = doc_llm.read_document("some text", T.RegistrarReport, FakeLLM(answer))
    assert parsed is answer and (usage.input_tokens, usage.output_tokens) == (1000, 500) and usage.cost_usd > 0


def test_reader_retries_when_the_provider_says_too_many_tokens(monkeypatch):
    monkeypatch.setattr(doc_llm.time, "sleep", lambda s: None)
    answer = T.RegistrarReport(stated_sections=None, stated_enrolments=None, rows=[])
    llm = FakeLLM(RuntimeError("RateLimitError 429 rate_limit_exceeded: please try again in 3.5s"), answer)
    parsed, _ = doc_llm.read_document("text", T.RegistrarReport, llm)
    assert parsed is answer and llm.calls == 2


def test_reader_gives_a_plain_error_when_it_cannot_continue(monkeypatch):
    monkeypatch.setattr(doc_llm.time, "sleep", lambda s: None)
    with pytest.raises(doc_llm.ReadFailed, match="enter the values by hand"):
        doc_llm.read_document("text", T.RegistrarReport, FakeLLM(ConnectionError("network down")))
    with pytest.raises(doc_llm.ReadFailed, match="no text"):
        doc_llm.read_document("   ", T.RegistrarReport, FakeLLM())


# ---- 17: registrar report --------------------------------------------------------------------------------------------

def reg(rows, sections=None, enrolments=None):
    return T.RegistrarReport(stated_sections=sections, stated_enrolments=enrolments, rows=[T.RegRow(**r) for r in rows])


ROW = dict(semester="Fall 2018", course_code="MCOM 201", course_title="Intro to Mass Communication", crn=10247, students=26)


def test_registrar_rows_become_course_drafts():
    drafts, notes = T.build_course_drafts(reg([ROW, dict(ROW, semester="Spring 2019", course_code="mcom520", course_title="Research Methods", students=12)], 2, 38))
    assert [(d.academic_year, d.semester, d.course_code, d.level) for d in drafts] == [
        ("2018/2019", "fall", "MCOM 201", "undergraduate"), ("2018/2019", "spring", "MCOM 520", "graduate")]
    assert notes == [] and all(d.ok for d in drafts)


def test_registrar_checks_use_the_totals_printed_in_the_document():
    drafts, notes = T.build_course_drafts(reg([ROW], sections=64, enrolments=2202))
    assert any("64 course sections, but 1 rows" in n for n in notes) and any("2202" in n and "26" in n for n in notes)


def test_registrar_flags_duplicates_and_unreadable_rows():
    drafts, _ = T.build_course_drafts(reg([ROW, dict(ROW), dict(ROW, semester="Autumn", course_code="MCOM 230"), dict(ROW, course_code="MCOM 310", students=None)]))
    assert drafts[0].ok and "twice" in drafts[1].issues[0] and "not understood" in drafts[2].issues[0] and "students missing" in drafts[3].issues[0]


# ---- 19: student evaluation report -----------------------------------------------------------------------------------

COURSES = [SimpleNamespace(id=7, academic_year="2018/2019", semester=SimpleNamespace(value="fall"), course_code="MCOM 201", students=26)]
EV = dict(semester="Fall 2018", course_code="MCOM 201", crn=10247, students=26, responses=20, instructor=4.36, department=4.21, college=4.10, university=4.05, difference=0.31)


def evals(rows, scale=5.0):
    return T.StudentEvaluations(scale_max=scale, rows=[T.EvalRow(**r) for r in rows])


def test_evaluation_rows_are_matched_to_the_applicants_courses():
    drafts, notes = T.build_sat_drafts(evals([EV]), COURSES)
    d = drafts[0]
    assert d.ok and notes == [] and (d.course_taught_id, d.respondents, d.average_score, d.scale_max) == (7, 20, 4.36, 5.0)


def test_evaluation_problems_are_reported_per_row():
    bad = [dict(EV, course_code="MCOM 999"), dict(EV, responses=None), dict(EV, responses=40), dict(EV, instructor=6.2), dict(EV, difference=0.9)]
    drafts, _ = T.build_sat_drafts(evals(bad), COURSES)
    text = [" | ".join(d.issues) for d in drafts]
    assert "not in your list" in text[0] and "how many students answered" in text[1] and "more responses" in text[2]
    assert "outside the scale" in text[3] and "difference column" in text[4]
    assert not any(d.ok for d in drafts)


def test_missing_scale_is_noted_and_can_be_entered():
    _, notes = T.build_sat_drafts(evals([EV], scale=None), COURSES)
    assert "scale" in notes[0]
    drafts, notes = T.build_sat_drafts(evals([EV], scale=None), COURSES, scale_override=5.0)
    assert notes == [] and drafts[0].scale_max == 5.0


def test_the_scale_is_found_in_the_text_when_the_model_misses_it():
    assert T.scale_from_text("Scores are the mean of student ratings on a scale from 1 to 5. The last column") == 5.0
    assert T.scale_from_text("Average rating 4.2 out of 10") == 10.0 and T.scale_from_text("no scale mentioned") is None
    llm = FakeLLM(T.StudentEvaluations(scale_max=None, rows=[T.EvalRow(**EV)]))
    res = T.read_student_evaluations("Scores ... on a scale from 1 to 5.", COURSES, llm)
    assert res.drafts[0].scale_max == 5.0 and res.notes == []


# ---- 21: advisee lists -----------------------------------------------------------------------------------------------

LIST_TEXT = """Academic Advising - Advisee List - Spring 2021
# Student
ID
Name College Department CGPA Hours
1 U20185608 Tariq Mansour College of
Communication
Mass Communication 3.65 90 Dean's honour
2 U20182449 Yousef Al-
Mazrouei College of
Communication
Mass Communication 2.57 105 Good standing
Advisees this semester: 2"""


def test_names_and_ids_are_removed_before_reading():
    out = T.redact_advisees(LIST_TEXT)
    for secret in ("U20185608", "U20182449", "Tariq", "Mansour", "Yousef", "Mazrouei"):
        assert secret not in out
    assert T.pseudonym("U20185608") in out and out.count("College of") == 2
    assert T.redact_advisees(LIST_TEXT) == out                       # the same student always gets the same code


def test_a_list_whose_names_cannot_be_removed_is_not_sent():
    with pytest.raises(T.PrivacyError):
        T.redact_advisees("1 U20185608 Tariq Mansour somewhere else entirely")


def adv(semester, rows, meetings=30, stated=None):
    return T.AdviseeList(semester=semester, stated_advisees=stated if stated is not None else len(rows), advising_meetings=meetings,
                         rows=[T.AdvRow(student_id=i, cgpa=c, hours=60, status=st) for i, c, st in rows])


def test_warning_figures_come_from_comparing_consecutive_lists():
    fall = adv("Fall 2020", [("a", 1.8, "Academic probation"), ("b", 1.9, "Academic probation"), ("c", 1.7, "Academic probation"), ("d", 3.0, "Good standing")])
    spring = adv("Spring 2021", [("a", 2.2, "Good standing"), ("b", 1.95, "Academic probation"), ("c", 1.6, "Academic probation"), ("d", 3.1, "Good standing"), ("e", 3.0, "Good standing")])
    drafts = T.build_advising_drafts([("spring.pdf", b"2", spring), ("fall.pdf", b"1", fall)])
    assert [d.label for d in drafts] == ["Fall 2020", "Spring 2021"]                 # put in time order
    first, second = drafts
    assert second.ok is True and (second.advisees, second.on_warning_at_start, second.cleared_warning, second.improved_gpa) == (5, 3, 1, 1)
    assert second.on_probation_now == 2
    assert first.on_warning_at_start is None and "previous semester" in first.issues[0]      # nothing before it: the applicant fills in


def test_advisee_count_must_match_the_list():
    d = T.build_advising_drafts([("a.pdf", b"x", adv("Fall 2020", [("a", 3.0, "Good standing")], stated=21))])[0]
    assert any("21 advisees, but 1 rows" in i for i in d.issues)


# ---- saving as entries -----------------------------------------------------------------------------------------------

def make_case(app_env) -> int:
    with app_env.session_scope() as s:
        uid = s.scalar(select(User.id).where(User.email == "applicant@promoflow.test"))
        s0.save(s, uid, dict(S0_VALUES), ON)
        return uid


def test_importing_courses_twice_adds_them_once(app_env):
    uid = make_case(app_env)
    drafts, _ = T.build_course_drafts(reg([ROW, dict(ROW, semester="Spring 2019", course_code="MCOM 230", course_title="Media Writing")]))
    with app_env.session_scope() as s:
        first = imports.add_courses(s, uid, drafts, ("report.pdf", b"%PDF"))
    with app_env.session_scope() as s:
        second = imports.add_courses(s, uid, drafts, ("report.pdf", b"%PDF"))
        courses = s6a.load(s, s0.active_case(s, uid).id)
    assert (first.added, first.skipped_existing) == (2, 0) and (second.added, second.skipped_existing) == (0, 2) and len(courses) == 2


def test_importing_evaluations_needs_courses_and_attaches_the_report(app_env):
    uid = make_case(app_env)
    with app_env.session_scope() as s:
        imports.add_courses(s, uid, T.build_course_drafts(reg([ROW]))[0])
        courses = s6a.load(s, s0.active_case(s, uid).id)
        drafts, _ = T.build_sat_drafts(evals([EV, dict(EV, course_code="MCOM 999")]), courses)
        report = imports.add_satisfaction(s, uid, [d for d in drafts if d.ok], ("eval.pdf", b"%PDF-1"))
        rows = s6c.load(s, s0.active_case(s, uid).id)
    assert report.added == 1 and not report.rejected
    assert len(rows) == 1 and float(rows[0].report.average_score) == 4.36 and rows[0].report.respondents == 20 and rows[0].evidence is not None


def test_importing_advising_semesters(app_env):
    uid = make_case(app_env)
    fall = adv("Fall 2020", [("a", 1.8, "Academic probation"), ("b", 3.0, "Good standing")])
    spring = adv("Spring 2021", [("a", 2.2, "Good standing"), ("b", 3.1, "Good standing")])
    drafts = T.build_advising_drafts([("f.pdf", b"1", fall), ("s.pdf", b"2", spring)])
    drafts[0].on_warning_at_start, drafts[0].cleared_warning, drafts[0].improved_gpa = 0, 0, 0     # the applicant fills in the first semester
    with app_env.session_scope() as s:
        out = imports.add_advising(s, uid, drafts)
        rows = s6e.load(s, s0.active_case(s, uid).id)
    assert out.added == 2 and not out.rejected
    spring_row = next(r for r in rows if r.semester.semester.value == "spring").semester
    assert (spring_row.advisees, spring_row.on_warning_at_start, spring_row.cleared_warning, spring_row.improved_gpa) == (2, 1, 1, 0)
