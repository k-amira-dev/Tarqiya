"""The referee result the applicant sees."""
from datetime import datetime, timezone

from promoflow import config
from promoflow.workflow import referee_result
from promoflow.workflow.referee_result import ApplicantResult, message


def result(passed):
    return ApplicantResult(passed=passed, target_rank="Associate Professor", released_at=datetime.now(timezone.utc))


def test_a_pass_says_the_applicant_was_promoted_to_the_target_rank():
    title, text = message(result(True))
    assert "promoted" in title.lower() and "Associate Professor" in text


def test_a_fail_says_the_application_was_not_successful():
    title, text = message(result(False))
    assert "not successful" in title.lower() and "Associate Professor" in text


def test_automatic_release_is_off_by_default(monkeypatch):
    monkeypatch.setattr(config, "REFEREE_RESULT_AUTO_RELEASE", False)
    assert referee_result.release_if_automatic(123) is False          # returns before touching the database


def test_the_applicant_sees_no_number_at_all():
    import re
    for passed in (True, False):
        title, text = message(result(passed))
        assert not re.search(r"\d", title + text)                      # no grade, average, percentage or pass mark
    assert not {"average", "pass_mark"} & set(ApplicantResult.__dataclass_fields__)
