"""Reading student-evaluation values from document text (pdfplumber text, plain rules): the rules, the safety checks, course matching."""
from types import SimpleNamespace
from pathlib import Path

import pytest

from promoflow.extraction.local_read import local_text
from promoflow.extraction.student_evaluation import extract_student_evaluation, match_course

FIXTURES = Path(__file__).parent / "fixtures" / "extraction"

B_STYLE = """SIMULATED - FOR TESTING
Student Evaluation Summary (simulated)
Course
ELEC311 Power Systems I (2020/2021 Spring)
Enrolled students: 53
Result
Respondents: 41
Average score: 4.3 out of 5"""


# ---- rules ----------------------------------------------------------------------------------------------------

def test_b_style_document_is_fully_read_by_rules():
    r = extract_student_evaluation(B_STYLE)
    assert r.values() == {"course_code": "ELEC311", "course_title": "Power Systems I", "academic_year": "2020/2021",
                          "semester": "spring", "enrolled": 53, "respondents": 41, "average_score": 4.3,
                          "scale_max": 5.0}
    assert r.respondents.snippet == "Respondents: 41" and r.respondents.source == "rule"
    assert r.missing() == [] and r.warnings == []


def test_real_sample_pdf_end_to_end():
    r = extract_student_evaluation(local_text((FIXTURES / "student_evaluation_b.pdf").read_bytes())[0])
    assert (r.course_code.value, r.respondents.value, r.enrolled.value) == ("ELEC300", 39, 51)
    assert (r.average_score.value, r.scale_max.value) == (4.3, 5.0)


def test_course_file_style_document():
    text = local_text((FIXTURES / "course_file_a.pdf").read_bytes())[0]
    r = extract_student_evaluation(text)
    assert r.course_code.value == "MEC210" and r.course_title.value == "Thermofluids Applications 1"
    assert r.semester.value == "spring"
    assert (r.respondents.value, r.average_score.value, r.scale_max.value) == (35, 4.8, 5.0)


@pytest.mark.parametrize("line,expected", [
    ("Overall rating: 8.7 / 10", (8.7, 10.0)),
    ("Mean rating 3.9 out of 4", (3.9, 4.0)),
    ("Student evaluation: 4.8/5 from 35 respondents", (4.8, 5.0)),
])
def test_score_and_scale_phrasings(line, expected):
    r = extract_student_evaluation(line)
    assert (r.average_score.value, r.scale_max.value) == expected


def test_score_without_scale_leaves_the_scale_for_the_applicant():
    r = extract_student_evaluation("Average score: 4.2\nRespondents: 20")
    assert r.average_score.value == 4.2 and r.scale_max is None and r.missing() == ["scale_max"]


def test_scale_on_its_own_line():
    r = extract_student_evaluation("Average score: 4.2\nScale: 5")
    assert (r.average_score.value, r.scale_max.value) == (4.2, 5.0)


def test_same_value_repeated_is_fine_but_conflicting_values_are_not_guessed():
    same = extract_student_evaluation("Respondents: 41\nTotal respondents: 41")
    assert same.respondents.value == 41
    clash = extract_student_evaluation("Respondents: 41\nRespondents: 9999\nAverage score: 4.3 out of 5")
    assert clash.respondents is None
    assert any("more than one value for respondents" in w for w in clash.warnings)
    assert clash.average_score.value == 4.3      # the other fields are still filled


# ---- safety checks -----------------------------------------------------------------------------------------------

def test_score_above_scale_is_dropped_with_a_warning():
    r = extract_student_evaluation("Average score: 6.1 out of 5")
    assert r.average_score is None and r.scale_max is None
    assert any("above the scale maximum" in w for w in r.warnings)


def test_more_respondents_than_enrolled_is_warned_but_kept():
    r = extract_student_evaluation("Enrolled students: 30\nRespondents: 45")
    assert r.respondents.value == 45
    assert any("more respondents" in w for w in r.warnings)


def test_empty_or_unrelated_text_finds_nothing():
    r = extract_student_evaluation("Dear committee, I am delighted to apply for promotion.")
    assert r.values() == {} and r.missing() == ["respondents", "average_score", "scale_max"]


# ---- matching to the Section 6A courses ----------------------------------------------------------------------------

def _course(i, code, year, sem):
    return SimpleNamespace(id=i, course_code=code, academic_year=year, semester=SimpleNamespace(value=sem))


COURSES = [_course(1, "ELEC300", "2019/2020", "fall"), _course(2, "ELEC311", "2020/2021", "spring"),
           _course(3, "ELEC311", "2022/2023", "fall")]


def test_course_matched_by_code_and_term():
    assert match_course(extract_student_evaluation(B_STYLE), COURSES) == 2      # same code twice -> the term decides


def test_course_with_a_single_match_ignores_spacing_and_case():
    out = extract_student_evaluation("Course: elec 300 Intro (2019/2020 Fall)")
    assert match_course(out, COURSES) == 1


def test_ambiguous_or_unknown_course_is_left_to_the_applicant():
    assert match_course(extract_student_evaluation("ELEC311 Power Systems I"), COURSES) is None   # two semesters, no term
    assert match_course(extract_student_evaluation("PHYS101 Mechanics (2020/2021 Spring)"), COURSES) is None
    assert match_course(extract_student_evaluation("Respondents: 5"), COURSES) is None
