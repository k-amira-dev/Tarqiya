"""Researcher profiles (cached from Scopus/OpenAlex) and the external referee workflow."""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from promoflow.db.base import Base, CaseChildMixin, IdMixin, TimestampMixin, pg_enum
from promoflow.db.enums import AssignmentStatus, DeliveryStatus, MessageKind, ProfileSource, Rank


class ResearcherProfile(IdMixin, TimestampMixin, Base):
    """Cached external profile of an applicant ("last synced" shown in the UI, refreshable)."""

    __tablename__ = "researcher_profile"
    __table_args__ = (UniqueConstraint("user_id", "source"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"))
    source: Mapped[ProfileSource] = mapped_column(pg_enum(ProfileSource))
    external_author_id: Mapped[str] = mapped_column(String(60))
    h_index: Mapped[int | None] = mapped_column(Integer)
    citation_count: Mapped[int | None] = mapped_column(Integer)
    works_count: Mapped[int | None] = mapped_column(Integer)
    topics: Mapped[list | None] = mapped_column(JSONB)
    coauthors: Mapped[list | None] = mapped_column(JSONB)
    affiliations: Mapped[list | None] = mapped_column(JSONB)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Referee(IdMixin, TimestampMixin, Base):
    """An external referee. Identity is confidential: never shown to the applicant (permission rule)."""

    __tablename__ = "referee"

    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(254), unique=True)
    university: Mapped[str] = mapped_column(String(300))
    country_code: Mapped[str] = mapped_column(String(2))  # must be outside the UAE (rule)
    rank: Mapped[Rank] = mapped_column(pg_enum(Rank))  # must be Professor (rule)
    scopus_author_id: Mapped[str | None] = mapped_column(String(40))
    openalex_author_id: Mapped[str | None] = mapped_column(String(40), unique=True)
    h_index: Mapped[int | None] = mapped_column(Integer)
    citation_count: Mapped[int | None] = mapped_column(Integer)
    topics: Mapped[list | None] = mapped_column(JSONB)


class RefereeCandidate(CaseChildMixin, Base):
    """Shortlist entry built by the Chancellor's Office Agent (max 10 per case, enforced in code)."""

    __tablename__ = "referee_candidate"
    __table_args__ = (UniqueConstraint("case_id", "referee_id"),)

    referee_id: Mapped[int] = mapped_column(ForeignKey("referee.id"))
    match_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    match_rationale: Mapped[str | None] = mapped_column(Text)
    coi_coauthor: Mapped[bool] = mapped_column(Boolean)
    coi_same_institution: Mapped[bool] = mapped_column(Boolean)
    coi_used_within_5_years: Mapped[bool] = mapped_column(Boolean)
    eligible: Mapped[bool] = mapped_column(Boolean)  # rank, country, metrics, no conflict
    selected_by_chancellor: Mapped[bool] = mapped_column(Boolean, default=False)
    selected_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
    selected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReviewerAssignment(CaseChildMixin, Base):
    """A contacted referee. Doubles as the history for the 5-year non-reuse rule."""

    __tablename__ = "reviewer_assignment"
    __table_args__ = (Index("ix_reviewer_assignment_referee_invited", "referee_id", "invited_at"),)

    referee_id: Mapped[int] = mapped_column(ForeignKey("referee.id"))
    candidate_id: Mapped[int | None] = mapped_column(ForeignKey("referee_candidate.id", ondelete="SET NULL"))
    status: Mapped[AssignmentStatus] = mapped_column(pg_enum(AssignmentStatus))
    invited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_reminder_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    report_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[int | None] = mapped_column(ForeignKey("reviewer_assignment.id"))  # 3-month rule


class OutreachMessage(IdMixin, Base):
    """Every email sent to a referee (invitation, reminder, ...), sent by the Reminder & Webhook Worker."""

    __tablename__ = "outreach_message"

    assignment_id: Mapped[int] = mapped_column(ForeignKey("reviewer_assignment.id", ondelete="CASCADE"), index=True)
    kind: Mapped[MessageKind] = mapped_column(pg_enum(MessageKind))
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivery_status: Mapped[DeliveryStatus] = mapped_column(pg_enum(DeliveryStatus), default=DeliveryStatus.QUEUED)


class RefereeReport(IdMixin, Base):
    """Appendix J/K – one returned report; the file itself is a case_document (kind=referee_report)."""

    __tablename__ = "referee_report"
    __table_args__ = (UniqueConstraint("assignment_id"),)

    assignment_id: Mapped[int] = mapped_column(ForeignKey("reviewer_assignment.id", ondelete="CASCADE"))
    recommendation: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RefereePaperGrade(IdMixin, Base):
    """Each referee grades each counted paper (%). Averages and the top-three mean are computed by rule."""

    __tablename__ = "referee_paper_grade"
    __table_args__ = (
        UniqueConstraint("report_id", "publication_id"),
        CheckConstraint("grade_pct BETWEEN 0 AND 100", name="grade_range"),
    )

    report_id: Mapped[int] = mapped_column(ForeignKey("referee_report.id", ondelete="CASCADE"), index=True)
    publication_id: Mapped[int] = mapped_column(ForeignKey("publication.id", ondelete="CASCADE"))
    grade_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))
