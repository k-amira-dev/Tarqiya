"""When the provider says "too many tokens this minute", the scoring call waits as long as it says and asks again; a request that is
simply too large is not retried (waiting cannot help)."""
import pytest

from promoflow.workflow import rubric


class RateLimitError(Exception):
    pass


class Flaky:
    def __init__(self, *failures):
        self.failures, self.calls = list(failures), 0

    def with_structured_output(self, schema):
        return self

    def invoke(self, messages):
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        return "answer"


TPM = RateLimitError("Error code: 429 - Rate limit reached ... on tokens per minute (TPM): Limit 8000, Used 2597, Requested 5868. Please try again in 3.4875s.")


def test_a_per_minute_limit_is_waited_out_and_retried(monkeypatch):
    slept = []
    monkeypatch.setattr(rubric.time, "sleep", slept.append)
    llm = Flaky(TPM, TPM)
    assert rubric._invoke(llm, []) == "answer" and llm.calls == 3
    assert len(slept) == 2 and all(3.4 < s < 7 for s in slept)


def test_a_request_that_is_too_large_is_not_retried(monkeypatch):
    slept = []
    monkeypatch.setattr(rubric.time, "sleep", slept.append)
    llm = Flaky(Exception("Error code: 413 - Request too large for model on tokens per minute (TPM): Limit 8000, Requested 10070 rate_limit_exceeded"))
    with pytest.raises(Exception, match="Request too large"):
        rubric._invoke(llm, [])
    assert llm.calls == 1 and slept == []


def test_the_daily_limit_is_not_retried(monkeypatch):
    monkeypatch.setattr(rubric.time, "sleep", lambda s: None)
    llm = Flaky(RateLimitError("Error code: 429 - Rate limit reached on tokens per day (TPD): Limit 200000"))
    with pytest.raises(RateLimitError):
        rubric._invoke(llm, [])
    assert llm.calls == 1
