"""Signed, expiring Accept / Decline links for referee emails.

A referee has no account, so the email carries a link. The link holds the assignment number, the action ("accept" or "decline") and an expiry
time, signed with HMAC-SHA256. Nobody can change the number or the action without the key, and a link stops working when it expires.
The signing key is derived from AUDIT_HMAC_KEY, so no new secret has to be set.

The link only OPENS a page. The answer is recorded when the referee presses Confirm there, so a mail scanner that opens every link in an
email cannot answer for the referee.
"""
import base64
import hashlib
import hmac
from datetime import datetime, timezone

from promoflow import config

ACTIONS = ("accept", "decline")


class LinkError(Exception):
    """The link is not valid (altered, malformed) or has expired. The message is safe to show to the referee."""


def _key() -> bytes:
    if not config.AUDIT_HMAC_KEY:
        raise LinkError("The signing key (AUDIT_HMAC_KEY) is not set.")
    return hmac.new(config.AUDIT_HMAC_KEY.encode(), b"referee-link-v1", hashlib.sha256).digest()


def _sign(payload: str) -> str:
    return base64.urlsafe_b64encode(hmac.new(_key(), payload.encode(), hashlib.sha256).digest()).decode().rstrip("=")


def make_token(assignment_id: int, action: str, expires_at: datetime) -> str:
    if action not in ACTIONS:
        raise ValueError(f"unknown action {action!r}")
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    payload = f"{assignment_id}.{action}.{int(expires_at.timestamp())}"
    return f"{payload}.{_sign(payload)}"


def verify_token(token: str, now: datetime | None = None) -> tuple[int, str]:
    """(assignment_id, action) of a good token. Raises LinkError("invalid") or LinkError("expired")."""
    parts = (token or "").strip().split(".")
    if len(parts) != 4:
        raise LinkError("invalid")
    assignment, action, expiry, signature = parts
    if action not in ACTIONS or not assignment.isdigit() or not expiry.isdigit():
        raise LinkError("invalid")
    if not hmac.compare_digest(_sign(f"{assignment}.{action}.{expiry}"), signature):
        raise LinkError("invalid")
    if (now or datetime.now(timezone.utc)).timestamp() > int(expiry):
        raise LinkError("expired")
    return int(assignment), action


def link_url(token: str) -> str:
    return f"{config.APP_BASE_URL.rstrip('/')}/?referee={token}"


def links_for(assignment_id: int, expires_at: datetime) -> dict[str, str]:
    """{"{accept_link}": url, "{decline_link}": url}: the placeholders the email templates use."""
    return {"{accept_link}": link_url(make_token(assignment_id, "accept", expires_at)),
            "{decline_link}": link_url(make_token(assignment_id, "decline", expires_at))}


def link_state(status: str, action: str) -> str:
    """What a valid link may do now, from the assignment's status:
    "open" = the referee can answer; "answered" = an answer is already recorded; "reported" = the report was received;
    "closed" = the request is over."""
    if status in ("invited", "reminded"):
        return "open"
    if status == "accepted":
        return "answered" if action == "accept" else "open"      # an accepting referee may still withdraw
    if status == "declined":
        return "answered"
    if status == "report_received":
        return "reported"
    return "closed"
