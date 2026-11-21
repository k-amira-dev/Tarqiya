"""The safety switch OUTREACH_REDIRECT_TO: in test mode every referee email goes to the tester, never to the referee."""
from types import SimpleNamespace

from promoflow import config
from promoflow.workflow import outreach


class FakeSMTP:
    """Stands in for the mail server: remembers what would have been sent."""
    sent = []

    def __init__(self, host, port, timeout=None):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        pass

    def login(self, user, password):
        pass

    def send_message(self, email):
        FakeSMTP.sent.append(email)


def send(monkeypatch, redirect_to):
    FakeSMTP.sent = []
    monkeypatch.setattr(outreach.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(config, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr(config, "SMTP_USER", "")
    monkeypatch.setattr(config, "OUTREACH_FROM", "office@university.test")
    monkeypatch.setattr(config, "OUTREACH_REDIRECT_TO", redirect_to)
    outreach._smtp_send(SimpleNamespace(subject="Invitation to review", body="Dear Professor ..."), "real.researcher@example.org")
    return FakeSMTP.sent[0]


def test_with_the_switch_on_the_email_goes_only_to_the_tester(monkeypatch):
    email = send(monkeypatch, "me@example.com")
    assert email["To"] == "me@example.com"
    assert email["Subject"] == "[TEST, meant for real.researcher@example.org] Invitation to review"
    assert "real.researcher@example.org" not in email["To"]


def test_with_the_switch_off_the_email_goes_to_the_referee(monkeypatch):
    email = send(monkeypatch, "")
    assert email["To"] == "real.researcher@example.org" and email["Subject"] == "Invitation to review"
