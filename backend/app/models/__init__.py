"""Panel-database ORM models.

Importing this package registers every model on ``Base.metadata`` so Alembic
autogeneration and ``create_all`` can see them.
"""

from app.db.base import Base
from app.models.connection import Connection, DataSourceType
from app.models.invite import Invite
from app.models.query_history import QueryHistory, QueryStatus
from app.models.schema_snapshot import SchemaSnapshot
from app.models.user import User, UserRole

__all__ = [
    "Base",
    "Connection",
    "DataSourceType",
    "Invite",
    "QueryHistory",
    "QueryStatus",
    "SchemaSnapshot",
    "User",
    "UserRole",
]
