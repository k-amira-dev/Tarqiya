"""A model that answers in its own tool-call format (qwen on Groq) is rejected by the provider although its answer is complete.
The scoring code reads the items from the rejected text; anything it cannot read is still an error."""
from promoflow.workflow import rubric
from promoflow.workflow.retry import _retry_wait

GENERATION = ('<tool_call>\n<function=Judgment>\n<parameter=items>\n'
              '[{"cited": ["td-123", "td-124"], "confidence": "high", "item_no": 10, "points": 2.0, "rationale": "Nine relevant activities."}, '
              '{"cited": [], "confidence": "high", "item_no": 10, "points": 2.0, "rationale": "Nine relevant activities."}]\n'
              '</ parameter>\n</function>\n</tool_call>')


class Rejected(Exception):
    def __init__(self, generation):
        super().__init__("Error code: 400 - tool_use_failed")
        self.body = {"error": {"code": "tool_use_failed", "failed_generation": generation}}


def test_items_are_read_from_the_rejected_tool_call_and_a_repeated_item_keeps_its_citations():
    judgment = rubric._salvage(Rejected(GENERATION))
    assert [(j.item_no, j.points, j.cited) for j in judgment.items] == [(10, 2.0, ["td-123", "td-124"])]


def test_unreadable_text_is_not_salvaged():
    assert rubric._salvage(Rejected("garbage")) is None
    assert rubric._salvage(Rejected("<parameter=items>\n[{\"item_no\": \"x\"}]\n</parameter>")) is None
    assert rubric._salvage(Exception("no body")) is None


def test_a_rejected_tool_call_is_tried_once_more():
    assert _retry_wait(Rejected(GENERATION), 0) == 2


def test_a_busy_provider_is_waited_out_and_asked_again():
    busy = Exception("GoogleAPIError: 503 UNAVAILABLE. This model is currently experiencing high demand.")
    assert [_retry_wait(busy, a) for a in range(4)] == [5, 10, 20, 40]
