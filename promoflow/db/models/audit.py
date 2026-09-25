"""Append-only audit log: every status change, approval, score change and upload."""
from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from promoflow.db.base import Base, IdMixin


# JSONB in PostgreSQL; plain JSON elsewhere so the login flow can also run on SQLite for quick tests.
JSON_DOC = JSON().with_variant(JSONB(), "postgresql")


class AuditLogEntry(IdMixin, Base):
    __tablename__ = "audit_log_entry"
    __table_args__ = (Index("ix_audit_log_entry_entity", "entity_table", "entity_id"),)

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))  # NULL = system / agent
    case_id: Mapped[int | None] = mapped_column(ForeignKey("promotion_case.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(64))  # e.g. "login", "gate_approve", "rubric_change"
    entity_table: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[int | None] = mapped_column(BigInteger)
    before: Mapped[dict | None] = mapped_column(JSON_DOC)
    after: Mapped[dict | None] = mapped_column(JSON_DOC)
    detail: Mapped[str | None] = mapped_column(Text)
