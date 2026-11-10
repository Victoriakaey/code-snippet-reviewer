"""Database engine + session setup.

SQLite with two pragmas enabled on every connection:
- foreign_keys=ON  — SQLite ignores FK constraints unless this is set per-connection.
- journal_mode=WAL — better read/write concurrency for our single-process worker + API.

Session rule (important): a SQLAlchemy Session is NOT thread-safe and must never be
shared across threads. `check_same_thread=False` only lets the DBAPI *connection* be
used from another thread — it does not make a Session safe to share. So:
- each API request gets its own Session via the `get_db` dependency;
- the background review worker (M3) must open its OWN Session per job via `session_scope`
  (or `SessionLocal()`), never reuse a request's Session.

Models/tables are added in M1; this module only owns the connection + session factory.
"""
import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

# Ensure the SQLite directory exists before the engine opens the file.
if settings.database_url.startswith("sqlite"):
    _path = settings.database_url.split("///")[-1]
    _dir = os.path.dirname(_path)
    if _dir:
        os.makedirs(_dir, exist_ok=True)

engine = create_engine(
    settings.database_url,
    # SQLite + a background worker thread share one engine: allow cross-thread use.
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, _connection_record):
    if not settings.database_url.startswith("sqlite"):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Declarative base for ORM models (populated in M1)."""


def get_db():
    """FastAPI dependency: yields a NEW Session per request and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """A transactional Session scope for code outside a request (e.g. the M3 worker).

    Each call opens its own Session — the worker must use this (or SessionLocal())
    per job, never a Session borrowed from another thread/request.

    Commits on clean exit (a read-only caller commits a harmless no-op) and rolls
    back + re-raises on any exception.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
