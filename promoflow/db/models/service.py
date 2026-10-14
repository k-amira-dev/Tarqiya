"""§7 University & community service entries (Appendix F evidence).

Each table feeds a line of the Appendix F rubric, which the Service Agent scores (see workflow/nodes/service.py).
Community activities have no line of their own on the form, so the agent decides where each one counts.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from promoflow.db.base import Base, CaseChildMixin, pg_enum
from promoflow.db.enums import OrgLevel, WorkshopRole


class CommitteeMembership(CaseChildMixin, Base):
    """§7A-1 – Appendix F item 1 (required section)."""

    __tablename__ = "committee_membership"

    committee_name: Mapped[str] = mapped_column(String(300))
    level: Mapped[OrgLevel] = mapped_column(pg_enum(OrgLevel))
    role_id: Mapped[int] = mapped_column(ForeignKey("lookup_value.id"))
    date_from: Mapped[date] = mapped_column(Date)
    date_to: Mapped[date | None] = mapped_column(Date)  # NULL = ongoing
    contribution_summary: Mapped[str | None] = mapped_column(Text)


class AdministrativePosition(CaseChildMixin, Base):
    """§7A-2 (optional) – mapped by the Service Agent to Appendix F item 1."""

    __tablename__ = "administrative_position"

    position_id: Mapped[int] = mapped_column(ForeignKey("lookup_value.id"))
    unit: Mapped[str] = mapped_column(String(300))
    date_from: Mapped[date] = mapped_column(Date)
    date_to: Mapped[date | None] = mapped_column(Date)


class WorkshopDelivered(CaseChildMixin, Base):
    """§7A-3 (optional) – Appendix F item 4."""

    __tablename__ = "workshop_delivered"

    title: Mapped[str] = mapped_column(String(300))
    organized_by: Mapped[OrgLevel] = mapped_column(pg_enum(OrgLevel))
    role: Mapped[WorkshopRole] = mapped_column(pg_enum(WorkshopRole))
    activity_date: Mapped[date] = mapped_column(Date)
    attendees: Mapped[int | None] = mapped_column(Integer)


class TrainingDelivered(CaseChildMixin, Base):
    """§7A-4 (optional) – Appendix F item 3."""

    __tablename__ = "training_delivered"

    title: Mapped[str] = mapped_column(String(300))
    inside_university: Mapped[bool] = mapped_column(Boolean)
    host_organisation: Mapped[str] = mapped_column(String(300))
    activity_date: Mapped[date] = mapped_column(Date)
    hours: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    participants: Mapped[int | None] = mapped_column(Integer)


class PolicyContribution(CaseChildMixin, Base):
    """§7A-5 (optional) – mapped to Appendix F item 1."""

    __tablename__ = "policy_contribution"

    policy_name: Mapped[str] = mapped_column(String(300))
    level: Mapped[OrgLevel] = mapped_column(pg_enum(OrgLevel))
    role_id: Mapped[int] = mapped_column(ForeignKey("lookup_value.id"))
    activity_date: Mapped[date] = mapped_column(Date)


class CommunityActivity(CaseChildMixin, Base):
    """§7B – mapped by the Service Agent to Appendix F items (there is no community line on the form)."""

    __tablename__ = "community_activity"

    activity_type_id: Mapped[int] = mapped_column(ForeignKey("lookup_value.id"))
    funded_project_id: Mapped[int | None] = mapped_column(ForeignKey("funded_project.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(300))
    beneficiary_organisation: Mapped[str] = mapped_column(String(300))
    applicant_role: Mapped[str] = mapped_column(String(200))
    date_from: Mapped[date] = mapped_column(Date)
    date_to: Mapped[date | None] = mapped_column(Date)
    beneficiaries: Mapped[int | None] = mapped_column(Integer)
    deliverables: Mapped[str] = mapped_column(Text)
    measurable_outcome: Mapped[str | None] = mapped_column(Text)
