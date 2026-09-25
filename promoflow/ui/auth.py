"""Streamlit login gate. Call `require_login()` at the top of every page.

The session token is kept in st.session_state and in a browser cookie, so a page refresh (which starts a
new Streamlit session) does not log the user out. Only the token's hash is in the database.
"""
from dataclasses import dataclass

import streamlit as st
import streamlit.components.v1 as components

from promoflow.auth.service import (
    LoginError, RoleGrant, authenticate, complete_profile, create_session, revoke_session, roles_for,
    user_for_token,
)
from promoflow.config import SESSION_HOURS
from promoflow.db.enums import RoleName
from promoflow.db.models import User
from promoflow.db.session import session_scope

COOKIE = "promoflow_session"

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
    # Streamlit can read cookies (st.context.cookies) but not set them, so a tiny script sets it on the page.
    components.html(
        f"<script>window.parent.document.cookie = '{COOKIE}={value}; path=/; max-age={max_age}; SameSite=Strict';"
        "</script>",
        height=0,
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


def _login_form() -> None:
    st.title("PromoFlow")
    st.caption("Faculty promotion review – decision support")
    with st.form("login"):
        email = st.text_input("University email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in", type="primary")
    if submitted:
        error, token = None, None
        with session_scope() as s:
            try:
                user = authenticate(s, email, password)
                token = create_session(s, user, st.context.headers.get("User-Agent"))
            except LoginError as e:
                error = str(e)  # caught inside the scope so the failed-attempt counter is saved
        if error:
            st.error(error)
        else:
            st.session_state["token"] = token
            _write_cookie(token, SESSION_HOURS * 3600)
            st.rerun()
    st.info("Accounts are created by the PromoFlow administrator. University single sign-on is planned for "
            "production.")


def _profile_form(user: CurrentUser) -> None:
    st.title("Complete your profile")
    st.write("Before you start, confirm the details that will appear on your promotion application.")
    with st.form("profile"):
        full_name = st.text_input("Full name (as on official documents)", value=user.full_name or "")
        employee_id = st.text_input("Employee ID", value=user.employee_id or "")
        submitted = st.form_submit_button("Save and continue", type="primary")
    if submitted:
        error = None
        with session_scope() as s:
            try:
                complete_profile(s, s.get(User, user.id), full_name, employee_id)
            except LoginError as e:
                error = str(e)
        if error:
            st.error(error)
        else:
            st.rerun()


def require_login(*allowed: RoleName) -> CurrentUser:
    """Show the login or profile form and stop the page until the user is ready; enforce roles if given."""
    token = st.session_state.get("token") or st.context.cookies.get(COOKIE)
    if not isinstance(token, str):  # no cookie context (e.g. headless tests) or malformed value
        token = None
    user = _load(token)
    if user is None:
        st.session_state.pop("token", None)
        _login_form()
        st.stop()
    st.session_state["token"] = token
    if not user.profile_complete:
        _profile_form(user)
        st.stop()
    if allowed and not user.has(*allowed):
        st.error("You do not have access to this page.")
        st.stop()
    with st.sidebar:
        st.write(f"**{user.full_name}**")
        st.caption(" · ".join(ROLE_LABELS[g.role] for g in user.roles) or "No role assigned")
        if st.button("Log out"):
            logout()
    return user


def logout() -> None:
    with session_scope() as s:
        revoke_session(s, st.session_state.get("token"))
    st.session_state.pop("token", None)
    _write_cookie("", 0)
    st.rerun()
