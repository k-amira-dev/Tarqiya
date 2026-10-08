"""Per-session page cache. Every database round trip costs ~190 ms from the UAE to the US-East database, and
Streamlit re-runs the whole page on every interaction, so loaders are cached in the user's session and the cache
is dropped as soon as any scope writes data (see `promoflow.db.session.write_hooks`).
"""
import time
from collections.abc import Callable
from typing import TypeVar

import streamlit as st
from sqlalchemy.orm import Session

from promoflow.db import session as db_session
from promoflow.db.session import session_scope

T = TypeVar("T")
VERSION_KEY = "pf_data_version"
TTL_SECONDS = 300  # also bounds how long data changed by someone else (e.g. a reviewer) can look stale


def _bump_version() -> None:
    try:
        st.session_state[VERSION_KEY] = st.session_state.get(VERSION_KEY, 0) + 1
    except Exception:  # not inside a Streamlit run (scripts, tests)
        pass


if _bump_version not in db_session.write_hooks:
    db_session.write_hooks.append(_bump_version)


def load_cached(key: str, loader: Callable[[Session], T], ttl: int = TTL_SECONDS) -> T:
    """Run `loader(session)` once per session until something is written or `ttl` seconds pass."""
    version = st.session_state.get(VERSION_KEY, 0)
    hit = st.session_state.get(key)
    if hit is not None and hit[0] == version and time.monotonic() - hit[1] < ttl:
        return hit[2]
    with session_scope() as s:
        value = loader(s)
    st.session_state[key] = (version, time.monotonic(), value)
    return value


def clear() -> None:
    """Forget every cached page (on logout)."""
    for key in [k for k in st.session_state if isinstance(st.session_state[k], tuple) and k.startswith("pfc:")]:
        del st.session_state[key]
    st.session_state.pop(VERSION_KEY, None)
