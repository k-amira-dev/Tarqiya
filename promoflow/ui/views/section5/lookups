"""Admin-editable dropdown lists used across Section 5's tabs (spec §15), loaded as {id: label} maps."""
import streamlit as st
from sqlalchemy import select

from promoflow.db.models import LookupValue
from promoflow.db.session import session_scope


@st.cache_data(ttl=600, show_spinner=False)
def _options(list_code: str) -> dict[int, str]:
    with session_scope() as s:
        rows = s.scalars(select(LookupValue).where(LookupValue.list_code == list_code, LookupValue.active.is_(True))
                         .order_by(LookupValue.sort_order)).all()
        return {r.id: r.label_en for r in rows}


def creative_form_options() -> dict[int, str]:
    return _options("creative_form")


def funder_type_options() -> dict[int, str]:
    return _options("funder_type")


def patent_office_options() -> dict[int, str]:
    return _options("patent_office")


def award_scope_options() -> dict[int, str]:
    return _options("award_scope")
