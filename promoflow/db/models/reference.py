"""Reference data: policy versions, thresholds, rubrics, journal rankings, editable lists, policy text.

"Reference data" is information the system looks up but applicants do not enter: the policy thresholds, the two
scoring rubrics (Appendix E and F), journal rankings, dropdown lists and the policy text used for search. It is loaded by
db/seed.py and meant to be changed by an admin, not by editing code.
"""
from datetime import date
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean, CheckConstraint, Computed, Date, ForeignKey, Index, Integer, Numeric, SmallInteger, String, Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from promoflow.config import EMBEDDING_DIM
from promoflow.db.base import Base, IdMixin, TimestampMixin, pg_enum
from promoflow.db.enums import CriterionArea, JournalClass, PromotionTrack, RubricCode


class PolicyVersion(IdMixin, TimestampMixin, Base):
    """A version of the governing policy. A case is judged by the version in force on its submission date."""

    __tablename__ = "policy_version"

    code: Mapped[str] = mapped_column(String(40), unique=True)  # e.g. "SCHESR-2026-05"
    title: Mapped[str] = mapped_column(String(300))
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    document_path: Mapped[str | None] = mapped_column(String(500))


class PromotionCriteria(IdMixin, TimestampMixin, Base):
    """All numeric thresholds for one track under one policy version (conditions doc §1, §2, §6, §7)."""

    __tablename__ = "promotion_criteria"
    __table_args__ = (UniqueConstraint("policy_version_id", "track"),)

    policy_version_id: Mapped[int] = mapped_column(ForeignKey("policy_version.id"))
    track: Mapped[PromotionTrack] = mapped_column(pg_enum(PromotionTrack))

    # Eligibility
    min_years_in_rank: Mapped[int] = mapped_column(SmallInteger)
    min_years_at_institution: Mapped[int] = mapped_column(SmallInteger)
    early_application_months: Mapped[int] = mapped_column(SmallInteger)
    exceptional_min_years: Mapped[int] = mapped_column(SmallInteger)
    reapply_min_years: Mapped[int] = mapped_column(SmallInteger)
    reapply_new_publications: Mapped[int] = mapped_column(SmallInteger)
    reapply_new_class_a: Mapped[int] = mapped_column(SmallInteger)
    reapply_new_main_author: Mapped[int] = mapped_column(SmallInteger)
    # Research minimums
    min_total_publications: Mapped[int] = mapped_column(SmallInteger)
    min_sole_main_author: Mapped[int] = mapped_column(SmallInteger)
    min_published: Mapped[int] = mapped_column(SmallInteger)
    min_at_institution: Mapped[int] = mapped_column(SmallInteger)
    min_class_a_main_author: Mapped[int] = mapped_column(SmallInteger)
    # Research caps
    max_supervision_rule_papers: Mapped[int] = mapped_column(SmallInteger)
    max_books_total: Mapped[int] = mapped_column(SmallInteger)
    max_patents: Mapped[int] = mapped_column(SmallInteger)
    max_creative_works: Mapped[int] = mapped_column(SmallInteger)
    # Referees
    min_referee_reports: Mapped[int] = mapped_column(SmallInteger)
    min_referee_average_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))


class ResearchItemCap(IdMixin, Base):
    """Per-type caps for books and similar items (p.6), e.g. textbooks max 1."""

    __tablename__ = "research_item_cap"
    __table_args__ = (UniqueConstraint("policy_version_id", "track", "item_type"),)

    policy_version_id: Mapped[int] = mapped_column(ForeignKey("policy_version.id"))
    track: Mapped[PromotionTrack] = mapped_column(pg_enum(PromotionTrack))
    item_type: Mapped[str] = mapped_column(String(40))  # BookItemType value
    max_count: Mapped[int] = mapped_column(SmallInteger)
    counts_as_class: Mapped[JournalClass | None] = mapped_column(pg_enum(JournalClass))


class Rubric(IdMixin, TimestampMixin, Base):
    """Appendix E (teaching, 30 pts) or Appendix F (service, 10 pts)."""

    __tablename__ = "rubric"
    __table_args__ = (UniqueConstraint("policy_version_id", "code"),)

    policy_version_id: Mapped[int] = mapped_column(ForeignKey("policy_version.id"))
    code: Mapped[RubricCode] = mapped_column(pg_enum(RubricCode))
    title: Mapped[str] = mapped_column(String(200))
    total_points: Mapped[Decimal] = mapped_column(Numeric(5, 1))
    pass_points: Mapped[Decimal] = mapped_column(Numeric(5, 1))  # a setting: service is 7 or 8 (open question)

    items: Mapped[list["RubricItem"]] = relationship(back_populates="rubric", order_by="RubricItem.item_no")


class RubricItem(IdMixin, Base):
    __tablename__ = "rubric_item"
    __table_args__ = (
        UniqueConstraint("rubric_id", "item_no"),
        CheckConstraint("min_points >= 0 AND max_points >= min_points", name="points_range"),
    )

    rubric_id: Mapped[int] = mapped_column(ForeignKey("rubric.id", ondelete="CASCADE"))
    item_no: Mapped[int] = mapped_column(SmallInteger)
    text_en: Mapped[str] = mapped_column(Text)
    text_ar: Mapped[str | None] = mapped_column(Text)
    min_points: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    max_points: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    full_professor_only: Mapped[bool] = mapped_column(Boolean, default=False)  # Appendix E item 5
    redistributable: Mapped[bool] = mapped_column(Boolean, default=False)  # Appendix E item 9 footnote

    rubric: Mapped[Rubric] = relationship(back_populates="items")


class Journal(IdMixin, TimestampMixin, Base):
    __tablename__ = "journal"

    title: Mapped[str] = mapped_column(String(400))
    issn: Mapped[str | None] = mapped_column(String(9), unique=True)
    eissn: Mapped[str | None] = mapped_column(String(9), unique=True)
    publisher: Mapped[str | None] = mapped_column(String(300))
    scopus_source_id: Mapped[str | None] = mapped_column(String(40))
    isi_listed: Mapped[bool] = mapped_column(Boolean, default=False)


class JournalRanking(IdMixin, Base):
    """One SJR category ranking of a journal for one year. The A/B class is computed by rule, not stored."""

    __tablename__ = "journal_ranking"
    __table_args__ = (
        UniqueConstraint("journal_id", "year", "sjr_category"),
        CheckConstraint("quartile BETWEEN 1 AND 4", name="quartile_range"),
        CheckConstraint("sjr_percentile BETWEEN 0 AND 100", name="percentile_range"),
    )

    journal_id: Mapped[int] = mapped_column(ForeignKey("journal.id", ondelete="CASCADE"), index=True)
    year: Mapped[int] = mapped_column(SmallInteger)
    scopus_indexed: Mapped[bool] = mapped_column(Boolean, default=True)
    sjr_category: Mapped[str] = mapped_column(String(200))
    sjr_percentile: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    quartile: Mapped[int | None] = mapped_column(SmallInteger)
    impact_factor: Mapped[Decimal | None] = mapped_column(Numeric(7, 3))


class LookupValue(IdMixin, Base):
    """Admin-editable dropdown values (spec §15), e.g. list_code='committee_role', code='chair'."""

    __tablename__ = "lookup_value"
    __table_args__ = (UniqueConstraint("list_code", "code"),)

    list_code: Mapped[str] = mapped_column(String(60), index=True)
    code: Mapped[str] = mapped_column(String(60))
    label_en: Mapped[str] = mapped_column(String(200))
    label_ar: Mapped[str | None] = mapped_column(String(200))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class PolicyChunk(IdMixin, TimestampMixin, Base):
    """A clause of the policy text for RAG: full-text search (tsv) + vector similarity (embedding)."""

    __tablename__ = "policy_chunk"
    __table_args__ = (
        Index("ix_policy_chunk_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_policy_chunk_embedding", "embedding",
            postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    policy_version_id: Mapped[int] = mapped_column(ForeignKey("policy_version.id"), index=True)
    area: Mapped[CriterionArea] = mapped_column(pg_enum(CriterionArea))
    section_ref: Mapped[str | None] = mapped_column(String(60))  # e.g. "§2.2"
    page: Mapped[int | None] = mapped_column(SmallInteger)
    text: Mapped[str] = mapped_column(Text)
    tsv: Mapped[str] = mapped_column(TSVECTOR, Computed("to_tsvector('simple', text)", persisted=True))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
