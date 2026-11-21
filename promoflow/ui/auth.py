"""Streamlit login gate. Call `require_login()` at the top of every page.

The session token is kept in st.session_state and in a browser cookie, so a page refresh (which starts a
new Streamlit session) does not log the user out. Only the token's hash is in the database.
"""
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import streamlit as st
from sqlalchemy.exc import OperationalError

from promoflow.auth.service import (
    LoginError, RoleGrant, authenticate, complete_profile, create_session, revoke_session, roles_for,
    user_for_token,
)
from promoflow.config import DATABASE_URL, SESSION_HOURS
from promoflow.db.enums import RoleName
from promoflow.db.models import User
from promoflow.db.session import session_scope
from promoflow.ui import cache, theme

COOKIE = "promoflow_session"
USER_CACHE_KEY = "pf_user_cache"
USER_TTL_SECONDS = 120  # how long a revoked session can keep working; saves 3 queries on every page change

ROLE_LABELS = {
    RoleName.APPLICANT: "Applicant", RoleName.HOD: "Head of Department", RoleName.DEAN: "Dean",
    RoleName.CHANCELLOR: "Chancellor", RoleName.ADMIN: "Admin",
}


@dataclass(frozen=True)
class CurrentUser:
    id: int
    email: str
    full_name: str | None
    employee_id: str | None
    department_id: int | None
    college_id: int | None
    profile_complete: bool
    roles: tuple[RoleGrant, ...]

    def has(self, *roles: RoleName) -> bool:
        return any(g.role in roles for g in self.roles)


def _write_cookie(value: str, max_age: int) -> None:
    # Streamlit can read cookies (st.context.cookies) but not set them, so a tiny same-origin script sets it.
    # Only our own fixed script and a random token go in here, never user input.
    st.iframe(
        f"<script>window.parent.document.cookie = '{COOKIE}={value}; path=/; max-age={max_age}; SameSite=Strict';"
        "</script>",
        height=1,
    )


def _load(token: str | None) -> CurrentUser | None:
    with session_scope() as s:
        user = user_for_token(s, token)
        if user is None:
            return None
        return CurrentUser(
            id=user.id, email=user.email, full_name=user.full_name, employee_id=user.employee_id,
            department_id=user.department_id, college_id=user.college_id,
            profile_complete=user.profile_completed_at is not None, roles=tuple(roles_for(s, user)),
        )


def _auth_frame(title: str, subtitle: str):
    """Black top bar + a centred white card; returns the card container."""
    theme.inject_auth()
    theme.html(f"""
    <div class="pf-topbar"><div class="l">{theme.logo(26)}<span>Tarqiya</span></div>
    <div class="r">University of Sharjah · Faculty Promotion Review</div></div>""")
    _, mid, _ = st.columns([1, 1.15, 1])
    card = mid.container(key="auth_card")
    theme.html(f"""
    <div class="pf-auth-mark">{theme.uos_logo(84)}</div>
    <div class="pf-auth-h">{theme.esc(title)}</div>
    <div class="pf-auth-s">{theme.esc(subtitle)}</div>""", card)
    return mid, card


def _login_form() -> None:
    mid, card = _auth_frame("Welcome to Tarqiya", "Sign in to continue to your promotion workspace")
    with card:
        with st.form("login", border=False):
            email = st.text_input("University email", placeholder="name@sharjah.ac.ae")
            password = st.text_input("Password", type="password", placeholder="••••••••")
            submitted = st.form_submit_button("Sign in  →", type="primary", use_container_width=True)
        error_slot = st.empty()
        theme.html('<div class="pf-auth-foot">Accounts are issued by the promotion office.<br/>'
                   'University single sign-on will replace passwords in production.</div>')
    theme.html('<div class="pf-legal">Decision support only: every step is approved by a person.</div>', mid)
    if submitted:
        error, token = None, None
        with session_scope() as s:
            try:
                user = authenticate(s, email, password)
                token = create_session(s, user, st.context.headers.get("User-Agent"))
            except LoginError as e:
                error = str(e)  # caught inside the scope so the failed-attempt counter is saved
        if error:
            error_slot.error(error)
        else:
            st.session_state["token"] = token
            _write_cookie(token, SESSION_HOURS * 3600)
            st.rerun()


def _profile_form(user: CurrentUser) -> None:
    _, card = _auth_frame("Complete your profile",
                          "These details appear on your promotion application. You only do this once.")
    with card:
        with st.form("profile", border=False):
            full_name = st.text_input("Full name (as on official documents)", value=user.full_name or "")
            employee_id = st.text_input("Employee ID", value=user.employee_id or "", placeholder="e.g. E-1001")
            submitted = st.form_submit_button("Save and continue  →", type="primary", use_container_width=True)
        error_slot = st.empty()
    if submitted:
        error = None
        with session_scope() as s:
            try:
                complete_profile(s, s.get(User, user.id), full_name, employee_id)
            except LoginError as e:
                error = str(e)
        if error:
            error_slot.error(error)
        else:
            st.rerun()


def require_login(*allowed: RoleName) -> CurrentUser:
    """Show the login or profile form and stop the page until the user is ready; enforce roles if given."""
    try:
        return _gate(allowed)
    except OperationalError as e:
        # Say which database could not be reached (never the password), instead of a long traceback.
        st.error(f"Cannot reach the database at **{urlsplit(DATABASE_URL).hostname}**. "
                 "Check DATABASE_URL in .env (local) or in the app's Secrets (Streamlit Cloud).")
        st.caption(str(e.orig).splitlines()[0] if e.orig else "")
        st.stop()


def _cached_user(token: str | None) -> CurrentUser | None:
    """`_load` costs three round trips, so reuse its result until a write happens or the TTL passes."""
    version = st.session_state.get(cache.VERSION_KEY, 0)
    hit = st.session_state.get(USER_CACHE_KEY)
    if token and hit and hit[0] == token and hit[1] == version and time.monotonic() - hit[2] < USER_TTL_SECONDS:
        return hit[3]
    user = _load(token)
    if user is not None:
        st.session_state[USER_CACHE_KEY] = (token, version, time.monotonic(), user)
    return user


def _gate(allowed: tuple[RoleName, ...]) -> CurrentUser:
    token = st.session_state.get("token") or st.context.cookies.get(COOKIE)
    if not isinstance(token, str):  # no cookie context (e.g. headless tests) or malformed value
        token = None
    user = _cached_user(token)
    if user is None:
        st.session_state.pop("token", None)
        st.session_state.pop(USER_CACHE_KEY, None)
        _login_form()
        st.stop()
    st.session_state["token"] = token
    if not user.profile_complete:
        _profile_form(user)
        st.stop()
    if allowed and not user.has(*allowed):
        st.error("You do not have access to this page.")
        st.stop()
    return user


def logout() -> None:
    with session_scope() as s:
        revoke_session(s, st.session_state.get("token"))
    st.session_state.pop("token", None)
    st.session_state.pop(USER_CACHE_KEY, None)
    cache.clear()
    _write_cookie("", 0)
    st.rerun()
