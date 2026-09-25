import importlib

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from promoflow.db.base import Base
from promoflow.db.models import AUTH_TABLES, SQLITE_TABLES

TEST_PASSWORD = "test-pass"


@pytest.fixture
def auth_db():
    """In-memory SQLite with only the login tables (portable types)."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=AUTH_TABLES)
    with Session(engine) as s:
        yield s


@pytest.fixture
def app_env(tmp_path, monkeypatch):
    """A seeded SQLite database file, with every module that holds the engine re-bound to it."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'app.db'}")
    import promoflow.config
    import promoflow.db.seed
    import promoflow.db.session
    import promoflow.ui.auth
    import promoflow.ui.shell
    import promoflow.ui.views.dashboard
    import promoflow.ui.views.section0
    for mod in (promoflow.config, promoflow.db.session, promoflow.db.seed, promoflow.ui.auth,
                promoflow.ui.views.dashboard, promoflow.ui.views.section0, promoflow.ui.shell):
        importlib.reload(mod)
    Base.metadata.create_all(promoflow.db.session.engine, tables=SQLITE_TABLES)
    with promoflow.db.session.session_scope() as s:
        promoflow.db.seed.seed_org_and_users(s, TEST_PASSWORD)
        promoflow.db.seed.seed_reference(s)
    return promoflow.db.session
