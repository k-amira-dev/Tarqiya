"""Shared audit-log helper: every entry add/edit/delete records a before/after snapshot (spec §2.4)."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from promoflow.db.models import AuditLogEntry


def json_value(v):
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return v.value if hasattr(v, "value") else v


def snapshot(obj, fields: list[str]) -> dict:
    return {f: json_value(getattr(obj, f)) for f in fields}


def log(s: Session, *, user_id: int, case_id: int, action: str, entity_table: str, entity_id: int,
       before: dict | None, after: dict | None) -> None:
    if before != after:
        s.add(AuditLogEntry(user_id=user_id, case_id=case_id, action=action, entity_table=entity_table,
                            entity_id=entity_id, before=before, after=after))
