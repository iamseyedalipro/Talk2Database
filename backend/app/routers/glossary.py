"""Semantic layer: per-connection table/column descriptions and business metrics.

Connections are owned per user, so the connection's owner manages its glossary
(``get_owned_connection`` enforces this — there is no cross-tenant access). The
annotations are fed into the AI prompt by the ask flow to improve SQL accuracy.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.deps import CurrentUser, SessionDep
from app.models.glossary import GlossaryDescription, Metric
from app.schemas.glossary import (
    DescriptionOut,
    DescriptionUpsert,
    GlossaryData,
    MetricCreate,
    MetricOut,
    MetricUpdate,
)
from app.services.connections import get_owned_connection
from app.services.schema.glossary import load_glossary

router = APIRouter(prefix="/connections/{connection_id}/glossary", tags=["glossary"])


@router.get("", response_model=GlossaryData)
async def get_glossary(connection_id: int, user: CurrentUser, session: SessionDep) -> GlossaryData:
    await get_owned_connection(session, connection_id, user)
    descriptions, metrics = await load_glossary(session, connection_id)
    return GlossaryData(
        descriptions=[DescriptionOut.model_validate(d) for d in descriptions],
        metrics=[MetricOut.model_validate(m) for m in metrics],
    )


@router.put("/descriptions", response_model=DescriptionOut)
async def upsert_description(
    connection_id: int,
    payload: DescriptionUpsert,
    user: CurrentUser,
    session: SessionDep,
) -> DescriptionOut:
    await get_owned_connection(session, connection_id, user)
    existing = await session.scalar(
        select(GlossaryDescription).where(
            GlossaryDescription.connection_id == connection_id,
            GlossaryDescription.table_name == payload.table_name,
            GlossaryDescription.column_name == payload.column_name,
        )
    )
    if existing is None:
        existing = GlossaryDescription(
            connection_id=connection_id,
            table_name=payload.table_name,
            column_name=payload.column_name,
            description=payload.description,
        )
        session.add(existing)
    else:
        existing.description = payload.description
    await session.flush()
    return DescriptionOut.model_validate(existing)


@router.delete("/descriptions/{description_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_description(
    connection_id: int, description_id: int, user: CurrentUser, session: SessionDep
) -> Response:
    await get_owned_connection(session, connection_id, user)
    entry = await session.get(GlossaryDescription, description_id)
    if entry is None or entry.connection_id != connection_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Description not found.")
    await session.delete(entry)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/metrics", response_model=MetricOut, status_code=status.HTTP_201_CREATED)
async def create_metric(
    connection_id: int, payload: MetricCreate, user: CurrentUser, session: SessionDep
) -> MetricOut:
    await get_owned_connection(session, connection_id, user)
    metric = Metric(
        connection_id=connection_id,
        name=payload.name,
        definition=payload.definition,
        expression=payload.expression,
    )
    session.add(metric)
    try:
        await session.flush()
    except Exception as exc:  # unique (connection, name) violation
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A metric with that name already exists for this connection.",
        ) from exc
    return MetricOut.model_validate(metric)


async def _owned_metric(
    session: SessionDep, connection_id: int, metric_id: int, user: CurrentUser
) -> Metric:
    await get_owned_connection(session, connection_id, user)
    metric = await session.get(Metric, metric_id)
    if metric is None or metric.connection_id != connection_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Metric not found.")
    return metric


@router.patch("/metrics/{metric_id}", response_model=MetricOut)
async def update_metric(
    connection_id: int,
    metric_id: int,
    payload: MetricUpdate,
    user: CurrentUser,
    session: SessionDep,
) -> MetricOut:
    metric = await _owned_metric(session, connection_id, metric_id, user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(metric, field, value)
    await session.flush()
    return MetricOut.model_validate(metric)


@router.delete("/metrics/{metric_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_metric(
    connection_id: int, metric_id: int, user: CurrentUser, session: SessionDep
) -> Response:
    metric = await _owned_metric(session, connection_id, metric_id, user)
    await session.delete(metric)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
