"""What the reviewer's report shows: summary tiles, points table, checks table (promoflow/ui/report_view.py)."""
from promoflow.ui import report_view as rv

TEACHING = {
    "component": "teaching", "verdict": "pass", "narrative": "Suggested total 28 of 30 ...", "is_stub": False,
    "criteria": [
        {"key": "teaching_total", "label": "Teaching total (Appendix E)", "required": 24.0, "actual": 28.0,
         "max_value": 30.0, "passed": True, "policy_ref": "Appendix E"},
        {"key": "item_1", "label": "Item 1: Effectiveness of teaching according to students' evaluations",
         "required": 2.0, "actual": 4.0, "max_value": 4.0, "passed": True},
        {"key": "item_7", "label": "Item 7: Case studies comparing the effectiveness of teaching methods",
         "required": 2.0, "actual": 0.0, "max_value": 2.0, "passed": False},
    ],
    "rubric": [
        {"rubric": "teaching", "item_no": 7, "suggested_points": 0.0, "basis": "rule",
         "rationale": "No evidence entered.", "confidence": "high"},
        {"rubric": "teaching", "item_no": 1, "suggested_points": 4.0, "basis": "llm",
         "rationale": "Weighted average 87.8%.", "confidence": "low"},
    ],
}


def test_points_table_has_one_row_per_item_in_order_with_maximums():
    t = rv.points_table(TEACHING)
    assert (t.total, t.max_total, t.pass_mark, t.passed) == (28.0, 30.0, 24.0, True)
    assert [r.item_no for r in t.rows] == [1, 7]
    first, seventh = t.rows
    assert first.label == "Effectiveness of teaching according to students' evaluations"   # "Item 1: " is dropped
    assert (first.points, first.max_points, first.share) == (4.0, 4.0, 1.0)
    assert (first.how, first.confidence, first.no_evidence) == ("AI-assisted", "Low", False)
    assert seventh.no_evidence and seventh.how == "Rule-based"        # 0 points because nothing was entered


def test_summary_tiles():
    assert rv.summary("teaching", TEACHING) == rv.Summary("teaching", "Teaching evaluation", "pass", "28 / 30",
                                                         "pass mark 24")
    eligibility = {"verdict": "pass", "criteria": [{"key": "a", "label": "A", "passed": True},
                                                   {"key": "b", "label": "B", "passed": True},
                                                   {"key": "c", "label": "C", "passed": None}]}
    s = rv.summary("eligibility", eligibility)
    assert (s.title, s.figure, s.detail) == ("Eligibility check", "2 of 3 checks", "conditions met")
    stub = rv.summary("research", {"verdict": "pass", "is_stub": True, "criteria": []})
    assert (stub.title, stub.figure) == ("Research evaluation", "Not built yet")


def test_check_rows_keep_none_as_needs_a_person():
    rows = rv.check_rows({"criteria": [{"key": "x", "label": "Time in rank", "required": 5.0, "actual": 4.99,
                                        "passed": False, "policy_ref": "Att. 2"},
                                       {"key": "y", "label": "Exceptional case", "passed": None}]})
    assert (rows[0].required, rows[0].actual, rows[0].passed, rows[0].policy_ref) == (5.0, 4.99, False, "Att. 2")
    assert rows[1].passed is None and rows[1].required is None


def test_reports_saved_before_max_value_existed_still_work():
    old = {"component": "service", "verdict": "pass", "criteria": [
        {"key": "service_total", "label": "Service total", "required": 8.0, "actual": 9.0, "passed": True},
        {"key": "item_1", "label": "Item 1: Committees", "required": 4.0, "actual": 5.0, "passed": True}],
        "rubric": [{"rubric": "service", "item_no": 1, "suggested_points": 5.0, "basis": "llm",
                    "rationale": "Chaired two committees.", "confidence": "medium"}]}
    t = rv.points_table(old)
    assert t.max_total is None and t.rows[0].max_points is None and t.rows[0].share is None
    assert rv.summary("service", old).figure == "9"            # no maximum known, so just the points


def test_number_formatting():
    assert (rv.g(12.0), rv.g(4.5), rv.g(None)) == ("12", "4.5", "–")
    assert rv.points_table({"criteria": [], "rubric": []}) is None


RESEARCH = {
    "model_name": "m", "flags": [{"code": "topic_mismatch", "entity_id": 2,
                                  "message": "'Cooking at home' may be outside the applicant's field (high confidence): It is about cooking. A reviewer should check."}],
    "items": [{"entity_table": "publication", "entity_id": 1, "counted": True, "classification": "class_a", "credited_role": "main author"},
              {"entity_table": "publication", "entity_id": 2, "counted": True, "classification": "class_b", "credited_role": "co-author"},
              {"entity_table": "book", "entity_id": 9, "counted": True, "classification": "chapter"}],
}
PAPERS = {1: ("Algorithmic visibility", "Frontiers in Sociology", True), 2: ("Cooking at home", "Some Journal", False)}


def test_paper_rows_show_the_rules_decision_and_the_models_topic_check():
    a, b = rv.paper_rows(RESEARCH, PAPERS)
    assert (a.journal_class, a.declared, a.credited, a.topic, a.topic_ok) == ("Class A", True, "Main author", "Fits the field (AI)", True)
    assert (b.journal_class, b.topic_ok) == ("Class B", False) and b.topic == "Check: It is about cooking."      # only papers; the book row is left out


def test_topic_is_not_checked_when_the_model_did_not_run():
    out = dict(RESEARCH, model_name=None, flags=[{"code": "llm_unavailable", "message": "x"}])
    assert {r.topic for r in rv.paper_rows(out, PAPERS)} == {"Not checked"}


# ---- committee: one column per model, the decision is the median ----------------------------------------------------

COMMITTEE = {
    "criteria": [{"key": "teaching_total", "label": "Teaching total", "required": 7, "actual": 9, "max_value": 14, "passed": True},
                 {"key": "item_1", "label": "Item 1: Courses", "required": 0, "actual": 5, "max_value": 6, "passed": True},
                 {"key": "item_2", "label": "Item 2: Innovation", "required": 0, "actual": 4, "max_value": 8, "passed": True}],
    "rubric": [
        {"item_no": 1, "suggested_points": 5, "basis": "llm", "confidence": "high", "rationale": "Median reason.",
         "opinions": [{"model_name": "openai/gpt-oss-120b", "points": 5, "rationale": "A"},
                      {"model_name": "qwen/qwen3.8-27b", "points": 6, "rationale": "B"},
                      {"model_name": "gemini-3.5-flash", "points": 5, "rationale": "C"}]},
        {"item_no": 2, "suggested_points": 4, "basis": "llm", "confidence": "high", "rationale": "Wide.",
         "opinions": [{"model_name": "openai/gpt-oss-120b", "points": 1, "rationale": "A"},
                      {"model_name": "qwen/qwen3.8-27b", "points": 7, "rationale": "B"},
                      {"model_name": "gemini-3.5-flash", "points": 4, "rationale": "C"}]}],
    "flags": [{"code": "committee_disagreement", "message": "Item 2: the models disagree (a 1, b 7). A person should decide."}],
}


def test_committee_table_has_a_column_per_model_and_marks_disagreement():
    t = rv.points_table(COMMITTEE)
    assert t.models == ("gpt-oss-120b", "qwen3.8-27b", "gemini-3.5-flash")
    first, second = t.rows
    assert [(m, p) for m, p, _ in first.opinions] == [("gpt-oss-120b", 5), ("qwen3.8-27b", 6), ("gemini-3.5-flash", 5)]
    assert first.points == 5 and not first.disagree and second.disagree


def test_a_single_model_report_has_no_model_columns():
    t = rv.points_table(TEACHING)
    assert t.models == () and all(r.opinions == () and not r.disagree for r in t.rows)
