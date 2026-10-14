"""Section 6 (teaching and advising): courses and diversity, the registrar report, peer observations, student
satisfaction, curriculum, advising, course files, innovation, development activities and supervision. Each test is
a small function whose name says what it checks. They use `app_env` (see conftest.py), a fresh temporary database
seeded with reference data and test accounts, so no test depends on another and none touches the real database.
"""
from datetime import date

import pytest
from sqlalchemy import select

from promoflow.db.enums import (
    ActivityFormat, CaseStatus, CourseLevel, DeliveryMode, GraduateDegree, OrgLevel, PromotionTrack, Rank,
    Semester, SupervisionRole, SupervisionStatus, TeachingRole,
)
from promoflow.db.models import CourseTaught, LookupValue, PromotionCase, User
from promoflow.dossier import section0 as s0
from promoflow.dossier import section6 as s6
from promoflow.dossier.section6 import (
    advising, course_files, courses, curriculum, development, innovation, peer_observations, satisfaction,
    supervision,
)

# A fixed 'today', so the tests give the same answer on any day of the year.
TODAY = date(2026, 9, 25)
# Valid Section 0 answers. Every test starts from a draft case built with these.
S0_VALUES = {
    "academic_year": "2026/2027", "track": PromotionTrack.TO_ASSOCIATE, "specialization": "Computer Science",
    "fine_specialization": "Machine Learning", "research_keywords": [],
    "appointment_date": date(2019, 9, 1), "rank_on_appointment": Rank.ASSISTANT_PROFESSOR,
    "current_rank_date": date(2019, 9, 1), "scopus_author_id": "57193456789", "orcid": None,
    "phd_outside_uae": False, "early_application": False, "exceptional_case": False,
    "exceptional_justification": None, "previously_rejected": False, "rejection_date": None,
}
COURSE = {"academic_year": "2025/2026", "semester": Semester.FALL, "course_code": "CS101",
         "course_title": "Intro to CS", "level": CourseLevel.UNDERGRADUATE, "sections": 2, "students": 60,
         "role": TeachingRole.INSTRUCTOR, "delivery_mode": DeliveryMode.FACE_TO_FACE}


# The seeded test applicant (created by db/seed.py), looked up by email.
def applicant(s):
    return s.scalar(select(User).where(User.email == "applicant@promoflow.test"))


# Create the draft case from S0_VALUES and return its id (most tests need a case to attach entries to).
def _case(s):
    return s0.save(s, applicant(s).id, dict(S0_VALUES), TODAY)


def test_add_course_before_section0_is_locked(app_env):
    with app_env.session_scope() as s:
        with pytest.raises(courses.CaseLocked):
            courses.add(s, applicant(s).id, dict(COURSE))


def test_course_crud_and_diversity(app_env):
    with app_env.session_scope() as s:
        uid = applicant(s).id
        _case(s)
        c1 = courses.add(s, uid, dict(COURSE))
        c2 = courses.add(s, uid, dict(COURSE, semester=Semester.SPRING))
        c3 = courses.add(s, uid, dict(COURSE, course_code="CS202", course_title="Data Structures"))
    with app_env.session_scope() as s:
        ctx = s6.load(s, applicant(s).id)
        assert len(ctx.courses) == 3
        summary = courses.diversity(ctx.courses)
        assert summary.distinct_courses == 2 and summary.total_rows == 3
        courses.delete(s, applicant(s).id, c3)
    with app_env.session_scope() as s:
        assert s.get(CourseTaught, c3) is None


def test_registrar_report_upload(app_env):
    with app_env.session_scope() as s:
        uid = applicant(s).id
        case_id = _case(s)
        courses.save_registrar_report(s, case_id, uid, ("report.pdf", b"x"))
    with app_env.session_scope() as s:
        doc = courses.registrar_report(s, case_id)
        assert doc.original_filename == "report.pdf"


def test_peer_observation_crud(app_env):
    with app_env.session_scope() as s:
        role_id = s.scalar(select(LookupValue).where(LookupValue.list_code == "observer_role")).id
    with app_env.session_scope() as s:
        uid = applicant(s).id
        _case(s)
        course_id = courses.add(s, uid, dict(COURSE))
        obs_id = peer_observations.add(s, uid, {
            "course_taught_id": course_id, "observer_role_id": role_id, "observer_name": "Dr X",
            "observation_date": date(2025, 10, 1), "rating": 4, "scale_max": 5,
        }, ("report.pdf", b"x"))
    with app_env.session_scope() as s:
        ctx = s6.load(s, applicant(s).id)
        assert len(ctx.peer_observations) == 1
        peer_observations.delete(s, applicant(s).id, obs_id)
    with app_env.session_scope() as s:
        ctx = s6.load(s, applicant(s).id)
        assert ctx.peer_observations == []


def test_satisfaction_respondents_cannot_exceed_students(app_env):
    with app_env.session_scope() as s:
        uid = applicant(s).id
        _case(s)
        course_id = courses.add(s, uid, dict(COURSE))
        errors = satisfaction.validate(s, {"course_taught_id": course_id, "respondents": 999,
                                          "average_score": 4, "scale_max": 5}, has_evidence=True)
        assert any("cannot exceed" in e for e in errors)
        satisfaction.add(s, uid, {"course_taught_id": course_id, "respondents": 50, "average_score": 4.2,
                                  "scale_max": 5}, ("report.pdf", b"x"))
    with app_env.session_scope() as s:
        ctx = s6.load(s, applicant(s).id)
        assert len(ctx.satisfaction) == 1
        assert satisfaction.coverage(ctx.satisfaction, ctx.courses) == 1.0


def test_curriculum_validate_requires_changes_for_modification():
    errors = curriculum.validate({"contribution_type_id": 1, "course_or_program": "CS101",
                                  "description": "x", "approved_by": OrgLevel.DEPARTMENT,
                                  "approval_date": date(2025, 1, 1)}, TODAY, is_modification=True,
                                 has_evidence=True)
    assert any("what changed" in e for e in errors)


def test_advising_validate_warning_math():
    values = {"academic_year": "2025/2026", "semester": Semester.FALL, "advisees": 20, "meetings_held": 10,
             "on_warning_at_start": 5, "cleared_warning": 6, "improved_gpa": 0}
    errors = advising.validate(values, has_evidence=True)
    assert any("cannot exceed those on warning" in e for e in errors)


def test_course_file_and_innovation_and_development(app_env):
    with app_env.session_scope() as s:
        kept_in_id = s.scalar(select(LookupValue).where(LookupValue.list_code == "course_file_system")).id
        item_id = s.scalar(select(LookupValue).where(LookupValue.list_code == "course_file_item")).code
        innovation_type_id = s.scalar(select(LookupValue).where(LookupValue.list_code == "innovation_type")).id
        topic_id = s.scalar(select(LookupValue).where(LookupValue.list_code == "development_topic")).id
    with app_env.session_scope() as s:
        uid = applicant(s).id
        _case(s)
        course_id = courses.add(s, uid, dict(COURSE))
        course_files.add(s, uid, {"course_taught_id": course_id, "is_coordinator": True, "kept_in_id": kept_in_id,
                                  "items": [item_id]}, ("export.pdf", b"x"))
        innovation.add(s, uid, {"innovation_type_id": innovation_type_id, "course_taught_id": course_id,
                                "description": "Used AI tutor", "measured_outcome": "Grades up 10%"},
                      ("materials.pdf", b"x"))
        development.add(s, uid, {"title": "AI in teaching", "format": ActivityFormat.WORKSHOP,
                                 "topic_id": topic_id, "organizer": "CTL", "activity_date": date(2025, 6, 1),
                                 "hours": 4}, ("cert.pdf", b"x"))
    with app_env.session_scope() as s:
        ctx = s6.load(s, applicant(s).id)
        assert len(ctx.course_files) == 1
        assert len(ctx.innovation) == 1
        assert len(ctx.development) == 1


def test_supervision_graduated_needs_date(app_env):
    values = {"student_name": "Jane Student", "degree": GraduateDegree.PHD, "role": SupervisionRole.MAIN,
             "thesis_title": "Something", "start_date": date(2022, 1, 1), "status": SupervisionStatus.GRADUATED,
             "graduation_date": None}
    errors = supervision.validate(values, TODAY, has_evidence=True)
    assert any("graduation date" in e.lower() for e in errors)
    with app_env.session_scope() as s:
        uid = applicant(s).id
        _case(s)
        supervision.add(s, uid, dict(values, status=SupervisionStatus.IN_PROGRESS), ("letter.pdf", b"x"))
    with app_env.session_scope() as s:
        ctx = s6.load(s, applicant(s).id)
        assert len(ctx.supervision) == 1


def test_submitted_case_is_locked(app_env):
    with app_env.session_scope() as s:
        uid = applicant(s).id
        case_id = _case(s)
        s.get(PromotionCase, case_id).status = CaseStatus.SUBMITTED
    with app_env.session_scope() as s:
        with pytest.raises(courses.CaseLocked):
            courses.add(s, applicant(s).id, dict(COURSE))
