"""Schemas for dashboards and their widgets."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

WidgetView = Literal["table", "bar", "hbar", "line", "area", "pie", "scatter"]


class WidgetViz(BaseModel):
    view: WidgetView = "table"
    x_column: str | None = None
    y_column: str | None = None


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
    widget_count: int = 0
    created_at: datetime
    updated_at: datetime


class DashboardDetail(DashboardItem):
    widgets: list[WidgetItem] = Field(default_factory=list)


class WidgetRunRequest(BaseModel):
    max_rows: int | None = Field(default=None, ge=1, le=100000)
