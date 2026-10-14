"""The promotion case (spec §0, §1), its documents, status history and dossier sections 3–4.

`PromotionCase` is the centre of the data model: every other table about an application points back to it through
`case_id`. Section 0 of the form lives directly on it; the other sections have their own tables.
"""
from datetime import date, datetime

from sqlalchemy import (
    JSON, BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from promoflow.config import MAX_UPLOAD_BYTES
from promoflow.db.base import Base, CaseChildMixin, IdMixin, TimestampMixin, pg_enum
from promoflow.db.enums import CaseStatus, DegreeLevel, DocumentKind, PromotionTrack, Rank


class PromotionCase(IdMixin, TimestampMixin, Base):
    """One application. Section 0 answers are stored here as a snapshot at submission time."""

    __tablename__ = "promotion_case"
    # Rules the DATABASE itself enforces, whatever the Python code does. Example: an exceptional-case request must
    # come with a justification, so bad data can never be saved.
    __table_args__ = (
        CheckConstraint(
            "NOT exceptional_case OR exceptional_justification IS NOT NULL", name="exceptional_needs_justification"
        ),
        CheckConstraint("NOT previously_rejected OR rejection_date IS NOT NULL", name="rejection_needs_date"),
    )

    # Who applied: a link (a 'foreign key') to that person's row in app_user.
    applicant_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), index=True)
    # Which version of the policy this case is judged by.
    policy_version_id: Mapped[int] = mapped_column(ForeignKey("policy_version.id"))
    track: Mapped[PromotionTrack] = mapped_column(pg_enum(PromotionTrack))
    academic_year: Mapped[str] = mapped_column(String(9))  # "2026/2027"
    # Where the case is in its life (see CaseStatus in enums.py). After the draft stage only review_service.py and
    # the Submit button change it.
    status: Mapped[CaseStatus] = mapped_column(pg_enum(CaseStatus), default=CaseStatus.DRAFT, index=True)

    # §4.2 promotion track details
    specialization: Mapped[str | None] = mapped_column(String(200))
    fine_specialization: Mapped[str | None] = mapped_column(String(200))
    research_keywords: Mapped[list[str] | None] = mapped_column(ARRAY(String(80)).with_variant(JSON(), "sqlite"))

    # §4.3 appointment and current rank
    appointment_date: Mapped[date | None] = mapped_column(Date)
    rank_on_appointment: Mapped[Rank | None] = mapped_column(pg_enum(Rank))
    current_rank: Mapped[Rank | None] = mapped_column(pg_enum(Rank))
    current_rank_date: Mapped[date | None] = mapped_column(Date)

    # §4.4 research identifiers
    scopus_author_id: Mapped[str | None] = mapped_column(String(40))
    orcid: Mapped[str | None] = mapped_column(String(19))
    openalex_author_id: Mapped[str | None] = mapped_column(String(40))

    # §4.5 special conditions
    phd_outside_uae: Mapped[bool | None] = mapped_column(Boolean)
    early_application: Mapped[bool] = mapped_column(Boolean, default=False)
    exceptional_case: Mapped[bool] = mapped_column(Boolean, default=False)
    exceptional_justification: Mapped[str | None] = mapped_column(Text)
    previously_rejected: Mapped[bool] = mapped_column(Boolean, default=False)
    rejection_date: Mapped[date | None] = mapped_column(Date)

    # §2 Curriculum Vitae
    cv_last_updated: Mapped[date | None] = mapped_column(Date)  # month-year, day = 1

    # §5.2 declaration (Appendix I, Ninth)
    decl_not_from_thesis: Mapped[bool] = mapped_column(Boolean, default=False)
    decl_after_current_rank: Mapped[bool] = mapped_column(Boolean, default=False)
    application_signed_date: Mapped[date | None] = mapped_column(Date)

    # §9 Conditions Form / §10 Cover Letter (each a signed-file upload plus its date)
    conditions_signed_date: Mapped[date | None] = mapped_column(Date)
    cover_letter_signed_date: Mapped[date | None] = mapped_column(Date)

    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # A relationship is a Python shortcut, not a column: `case.applicant` gives the User object without writing a
    # query.
    applicant = relationship("User")
    status_history: Mapped[list["CaseStatusHistory"]] = relationship(back_populates="case")


# One row per status change: who changed it, when, and why. It gives the full timeline of a case.
class CaseStatusHistory(IdMixin, Base):
    __tablename__ = "case_status_history"

    case_id: Mapped[int] = mapped_column(ForeignKey("promotion_case.id", ondelete="CASCADE"), index=True)
    from_status: Mapped[CaseStatus | None] = mapped_column(pg_enum(CaseStatus))
    to_status: Mapped[CaseStatus] = mapped_column(pg_enum(CaseStatus))
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))  # NULL = system
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    note: Mapped[str | None] = mapped_column(Text)

    case: Mapped[PromotionCase] = relationship(back_populates="status_history")


class CaseDocument(IdMixin, Base):
    """Every uploaded file. Attached to one dossier entry (entity_table + entity_id) or to a whole section.

    The (entity_table, entity_id) pair is a polymorphic link, validated in application code: one table
    serves ~30 entry tables instead of 30 separate document tables.
    """

    __tablename__ = "case_document"
    __table_args__ = (
        CheckConstraint("(entity_table IS NULL) = (entity_id IS NULL)", name="entity_pair"),
        CheckConstraint(f"size_bytes > 0 AND size_bytes <= {MAX_UPLOAD_BYTES}", name="size_limit"),
        Index("ix_case_document_entity", "entity_table", "entity_id"),
    )

    case_id: Mapped[int] = mapped_column(ForeignKey("promotion_case.id", ondelete="CASCADE"), index=True)
    section_code: Mapped[str] = mapped_column(String(8))  # "1", "5A", "6C", ...
    entity_table: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[int | None] = mapped_column(BigInteger)
    kind: Mapped[DocumentKind] = mapped_column(pg_enum(DocumentKind))
    # Disambiguates several files of the same kind on one entity, e.g. degree "certificate" vs "equivalency".
    slot: Mapped[str | None] = mapped_column(String(60))
    original_filename: Mapped[str] = mapped_column(String(300))
    stored_path: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    # A fingerprint of the file's contents. It proves later that the file was not altered, and spots duplicates.
    sha256: Mapped[str] = mapped_column(String(64))
    signed_date: Mapped[date | None] = mapped_column(Date)  # for signed forms and letters
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("app_user.id"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    superseded_by_id: Mapped[int | None] = mapped_column(ForeignKey("case_document.id"))  # kept on replacement


class Degree(CaseChildMixin, Base):
    """§3 – one academic degree (Appendix I, First)."""

    __tablename__ = "degree"
    __table_args__ = (CheckConstraint("study_to IS NULL OR study_to >= study_from", name="study_period"),)

    level: Mapped[DegreeLevel] = mapped_column(pg_enum(DegreeLevel))
    specialization: Mapped[str] = mapped_column(String(200))
    university: Mapped[str] = mapped_column(String(300))
    country_code: Mapped[str] = mapped_column(String(2))  # ISO 3166-1 alpha-2
    study_from: Mapped[date] = mapped_column(Date)
    study_to: Mapped[date | None] = mapped_column(Date)
    graduation_date: Mapped[date] = mapped_column(Date)
    thesis_title: Mapped[str | None] = mapped_column(String(500))
    equivalency_required: Mapped[bool] = mapped_column(Boolean, default=False)


class RankHistory(CaseChildMixin, Base):
    """§4A – one academic rank held (Appendix I, Second). Drives time-in-rank."""

    __tablename__ = "rank_history"
    __table_args__ = (CheckConstraint("held_to IS NULL OR held_to >= held_from", name="held_period"),)

    rank: Mapped[Rank] = mapped_column(pg_enum(Rank))
    date_obtained: Mapped[date] = mapped_column(Date)
    university: Mapped[str] = mapped_column(String(300))
    country_code: Mapped[str] = mapped_column(String(2))
    held_from: Mapped[date] = mapped_column(Date)
    held_to: Mapped[date | None] = mapped_column(Date)  # NULL = current rank
    at_this_university: Mapped[bool] = mapped_column(Boolean)


class NonAcademicPosition(CaseChildMixin, Base):
    """§4B – Appendix I, Third."""

    __tablename__ = "non_academic_position"

    position: Mapped[str] = mapped_column(String(200))
    employer: Mapped[str] = mapped_column(String(300))
    country_code: Mapped[str] = mapped_column(String(2))
    date_from: Mapped[date] = mapped_column(Date)
    date_to: Mapped[date | None] = mapped_column(Date)


class ScopusEvidence(CaseChildMixin, Base):
    """§5F – metrics as entered by the applicant from their Scopus profile screenshot."""

    __tablename__ = "scopus_evidence"
    __table_args__ = (
        UniqueConstraint("case_id"),
        CheckConstraint("h_index >= 0 AND total_citations >= 0", name="non_negative"),
    )

    h_index: Mapped[int] = mapped_column(Integer)
    total_citations: Mapped[int] = mapped_column(Integer)
    screenshot_date: Mapped[date] = mapped_column(Date)  # must be within 30 days of submission (rule)


class RecommendationLetter(CaseChildMixin, Base):
    """§8 – optional letters (file in case_document)."""

    __tablename__ = "recommendation_letter"

    writer_name: Mapped[str] = mapped_column(String(200))  # sensitive
    writer_rank: Mapped[str] = mapped_column(String(100))
    writer_institution: Mapped[str] = mapped_column(String(300))
    relationship_id: Mapped[int] = mapped_column(ForeignKey("lookup_value.id"))
