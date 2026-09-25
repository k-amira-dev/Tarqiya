"""What the agents, the Report Builder and the human gates produce."""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, SmallInteger, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from promoflow.db.base import Base, CaseChildMixin, IdMixin, pg_enum
from promoflow.db.enums import (
    Component, Confidence, DeanRating, DecisionBasis, FlagSeverity, Gate, GateOutcome, RunStatus, Verdict,
)


class AgentRun(CaseChildMixin, Base):
    """One execution of a component on a case; kept for reproducibility (model, prompt version, input hash)."""

    __tablename__ = "agent_run"

    component: Mapped[Component] = mapped_column(pg_enum(Component))
    status: Mapped[RunStatus] = mapped_column(pg_enum(RunStatus), default=RunStatus.RUNNING)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    model_name: Mapped[str | None] = mapped_column(String(100))  # NULL for rule-only components
    prompt_version: Mapped[str | None] = mapped_column(String(40))
    input_hash: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(Text)


class AgentAssessment(CaseChildMixin, Base):
    """Result of one component run (formerly 'TierAssessment')."""

    __tablename__ = "agent_assessment"

    agent_run_id: Mapped[int] = mapped_column(ForeignKey("agent_run.id", ondelete="CASCADE"), unique=True)
    component: Mapped[Component] = mapped_column(pg_enum(Component))
    verdict: Mapped[Verdict] = mapped_column(pg_enum(Verdict))
    narrative: Mapped[str | None] = mapped_column(Text)

    criteria: Mapped[list["CriterionResult"]] = relationship(cascade="all, delete-orphan")
    items: Mapped[list["ItemResult"]] = relationship(cascade="all, delete-orphan")
    claims: Mapped[list["Claim"]] = relationship(cascade="all, delete-orphan")


class CriterionResult(IdMixin, Base):
    """One row of the report's summary table: criterion · required · actual · pass/fail."""

    __tablename__ = "criterion_result"

    assessment_id: Mapped[int] = mapped_column(ForeignKey("agent_assessment.id", ondelete="CASCADE"), index=True)
    criterion_key: Mapped[str] = mapped_column(String(60))  # e.g. "min_class_a_main_author"
    label: Mapped[str] = mapped_column(String(200))
    required_value: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    actual_value: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    passed: Mapped[bool | None] = mapped_column(Boolean)  # NULL = needs a human decision
    policy_ref: Mapped[str | None] = mapped_column(String(60))


class ItemResult(IdMixin, Base):
    """Per-entry verdict, e.g. paper #3: counted, Class A, credited as main author (by rule)."""

    __tablename__ = "item_result"

    assessment_id: Mapped[int] = mapped_column(ForeignKey("agent_assessment.id", ondelete="CASCADE"), index=True)
    entity_table: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[int] = mapped_column(BigInteger)
    counted: Mapped[bool | None] = mapped_column(Boolean)
    classification: Mapped[str | None] = mapped_column(String(60))  # e.g. "class_a", "deep", "item_3"
    credited_role: Mapped[str | None] = mapped_column(String(60))
    basis: Mapped[DecisionBasis] = mapped_column(pg_enum(DecisionBasis))
    confidence: Mapped[Confidence | None] = mapped_column(pg_enum(Confidence))
    reason: Mapped[str | None] = mapped_column(Text)


class Claim(IdMixin, Base):
    """A factual statement in an agent's output and the records it cites; checked by verify_claims()."""

    __tablename__ = "claim"

    assessment_id: Mapped[int] = mapped_column(ForeignKey("agent_assessment.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    value: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    source_table: Mapped[str] = mapped_column(String(64))
    source_ids: Mapped[list[int]] = mapped_column(ARRAY(BigInteger))
    verified: Mapped[bool | None] = mapped_column(Boolean)  # NULL = not yet checked
    verification_note: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(SmallInteger, default=0)


class Flag(CaseChildMixin, Base):
    """Anything a human must look at: mismatches, unverified claims, exceptional-case requests."""

    __tablename__ = "flag"

    assessment_id: Mapped[int | None] = mapped_column(ForeignKey("agent_assessment.id", ondelete="SET NULL"))
    severity: Mapped[FlagSeverity] = mapped_column(pg_enum(FlagSeverity))
    code: Mapped[str] = mapped_column(String(64))  # e.g. "metric_mismatch", "exceptional_case"
    message: Mapped[str] = mapped_column(Text)
    entity_table: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[int | None] = mapped_column(BigInteger)
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_note: Mapped[str | None] = mapped_column(Text)


class RubricScore(CaseChildMixin, Base):
    """One Appendix E/F line: agent suggestion, then HoD and Dean approval (spec §14.1)."""

    __tablename__ = "rubric_score"
    __table_args__ = (
        UniqueConstraint("case_id", "rubric_item_id"),
        CheckConstraint(
            "suggested_points >= 0 AND (hod_points IS NULL OR hod_points >= 0) "
            "AND (dean_points IS NULL OR dean_points >= 0)",
            name="non_negative",
        ),
    )

    rubric_item_id: Mapped[int] = mapped_column(ForeignKey("rubric_item.id"))
    suggested_points: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    suggested_by_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_run.id", ondelete="SET NULL"))
    suggestion_basis: Mapped[DecisionBasis] = mapped_column(pg_enum(DecisionBasis))
    suggestion_rationale: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[Confidence | None] = mapped_column(pg_enum(Confidence))
    hod_points: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    hod_user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
    hod_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dean_points: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    dean_user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
    dean_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    change_reason: Mapped[str | None] = mapped_column(Text)  # required (in app code) when approved != suggested


class CaseReport(CaseChildMixin, Base):
    """Output of the Report Builder; a new version after each revision cycle."""

    __tablename__ = "case_report"
    __table_args__ = (UniqueConstraint("case_id", "version"),)

    version: Mapped[int] = mapped_column(Integer)
    overall_pass: Mapped[bool | None] = mapped_column(Boolean)
    content: Mapped[dict] = mapped_column(JSONB)
    rendered_path: Mapped[str | None] = mapped_column(String(500))


class GateDecision(CaseChildMixin, Base):
    """A human approval gate (HoD, Dean). The Chancellor selects referees; that is not an approval."""

    __tablename__ = "gate_decision"
    __table_args__ = (
        CheckConstraint(
            "outcome <> 'return_for_revision' OR sections_to_revise IS NOT NULL", name="revision_names_sections"
        ),
    )

    gate: Mapped[Gate] = mapped_column(pg_enum(Gate))
    decided_by: Mapped[int] = mapped_column(ForeignKey("app_user.id"))
    outcome: Mapped[GateOutcome] = mapped_column(pg_enum(GateOutcome))
    comment: Mapped[str | None] = mapped_column(Text)
    sections_to_revise: Mapped[list[str] | None] = mapped_column(ARRAY(String(8)))  # only these unlock
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DeanEvaluation(CaseChildMixin, Base):
    """Appendix D – Dean's Performance Evaluation Report (narratives pre-drafted by the agents)."""

    __tablename__ = "dean_evaluation"
    __table_args__ = (UniqueConstraint("case_id"),)

    teaching_text: Mapped[str | None] = mapped_column(Text)
    teaching_rating: Mapped[DeanRating | None] = mapped_column(pg_enum(DeanRating))
    research_text: Mapped[str | None] = mapped_column(Text)
    research_rating: Mapped[DeanRating | None] = mapped_column(pg_enum(DeanRating))
    service_text: Mapped[str | None] = mapped_column(Text)
    service_rating: Mapped[DeanRating | None] = mapped_column(pg_enum(DeanRating))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
