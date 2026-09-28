"""Importing this package registers every table on Base.metadata (needed by Alembic and the seed script)."""
from promoflow.db.models.org import AuthSession, College, Department, User, UserRole
from promoflow.db.models.reference import (
    Journal, JournalRanking, LookupValue, PolicyChunk, PolicyVersion, PromotionCriteria, ResearchItemCap,
    Rubric, RubricItem,
)
from promoflow.db.models.case import (
    CaseDocument, CaseStatusHistory, Degree, NonAcademicPosition, PromotionCase, RankHistory,
    RecommendationLetter, ScopusEvidence,
)
from promoflow.db.models.research import (
    Award, Book, CoauthoredPaperEvaluation, ConferencePaper, CreativeWork, FundedProject,
    JournalCriteriaConfirmation, Patent, Publication, PublicationAuthor,
)
from promoflow.db.models.teaching import (
    AdvisingSemester, CourseFile, CourseTaught, CurriculumContribution, PeerObservation, StudentSatisfaction,
    Supervision, TeachingDevelopment, TeachingInnovation,
)
from promoflow.db.models.service import (
    AdministrativePosition, CommitteeMembership, CommunityActivity, PolicyContribution, TrainingDelivered,
    WorkshopDelivered,
)
from promoflow.db.models.assessment import (
    AgentAssessment, AgentRun, CaseReport, Claim, CriterionResult, DeanEvaluation, Flag, GateDecision,
    ItemResult, RubricScore,
)
from promoflow.db.models.referees import (
    OutreachMessage, Referee, RefereeCandidate, RefereePaperGrade, RefereeReport, ResearcherProfile,
    ReviewerAssignment,
)
from promoflow.db.models.audit import AuditLogEntry

# Tables that only use portable column types; they also run on SQLite, for tests without PostgreSQL.
AUTH_TABLES = [
    College.__table__, Department.__table__, User.__table__, UserRole.__table__, AuthSession.__table__,
    AuditLogEntry.__table__,
]
SQLITE_TABLES = AUTH_TABLES + [
    PolicyVersion.__table__, PromotionCriteria.__table__, ResearchItemCap.__table__, Rubric.__table__,
    RubricItem.__table__, LookupValue.__table__, PromotionCase.__table__, CaseStatusHistory.__table__,
    CaseDocument.__table__, Publication.__table__, PublicationAuthor.__table__, CreativeWork.__table__,
    Book.__table__, ConferencePaper.__table__, Patent.__table__, Degree.__table__, RankHistory.__table__,
    NonAcademicPosition.__table__, FundedProject.__table__, Award.__table__, ScopusEvidence.__table__,
    Journal.__table__, JournalRanking.__table__, CourseTaught.__table__, PeerObservation.__table__,
    StudentSatisfaction.__table__, CurriculumContribution.__table__, AdvisingSemester.__table__,
    CourseFile.__table__, TeachingInnovation.__table__, Supervision.__table__, TeachingDevelopment.__table__,
    CommitteeMembership.__table__, AdministrativePosition.__table__, WorkshopDelivered.__table__,
    TrainingDelivered.__table__, PolicyContribution.__table__, CommunityActivity.__table__,
    RecommendationLetter.__table__,
]
