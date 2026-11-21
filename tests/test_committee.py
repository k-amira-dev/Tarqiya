"""The model committee: several models score the same items, the suggestion is the median, a wide spread is flagged for a person, and a
model that fails is left out. Fake models only: no key, no internet."""
from promoflow.db.enums import Component, Confidence, FlagSeverity, PromotionTrack, RubricCode, Verdict
from promoflow.workflow import llm as llm_module, rubric
from promoflow.workflow.rubric import Context, ItemJudgment, Judgment, Profile, Spec


class FakeModel:
    """Answers every item with the points in `scores` ({item_no: points}); raises `error` instead when given."""

    def __init__(self, scores=None, error=None):
        self.scores, self.error, self.calls = scores or {}, error, 0

    def with_structured_output(self, _schema):
        return self

    def invoke(self, _messages):
        self.calls += 1
        if self.error:
            raise self.error
        return Judgment(items=[ItemJudgment(item_no=n, points=p, rationale=f"Reason for {n} at {p}.", cited=["ss-1"],
                                            confidence=Confidence.HIGH) for n, p in self.scores.items()])


def make(*, specs=((1, 4, 6), (2, 0, 8))):
    profile = Profile(component=Component.TEACHING, rubric_code=RubricCode.TEACHING, title="Teaching total",
                      policy_ref="Appendix E", system="s", guidance={n: "g" for n, _, _ in specs}, prompt_version="t-v1",
                      fixed_items=(), llm_items=tuple(n for n, _, _ in specs), assumption_note="assumed {version}")
    ctx = Context(1, PromotionTrack.TO_ASSOCIATE, [Spec(n, f"item {n}", lo, hi, False, False) for n, lo, hi in specs],
                  total_points=14, pass_points=7)
    for n, _, _ in specs:
        ctx.evidence[n] = {"records": [{"handle": "ss-1", "x": 1}], "summary": {}}
    return ctx, profile


def line(out, n):
    return next(l for l in out.rubric if l.item_no == n)


def test_the_suggestion_is_the_median_and_every_opinion_is_kept():
    ctx, profile = make()
    committee = [("a", FakeModel({1: 5, 2: 4})), ("b", FakeModel({1: 6, 2: 5})), ("c", FakeModel({1: 5, 2: 4}))]
    out = rubric.assess(ctx, None, profile, committee)
    assert line(out, 1).suggested_points == 5 and line(out, 2).suggested_points == 4
    assert [(o.model_name, o.points) for o in line(out, 1).opinions] == [("a", 5), ("b", 6), ("c", 5)]
    assert out.model_name == "committee: a + b + c"
    assert not any(f.code == "committee_disagreement" for f in out.flags)


def test_a_wide_spread_asks_for_a_person():
    ctx, profile = make()
    # item 2 ranges 0-8, so the models may differ by up to 2 points; 1 vs 7 is far more.
    committee = [("a", FakeModel({1: 5, 2: 1})), ("b", FakeModel({1: 5, 2: 7})), ("c", FakeModel({1: 5, 2: 4}))]
    out = rubric.assess(ctx, None, profile, committee)
    flags = [f for f in out.flags if f.code == "committee_disagreement"]
    assert len(flags) == 1 and "Item 2" in flags[0].message and flags[0].severity == FlagSeverity.NEEDS_HUMAN
    assert line(out, 2).suggested_points == 4 and line(out, 2).spread == 6
    assert out.verdict == Verdict.NEEDS_HUMAN


def test_a_failed_model_is_left_out_and_reported():
    ctx, profile = make()
    committee = [("a", FakeModel({1: 5, 2: 4})), ("b", FakeModel(error=RuntimeError("down"))),
                 ("c", FakeModel({1: 5, 2: 4}))]
    out = rubric.assess(ctx, None, profile, committee)
    assert [o.model_name for o in line(out, 1).opinions] == ["a", "c"]
    assert any(f.code == "committee_member_failed" and "b" in f.message for f in out.flags)
    assert out.verdict != Verdict.INCOMPLETE


def test_when_every_model_fails_nothing_is_guessed():
    ctx, profile = make()
    committee = [("a", FakeModel(error=RuntimeError("x"))), ("b", FakeModel(error=RuntimeError("y")))]
    out = rubric.assess(ctx, None, profile, committee)
    assert out.verdict == Verdict.INCOMPLETE and any(f.code == "llm_unavailable" for f in out.flags)


def test_out_of_range_opinions_are_clamped_before_the_median():
    ctx, profile = make(specs=((1, 4, 6),))
    committee = [("a", FakeModel({1: 6})), ("b", FakeModel({1: 6}))]
    out = rubric.assess(ctx, None, profile, committee)
    assert line(out, 1).suggested_points == 6 and all(o.points <= 6 for o in line(out, 1).opinions)


def test_without_a_committee_one_model_works_as_before():
    ctx, profile = make()
    single = FakeModel({1: 5, 2: 4})
    out = rubric.assess(ctx, single, profile)
    assert single.calls == 1 and line(out, 1).opinions == [] and line(out, 1).spread is None
    # A committee of one is not a committee.
    out = rubric.assess(ctx, single, profile, [("a", FakeModel({1: 6, 2: 6}))])
    assert line(out, 1).suggested_points == 5


def test_the_committee_list_comes_from_settings(monkeypatch):
    monkeypatch.setattr(llm_module, "COMMITTEE_MODELS", "groq:m1,groq:m2,google:g1")
    monkeypatch.setattr(llm_module, "get_model", lambda spec: spec.upper())
    assert llm_module.committee_llms() == [("m1", "GROQ:M1"), ("m2", "GROQ:M2"), ("g1", "GOOGLE:G1")]
    # A member without a key is skipped; fewer than two members means the committee is off.
    def only_groq(spec):
        if spec.startswith("google"):
            raise llm_module.LLMNotConfigured("no key")
        return spec
    monkeypatch.setattr(llm_module, "get_model", only_groq)
    assert len(llm_module.committee_llms()) == 2
    monkeypatch.setattr(llm_module, "COMMITTEE_MODELS", "groq:m1,google:g1")
    assert llm_module.committee_llms() == []


def test_a_small_window_model_gets_its_items_in_batches(monkeypatch):
    ctx, profile = make(specs=((1, 4, 6), (2, 0, 8), (3, 0, 5)))
    for n in (1, 2, 3):
        ctx.evidence[n]["summary"] = {"note": "x" * 3000}          # about 850 tokens per item
    monkeypatch.setattr(rubric, "COMMITTEE_INPUT_BUDGETS", "small=1200")
    small, big = FakeModel({1: 5, 2: 4, 3: 3}), FakeModel({1: 5, 2: 4, 3: 3})
    out = rubric.assess(ctx, None, profile, [("small", small), ("big", big)])
    assert small.calls == 3 and big.calls == 1                      # one item per batch vs everything at once
    assert [l.suggested_points for l in out.rubric] == [5, 4, 3]
    assert all(len(l.opinions) == 2 for l in out.rubric)


def test_a_failed_batch_keeps_the_items_from_the_other_batches(monkeypatch):
    ctx, profile = make(specs=((1, 4, 6), (2, 0, 8)))
    for n in (1, 2):
        ctx.evidence[n]["summary"] = {"note": "x" * 3000}
    monkeypatch.setattr(rubric, "COMMITTEE_INPUT_BUDGETS", "small=1200")

    class FailsSecond(FakeModel):
        def invoke(self, messages):
            if self.calls == 1:                                     # the second request fails
                self.calls += 1
                raise RuntimeError("boom")
            return super().invoke(messages)

    out = rubric.assess(ctx, None, profile, [("small", FailsSecond({1: 5, 2: 4})), ("big", FakeModel({1: 5, 2: 4}))])
    assert [o.model_name for o in line(out, 1).opinions] == ["small", "big"]
    assert [o.model_name for o in line(out, 2).opinions] == ["big"]
    assert any(f.code == "committee_member_failed" for f in out.flags)
