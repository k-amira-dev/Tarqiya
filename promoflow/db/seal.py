"""Tamper evidence for the audit log and for each model's score.

AUDIT LOG: every new audit row gets `entry_hash` = HMAC-SHA256 (keyed with AUDIT_HMAC_KEY) of all its fields plus the
previous row's hash (`prev_hash`). Change, remove or insert a row anywhere and the chain no longer checks out. Anyone who edits the
database but does not hold the key cannot recompute the hashes.

MODEL SCORES: each `rubric_opinion` row (one model's points for one rubric line) carries a `seal`, an HMAC of its own fields. The
live table is replaced whenever a case is re-scored, so every score is ALSO written to the audit log (see workflow/persist.py),
which keeps the full history of what each model said.

Sealing happens automatically when rows are saved (see the listeners at the bottom). Check everything with:
    python -m promoflow.db.seal verify
    python -m promoflow.db.seal backfill       (once, after migration 0009, to seal rows written before it)
"""
import hmac
import json
import sys
from datetime import datetime, timezone
from hashlib import sha256

from sqlalchemy import event, select, text, update
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import set_committed_value

from promoflow import config
from promoflow.db.models.assessment import RubricOpinion
from promoflow.db.models.audit import AuditLogEntry

LOCK_KEY = 73050001   # PostgreSQL advisory lock: audit writers take turns, so the chain cannot fork


def _key() -> bytes | None:
    return config.AUDIT_HMAC_KEY.encode() if config.AUDIT_HMAC_KEY else None


def _canon(obj) -> bytes:
    """One exact byte string per value: sorted keys, no spaces. JSON round-trip first so a tuple, or a number stored
    and read back from the database, gives the same bytes."""
    return json.dumps(json.loads(json.dumps(obj, default=str)), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _utc(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds")


def audit_hash(row, prev_hash: str, key: bytes) -> str:
    fields = {"id": row.id, "at": _utc(row.occurred_at), "user": row.user_id, "case": row.case_id, "action": row.action,
              "table": row.entity_table, "entity": row.entity_id, "before": row.before, "after": row.after, "detail": row.detail,
              "prev": prev_hash}
    return hmac.new(key, _canon(fields), sha256).hexdigest()


def opinion_seal(row, key: bytes) -> str:
    fields = {"id": row.id, "score": row.rubric_score_id, "model": row.model_name, "points": f"{float(row.points):.1f}",
              "rationale": row.rationale, "confidence": row.confidence}
    return hmac.new(key, _canon(fields), sha256).hexdigest()


# ---- automatic sealing while rows are saved ------------------------------------------------------------------------------
def _last_hash(conn) -> str:
    """The hash of the newest sealed row ('' when the chain is empty)."""
    t = AuditLogEntry.__table__
    return conn.execute(select(t.c.entry_hash).where(t.c.entry_hash.is_not(None)).order_by(t.c.id.desc()).limit(1)).scalar() or ""


@event.listens_for(Session, "before_flush")
def _stamp_time(session, _ctx, _instances):
    """The time goes into the hash, so it is set here (not by the database) before the row is written."""
    new_audit = False
    for obj in session.new:
        if isinstance(obj, AuditLogEntry):
            new_audit = True
            if obj.occurred_at is None:
                obj.occurred_at = datetime.now(timezone.utc)
    if new_audit and _key() is not None:
        # Take the writers' turn BEFORE the rows get their ids. Taken only after the insert (as it was), two writers could be given ids in one
        # order and seal in the other, and the next row then chained to the wrong one: the chain forked (seen when agents ran in parallel).
        conn = session.connection()
        if conn.dialect.name == "postgresql":
            conn.execute(text("select pg_advisory_xact_lock(:k)"), {"k": LOCK_KEY})


@event.listens_for(Session, "after_flush")
def _seal_new_rows(session, _ctx):
    key = _key()
    audits = sorted((o for o in session.new if isinstance(o, AuditLogEntry)), key=lambda o: o.id)
    opinions = [o for o in session.new if isinstance(o, RubricOpinion)]
    if key is None or not (audits or opinions):
        return                                    # no key set: rows stay unsealed and `verify` reports them
    conn = session.connection()
    if audits:
        if conn.dialect.name == "postgresql":
            conn.execute(text("select pg_advisory_xact_lock(:k)"), {"k": LOCK_KEY})
        prev = _last_hash(conn)
        for o in audits:
            h = audit_hash(o, prev, key)
            conn.execute(update(AuditLogEntry.__table__).where(AuditLogEntry.__table__.c.id == o.id).values(prev_hash=prev, entry_hash=h))
            set_committed_value(o, "prev_hash", prev)
            set_committed_value(o, "entry_hash", h)
            prev = h
    for o in opinions:
        s = opinion_seal(o, key)
        conn.execute(update(RubricOpinion.__table__).where(RubricOpinion.__table__.c.id == o.id).values(seal=s))
        set_committed_value(o, "seal", s)


# ---- checking ---------------------------------------------------------------------------------------------------------------
def verify(s: Session) -> dict:
    key = _key()
    if key is None:
        return {"error": "AUDIT_HMAC_KEY is not set"}
    rows = s.scalars(select(AuditLogEntry).order_by(AuditLogEntry.id)).all()
    problems, unsealed, sealed = [], 0, []
    for r in rows:
        if r.entry_hash is None:
            unsealed += 1
            continue
        sealed.append(r)
        if not hmac.compare_digest(audit_hash(r, r.prev_hash or "", key), r.entry_hash):
            problems.append(f"audit row {r.id} ({r.action}) was modified")
    hashes = {r.entry_hash for r in sealed}
    for r in sealed:
        if (r.prev_hash or "") != "" and r.prev_hash not in hashes:
            problems.append(f"audit row {r.id} ({r.action}): the row before it is missing or was altered")
    by_prev: dict[str, list[int]] = {}
    for r in sealed:
        by_prev.setdefault(r.prev_hash or "", []).append(r.id)
    for prev, ids in by_prev.items():
        if len(ids) > 1:
            problems.append(f"the chain forks after {prev[:10] or 'the start'}: rows {ids}")
    ops = s.scalars(select(RubricOpinion)).all()
    op_unsealed = 0
    for o in ops:
        if o.seal is None:
            op_unsealed += 1
        elif not hmac.compare_digest(opinion_seal(o, key), o.seal):
            problems.append(f"model score (rubric_opinion {o.id}, {o.model_name}) was modified")
    head = sealed[-1] if sealed else None
    return {"audit_rows": len(rows), "audit_sealed": len(sealed), "audit_unsealed": unsealed, "opinions": len(ops), "opinions_unsealed": op_unsealed,
            "head_id": head.id if head else None, "head_hash": head.entry_hash[:16] if head else None, "problems": problems}


def backfill(s: Session) -> dict:
    """Seal rows written before migration 0009, oldest first, continuing the existing chain. Run once.
    Rows sealed here are protected from now on; whether they were untouched before today cannot be proven."""
    key = _key()
    if key is None:
        return {"error": "AUDIT_HMAC_KEY is not set"}
    conn = s.connection()
    prev = _last_hash(conn)
    n = 0
    for r in s.scalars(select(AuditLogEntry).where(AuditLogEntry.entry_hash.is_(None)).order_by(AuditLogEntry.id)).all():
        h = audit_hash(r, prev, key)
        conn.execute(update(AuditLogEntry.__table__).where(AuditLogEntry.__table__.c.id == r.id).values(prev_hash=prev, entry_hash=h))
        prev = h
        n += 1
    m = 0
    for o in s.scalars(select(RubricOpinion).where(RubricOpinion.seal.is_(None))).all():
        conn.execute(update(RubricOpinion.__table__).where(RubricOpinion.__table__.c.id == o.id).values(seal=opinion_seal(o, key)))
        m += 1
    return {"audit_rows_sealed": n, "opinions_sealed": m}


if __name__ == "__main__":
    from promoflow.db.session import session_scope

    cmd = sys.argv[1] if len(sys.argv) > 1 else "verify"
    with session_scope() as sess:
        out = backfill(sess) if cmd == "backfill" else verify(sess)
    print(json.dumps(out, indent=1))
    sys.exit(1 if out.get("error") or out.get("problems") else 0)
