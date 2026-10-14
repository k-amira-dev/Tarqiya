"""Section 3 (degrees): add, update and delete a degree with its certificate files, and the locked case. Each test is
a small function whose name says what it checks. They use `app_env` (see conftest.py), a fresh temporary database
seeded with reference data and test accounts, so no test depends on another and none touches the real database.
"""
from datetime import date

import pytest
from sqlalchemy import select

from promoflow.db.enums import CaseStatus, DegreeLevel, PromotionTrack, Rank
from promoflow.db.models import CaseDocument, Degree, PromotionCase, User
from promoflow.dossier import section0 as s0
from promoflow.dossier import section3 as s3

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
PHD = {
    "level": DegreeLevel.PHD, "specialization": "Computer Science", "university": "MIT", "country_code": "US",
    "study_from": date(2012, 9, 1), "study_to": date(2016, 6, 1), "graduation_date": date(2016, 6, 15),
    "thesis_title": "Distributed systems", "equivalency_required": True,
}


# The seeded test applicant (created by db/seed.py), looked up by email.
def applicant(s):
    return s.scalar(select(User).where(User.email == "applicant@promoflow.test"))


# Create the draft case from S0_VALUES and return its id (most tests need a case to attach entries to).
def _case(s):
    return s0.save(s, applicant(s).id, dict(S0_VALUES), TODAY)


def test_add_before_section0_is_locked(app_env):
    with app_env.session_scope() as s:
        with pytest.raises(s3.CaseLocked):
            s3.add(s, applicant(s).id, dict(PHD), ("cert.pdf", b"x"))


def test_add_requires_certificate_and_equivalency(app_env):
    errors = s3.validate_degree(PHD, has_certificate=False, today=TODAY)
    assert any("certificate" in e for e in errors)
    ok = s3.validate_degree(PHD, has_certificate=True, today=TODAY, has_equivalency_certificate=True)
    assert ok == []


def test_add_update_delete(app_env):
    with app_env.session_scope() as s:
        uid = applicant(s).id
        case_id = _case(s)
        degree_id = s3.add(s, uid, dict(PHD), ("cert.pdf", b"cert"), ("equiv.pdf", b"equiv"))
    with app_env.session_scope() as s:
        ctx = s3.load(s, applicant(s).id, TODAY)
        assert len(ctx.degrees) == 1
        row = ctx.degrees[0]
        assert row.degree.level == DegreeLevel.PHD
        assert row.certificate.original_filename == "cert.pdf"
        assert row.equivalency_certificate.original_filename == "equiv.pdf"
        assert s3.has_doctorate(ctx.degrees)

        s3.update(s, applicant(s).id, degree_id, dict(PHD, specialization="Distributed Systems"))
    with app_env.session_scope() as s:
        degree = s.get(Degree, degree_id)
        assert degree.specialization == "Distributed Systems"

        s3.delete(s, applicant(s).id, degree_id)
    with app_env.session_scope() as s:
        assert s.get(Degree, degree_id) is None
        docs = s.scalars(select(CaseDocument).where(CaseDocument.case_id == case_id)).all()
        assert len(docs) == 2  # documents stay even after the entry is deleted


def test_submitted_case_is_locked(app_env):
    with app_env.session_scope() as s:
        uid = applicant(s).id
        case_id = _case(s)
        s.get(PromotionCase, case_id).status = CaseStatus.SUBMITTED
    with app_env.session_scope() as s:
        with pytest.raises(s3.CaseLocked):
            s3.add(s, applicant(s).id, dict(PHD), ("cert.pdf", b"x"))
