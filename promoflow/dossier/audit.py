"""Shared audit-log helper: every entry add/edit/delete records a before/after snapshot (spec §2.4)."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from promoflow.db.models import AuditLogEntry


# Turn dates, decimals and enums into plain values that can be stored as JSON.
def json_value(v):
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return v.value if hasattr(v, "value") else v


# Copy the listed fields of a row into a dictionary. Taken BEFORE and AFTER a change, so the audit log shows exactly
# what changed.
def snapshot(obj, fields: list[str]) -> dict:
    return {f: json_value(getattr(obj, f)) for f in fields}


# Add one audit-log row. Nothing is written when before and after are the same, so saving without changing anything
# leaves no trace.
def log(s: Session, *, user_id: int, case_id: int, action: str, entity_table: str, entity_id: int,
       before: dict | None, after: dict | None) -> None:
    if before != after:
        s.add(AuditLogEntry(user_id=user_id, case_id=case_id, action=action, entity_table=entity_table,
                            entity_id=entity_id, before=before, after=after))
