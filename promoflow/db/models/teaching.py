"""§6 Teaching & academic advising entries (Appendix E evidence)."""
from datetime import date
from decimal import Decimal

from sqlalchemy import JSON, Boolean, CheckConstraint, Date, ForeignKey, Numeric, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from promoflow.db.base import Base, CaseChildMixin, pg_enum
from promoflow.db.enums import (
    ActivityFormat, CourseLevel, DeliveryMode, DevelopmentDepth, GraduateDegree, OrgLevel, Semester,
    SupervisionRole, SupervisionStatus, TeachingRole,
)


class CourseTaught(CaseChildMixin, Base):
    """§6A – one course in one semester (Appendix I, Fifth A)."""

    __tablename__ = "course_taught"
    __table_args__ = (CheckConstraint("sections >= 1 AND students >= 0", name="counts"),)

    academic_year: Mapped[str] = mapped_column(String(9))
    semester: Mapped[Semester] = mapped_column(pg_enum(Semester))
    course_code: Mapped[str] = mapped_column(String(20), index=True)
    course_title: Mapped[str] = mapped_column(String(300))
    level: Mapped[CourseLevel] = mapped_column(pg_enum(CourseLevel))
    sections: Mapped[int] = mapped_column(SmallInteger, default=1)
    students: Mapped[int] = mapped_column(SmallInteger)
    role: Mapped[TeachingRole] = mapped_column(pg_enum(TeachingRole))
    delivery_mode: Mapped[DeliveryMode] = mapped_column(pg_enum(DeliveryMode))


class PeerObservation(CaseChildMixin, Base):
    """§6B – Appendix E item 2."""

    __tablename__ = "peer_observation"
    __table_args__ = (CheckConstraint("rating >= 0 AND rating <= scale_max", name="rating_in_scale"),)

    course_taught_id: Mapped[int] = mapped_column(ForeignKey("course_taught.id", ondelete="CASCADE"))
    observer_role_id: Mapped[int] = mapped_column(ForeignKey("lookup_value.id"))
    observer_name: Mapped[str | None] = mapped_column(String(200))  # sensitive
    observation_date: Mapped[date] = mapped_column(Date)
    rating: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    scale_max: Mapped[Decimal] = mapped_column(Numeric(6, 2))


class StudentSatisfaction(CaseChildMixin, Base):
    """§6C – Appendix E item 1. Respondents <= students is checked in application code (cross-table)."""

    __tablename__ = "student_satisfaction"
    __table_args__ = (CheckConstraint("average_score >= 0 AND average_score <= scale_max", name="score_in_scale"),)

    course_taught_id: Mapped[int] = mapped_column(ForeignKey("course_taught.id", ondelete="CASCADE"))
    respondents: Mapped[int] = mapped_column(SmallInteger)
    average_score: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    scale_max: Mapped[Decimal] = mapped_column(Numeric(6, 2))


class CurriculumContribution(CaseChildMixin, Base):
    """§6D – Appendix E item 6 (deep vs. mild judged by the Teaching Agent)."""

    __tablename__ = "curriculum_contribution"

    contribution_type_id: Mapped[int] = mapped_column(ForeignKey("lookup_value.id"))
    course_or_program: Mapped[str] = mapped_column(String(300))
    changes: Mapped[list[str] | None] = mapped_column(ARRAY(String(60)).with_variant(JSON(), "sqlite"))  # lookup codes, list 'course_change'
    self_classification: Mapped[DevelopmentDepth | None] = mapped_column(pg_enum(DevelopmentDepth))
    description: Mapped[str] = mapped_column(Text)
    approved_by: Mapped[OrgLevel] = mapped_column(pg_enum(OrgLevel))
    approval_date: Mapped[date] = mapped_column(Date)


class AdvisingSemester(CaseChildMixin, Base):
    """§6E – Appendix E item 9. Counts only; no student names."""

    __tablename__ = "advising_semester"
    __table_args__ = (
        CheckConstraint("cleared_warning <= on_warning_at_start", name="cleared_le_warning"),
        CheckConstraint("improved_gpa <= on_warning_at_start - cleared_warning", name="improved_le_remaining"),
        CheckConstraint("advisees >= 0 AND meetings_held >= 0", name="non_negative"),
    )

    academic_year: Mapped[str] = mapped_column(String(9))
    semester: Mapped[Semester] = mapped_column(pg_enum(Semester))
    advisees: Mapped[int] = mapped_column(SmallInteger)
    meetings_held: Mapped[int] = mapped_column(SmallInteger)
    on_warning_at_start: Mapped[int] = mapped_column(SmallInteger)
    cleared_warning: Mapped[int] = mapped_column(SmallInteger)
    improved_gpa: Mapped[int] = mapped_column(SmallInteger)
    notes: Mapped[str | None] = mapped_column(Text)


class CourseFile(CaseChildMixin, Base):
    """§6F – Appendix E item 4."""

    __tablename__ = "course_file"

    course_taught_id: Mapped[int] = mapped_column(ForeignKey("course_taught.id", ondelete="CASCADE"))
    is_coordinator: Mapped[bool] = mapped_column(Boolean)
    kept_in_id: Mapped[int] = mapped_column(ForeignKey("lookup_value.id"))  # TaskStream / Blackboard / Other
    items: Mapped[list[str]] = mapped_column(ARRAY(String(60)).with_variant(JSON(), "sqlite"))  # lookup codes, list 'course_file_item'


class TeachingInnovation(CaseChildMixin, Base):
    """§6G – Appendix E items 7 (case studies) and 8 (educational technology)."""

    __tablename__ = "teaching_innovation"

    innovation_type_id: Mapped[int] = mapped_column(ForeignKey("lookup_value.id"))
    course_taught_id: Mapped[int] = mapped_column(ForeignKey("course_taught.id", ondelete="CASCADE"))
    description: Mapped[str] = mapped_column(Text)
    measured_outcome: Mapped[str | None] = mapped_column(Text)


class Supervision(CaseChildMixin, Base):
    """§6H – graduate supervision. Appendix E item 5 (Full only) and the research supervision rule."""

    __tablename__ = "supervision"
    __table_args__ = (
        CheckConstraint("status <> 'graduated' OR graduation_date IS NOT NULL", name="graduated_has_date"),
    )

    student_name: Mapped[str] = mapped_column(String(200))  # sensitive: matching only, never sent to the LLM
    degree: Mapped[GraduateDegree] = mapped_column(pg_enum(GraduateDegree))
    role: Mapped[SupervisionRole] = mapped_column(pg_enum(SupervisionRole))
    thesis_title: Mapped[str] = mapped_column(String(600))
    start_date: Mapped[date] = mapped_column(Date)
    status: Mapped[SupervisionStatus] = mapped_column(pg_enum(SupervisionStatus))
    graduation_date: Mapped[date | None] = mapped_column(Date)


class TeachingDevelopment(CaseChildMixin, Base):
    """§6I – activities attended; Appendix E item 10."""

    __tablename__ = "teaching_development"

    title: Mapped[str] = mapped_column(String(300))
    format: Mapped[ActivityFormat] = mapped_column(pg_enum(ActivityFormat))
    topic_id: Mapped[int] = mapped_column(ForeignKey("lookup_value.id"))
    organizer: Mapped[str] = mapped_column(String(300))
    activity_date: Mapped[date] = mapped_column(Date)
    hours: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
