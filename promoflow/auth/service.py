"""Login, sessions and role lookup. UI-independent so it can be unit-tested and reused by the worker.

Swapping to university single sign-on later only replaces `authenticate()`; sessions and roles stay.
"""
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from promoflow.auth.passwords import hash_password, needs_rehash, verify_password
from promoflow.config import LOCKOUT_MINUTES, MAX_FAILED_LOGINS, SESSION_HOURS
from promoflow.db.enums import AuthProvider, RoleName
from promoflow.db.models import AuditLogEntry, AuthSession, User, UserRole


# Always use timezone-aware UTC times, so comparisons are never off by the server's time zone.
def _now() -> datetime:
    return datetime.now(timezone.utc)


# SQLite returns naive datetimes; PostgreSQL returns aware ones. This makes both comparable (tests run on SQLite,
# the real database is PostgreSQL).
def _aware(dt: datetime | None) -> datetime | None:
    # SQLite returns naive datetimes; PostgreSQL returns aware ones. Treat naive values as UTC.
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


# A one-way fingerprint of a session token. We store this, never the token itself.
def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# One role a person holds, with its scope: a HoD role is tied to a department, a Dean role to a college.
@dataclass(frozen=True)
class RoleGrant:
    role: RoleName
    department_id: int | None = None
    college_id: int | None = None


class LoginError(Exception):
    """Raised with a message that is safe to show to the user."""


# Log-in check. Returns the user or raises LoginError.
def authenticate(s: Session, email: str, password: str) -> User:
    """Check email + password. Same message for unknown email and wrong password (no account probing).

    Callers must catch LoginError *inside* their session scope so the failed-attempt counter is committed.
    """
    user = s.scalar(select(User).where(User.email == email.strip().lower()))
    # The SAME message for an unknown email and a wrong password, so nobody can use the login page to discover which
    # emails have accounts.
    generic = "Incorrect email or password."
    if user is None or not user.is_active or user.auth_provider != AuthProvider.LOCAL:
        raise LoginError(generic)
    # Lockout: after too many wrong passwords the account is locked for a few minutes (see config.py).
    if user.locked_until and _aware(user.locked_until) > _now():
        raise LoginError(f"Too many failed attempts. Try again after {LOCKOUT_MINUTES} minutes.")
    # Wrong password: count the failure, lock the account when the limit is reached, and leave a trace in the audit
    # log.
    if not verify_password(user.password_hash, password):
        user.failed_login_count += 1
        if user.failed_login_count >= MAX_FAILED_LOGINS:
            user.locked_until = _now() + timedelta(minutes=LOCKOUT_MINUTES)
            user.failed_login_count = 0
        s.add(AuditLogEntry(user_id=user.id, action="login_failed"))
        raise LoginError(generic)
    # Success. Quietly upgrade an old-style hash while we have the real password in hand, then reset the failure
    # counter.
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = _now()
    s.add(AuditLogEntry(user_id=user.id, action="login"))
    return user


# After a successful login: create a session. The browser gets a random token (a cookie); the database keeps only
# its hash.
def create_session(s: Session, user: User, user_agent: str | None = None) -> str:
    """Return a new random token. Only its SHA-256 is stored, so a database leak does not leak sessions."""
    token = secrets.token_urlsafe(32)
    now = _now()
    s.add(AuthSession(user_id=user.id, token_hash=_token_hash(token), created_at=now,
                      expires_at=now + timedelta(hours=SESSION_HOURS), user_agent=(user_agent or "")[:300]))
    return token


# Who is this token? Returns the user, or None if the token is unknown, expired, revoked or the account is switched
# off.
def user_for_token(s: Session, token: str | None) -> User | None:
    if not token:
        return None
    sess = s.scalar(select(AuthSession).where(AuthSession.token_hash == _token_hash(token)))
    if sess is None or sess.revoked_at is not None or _aware(sess.expires_at) <= _now():
        return None
    user = s.get(User, sess.user_id)
    return user if user is not None and user.is_active else None


# Log out: mark the session as revoked so the token stops working immediately.
def revoke_session(s: Session, token: str | None) -> None:
    if not token:
        return
    sess = s.scalar(select(AuthSession).where(AuthSession.token_hash == _token_hash(token)))
    if sess is not None and sess.revoked_at is None:
        sess.revoked_at = _now()
        s.add(AuditLogEntry(user_id=sess.user_id, action="logout"))


# The roles a person holds today (a role can have a start and end date).
def roles_for(s: Session, user: User) -> list[RoleGrant]:
    today = _now().date()
    rows = s.scalars(select(UserRole).where(UserRole.user_id == user.id))
    return [
        RoleGrant(r.role, r.department_id, r.college_id)
        for r in rows
        if (r.valid_from is None or r.valid_from <= today) and (r.valid_to is None or r.valid_to >= today)
    ]


# First login: the person confirms their name and employee id.
def complete_profile(s: Session, user: User, full_name: str, employee_id: str) -> None:
    """First-login profile (spec §4.1). College and department are set by Admin, not here."""
    full_name, employee_id = full_name.strip(), employee_id.strip()
    if not full_name or not employee_id:
        raise LoginError("Full name and employee ID are required.")
    taken = s.scalar(select(User).where(User.employee_id == employee_id, User.id != user.id))
    if taken is not None:
        raise LoginError("This employee ID is already registered to another account.")
    user.full_name = full_name
    user.employee_id = employee_id
    user.profile_completed_at = _now()
    s.add(AuditLogEntry(user_id=user.id, action="profile_completed"))
