"""Engine and session factory.

WHAT ARE THESE? (for beginners)
  * The ENGINE is the connection to the database (and a small pool of reusable connections).
  * A SESSION is one "conversation" with the database: you read and change objects, then COMMIT to make the changes
    permanent, or ROLL BACK to undo them. Always use `session_scope()` below rather than creating sessions by hand.
"""
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from promoflow.config import DATABASE_URL

# Parallel page loads (see `parallel`) need several warm connections; opening a fresh one to a far-away database
# costs about a second, so keep a few open and drop idle ones after five minutes.
POOL_SIZE = 6
# pool_pre_ping = test a connection before using it, so a connection the server closed is replaced instead of failing.
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=POOL_SIZE, max_overflow=2, pool_recycle=300)
# expire_on_commit=False keeps loaded objects readable after commit (otherwise reading them would query again).
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

# Called after a scope that wrote something commits; the UI uses it to drop its per-session page cache.
write_hooks: list[Callable[[], None]] = []


@contextmanager
def session_scope() -> Iterator[Session]:
    """Commit on success, roll back on error.

    Use it with `with`:
        with session_scope() as s:
            s.add(something)        # committed automatically when the block ends normally
    If an exception is raised inside the block, nothing is saved (rollback) and the exception continues upward."""
    session = SessionLocal()
    wrote = []
    # A flush that carried changes means this scope wrote data (explicit s.flush() calls included).
    event.listen(session, "after_flush", lambda *_: wrote.append(True))
    try:
        yield session
        session.commit()
        if wrote:
            for hook in write_hooks:
                hook()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def parallel(*loaders: Callable[[Session], Any]) -> list[Any]:
    """Run independent read-only loaders at the same time, each in its own session, and return their results in
    order. The database is far away (~190 ms per round trip), so waiting for them one after another is slow."""
    def run(loader: Callable[[Session], Any]) -> Any:
        with session_scope() as session:
            return loader(session)

    # One pool slot is already held by the caller's own session; using more would open a slow extra connection.
    with ThreadPoolExecutor(max_workers=min(len(loaders), POOL_SIZE - 1)) as pool:
        futures = [pool.submit(run, loader) for loader in loaders]
        return [f.result() for f in futures]
