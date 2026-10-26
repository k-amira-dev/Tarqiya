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
