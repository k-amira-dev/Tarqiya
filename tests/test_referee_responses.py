"""The Chancellor's view of what each referee answered."""
from promoflow.workflow import referee_view
from promoflow.workflow.referee_view import GradeRow, ResponseRow, STATUS_LABEL


def test_every_assignment_status_has_a_plain_label():
    from promoflow.db.enums import AssignmentStatus
    assert {s.value for s in AssignmentStatus} <= set(STATUS_LABEL)


def test_a_response_row_carries_the_grades_and_recommendation():
    row = ResponseRow(1, "Prof. Example", "Example University", STATUS_LABEL["report_received"], None, None, None, None,
                      [GradeRow("Paper one", 90.0), GradeRow("Paper two", 95.0)], 92.5, "good papers")
    assert row.average == 92.5 and row.recommendation == "good papers" and len(row.grades) == 2
