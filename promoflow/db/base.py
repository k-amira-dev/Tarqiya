"""Declarative base, naming conventions and shared column mixins.

READ THIS FIRST IF YOU ARE NEW TO SQLALCHEMY
--------------------------------------------
A database table is described in Python as a CLASS. Each class attribute is a COLUMN:

    class Degree(CaseChildMixin, Base):          # -> the table `degree`
        level: Mapped[DegreeLevel] = mapped_column(...)   # -> a column `level` holding a DegreeLevel value

  * `Base` is the parent of every table class. It collects them all so Alembic (the migration tool) can see them.
  * `Mapped[X]` says what Python type the column holds; `mapped_column(...)` adds the database details (length,
    foreign key, default, and so on). `Mapped[str | None]` means the column may be empty (NULL).
  * A "mixin" is a small class that adds columns to every class that inherits from it, so we don't repeat them.
    `IdMixin` gives every table an `id`, `TimestampMixin` adds created/updated times, and `CaseChildMixin` marks a
    table as "belongs to one promotion case" (it adds `case_id`).
  * A row is one Python OBJECT: `Degree(level=..., university=...)`. You `session.add(obj)` to insert it.
"""
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

# Deterministic constraint names, so Alembic migrations are stable across machines.
# (Without this, the database invents random names for keys and indexes, and every migration would differ.)
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# BIGINT primary keys in PostgreSQL; plain INTEGER on SQLite so autoincrement works in quick local tests.
# (`with_variant` = "use this type normally, but that one when the database is SQLite".)
PK_TYPE = BigInteger().with_variant(Integer(), "sqlite")


class Base(DeclarativeBase):
    """Parent of every table class. Its `metadata` is the registry of all tables."""
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def pg_enum(enum_cls: type[PyEnum], name: str | None = None) -> Enum:
    """Store the enum's lowercase *values* (not member names) as a native PostgreSQL enum type.

    Example: the Python enum member `CaseStatus.HOD_REVIEW` is saved in the database as the text "hod_review".
    The database then refuses any other value, which protects the data from typos."""
    return Enum(
        enum_cls,
        name=name or enum_cls.__name__.lower(),
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )


class IdMixin:
    """Every table gets an automatic whole-number `id`, its unique row number (the primary key)."""
    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, sort_order=-100)


class TimestampMixin:
    """`created_at` is set by the database when the row is inserted; `updated_at` changes whenever it is edited."""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), sort_order=100)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), sort_order=101
    )


class CaseChildMixin(IdMixin, TimestampMixin):
    """Every dossier entry belongs to exactly one promotion case and is deleted with it.

    `ondelete="CASCADE"` is the "deleted with it" part: when a case row is deleted, the database automatically deletes
    all of its child rows too (degrees, papers, courses, ...). `index=True` makes looking up "all rows of case 7" fast."""

    @declared_attr
    def case_id(cls) -> Mapped[int]:
        return mapped_column(ForeignKey("promotion_case.id", ondelete="CASCADE"), index=True, sort_order=-99)
