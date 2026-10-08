"""Admin-editable dropdown lists used across Section 7's tabs (spec §15). Section 8 also borrows
`recommendation_relationship_options` from here rather than duplicating the small `Option` helper."""
from dataclasses import dataclass

import streamlit as st
from sqlalchemy import select

from promoflow.db.models import LookupValue
from promoflow.db.session import session_scope


@dataclass(frozen=True)
class Option:
    id: int
    code: str
    label: str


@st.cache_data(ttl=600, show_spinner=False)
def _options(list_code: str) -> list[Option]:
    with session_scope() as s:
        rows = s.scalars(select(LookupValue).where(LookupValue.list_code == list_code, LookupValue.active.is_(True))
                         .order_by(LookupValue.sort_order)).all()
        return [Option(r.id, r.code, r.label_en) for r in rows]


def committee_role_options() -> list[Option]:
    return _options("committee_role")


def admin_position_options() -> list[Option]:
    return _options("admin_position")


def policy_role_options() -> list[Option]:
    return _options("policy_role")


def community_activity_type_options() -> list[Option]:
    return _options("community_activity_type")


def recommendation_relationship_options() -> list[Option]:
    return _options("recommendation_relationship")
