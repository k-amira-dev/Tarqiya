"""Signed, expiring Accept / Decline links for referee emails."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from promoflow import config
from promoflow.db.enums import MessageKind
from promoflow.workflow import outreach, referee_links
from promoflow.workflow.referee_links import LinkError, link_state, make_token, verify_token

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)
LATER = NOW + timedelta(days=90)


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setattr(config, "AUDIT_HMAC_KEY", "test-key-for-referee-links")
    monkeypatch.setattr(config, "APP_BASE_URL", "https://tarqiya.example")


def test_a_good_token_gives_back_the_assignment_and_action():
    assert verify_token(make_token(42, "accept", LATER), NOW) == (42, "accept")
    assert verify_token(make_token(42, "decline", LATER), NOW) == (42, "decline")


def test_changing_the_action_or_the_number_breaks_the_signature():
    token = make_token(42, "decline", LATER)
    for forged in (token.replace(".decline.", ".accept.", 1), token.replace("42.", "43.", 1)):
        with pytest.raises(LinkError, match="invalid"):
            verify_token(forged, NOW)


def test_extending_the_expiry_breaks_the_signature():
    assignment, action, expiry, signature = make_token(42, "accept", LATER).split(".")
    with pytest.raises(LinkError, match="invalid"):
        verify_token(f"{assignment}.{action}.{int(expiry) + 10_000_000}.{signature}", NOW)


def test_a_token_stops_working_after_its_expiry():
    token = make_token(42, "accept", LATER)
    assert verify_token(token, LATER - timedelta(seconds=1))[0] == 42
    with pytest.raises(LinkError, match="expired"):
        verify_token(token, LATER + timedelta(seconds=1))


@pytest.mark.parametrize("junk", ["", "abc", "1.accept.99.sig.extra", "x.accept.123.sig", "1.delete.123.sig", None])
def test_junk_is_invalid(junk):
    with pytest.raises(LinkError, match="invalid"):
        verify_token(junk, NOW)


def test_a_token_made_with_another_key_is_invalid(monkeypatch):
    token = make_token(42, "accept", LATER)
    monkeypatch.setattr(config, "AUDIT_HMAC_KEY", "a-different-key")
    with pytest.raises(LinkError, match="invalid"):
        verify_token(token, NOW)


def test_no_key_means_no_links(monkeypatch):
    monkeypatch.setattr(config, "AUDIT_HMAC_KEY", "")
    with pytest.raises(LinkError):
        make_token(42, "accept", LATER)


def test_what_a_link_may_do_for_each_status():
    assert link_state("invited", "accept") == link_state("reminded", "decline") == "open"
    assert link_state("accepted", "accept") == "answered"
    assert link_state("accepted", "decline") == "open"               # may still withdraw
    assert link_state("declined", "accept") == link_state("declined", "decline") == "answered"
    assert link_state("report_received", "accept") == link_state("report_received", "decline") == "reported"
    for closed in ("replaced_no_response", "withdrawn"):
        assert link_state(closed, "accept") == "closed"


def test_the_links_use_the_public_address():
    links = referee_links.links_for(7, LATER)
    assert links["{accept_link}"].startswith("https://tarqiya.example/?referee=7.accept.")
    assert links["{decline_link}"].startswith("https://tarqiya.example/?referee=7.decline.")


def test_the_invitation_and_the_reminder_carry_both_links_and_the_filled_email_has_none_left():
    referee = SimpleNamespace(full_name="Prof. Example")
    for kind in (MessageKind.INVITATION, MessageKind.REMINDER):
        subject, body = outreach.draft_email(kind, {"field": "Computer Science", "target_rank": "Professor"})
        assert "{accept_link}" in body and "{decline_link}" in body
        filled = outreach._fill(body, referee, LATER, 9, referee_links.links_for(7, LATER))
        assert "{" not in filled and "?referee=7.accept." in filled and "?referee=7.decline." in filled


def test_the_other_emails_have_no_links():
    for kind in (MessageKind.REPLACEMENT_NOTICE, MessageKind.THANK_YOU):
        _, body = outreach.draft_email(kind, {"field": "x", "target_rank": "y"})
        assert "{accept_link}" not in body


def test_a_model_rewrite_that_drops_a_link_is_replaced_by_the_fixed_template():
    class Dropper:
        def with_structured_output(self, schema):
            return self

        def invoke(self, messages):
            return outreach.EmailDraft(subject="Hello {case_ref}", body="Dear {referee_name}, please answer by {deadline}.")

    _, body = outreach.draft_email(MessageKind.INVITATION, {"field": "x", "target_rank": "y"}, Dropper())
    assert "{accept_link}" in body and "{decline_link}" in body


# ---- grading the papers ----------------------------------------------------------------------------------------------

IDS = {1, 2, 3}


def test_a_complete_report_is_accepted():
    assert outreach.validate_report(IDS, {1: 80, 2: 75.5, 3: 0}, "A solid body of work.") == []


def test_every_paper_needs_a_grade():
    problems = outreach.validate_report(IDS, {1: 80, 2: None}, "ok")
    assert any("2 still need a grade" in p for p in problems)


def test_a_paper_outside_the_review_cannot_be_graded():
    assert any("not part of this review" in p for p in outreach.validate_report(IDS, {1: 80, 2: 80, 3: 80, 99: 50}, "ok"))


@pytest.mark.parametrize("bad", [-1, 100.5, 250])
def test_grades_must_be_between_0_and_100(bad):
    assert any("between 0 and 100" in p for p in outreach.validate_report(IDS, {1: bad, 2: 80, 3: 80}, "ok"))


@pytest.mark.parametrize("text", [None, "", "   ", "x" * 2001])
def test_the_recommendation_is_required_and_limited(text):
    assert outreach.validate_report(IDS, {1: 80, 2: 80, 3: 80}, text)
