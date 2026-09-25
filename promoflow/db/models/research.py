"""§5 Academic research entries. Computed results (journal class, counted or not) live in assessment tables."""
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Boolean, CheckConstraint, Date, ForeignKey, Numeric, SmallInteger, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from promoflow.db.base import Base, CaseChildMixin, IdMixin, pg_enum
from promoflow.db.enums import (
    AuthorRole, BookItemType, InvestigatorRole, Language, LookupSource, MainAuthorBasis,
    PatentStatus, ProjectStatus, PublicationStatus,
)


class Publication(CaseChildMixin, Base):
    """§5A – one journal paper."""

    __tablename__ = "publication"
    __table_args__ = (
        CheckConstraint("status <> 'published' OR issue_date IS NOT NULL", name="published_has_issue_date"),
        CheckConstraint("status <> 'accepted' OR acceptance_date IS NOT NULL", name="accepted_has_date"),
        CheckConstraint("applicant_role <> 'main' OR main_author_basis IS NOT NULL", name="main_has_basis"),
        CheckConstraint("main_author_basis <> 'other' OR main_author_explanation IS NOT NULL", name="other_explained"),
        CheckConstraint("NOT with_supervised_student OR supervision_id IS NOT NULL", name="supervision_linked"),
        CheckConstraint("author_position BETWEEN 1 AND total_authors", name="author_position_range"),
    )

    submit_for_promotion: Mapped[bool] = mapped_column(Boolean, default=True)
    lookup_source: Mapped[LookupSource] = mapped_column(pg_enum(LookupSource))
    doi: Mapped[str | None] = mapped_column(String(200), index=True)  # not every paper has one
    openalex_work_id: Mapped[str | None] = mapped_column(String(40))

    title: Mapped[str] = mapped_column(String(600))
    journal_id: Mapped[int | None] = mapped_column(ForeignKey("journal.id"), index=True)  # NULL if not in table
    journal_name: Mapped[str] = mapped_column(String(400))  # as entered / looked up
    issn: Mapped[str | None] = mapped_column(String(9))
    publisher: Mapped[str] = mapped_column(String(300))
    volume: Mapped[str | None] = mapped_column(String(20))
    issue: Mapped[str | None] = mapped_column(String(20))
    pages: Mapped[str | None] = mapped_column(String(30))
    language: Mapped[Language] = mapped_column(pg_enum(Language))

    status: Mapped[PublicationStatus] = mapped_column(pg_enum(PublicationStatus))
    issue_date: Mapped[date | None] = mapped_column(Date)  # month-year stored as day 1
    acceptance_date: Mapped[date | None] = mapped_column(Date)
    new_since_rejection: Mapped[bool | None] = mapped_column(Boolean)

    author_position: Mapped[int] = mapped_column(SmallInteger)
    total_authors: Mapped[int] = mapped_column(SmallInteger)
    applicant_role: Mapped[AuthorRole] = mapped_column(pg_enum(AuthorRole))
    main_author_basis: Mapped[MainAuthorBasis | None] = mapped_column(pg_enum(MainAuthorBasis))
    main_author_explanation: Mapped[str | None] = mapped_column(Text)
    with_supervised_student: Mapped[bool] = mapped_column(Boolean, default=False)
    supervision_id: Mapped[int | None] = mapped_column(ForeignKey("supervision.id"))

    at_this_university: Mapped[bool] = mapped_column(Boolean)
    from_thesis: Mapped[bool] = mapped_column(Boolean)

    impact_factor: Mapped[Decimal | None] = mapped_column(Numeric(7, 3))
    disputes_class: Mapped[bool] = mapped_column(Boolean, default=False)
    dispute_reason: Mapped[str | None] = mapped_column(Text)

    authors: Mapped[list["PublicationAuthor"]] = relationship(
        back_populates="publication", cascade="all, delete-orphan", order_by="PublicationAuthor.position"
    )


class PublicationAuthor(IdMixin, Base):
    """Author list of a paper; used for the supervision rule and referee conflict-of-interest checks."""

    __tablename__ = "publication_author"
    __table_args__ = (UniqueConstraint("publication_id", "position"),)

    publication_id: Mapped[int] = mapped_column(ForeignKey("publication.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(SmallInteger)
    display_name: Mapped[str] = mapped_column(String(200))
    openalex_author_id: Mapped[str | None] = mapped_column(String(40), index=True)
    is_applicant: Mapped[bool] = mapped_column(Boolean, default=False)

    publication: Mapped[Publication] = relationship(back_populates="authors")


class CoauthoredPaperEvaluation(IdMixin, Base):
    """Appendix H row for a co-authored paper. PROVISIONAL: columns to be confirmed with the 5A template."""

    __tablename__ = "coauthored_paper_evaluation"
    __table_args__ = (UniqueConstraint("publication_id"),)

    publication_id: Mapped[int] = mapped_column(ForeignKey("publication.id", ondelete="CASCADE"))
    coauthor_order: Mapped[str | None] = mapped_column(String(100))
    applicant_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    senior_coauthor_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    decision: Mapped[str | None] = mapped_column(String(100))
    rank: Mapped[str | None] = mapped_column(String(40))


class JournalCriteriaConfirmation(CaseChildMixin, Base):
    """§5E – policy §4 journal criteria, only for journals missing from the journal table."""

    __tablename__ = "journal_criteria_confirmation"

    journal_name: Mapped[str] = mapped_column(String(400))
    issn: Mapped[str | None] = mapped_column(String(9))
    publisher_type_id: Mapped[int] = mapped_column(ForeignKey("lookup_value.id"))
    specialised_editorial_board: Mapped[bool] = mapped_column(Boolean)
    peer_review_two_referees: Mapped[bool] = mapped_column(Boolean)
    years_regular_publication: Mapped[int] = mapped_column(SmallInteger)


class CreativeWork(CaseChildMixin, Base):
    """§5A-2 – approved creative / studio work (Class B, capped)."""

    __tablename__ = "creative_work"

    form_id: Mapped[int] = mapped_column(ForeignKey("lookup_value.id"))
    title: Mapped[str] = mapped_column(String(400))
    venue: Mapped[str] = mapped_column(String(300))
    organizing_institution: Mapped[str] = mapped_column(String(300))
    date_from: Mapped[date] = mapped_column(Date)
    date_to: Mapped[date | None] = mapped_column(Date)
    approved: Mapped[bool] = mapped_column(Boolean)


class Book(CaseChildMixin, Base):
    """§5B – book or book chapter (per-type caps in research_item_cap)."""

    __tablename__ = "book"
    __table_args__ = (
        CheckConstraint("item_type <> 'chapter' OR chapter_title IS NOT NULL", name="chapter_has_title"),
        CheckConstraint("item_type <> 'heritage' OR referee_count IS NOT NULL", name="heritage_refereed"),
    )

    item_type: Mapped[BookItemType] = mapped_column(pg_enum(BookItemType))
    book_title: Mapped[str] = mapped_column(String(600))
    chapter_title: Mapped[str | None] = mapped_column(String(600))
    publisher: Mapped[str] = mapped_column(String(300))
    publication_date: Mapped[date] = mapped_column(Date)
    isbn: Mapped[str] = mapped_column(String(17))
    main_or_sole_author: Mapped[bool] = mapped_column(Boolean)
    financial_support_by: Mapped[str | None] = mapped_column(String(300))
    refereed: Mapped[bool] = mapped_column(Boolean, default=False)
    referee_count: Mapped[int | None] = mapped_column(SmallInteger)
    from_thesis: Mapped[bool] = mapped_column(Boolean)


class ConferencePaper(CaseChildMixin, Base):
    """§5C – recorded; not counted towards minimums unless the policy confirms (open question 7)."""

    __tablename__ = "conference_paper"

    title: Mapped[str] = mapped_column(String(600))
    conference_title: Mapped[str] = mapped_column(String(400))
    organizer: Mapped[str] = mapped_column(String(300))
    conference_date: Mapped[date] = mapped_column(Date)
    place: Mapped[str] = mapped_column(String(200))
    pages: Mapped[str | None] = mapped_column(String(30))
    main_or_sole_author: Mapped[bool] = mapped_column(Boolean)
    scopus_indexed: Mapped[bool] = mapped_column(Boolean)
    doi: Mapped[str | None] = mapped_column(String(200))


class FundedProject(CaseChildMixin, Base):
    """§5D – also linkable from §7B community service (scored once)."""

    __tablename__ = "funded_project"

    title: Mapped[str] = mapped_column(String(400))
    funding_body: Mapped[str] = mapped_column(String(300))
    funder_type_id: Mapped[int] = mapped_column(ForeignKey("lookup_value.id"))
    role: Mapped[InvestigatorRole] = mapped_column(pg_enum(InvestigatorRole))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[ProjectStatus] = mapped_column(pg_enum(ProjectStatus))


class Patent(CaseChildMixin, Base):
    """§5G – only granted patents count (Class B, capped)."""

    __tablename__ = "patent"
    __table_args__ = (CheckConstraint("status <> 'granted' OR grant_date IS NOT NULL", name="granted_has_date"),)

    title: Mapped[str] = mapped_column(String(400))
    patent_number: Mapped[str] = mapped_column(String(60))
    office_id: Mapped[int] = mapped_column(ForeignKey("lookup_value.id"))
    status: Mapped[PatentStatus] = mapped_column(pg_enum(PatentStatus))
    grant_date: Mapped[date | None] = mapped_column(Date)
    inventors: Mapped[str] = mapped_column(Text)


class Award(CaseChildMixin, Base):
    """§5H – narrative only, not counted."""

    __tablename__ = "award"

    name: Mapped[str] = mapped_column(String(300))
    awarding_body: Mapped[str] = mapped_column(String(300))
    year: Mapped[int] = mapped_column(SmallInteger)
    scope_id: Mapped[int] = mapped_column(ForeignKey("lookup_value.id"))
