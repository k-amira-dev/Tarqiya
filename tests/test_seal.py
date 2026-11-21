"""The audit log and each model's score are tamper-evident."""
from sqlalchemy import delete, select, text, update

from promoflow.db import seal
import pytest

from promoflow.db.models import AuditLogEntry, RubricOpinion


@pytest.fixture(autouse=True)
def _opinion_table(auth_db):
    RubricOpinion.__table__.create(auth_db.get_bind(), checkfirst=True)     # the login-only test database lacks it


def _add(s, n=4):
    for i in range(n):
        s.add(AuditLogEntry(user_id=1, case_id=5, action=f"act{i}", after={"x": i, "k": [1, 2]}))
        s.flush()
    s.commit()


def test_every_new_row_is_chained_and_verifies(auth_db):
    _add(auth_db)
    rows = auth_db.scalars(select(AuditLogEntry).order_by(AuditLogEntry.id)).all()
    assert all(r.entry_hash for r in rows)
    assert rows[0].prev_hash == "" and all(rows[i].prev_hash == rows[i - 1].entry_hash for i in range(1, len(rows)))
    out = seal.verify(auth_db)
    assert out["problems"] == [] and out["audit_sealed"] == 4 and out["audit_unsealed"] == 0


def test_rows_saved_together_are_chained_in_order(auth_db):
    for i in range(3):
        auth_db.add(AuditLogEntry(user_id=1, action=f"a{i}"))
    auth_db.commit()
    assert seal.verify(auth_db)["problems"] == []


def test_editing_a_row_is_detected(auth_db):
    _add(auth_db)
    auth_db.execute(update(AuditLogEntry).where(AuditLogEntry.action == "act1").values(user_id=99))
    auth_db.commit()
    problems = seal.verify(auth_db)["problems"]
    assert any("act1" in p and "modified" in p for p in problems)


def test_editing_the_snapshot_is_detected(auth_db):
    _add(auth_db)
    auth_db.execute(update(AuditLogEntry).where(AuditLogEntry.action == "act2").values(after={"x": 999}))
    auth_db.commit()
    assert any("act2" in p for p in seal.verify(auth_db)["problems"])


def test_deleting_a_row_is_detected(auth_db):
    _add(auth_db)
    auth_db.execute(delete(AuditLogEntry).where(AuditLogEntry.action == "act1"))
    auth_db.commit()
    assert any("missing" in p for p in seal.verify(auth_db)["problems"])


def test_hashes_cannot_be_recomputed_without_the_key(auth_db, monkeypatch):
    _add(auth_db)
    from promoflow import config
    monkeypatch.setattr(config, "AUDIT_HMAC_KEY", "a-different-key")
    assert seal.verify(auth_db)["problems"]            # the real chain does not check out under another key


def test_rows_from_before_the_migration_are_sealed_by_backfill(auth_db, monkeypatch):
    from promoflow import config
    monkeypatch.setattr(config, "AUDIT_HMAC_KEY", "")
    _add(auth_db, 3)                                   # written while no key was set: left unsealed
    monkeypatch.setattr(config, "AUDIT_HMAC_KEY", "test-audit-key")
    assert seal.verify(auth_db)["audit_unsealed"] == 3
    assert seal.backfill(auth_db)["audit_rows_sealed"] == 3
    auth_db.commit()
    out = seal.verify(auth_db)
    assert out["audit_unsealed"] == 0 and out["problems"] == []


def test_a_model_score_row_is_sealed_and_an_edit_is_detected(auth_db):
    auth_db.add(RubricOpinion(rubric_score_id=1, model_name="groq:openai/gpt-oss-120b", points=3.5, rationale="clear syllabus", confidence="high"))
    auth_db.commit()
    assert seal.verify(auth_db)["problems"] == [] and seal.verify(auth_db)["opinions_unsealed"] == 0
    auth_db.execute(update(RubricOpinion).values(points=5))
    auth_db.commit()
    assert any("model score" in p for p in seal.verify(auth_db)["problems"])
