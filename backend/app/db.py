"""Database engine + session setup.

SQLite with two pragmas enabled on every connection:
- foreign_keys=ON  — SQLite ignores FK constraints unless this is set per-connection.
- journal_mode=WAL — better read/write concurrency for our single-process worker + API.

Models/tables are added in M1; this module only owns the connection + session factory.
"""
import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

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
    """FastAPI dependency: yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
