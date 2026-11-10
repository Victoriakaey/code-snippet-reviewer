"""ensure_schema (additive column migration) — create_all does not alter existing tables,
so a pre-existing finding_messages table must gain the new columns explicitly.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from app import models  # noqa: F401 — register tables on Base.
from app.db import Base, ensure_schema

NEW_COLS = {"provider", "model_name"}


def _columns(engine, table: str) -> set[str]:
    with engine.connect() as conn:
        return {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}


def _old_finding_messages(engine) -> None:
    """A finding_messages table from BEFORE the provider/model_name columns existed."""
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE finding_messages ("
            "id TEXT PRIMARY KEY, finding_id TEXT, role TEXT, content TEXT, created_at TIMESTAMP)"
        )


def test_fresh_db_table_already_has_new_columns(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    Base.metadata.create_all(eng)
    ensure_schema(eng)  # no-op
    assert NEW_COLS <= _columns(eng, "finding_messages")


def test_old_db_is_upgraded_without_losing_data(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    _old_finding_messages(eng)
    with eng.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO finding_messages (id, finding_id, role, content, created_at) "
            "VALUES ('m1', 'f1', 'user', 'existing message', '2026-01-01 00:00:00')"
        )
    assert "provider" not in _columns(eng, "finding_messages")

    ensure_schema(eng)

    assert NEW_COLS <= _columns(eng, "finding_messages")
    with eng.connect() as conn:
        row = conn.exec_driver_sql(
            "SELECT content, provider FROM finding_messages WHERE id = 'm1'"
        ).fetchone()
    assert row[0] == "existing message"  # data preserved
    assert row[1] is None  # new column is null for the old row


def test_repeated_startup_is_idempotent(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'idem.db'}")
    _old_finding_messages(eng)
    ensure_schema(eng)
    ensure_schema(eng)  # again — must not error or duplicate columns
    cols = _columns(eng, "finding_messages")
    assert NEW_COLS <= cols


def test_migration_raises_on_failure_not_silent(tmp_path, monkeypatch):
    # If the migration cannot complete, it must RAISE (never swallow and continue with a
    # missing column). Force a failure via an invalid column spec.
    eng = create_engine(f"sqlite:///{tmp_path / 'fail.db'}")
    _old_finding_messages(eng)
    # An invalid column type makes ALTER TABLE a syntax error -> the DB raises.
    monkeypatch.setattr(
        "app.db._REQUIRED_COLUMNS", {"finding_messages": {"newcol": "VARCHAR)"}}
    )
    with pytest.raises(Exception):
        ensure_schema(eng)
