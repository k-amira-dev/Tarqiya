"""Shared test setup. pytest loads this file automatically: the fixtures defined here (`auth_db`, `app_env`) can be
used by any test just by naming them as a parameter.
"""
import importlib

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from promoflow.db.base import Base
from promoflow.db.models import AUTH_TABLES, SQLITE_TABLES

# The development switch that ignores the submission window must never leak into a test: this runs before EVERY test
# and turns it off, even if a developer has it switched on in their own .env file.
@pytest.fixture(autouse=True)
def submission_window_rule_on(monkeypatch):
    import promoflow.rules.eligibility as rules
    monkeypatch.setattr(rules, "DEV_IGNORE_SUBMISSION_WINDOW", False)


# Evidence files are always encrypted, so every test gets a throw-away key (never a real one).
@pytest.fixture(autouse=True)
def document_key(monkeypatch):
    import base64

    from promoflow import config
    monkeypatch.setattr(config, "DOCUMENT_ENCRYPTION_KEY", base64.urlsafe_b64encode(b"k" * 32).decode())
    monkeypatch.setattr(config, "AUDIT_HMAC_KEY", "test-audit-key")


# The password given to every seeded test account in these tests.
TEST_PASSWORD = "test-pass"


# A tiny in-memory SQLite database holding only the login tables, for the fastest tests.
@pytest.fixture
def auth_db():
    """In-memory SQLite with only the login tables (portable types)."""
    engine = create_engine("sqlite://")
    # Create the tables on SQLite. Only SQLITE_TABLES can be created there (see db/models/__init__.py), which is why
    # the tests need no PostgreSQL.
    Base.metadata.create_all(engine, tables=AUTH_TABLES)
    with Session(engine) as s:
        yield s


# THE MAIN TEST FIXTURE. Each test that asks for `app_env` gets its own temporary database file, filled with the
# reference data and test accounts, and every module that holds the database connection is re-pointed at it.
@pytest.fixture
def app_env(tmp_path, monkeypatch):
    """A seeded SQLite database file, with every module that holds the engine re-bound to it."""
    # Point the app at a throw-away SQLite file inside pytest's temporary folder, and send uploaded files there too.
    # `monkeypatch` undoes this after the test.
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'app.db'}")
    monkeypatch.setenv("EVIDENCE_DIR", str(tmp_path / "evidence"))
    # These imports are done INSIDE the fixture, after the environment variables are set, so the modules read the
    # test settings.
    import promoflow.config
    import promoflow.db.seed
    import promoflow.db.session
    import promoflow.ui.auth
    import promoflow.ui.cache
    import promoflow.ui.shell
    import promoflow.ui.views.dashboard
    import promoflow.ui.views.reviews
    import promoflow.ui.views.section0
    import promoflow.ui.views.section1
    import promoflow.ui.views.section2
    import promoflow.ui.views.section3
    import promoflow.ui.views.section4
    import promoflow.ui.views.section5
    import promoflow.ui.views.section6
    import promoflow.ui.views.section7
    import promoflow.ui.views.section8
    import promoflow.ui.views.section9
    import promoflow.ui.views.section10
    import promoflow.ui.views.section11
    # Reload every module that created its database connection at import time, so they all use the test database
    # instead of the real one.
    for mod in (promoflow.config, promoflow.db.session, promoflow.db.seed, promoflow.ui.cache, promoflow.ui.auth,
                promoflow.ui.views.dashboard, promoflow.ui.views.reviews, promoflow.ui.views.section0,
                promoflow.ui.views.section1,
                promoflow.ui.views.section2, promoflow.ui.views.section3, promoflow.ui.views.section4,
                promoflow.ui.views.section5, promoflow.ui.views.section6, promoflow.ui.views.section7,
                promoflow.ui.views.section8, promoflow.ui.views.section9, promoflow.ui.views.section10,
                promoflow.ui.views.section11, promoflow.ui.shell):
        importlib.reload(mod)
    Base.metadata.create_all(promoflow.db.session.engine, tables=SQLITE_TABLES)
    # Load the starting data: test colleges, departments and accounts, then the policy thresholds, rubrics and
    # dropdown lists.
    with promoflow.db.session.session_scope() as s:
        promoflow.db.seed.seed_org_and_users(s, TEST_PASSWORD)
        promoflow.db.seed.seed_reference(s)
    return promoflow.db.session
