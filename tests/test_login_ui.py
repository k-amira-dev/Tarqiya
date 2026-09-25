"""End-to-end login flow through the real Streamlit page, using Streamlit's headless AppTest."""
import importlib

import pytest
from streamlit.testing.v1 import AppTest

from promoflow.db.base import Base
from promoflow.db.models import AUTH_TABLES


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'ui.db'}")
    import promoflow.config, promoflow.db.session, promoflow.db.seed, promoflow.ui.auth
    for mod in (promoflow.config, promoflow.db.session, promoflow.db.seed, promoflow.ui.auth):
        importlib.reload(mod)  # rebind the engine to the temporary database
    Base.metadata.create_all(promoflow.db.session.engine, tables=AUTH_TABLES)
    with promoflow.db.session.session_scope() as s:
        promoflow.db.seed.seed_org_and_users(s, "test-pass")
    return AppTest.from_file("../app/Home.py", default_timeout=30)


def login(at, email, password):
    at.text_input[0].input(email)
    at.text_input[1].input(password)
    at.button[0].click()
    return at.run()


def test_wrong_password_shows_error(app):
    at = login(app.run(), "applicant@promoflow.test", "wrong")
    assert "Incorrect email or password." in [e.value for e in at.error]


def test_login_then_profile_then_dashboard_then_logout(app):
    at = login(app.run(), "applicant@promoflow.test", "test-pass")
    assert at.title[0].value == "Complete your profile"
    at.text_input[1].input("E-1001")
    at.button[0].click()
    at = at.run()
    assert at.title[0].value == "Welcome, Test Applicant"
    assert "My Promotion" in [h.value for h in at.subheader]
    assert "Reviews" not in [h.value for h in at.subheader]  # applicant only
    at.sidebar.button[0].click()  # Log out
    at = at.run()
    assert at.title[0].value == "PromoFlow"


def test_hod_sees_reviews(app):
    at = login(app.run(), "hod.cs@promoflow.test", "test-pass")
    at.text_input[1].input("E-2001")
    at.button[0].click()
    at = at.run()
    headers = [h.value for h in at.subheader]
    assert "My Promotion" in headers and "Reviews" in headers  # a HoD is also an applicant
