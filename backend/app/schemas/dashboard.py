"""Schemas for dashboards and their widgets."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

WidgetView = Literal["table", "bar", "hbar", "line", "area", "pie", "scatter", "radar", "combo"]
StackMode = Literal["none", "stacked", "percent"]
ComboSeriesType = Literal["bar", "line"]
PieMode = Literal["category", "columns"]
# Per-user share access level, plus the caller's effective access on a dashboard.
ShareAccess = Literal["view", "edit"]
MyAccess = Literal["owner", "edit", "view"]


class WidgetViz(BaseModel):
    view: WidgetView = "table"
    x_column: str | None = None
    # Ordered Y columns (wide multi-series). Empty means auto-pick the first numeric.
    y_columns: list[str] = Field(default_factory=list)
    # Long-shape pivot: one series per distinct value; uses y_columns[0] as the value.
    series_column: str | None = None
    # bar / hbar / area only; "percent" is 100%-stacked.
    stacked: StackMode = "none"
    # combo only: per-Y-column mark; columns absent from the map default to "bar".
    combo_types: dict[str, ComboSeriesType] = Field(default_factory=dict)
    # combo only: Y columns plotted on the secondary (right) axis.
    right_axis: list[str] = Field(default_factory=list)
    # pie only: "category" = one slice per row; "columns" = one slice per y column total.
    pie_mode: PieMode = "category"
    # Legacy single-Y key: accepted from old rows/clients, kept in sync on output.
    y_column: str | None = None

    @model_validator(mode="after")
    def _normalize_legacy(self) -> WidgetViz:
        if not self.y_columns and self.y_column:
            self.y_columns = [self.y_column]
        self.y_column = self.y_columns[0] if self.y_columns else None
        return self


class WidgetCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    connection_id: int
    sql: str = Field(min_length=1, max_length=20000)
    viz: WidgetViz = Field(default_factory=WidgetViz)
    x: int = Field(default=0, ge=0)
    y: int = Field(default=0, ge=0)
    w: int = Field(default=6, ge=1, le=12)
    h: int = Field(default=4, ge=1, le=24)


class WidgetUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    connection_id: int | None = None
    sql: str | None = Field(default=None, min_length=1, max_length=20000)
    viz: WidgetViz | None = None


class WidgetItem(BaseModel):
    id: int
    title: str
    connection_id: int | None
    sql: str
    viz: WidgetViz
    x: int
    y: int
    w: int
    h: int


class LayoutItem(BaseModel):
    widget_id: int
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(ge=1, le=12)
    h: int = Field(ge=1, le=24)


class LayoutUpdate(BaseModel):
    items: list[LayoutItem]


class DashboardCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    shared: bool = False


class DashboardUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    shared: bool | None = None


class DashboardItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    shared: bool
    owner_email: str | None = None
    is_owner: bool = False
    # The caller's effective access: they own it, may edit it, or may only view.
    my_access: MyAccess = "view"
    widget_count: int = 0
    created_at: datetime
    updated_at: datetime


class DashboardDetail(DashboardItem):
    widgets: list[WidgetItem] = Field(default_factory=list)


class WidgetRunRequest(BaseModel):
    max_rows: int | None = Field(default=None, ge=1, le=100000)


class DashboardShareEntry(BaseModel):
    """One requested share grant: give ``user_id`` this ``access_level``."""

    user_id: int
    access_level: ShareAccess


class DashboardSharesUpdate(BaseModel):
    """Replace a dashboard's full set of per-user share grants."""

    shares: list[DashboardShareEntry] = Field(default_factory=list)


class DashboardShareItem(BaseModel):
    """A share grant, with the recipient's email for display."""

    user_id: int
    email: str
    access_level: ShareAccess
