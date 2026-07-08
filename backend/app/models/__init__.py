"""Panel-database ORM models.

Importing this package registers every model on ``Base.metadata`` so Alembic
autogeneration and ``create_all`` can see them.
"""

from app.db.base import Base
from app.models.app_setting import AppSetting
from app.models.chat import ChatMessage, ChatSession
from app.models.clarity import ClarityFetchRun, ClaritySnapshot
from app.models.connection import Connection, DataSourceType
from app.models.connection_access import ConnectionAccess
from app.models.dashboard import Dashboard, DashboardWidget
from app.models.dashboard_share import DashboardAccessLevel, DashboardShare
from app.models.glossary import GlossaryDescription, Metric
from app.models.invite import Invite
from app.models.query_history import QueryHistory, QueryStatus
from app.models.saved_query import SavedQuery
from app.models.schema_snapshot import SchemaSnapshot
from app.models.token_usage import TokenUsageRecord
from app.models.user import User, UserRole

__all__ = [
    "AppSetting",
    "Base",
    "ChatMessage",
    "ChatSession",
    "ClarityFetchRun",
    "ClaritySnapshot",
    "Connection",
    "ConnectionAccess",
    "Dashboard",
    "DashboardAccessLevel",
    "DashboardShare",
    "DashboardWidget",
    "DataSourceType",
    "GlossaryDescription",
    "Invite",
    "Metric",
    "QueryHistory",
    "QueryStatus",
    "SavedQuery",
    "SchemaSnapshot",
    "TokenUsageRecord",
    "User",
    "UserRole",
]
