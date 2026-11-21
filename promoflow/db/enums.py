"""Fixed value lists that the rules depend on. Stored as native PostgreSQL enum types.

Descriptive lists that Admin may edit (committee roles, activity types, ...) are NOT here:
they live in the lookup_value table (see models/reference.py).

WHAT IS AN ENUM? (for beginners)
An enum is a short, fixed list of allowed values, such as the four academic ranks. Using one instead of free text
means a typo ("assoicate_professor") is impossible: Python and the database both refuse anything not on the list.
In the code you write `Rank.PROFESSOR`; in the database the same value is stored as the text "professor".

These are the values the RULES depend on, so changing one is a policy change: discuss it with the team first, and a
change to an enum also needs a database migration (see the README, "Changing the database schema").
"""
from enum import Enum


# The four academic ranks, lowest to highest. A promotion moves a person up one step.
class Rank(str, Enum):
    ASSISTANT_LECTURER = "assistant_lecturer"   # rank history only: not part of the promotion ladder
    POSTDOC = "postdoc"                         # rank history only
    LECTURER = "lecturer"
    ASSISTANT_PROFESSOR = "assistant_professor"
    ASSOCIATE_PROFESSOR = "associate_professor"
    PROFESSOR = "professor"


# Which promotion the application is for. Every threshold (years in rank, number of papers, ...) is looked up per
# track.
class PromotionTrack(str, Enum):
    TO_ASSOCIATE = "to_associate"  # Assistant -> Associate Professor
    TO_FULL = "to_full"  # Associate -> Professor


# Where an application is in its life. Normal path: draft -> submitted -> under_evaluation -> hod_review ->
# dean_review -> referee_selection -> awaiting_referee_reports -> referee_results_recorded. Side exits:
# not_eligible, returned_for_revision (back to the applicant), withdrawn. review_service.py is what moves a case
# between these.
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


# What a person is allowed to do in the system. One account can hold several roles.
class RoleName(str, Enum):
    APPLICANT = "applicant"
    HOD = "hod"
    DEAN = "dean"
    CHANCELLOR = "chancellor"
    ADMIN = "admin"


class AuthProvider(str, Enum):
    LOCAL = "local"  # email + password (prototype)
    OIDC = "oidc"  # university single sign-on (production)


# What an uploaded file is, so the system knows which are required (signed forms, CV, ...).
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


# The parts of the review system that produce a result. Each agent run and result is stored against one of these.
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


# The outcome an agent reports. needs_human means 'I cannot decide, a person must look'; incomplete means something
# is missing.
class Verdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NEEDS_HUMAN = "needs_human"
    INCOMPLETE = "incomplete"


# How sure an agent is about one result. Low confidence is what makes a person look at it.
class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# How a result was decided: by a fixed rule, by the language model, or by both. Shown to reviewers so they know how
# much to trust it.
class DecisionBasis(str, Enum):
    RULE = "rule"
    LLM = "llm"
    MIXED = "mixed"


# How urgent a flag is. needs_human = a person MUST decide before the case moves on.
class FlagSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    NEEDS_HUMAN = "needs_human"


# The two human approval steps. The Chancellor does NOT approve: the Chancellor only selects referees.
class Gate(str, Enum):
    HOD = "hod"
    DEAN = "dean"


# What a reviewer can decide at a gate.
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
