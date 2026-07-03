"""Request/response schemas for the admin connection-access manager."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ConnectionAccessOut(BaseModel):
    """The set of connections a user has been explicitly granted access to.

    Excludes connections the user owns (their access there is implicit).
    """

    connection_ids: list[int]


class ConnectionAccessUpdate(BaseModel):
    """Replace a user's full set of connection grants."""

    connection_ids: list[int] = Field(default_factory=list)
