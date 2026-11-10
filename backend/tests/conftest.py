"""Test fixtures: an ISOLATED SQLite DB per test — never the app's ./data/app.db.

Each test gets a fresh temp-file database with `PRAGMA foreign_keys=ON` (so the FK-
enforcement test is meaningful) and all tables created. The `client` fixture overrides the
app's `get_db` dependency to use that same database, so API calls and direct-model
assertions see one consistent store.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app import models  # noqa: F401 — register tables on Base.
from app.db import Base, get_db
from app.main import app


@pytest.fixture
def engine(tmp_path) -> Iterator[Engine]:
    url = f"sqlite:///{tmp_path / 'test.db'}"
    eng = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(eng, "connect")
    def _pragmas(dbapi_connection, _record):  # noqa: ANN001
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture
def db(session_factory: sessionmaker) -> Iterator[Session]:
    """A direct Session for model-level constraint tests."""
    s = session_factory()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def client(session_factory: sessionmaker) -> Iterator[TestClient]:
    def _override() -> Iterator[Session]:
        s = session_factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override
    try:
        # Deliberately NOT `with TestClient(app)`: without the context manager the lifespan
        # (and thus the background worker) does not run, so review-API tests see a stable
        # `queued` state. Worker processing is covered separately in test_worker.py by
        # driving worker.process_next() directly. If this is ever switched to a `with`
        # block, the queued-state assertions in test_reviews_api.py can race the worker.
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def worker_scope(session_factory: sessionmaker, monkeypatch):
    """Point the worker's transaction scope at the test database (it otherwise uses the real
    engine). Returns the scope so tests can also seed/inspect rows through it."""

    @contextmanager
    def scope() -> Iterator[Session]:
        s = session_factory()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    monkeypatch.setattr("app.worker._session_scope", scope)
    return scope
