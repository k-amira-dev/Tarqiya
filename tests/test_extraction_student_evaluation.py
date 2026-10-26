"""Reading student-evaluation values from document text: rules, the model fallback, safety checks, course matching."""
from types import SimpleNamespace
from pathlib import Path

import pytest

from promoflow.extraction.pdf_text import extract_text
from promoflow.extraction.student_evaluation import (
    LLMExtraction, extract_student_evaluation, match_course,
)

FIXTURES = Path(__file__).parent / "fixtures" / "extraction"

B_STYLE = """SIMULATED - FOR TESTING
Student Evaluation Summary (simulated)
Course
ELEC311 Power Systems I (2020/2021 Spring)
Enrolled students: 53
Result
Respondents: 41
Average score: 4.3 out of 5"""


class FakeLLM:
    """Stands in for the Groq model: returns a fixed answer, or raises."""
    def __init__(self, answer=None, error=None):
        self.answer, self.error, self.calls = answer, error, 0

    def with_structured_output(self, model):
        return self

    def invoke(self, messages):
        self.calls += 1
        if self.error:
            raise self.error
        return self.answer


# ---- rules ----------------------------------------------------------------------------------------------------

def test_b_style_document_is_fully_read_by_rules():
    llm = FakeLLM(LLMExtraction())
    r = extract_student_evaluation(B_STYLE, llm)
    assert r.values() == {"course_code": "ELEC311", "course_title": "Power Systems I", "academic_year": "2020/2021",
                          "semester": "spring", "enrolled": 53, "respondents": 41, "average_score": 4.3,
                          "scale_max": 5.0}
    assert r.respondents.snippet == "Respondents: 41" and r.respondents.source == "rule"
    assert r.missing() == [] and r.warnings == []
    assert llm.calls == 0                      # nothing missing, so the model is not even asked


def test_real_sample_pdf_end_to_end():
    r = extract_student_evaluation(extract_text((FIXTURES / "student_evaluation_b.pdf").read_bytes()).text)
    assert (r.course_code.value, r.respondents.value, r.enrolled.value) == ("ELEC300", 39, 51)
    assert (r.average_score.value, r.scale_max.value) == (4.3, 5.0)


def test_course_file_style_document():
    text = extract_text((FIXTURES / "course_file_a.pdf").read_bytes()).text
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


# ---- language-model fallback ----------------------------------------------------------------------------------

PERCENT_DOC = "Course\nELEC300 Intro\nEvaluation result: 86% satisfied\nThirty-nine students answered the survey."


def test_model_fills_a_value_the_rules_missed_when_it_quotes_the_page():
    llm = FakeLLM(LLMExtraction(average_score=86, scale_max=100, score_quote="Evaluation result: 86% satisfied"))
    r = extract_student_evaluation(PERCENT_DOC, llm)
    assert (r.average_score.value, r.scale_max.value) == (86, 100)
    assert r.average_score.source == "llm" and r.average_score.snippet == "Evaluation result: 86% satisfied"
    assert llm.calls == 1


def test_model_answer_with_an_invented_quote_is_rejected():
    llm = FakeLLM(LLMExtraction(respondents=39, respondents_quote="Respondents: 39"))
    r = extract_student_evaluation(PERCENT_DOC, llm)
    assert r.respondents is None


def test_model_answer_whose_quote_does_not_contain_the_value_is_rejected():
    llm = FakeLLM(LLMExtraction(respondents=40, respondents_quote="Thirty-nine students answered the survey."))
    assert extract_student_evaluation(PERCENT_DOC, llm).respondents is None


def test_model_cannot_override_what_the_rules_found():
    llm = FakeLLM(LLMExtraction(respondents=99, respondents_quote="Respondents: 41"))
    r = extract_student_evaluation(B_STYLE.replace("Average score: 4.3 out of 5", "Average score: 4.3"), llm)
    assert r.respondents.value == 41 and r.respondents.source == "rule"


def test_model_failure_is_a_warning_not_a_crash():
    r = extract_student_evaluation("Respondents: 20", FakeLLM(error=RuntimeError("rate limit")))
    assert r.respondents.value == 20 and r.average_score is None
    assert any("not available" in w for w in r.warnings)


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
