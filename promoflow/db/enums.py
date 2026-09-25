"""Fixed value lists that the rules depend on. Stored as native PostgreSQL enum types.

Descriptive lists that Admin may edit (committee roles, activity types, ...) are NOT here:
they live in the lookup_value table (see models/reference.py).
"""
from enum import Enum


class Rank(str, Enum):
    LECTURER = "lecturer"
    ASSISTANT_PROFESSOR = "assistant_professor"
    ASSOCIATE_PROFESSOR = "associate_professor"
    PROFESSOR = "professor"


class PromotionTrack(str, Enum):
    TO_ASSOCIATE = "to_associate"  # Assistant -> Associate Professor
    TO_FULL = "to_full"  # Associate -> Professor


class CaseStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    NOT_ELIGIBLE = "not_eligible"
    UNDER_EVALUATION = "under_evaluation"
    HOD_REVIEW = "hod_review"
    DEAN_REVIEW = "dean_review"
    RETURNED_FOR_REVISION = "returned_for_revision"
    REFEREE_SELECTION = "referee_selection"
    AWAITING_REFEREE_REPORTS = "awaiting_referee_reports"
    REFEREE_RESULTS_RECORDED = "referee_results_recorded"
    WITHDRAWN = "withdrawn"


class RoleName(str, Enum):
    APPLICANT = "applicant"
    HOD = "hod"
    DEAN = "dean"
    CHANCELLOR = "chancellor"
    ADMIN = "admin"


class AuthProvider(str, Enum):
    LOCAL = "local"  # email + password (prototype)
    OIDC = "oidc"  # university single sign-on (production)


class DocumentKind(str, Enum):
    EVIDENCE = "evidence"
    SIGNED_FORM = "signed_form"
    GENERATED_FORM = "generated_form"
    SCREENSHOT = "screenshot"
    PHOTO = "photo"
    CV = "cv"
    REFEREE_REPORT = "referee_report"


class DegreeLevel(str, Enum):
    BACHELOR = "bachelor"
    MASTER = "master"
    PHD = "phd"
    OTHER_DOCTORATE = "other_doctorate"


class PublicationStatus(str, Enum):
    PUBLISHED = "published"
    ACCEPTED = "accepted"


class LookupSource(str, Enum):
    DOI = "doi"
    TITLE_SEARCH = "title_search"
    PROFILE_IMPORT = "profile_import"
    MANUAL = "manual"


class Language(str, Enum):
    ENGLISH = "english"
    ARABIC = "arabic"
    OTHER = "other"


class AuthorRole(str, Enum):
    SOLE = "sole"
    MAIN = "main"
    CO_AUTHOR = "co_author"


class MainAuthorBasis(str, Enum):
    FIRST_AUTHOR = "first_author"
    CORRESPONDING_AUTHOR = "corresponding_author"
    SUPERVISION_RULE = "supervision_rule"
    OTHER = "other"


class JournalClass(str, Enum):
    CLASS_A = "class_a"
    CLASS_B = "class_b"
    NOT_COUNTED = "not_counted"


class BookItemType(str, Enum):
    KNOWLEDGE_CONTRIBUTION = "knowledge_contribution"
    SPECIALIZED = "specialized"
    TEXTBOOK = "textbook"
    HERITAGE = "heritage"
    CHAPTER = "chapter"


class InvestigatorRole(str, Enum):
    PI = "pi"
    CI = "ci"


class ProjectStatus(str, Enum):
    ONGOING = "ongoing"
    COMPLETED = "completed"


class PatentStatus(str, Enum):
    FILED = "filed"
    GRANTED = "granted"


class Semester(str, Enum):
    FALL = "fall"
    SPRING = "spring"
    SUMMER = "summer"


class CourseLevel(str, Enum):
    UNDERGRADUATE = "undergraduate"
    GRADUATE = "graduate"


class TeachingRole(str, Enum):
    INSTRUCTOR = "instructor"
    INSTRUCTOR_COORDINATOR = "instructor_coordinator"


class DeliveryMode(str, Enum):
    FACE_TO_FACE = "face_to_face"
    BLENDED = "blended"
    ONLINE = "online"


class DevelopmentDepth(str, Enum):
    DEEP = "deep"  # textbook or objectives changed
    MILD = "mild"  # partial content change


class OrgLevel(str, Enum):
    DEPARTMENT = "department"
    COLLEGE = "college"
    UNIVERSITY = "university"


class GraduateDegree(str, Enum):
    MSC = "msc"
    PHD = "phd"


class SupervisionRole(str, Enum):
    MAIN = "main"
    ASSOCIATE = "associate"


class SupervisionStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    GRADUATED = "graduated"


class ActivityFormat(str, Enum):
    WORKSHOP = "workshop"
    SEMINAR = "seminar"
    CONFERENCE = "conference"


class WorkshopRole(str, Enum):
    ORGANISER = "organiser"
    LECTURER = "lecturer"
    ORGANISER_AND_LECTURER = "organiser_and_lecturer"


class RubricCode(str, Enum):
    TEACHING = "teaching"  # Appendix E, 30 points
    SERVICE = "service"  # Appendix F, 10 points


class CriterionArea(str, Enum):
    ELIGIBILITY = "eligibility"
    RESEARCH = "research"
    TEACHING = "teaching"
    SERVICE = "service"
    REFEREES = "referees"
    GENERAL = "general"


class Component(str, Enum):
    ELIGIBILITY = "eligibility"
    RESEARCH = "research"
    TEACHING = "teaching"
    SERVICE = "service"
    REPORT_BUILDER = "report_builder"
    CHANCELLOR_OFFICE = "chancellor_office"


class RunStatus(str, Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Verdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NEEDS_HUMAN = "needs_human"
    INCOMPLETE = "incomplete"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DecisionBasis(str, Enum):
    RULE = "rule"
    LLM = "llm"
    MIXED = "mixed"


class FlagSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    NEEDS_HUMAN = "needs_human"


class Gate(str, Enum):
    HOD = "hod"
    DEAN = "dean"


class GateOutcome(str, Enum):
    APPROVE = "approve"
    RETURN_FOR_REVISION = "return_for_revision"


class DeanRating(str, Enum):
    EXCELLENT = "excellent"
    VERY_GOOD = "very_good"
    GOOD = "good"


class ProfileSource(str, Enum):
    SCOPUS = "scopus"
    OPENALEX = "openalex"


class AssignmentStatus(str, Enum):
    INVITED = "invited"
    REMINDED = "reminded"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    REPLACED_NO_RESPONSE = "replaced_no_response"
    REPORT_RECEIVED = "report_received"
    WITHDRAWN = "withdrawn"


class MessageKind(str, Enum):
    INVITATION = "invitation"
    REMINDER = "reminder"
    REPLACEMENT_NOTICE = "replacement_notice"
    THANK_YOU = "thank_you"


class DeliveryStatus(str, Enum):
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"
