"""Model / database constraint tests — the DB itself must reject bad data.

Covers: FK enforcement (orphan review rejected), the partial unique index (one active
review per snippet), UNIQUE(snippet_id, run_number), and the enum + line-range CHECKs.
"""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Finding, FindingMessage, Review, Snippet


def _snippet(db: Session, **kw) -> Snippet:
    s = Snippet(
        title=kw.get("title", "t"),
        language=kw.get("language", "python"),
        code=kw.get("code", "print(1)"),
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _review(snippet_id: str, run_number: int, status: str = "queued") -> Review:
    return Review(snippet_id=snippet_id, run_number=run_number, status=status)


# --- Foreign keys ---------------------------------------------------------------


def test_fk_rejects_orphan_review(db: Session):
    """Proves PRAGMA foreign_keys=ON is live: a review on a nonexistent snippet fails."""
    db.add(_review("does-not-exist", 1))
    with pytest.raises(IntegrityError):
        db.commit()


def test_fk_rejects_orphan_finding(db: Session):
    db.add(
        Finding(
            review_id="nope",
            line_start=1,
            line_end=1,
            severity="info",
            category="bug",
            description="x",
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()


# --- Partial unique index: one active review per snippet ------------------------


def test_partial_index_blocks_second_active_review(db: Session):
    s = _snippet(db)
    db.add(_review(s.id, 1, "queued"))
    db.commit()
    db.add(_review(s.id, 2, "running"))  # second ACTIVE review for same snippet
    with pytest.raises(IntegrityError):
        db.commit()


def test_partial_index_allows_new_review_after_completion(db: Session):
    """A completed review is OUTSIDE the partial set, so a fresh queued one is allowed."""
    s = _snippet(db)
    db.add(_review(s.id, 1, "completed"))
    db.commit()
    db.add(_review(s.id, 2, "queued"))
    db.commit()  # must not raise
    assert db.query(Review).filter_by(snippet_id=s.id).count() == 2


def test_partial_index_is_per_snippet(db: Session):
    """Two different snippets may each have an active review simultaneously."""
    a, b = _snippet(db, title="a"), _snippet(db, title="b")
    db.add(_review(a.id, 1, "queued"))
    db.add(_review(b.id, 1, "queued"))
    db.commit()  # must not raise


# --- UNIQUE(snippet_id, run_number) ---------------------------------------------


def test_unique_snippet_run_number(db: Session):
    s = _snippet(db)
    db.add(_review(s.id, 1, "completed"))
    db.commit()
    db.add(_review(s.id, 1, "failed"))  # same run_number, same snippet
    with pytest.raises(IntegrityError):
        db.commit()


# --- Enum + line-range CHECK constraints ----------------------------------------


@pytest.mark.parametrize(
    "field,value",
    [
        ("severity", "fatal"),
        ("category", "typo"),
        ("resolution_status", "maybe"),
    ],
)
def test_finding_enum_checks(db: Session, field: str, value: str):
    s = _snippet(db)
    r = _review(s.id, 1, "completed")
    db.add(r)
    db.commit()
    kw = dict(
        review_id=r.id,
        line_start=1,
        line_end=1,
        severity="info",
        category="bug",
        description="x",
    )
    kw[field] = value
    db.add(Finding(**kw))
    with pytest.raises(IntegrityError):
        db.commit()


@pytest.mark.parametrize("start,end", [(0, 5), (5, 3)])
def test_finding_line_checks(db: Session, start: int, end: int):
    s = _snippet(db)
    r = _review(s.id, 1, "completed")
    db.add(r)
    db.commit()
    db.add(
        Finding(
            review_id=r.id,
            line_start=start,
            line_end=end,
            severity="info",
            category="bug",
            description="x",
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()


def test_review_status_check(db: Session):
    s = _snippet(db)
    db.add(_review(s.id, 1, "pending"))  # not a valid status
    with pytest.raises(IntegrityError):
        db.commit()


def test_snippet_language_check(db: Session):
    db.add(Snippet(title="t", language="cobol", code="x"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_message_role_check(db: Session):
    s = _snippet(db)
    r = _review(s.id, 1, "completed")
    db.add(r)
    db.commit()
    f = Finding(
        review_id=r.id,
        line_start=1,
        line_end=1,
        severity="info",
        category="bug",
        description="x",
    )
    db.add(f)
    db.commit()
    db.add(FindingMessage(finding_id=f.id, role="system", content="x"))
    with pytest.raises(IntegrityError):
        db.commit()


@pytest.mark.parametrize(
    "latest_status,expected",
    [
        (None, "not_reviewed"),
        ("queued", "in_progress"),
        ("running", "in_progress"),
        ("completed", "reviewed"),
        ("failed", "failed"),
    ],
)
def test_derive_status_maps_latest_review(db: Session, latest_status, expected):
    """Derived dashboard status follows the snippet's latest review by run_number."""
    from app.routers.snippets import _derive_status, _latest_review

    s = _snippet(db)
    if latest_status is not None:
        # An older completed run must be ignored in favor of the highest run_number.
        db.add(_review(s.id, 1, "completed"))
        db.add(_review(s.id, 2, latest_status))
        db.commit()
    assert _derive_status(_latest_review(db, s.id)) == expected


def test_finding_resolution_defaults_open(db: Session):
    s = _snippet(db)
    r = _review(s.id, 1, "completed")
    db.add(r)
    db.commit()
    f = Finding(
        review_id=r.id,
        line_start=1,
        line_end=2,
        severity="warning",
        category="security",
        description="x",
    )
    db.add(f)
    db.commit()
    db.refresh(f)
    assert f.resolution_status == "open"
    assert f.resolved_at is None
