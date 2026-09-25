"""Declarative base, naming conventions and shared column mixins."""
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

# Deterministic constraint names, so Alembic migrations are stable across machines.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# BIGINT primary keys in PostgreSQL; plain INTEGER on SQLite so autoincrement works in quick local tests.
PK_TYPE = BigInteger().with_variant(Integer(), "sqlite")


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def pg_enum(enum_cls: type[PyEnum], name: str | None = None) -> Enum:
    """Store the enum's lowercase *values* (not member names) as a native PostgreSQL enum type."""
    return Enum(
        enum_cls,
        name=name or enum_cls.__name__.lower(),
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )


class IdMixin:
    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, sort_order=-100)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), sort_order=100)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), sort_order=101
    )


class CaseChildMixin(IdMixin, TimestampMixin):
    """Every dossier entry belongs to exactly one promotion case and is deleted with it."""

    @declared_attr
    def case_id(cls) -> Mapped[int]:
        return mapped_column(ForeignKey("promotion_case.id", ondelete="CASCADE"), index=True, sort_order=-99)
