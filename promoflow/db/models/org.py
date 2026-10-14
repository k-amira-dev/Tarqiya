"""Organisation, users, roles and login sessions."""
from datetime import date, datetime

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from promoflow.db.base import Base, IdMixin, TimestampMixin, pg_enum
from promoflow.db.enums import AuthProvider, RoleName


# A college contains departments. It decides which Dean sees an applicant's case.
class College(IdMixin, TimestampMixin, Base):
    __tablename__ = "college"

    code: Mapped[str] = mapped_column(String(20), unique=True)
    name_en: Mapped[str] = mapped_column(String(200))
    name_ar: Mapped[str | None] = mapped_column(String(200))

    departments: Mapped[list["Department"]] = relationship(back_populates="college")


# A department belongs to one college. It decides which Head of Department sees an applicant's case.
class Department(IdMixin, TimestampMixin, Base):
    __tablename__ = "department"

    college_id: Mapped[int] = mapped_column(ForeignKey("college.id"), index=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name_en: Mapped[str] = mapped_column(String(200))
    name_ar: Mapped[str | None] = mapped_column(String(200))
    # Appendix E footnote: advising points may be redistributed in departments that award no degrees.
    awards_degrees: Mapped[bool] = mapped_column(Boolean, default=True)

    college: Mapped[College] = relationship(back_populates="departments")


class User(IdMixin, TimestampMixin, Base):
    """A person who can log in. Identity fields feed Section 0 of the dossier (spec §4.1)."""

    __tablename__ = "app_user"  # "user" is a reserved word in PostgreSQL
    __table_args__ = (
        CheckConstraint(
            "(auth_provider = 'local' AND password_hash IS NOT NULL) "
            "OR (auth_provider = 'oidc' AND external_subject IS NOT NULL)",
            name="credentials_match_provider",
        ),
    )

    email: Mapped[str] = mapped_column(String(254), unique=True)
    auth_provider: Mapped[AuthProvider] = mapped_column(pg_enum(AuthProvider), default=AuthProvider.LOCAL)
    password_hash: Mapped[str | None] = mapped_column(String(255))  # argon2id; NULL for SSO users
    external_subject: Mapped[str | None] = mapped_column(String(255), unique=True)  # SSO "sub" claim

    # Entered by the professor at first login (sensitive: never sent to the LLM).
    full_name: Mapped[str | None] = mapped_column(String(200))
    employee_id: Mapped[str | None] = mapped_column(String(40), unique=True)
    profile_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Set by Admin: decides which Head of Department and Dean see this person's case.
    college_id: Mapped[int | None] = mapped_column(ForeignKey("college.id"))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("department.id"))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Brute-force protection: after too many wrong passwords the account is locked until `locked_until`.
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    roles: Mapped[list["UserRole"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    college: Mapped[College | None] = relationship()
    department: Mapped[Department | None] = relationship()


class UserRole(IdMixin, TimestampMixin, Base):
    """One person can hold several roles (a Head of Department is also a professor).

    HoD roles are scoped to a department, Dean roles to a college.
    """

    __tablename__ = "user_role"
    __table_args__ = (
        CheckConstraint("role <> 'hod' OR department_id IS NOT NULL", name="hod_has_department"),
        CheckConstraint("role <> 'dean' OR college_id IS NOT NULL", name="dean_has_college"),
        UniqueConstraint("user_id", "role", "department_id", "college_id"),
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    role: Mapped[RoleName] = mapped_column(pg_enum(RoleName, "role_name"))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("department.id"))
    college_id: Mapped[int | None] = mapped_column(ForeignKey("college.id"))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)

    user: Mapped[User] = relationship(back_populates="roles")


class AuthSession(IdMixin, Base):
    """Login session. Only the SHA-256 of the token is stored; the raw token lives in the browser cookie."""

    __tablename__ = "auth_session"

    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(300))

    user: Mapped[User] = relationship()
