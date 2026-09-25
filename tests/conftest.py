import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from promoflow.db.base import Base
from promoflow.db.models import AUTH_TABLES


@pytest.fixture
def auth_db():
    """In-memory SQLite with only the login tables (portable types)."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=AUTH_TABLES)
    with Session(engine) as s:
        yield s
