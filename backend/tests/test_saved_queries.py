"""Tests for saved-query visibility and edit permissions (pure logic, no DB)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from app.routers.saved_queries import can_edit, can_view


@dataclass
class _User:
    id: int
    is_admin: bool = False


@dataclass
class _SavedQuery:
    owner_id: int
    shared: bool = False


OWNER = _User(id=1)
OTHER = _User(id=2)
ADMIN = _User(id=3, is_admin=True)


@pytest.mark.parametrize(
    ("user", "sq", "expected"),
    [
        (OWNER, _SavedQuery(owner_id=1, shared=False), True),  # own private
        (OTHER, _SavedQuery(owner_id=1, shared=False), False),  # other's private hidden
        (OTHER, _SavedQuery(owner_id=1, shared=True), True),  # other's shared visible
        (ADMIN, _SavedQuery(owner_id=1, shared=False), False),  # admin can't see private
    ],
)
def test_can_view(user: _User, sq: _SavedQuery, expected: bool) -> None:
    assert can_view(user, sq) is expected  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("user", "sq", "expected"),
    [
        (OWNER, _SavedQuery(owner_id=1, shared=False), True),  # owner edits own
        (OTHER, _SavedQuery(owner_id=1, shared=True), False),  # non-owner cannot edit shared
        (ADMIN, _SavedQuery(owner_id=1, shared=True), True),  # admin moderates shared
        (ADMIN, _SavedQuery(owner_id=1, shared=False), False),  # admin can't touch private
    ],
)
def test_can_edit(user: _User, sq: _SavedQuery, expected: bool) -> None:
    assert can_edit(user, sq) is expected  # type: ignore[arg-type]
