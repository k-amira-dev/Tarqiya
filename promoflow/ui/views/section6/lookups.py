"""Admin-editable dropdown lists used across Section 6's tabs (spec §15), as (id, code, label) rows so the
UI can both display a label and branch on the underlying code (e.g. "is this a course modification?")."""
from dataclasses import dataclass

from sqlalchemy import select

from promoflow.db.models import LookupValue
from promoflow.db.session import session_scope


@dataclass(frozen=True)
class Option:
    id: int
    code: str
    label: str


def _options(list_code: str) -> list[Option]:
    with session_scope() as s:
        rows = s.scalars(select(LookupValue).where(LookupValue.list_code == list_code, LookupValue.active.is_(True))
                         .order_by(LookupValue.sort_order)).all()
        return [Option(r.id, r.code, r.label_en) for r in rows]


def observer_role_options() -> list[Option]:
    return _options("observer_role")


def curriculum_contribution_type_options() -> list[Option]:
    return _options("curriculum_contribution_type")


def course_change_options() -> list[Option]:
    return _options("course_change")


def course_file_system_options() -> list[Option]:
    return _options("course_file_system")


def course_file_item_options() -> list[Option]:
    return _options("course_file_item")


def innovation_type_options() -> list[Option]:
    return _options("innovation_type")


def development_topic_options() -> list[Option]:
    return _options("development_topic")
