import pytest
from sqlalchemy import select

from promoflow.admin import AdminError, create_user, set_password
from promoflow.auth.service import authenticate
from promoflow.db.enums import RoleName
from promoflow.db.models import College, Department, UserRole

ARGS = dict(email="Prof.Example@Sharjah.ac.ae", full_name="Dr. Example", password="a-long-password",
            college="College of Arts, Humanities and Social Sciences", department="Sociology",
            roles=[RoleName.APPLICANT])


def test_create_user_creates_college_department_and_can_log_in(auth_db):
    user = create_user(auth_db, **ARGS)
    auth_db.flush()
    college = auth_db.scalar(select(College))
    assert college.code == "CAHSS" and college.name_en == ARGS["college"]
    assert auth_db.scalar(select(Department)).name_en == "Sociology"
    assert user.email == "prof.example@sharjah.ac.ae" and user.profile_completed_at is None
    assert [r.role for r in auth_db.scalars(select(UserRole))] == [RoleName.APPLICANT]
    assert authenticate(auth_db, "prof.example@sharjah.ac.ae", "a-long-password").id == user.id


def test_existing_college_is_reused_case_insensitively(auth_db):
    create_user(auth_db, **ARGS)
    create_user(auth_db, **dict(ARGS, email="second@sharjah.ac.ae", college=ARGS["college"].upper()))
    auth_db.flush()
    assert len(auth_db.scalars(select(College)).all()) == 1
    assert len(auth_db.scalars(select(Department)).all()) == 1


def test_rejections(auth_db):
    create_user(auth_db, **ARGS)
    with pytest.raises(AdminError, match="already exists"):
        create_user(auth_db, **ARGS)
    with pytest.raises(AdminError, match="at least"):
        create_user(auth_db, **dict(ARGS, email="x@sharjah.ac.ae", password="short"))
    with pytest.raises(AdminError, match="not a valid email"):
        create_user(auth_db, **dict(ARGS, email="not-an-email"))


def test_set_password(auth_db):
    create_user(auth_db, **ARGS)
    set_password(auth_db, "prof.example@sharjah.ac.ae", "another-long-one")
    auth_db.flush()
    assert authenticate(auth_db, "prof.example@sharjah.ac.ae", "another-long-one")
