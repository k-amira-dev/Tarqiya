"""The Research agent's committee: every model judges each paper, the majority decides which flags are raised."""
from types import SimpleNamespace

from promoflow.db.enums import Confidence, FlagSeverity
from promoflow.workflow.nodes import research
from promoflow.workflow.nodes.research import (
    ContributionNote, NarrativePart, ResearchJudgment, ResearchVotes, TopicCheck, _ask_committee, _committee_flags,
)

CTX = SimpleNamespace(records={1: {"title": "Paper one"}, 2: {"title": "Paper two"}}, ambiguous={2: {}})


def votes(relevant1=True, relevant2=True, credit=None):
    return ResearchVotes(
        topics=[TopicCheck(handle="pb-1", relevant=relevant1, reason="r1", confidence=Confidence.HIGH),
                TopicCheck(handle="pb-2", relevant=relevant2, reason="r2", confidence=Confidence.HIGH)],
        contributions=[ContributionNote(handle="pb-2", suggestion=credit, reason="why")] if credit else [])


def codes(flags):
    return [(f.code, f.severity) for f in flags]


def test_all_agree_the_papers_fit_raises_nothing():
    assert _committee_flags(CTX, [("a", votes()), ("b", votes()), ("c", votes())]) == []


def test_two_of_three_say_off_topic_is_a_warning_with_the_votes():
    flags = _committee_flags(CTX, [("a", votes(relevant1=False)), ("b", votes(relevant1=False)), ("c", votes())])
    assert codes(flags) == [("topic_mismatch", FlagSeverity.WARNING)]
    assert "2 of 3" in flags[0].message and "a=no" in flags[0].message and "c=yes" in flags[0].message


def test_one_of_three_off_topic_is_only_a_note():
    flags = _committee_flags(CTX, [("a", votes(relevant1=False)), ("b", votes()), ("c", votes())])
    assert codes(flags) == [("topic_disagreement", FlagSeverity.INFO)]


def test_a_tie_between_two_models_goes_to_a_reviewer():
    flags = _committee_flags(CTX, [("a", votes(relevant2=False)), ("b", votes())])
    assert codes(flags) == [("topic_mismatch", FlagSeverity.WARNING)]


def test_contribution_all_main_is_a_note():
    flags = _committee_flags(CTX, [("a", votes(credit="main")), ("b", votes(credit="main")), ("c", votes(credit="main"))])
    assert codes(flags) == [("contribution_review", FlagSeverity.INFO)]


def test_contribution_disagreement_needs_a_person():
    flags = _committee_flags(CTX, [("a", votes(credit="main")), ("b", votes(credit="co_author")), ("c", votes(credit="main"))])
    assert codes(flags) == [("contribution_review", FlagSeverity.NEEDS_HUMAN)]
    assert "disagree" in flags[0].message and "b=co_author" in flags[0].message and "'main'" in flags[0].message


def test_contribution_with_no_majority_is_unclear():
    flags = _committee_flags(CTX, [("a", votes(credit="main")), ("b", votes(credit="co_author")), ("c", votes(credit="unclear"))])
    assert "'unclear'" in flags[0].message and flags[0].severity == FlagSeverity.NEEDS_HUMAN


def test_a_single_answer_gives_the_single_model_flags():
    flags = _committee_flags(CTX, [("a", votes(relevant1=False))])
    assert codes(flags) == [("topic_mismatch", FlagSeverity.WARNING)]
    assert "models" not in flags[0].message                      # no "x of y models" text without a committee


class FakeModel:
    def __init__(self, answer=None, error=None):
        self.answer, self.error, self.schema = answer, error, None

    def with_structured_output(self, schema):
        self.schema = schema
        return self

    def invoke(self, messages):
        if self.error:
            raise self.error
        return self.answer


def test_the_first_member_writes_the_narrative_the_others_vote_only(monkeypatch):
    monkeypatch.setattr(research, "_messages", lambda *a, **k: [])
    monkeypatch.setattr(research, "_problems", lambda j, ctx: [])
    full = ResearchJudgment(topics=votes().topics, narrative=[NarrativePart(text="x", cited=[])])
    a, b = FakeModel(full), FakeModel(votes())
    answers, errors = _ask_committee([("a", a), ("b", b)], CTX, [], None)
    assert a.schema is ResearchJudgment and b.schema is ResearchVotes
    assert [label for label, _ in answers] == ["a", "b"] and errors == []


def test_a_member_that_fails_is_skipped_and_reported(monkeypatch):
    monkeypatch.setattr(research, "_messages", lambda *a, **k: [])
    monkeypatch.setattr(research, "_problems", lambda j, ctx: [])
    monkeypatch.setattr(research, "_retry_wait", lambda e, attempt: None)    # no waiting in tests
    full = ResearchJudgment(topics=votes().topics, narrative=[NarrativePart(text="x", cited=[])])
    answers, errors = _ask_committee([("a", FakeModel(full)), ("b", FakeModel(error=RuntimeError("quota"))), ("c", FakeModel(votes()))],
                                     CTX, [], None)
    assert [label for label, _ in answers] == ["a", "c"]
    assert errors[0][0] == "b" and "quota" in errors[0][1]
