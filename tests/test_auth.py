"""Login and sessions (promoflow/auth): password hashing, the same error for a wrong email and a wrong password,
lock-out after repeated failures, hashed and revocable session tokens, scoped roles, and the unique employee id.
These run on a tiny in-memory SQLite database.
"""
from datetime import timedelta

import pytest

from promoflow.auth.passwords import hash_password, verify_password
from promoflow.auth.service import (
    LoginError, _now, authenticate, complete_profile, create_session, revoke_session, roles_for, user_for_token,
)
from promoflow.config import MAX_FAILED_LOGINS
from promoflow.db.enums import RoleName
from promoflow.db.models import AuthSession, College, Department, User, UserRole


def make_user(s, email="a@x.test", password="secret-pass"):
    u = User(email=email, password_hash=hash_password(password))
    s.add(u)
    s.flush()
    return u


def test_password_hash_roundtrip():
    h = hash_password("correct horse")
    assert h.startswith("$argon2id$")
    assert verify_password(h, "correct horse")
    assert not verify_password(h, "wrong")
    assert not verify_password("not-a-hash", "x")


def test_login_success_and_same_error_for_unknown_email(auth_db):
    make_user(auth_db)
    assert authenticate(auth_db, "A@X.test ", "secret-pass").email == "a@x.test"
    with pytest.raises(LoginError) as wrong_pw:
        authenticate(auth_db, "a@x.test", "nope")
    with pytest.raises(LoginError) as unknown:
        authenticate(auth_db, "nobody@x.test", "nope")
    assert str(wrong_pw.value) == str(unknown.value)


def test_lockout_after_repeated_failures(auth_db):
    make_user(auth_db)
    for _ in range(MAX_FAILED_LOGINS):
        with pytest.raises(LoginError):
            authenticate(auth_db, "a@x.test", "nope")
    with pytest.raises(LoginError, match="Too many failed attempts"):
        authenticate(auth_db, "a@x.test", "secret-pass")


def test_session_token_is_hashed_and_revocable(auth_db):
    u = make_user(auth_db)
    token = create_session(auth_db, u)
    auth_db.flush()
    stored = auth_db.query(AuthSession).one()
    assert stored.token_hash != token and len(stored.token_hash) == 64
    assert user_for_token(auth_db, token).id == u.id
    revoke_session(auth_db, token)
    auth_db.flush()
    assert user_for_token(auth_db, token) is None


def test_expired_session_rejected(auth_db):
    u = make_user(auth_db)
    token = create_session(auth_db, u)
    auth_db.flush()
    auth_db.query(AuthSession).one().expires_at = _now() - timedelta(minutes=1)
    auth_db.flush()
    assert user_for_token(auth_db, token) is None


def test_one_person_several_scoped_roles(auth_db):
    college = College(code="C", name_en="College")
    auth_db.add(college)
    auth_db.flush()
    dept = Department(code="D", name_en="Dept", college_id=college.id)
    auth_db.add(dept)
    u = make_user(auth_db)
    auth_db.add_all([UserRole(user_id=u.id, role=RoleName.APPLICANT),
                     UserRole(user_id=u.id, role=RoleName.HOD, department_id=dept.id)])
    auth_db.flush()
    grants = {g.role: g for g in roles_for(auth_db, u)}
    assert set(grants) == {RoleName.APPLICANT, RoleName.HOD}
    assert grants[RoleName.HOD].department_id == dept.id


def test_profile_requires_unique_employee_id(auth_db):
    a, b = make_user(auth_db, "a@x.test"), make_user(auth_db, "b@x.test")
    complete_profile(auth_db, a, "Dr A", "E1")
    auth_db.flush()
    assert a.profile_completed_at is not None
    with pytest.raises(LoginError, match="already registered"):
        complete_profile(auth_db, b, "Dr B", "E1")
