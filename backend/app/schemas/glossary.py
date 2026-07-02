"""Schemas for the semantic layer (glossary descriptions + metrics)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DescriptionUpsert(BaseModel):
    table_name: str = Field(min_length=1, max_length=255)
    column_name: str = Field(default="", max_length=255)  # "" => table-level
    description: str = Field(min_length=1, max_length=4000)


class DescriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    table_name: str
    column_name: str
    description: str


class MetricCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    definition: str = Field(min_length=1, max_length=4000)
    expression: str | None = Field(default=None, max_length=4000)


class MetricUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    definition: str | None = Field(default=None, min_length=1, max_length=4000)
    expression: str | None = Field(default=None, max_length=4000)


class MetricOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    definition: str
    expression: str | None = None


class GlossaryData(BaseModel):
    descriptions: list[DescriptionOut]
    metrics: list[MetricOut]
