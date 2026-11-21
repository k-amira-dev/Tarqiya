"""Schema checks that need no database: every table compiles for PostgreSQL and follows the conventions."""
from sqlalchemy import Enum
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

import promoflow.db.models  # noqa: F401
from promoflow.db.base import Base
from promoflow.db.seed import SERVICE_ITEMS, TEACHING_ITEMS

TABLES = Base.metadata.tables


def test_all_tables_compile_for_postgresql():
    for t in Base.metadata.sorted_tables:
        CreateTable(t).compile(dialect=postgresql.dialect())
    assert len(TABLES) == 66


def test_every_table_has_single_id_primary_key():
    for t in TABLES.values():
        assert [c.name for c in t.primary_key.columns] == ["id"], t.name


def test_dossier_entries_cascade_with_their_case():
    for t in TABLES.values():
        for fk in t.foreign_keys:
            if fk.column.table.name == "promotion_case" and fk.parent.name == "case_id" and t.name != "audit_log_entry":
                assert fk.ondelete == "CASCADE", t.name


def test_enum_types_store_lowercase_values():
    for t in TABLES.values():
        for c in t.columns:
            if isinstance(c.type, Enum):
                assert all(v == v.lower() for v in c.type.enums), (t.name, c.name)


def test_rubric_seed_matches_official_forms():
    # Appendix E: maxima add up to 33 but the form total is 30 (capped); Appendix F: 14 vs 10.
    assert len(TEACHING_ITEMS) == 10 and sum(i[3] for i in TEACHING_ITEMS) == 33
    assert len(SERVICE_ITEMS) == 5 and sum(i[3] for i in SERVICE_ITEMS) == 14
