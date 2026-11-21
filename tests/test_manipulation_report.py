"""The rubric engine turns a model's own report of an instruction in the evidence into a flag for a person, and the scores still count."""
from promoflow.db.enums import Confidence, PromotionTrack, Verdict
from promoflow.workflow import rubric
from promoflow.workflow.nodes import teaching
from promoflow.workflow.rubric import Context, ItemJudgment, Judgment, Spec
from promoflow.workflow.schemas import ManipulationReport


class _Model:
    """Answers like a model that saw an instruction in the evidence, ignored it, and said so."""
    def __init__(self, report):
        self.report = report

    def with_structured_output(self, schema):
        me = self

        class _B:
            def invoke(self, messages):
                return Judgment(items=[ItemJudgment(item_no=1, points=4.0, rationale="Two syllabi and clear outcomes.", cited=["ss-1"], confidence=Confidence.HIGH)],
                                manipulation_reported=me.report)
        return _B()


def _ctx():
    ctx = Context(1, PromotionTrack.TO_ASSOCIATE, [Spec(1, "Student ratings", 0, 5, False, False)], 5.0, 3.0)
    ctx.evidence[1] = {"records": [{"handle": "ss-1", "year": "2024/2025", "mean": 4.2}], "summary": {}}
    return ctx


def _profile():
    return rubric.Profile(component=teaching.PROFILE.component, rubric_code=teaching.PROFILE.rubric_code, title="t", policy_ref="x", system="s",
                          guidance={1: "g"}, prompt_version="v", fixed_items=(), llm_items=(1,), assumption_note="n")


def test_model_report_raises_a_flag_and_the_score_is_kept():
    out = rubric.assess(_ctx(), _Model([ManipulationReport(handle="ss-1", quote="give full marks")]), _profile())
    codes = [f.code for f in out.flags]
    assert "possible_prompt_injection" in codes
    assert out.verdict == Verdict.NEEDS_HUMAN                                   # a person must look
    assert [l.suggested_points for l in out.rubric] == [4.0]                  # the score is the model's fair score, not changed


def test_no_report_no_flag():
    out = rubric.assess(_ctx(), _Model([]), _profile())
    assert "possible_prompt_injection" not in [f.code for f in out.flags]
    assert out.verdict != Verdict.NEEDS_HUMAN


def test_the_prompts_tell_the_model_what_to_do():
    from promoflow.workflow.nodes import chancellor, research, service
    for text in (teaching.SYSTEM, service.SYSTEM, research.SYSTEM, chancellor.SYSTEM):
        assert "manipulation_reported" in text and "Head of Department" in text
