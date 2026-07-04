"""Admin token-usage monitoring: totals, breakdowns, and a daily series.

Aggregates the ``token_usage`` table (one row per LLM API call) over an optional
date window. Admin-guarded. No question text or row data is involved — only token
counts and the provider/model/user they are attributed to.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

from app.deps import AdminUser, SessionDep
from app.models.token_usage import TokenUsageRecord
from app.models.user import User
from app.schemas.usage import UsageByKey, UsageDailyPoint, UsageReport, UsageTotals

router = APIRouter(prefix="/admin/usage", tags=["admin"])

_DEFAULT_WINDOW_DAYS = 30

# The token columns summed in every aggregation, in a fixed order.
_SUM_COLUMNS = (
    TokenUsageRecord.input_tokens,
    TokenUsageRecord.output_tokens,
    TokenUsageRecord.cache_read_tokens,
    TokenUsageRecord.cache_write_tokens,
    TokenUsageRecord.total_tokens,
)


def _sums() -> list[ColumnElement[int]]:
    return [func.coalesce(func.sum(col), 0) for col in _SUM_COLUMNS]


def _window(date_from: datetime | None, date_to: datetime | None) -> list[ColumnElement[bool]]:
    clauses: list[ColumnElement[bool]] = []
    if date_from is not None:
        clauses.append(TokenUsageRecord.created_at >= date_from)
    if date_to is not None:
        clauses.append(TokenUsageRecord.created_at <= date_to)
    return clauses


@router.get("", response_model=UsageReport)
async def usage_report(
    _admin: AdminUser,
    session: SessionDep,
    date_from: datetime | None = Query(default=None, alias="from"),
    date_to: datetime | None = Query(default=None, alias="to"),
) -> UsageReport:
    """Aggregate token usage into totals, per-dimension breakdowns, and a daily series."""
    if date_from is None and date_to is None:
        date_from = datetime.now(tz=UTC) - timedelta(days=_DEFAULT_WINDOW_DAYS)
    where = _window(date_from, date_to)

    # --- Totals (+ call count) -------------------------------------------- #
    totals_stmt = select(*_sums(), func.count()).where(*where)
    tin, tout, tcr, tcw, ttot, tcount = (await session.execute(totals_stmt)).one()
    totals = UsageTotals(
        input_tokens=tin,
        output_tokens=tout,
        cache_read_tokens=tcr,
        cache_write_tokens=tcw,
        total_tokens=ttot,
        call_count=tcount,
    )

    # --- Breakdown by user (label = email) -------------------------------- #
    by_user_stmt = (
        select(TokenUsageRecord.user_id, User.email, *_sums(), func.count())
        .join(User, User.id == TokenUsageRecord.user_id)
        .where(*where)
        .group_by(TokenUsageRecord.user_id, User.email)
        .order_by(func.sum(TokenUsageRecord.total_tokens).desc())
    )
    by_user = [
        UsageByKey(
            key=str(uid),
            label=email or f"#{uid}",
            input_tokens=i,
            output_tokens=o,
            cache_read_tokens=cr,
            cache_write_tokens=cw,
            total_tokens=t,
            call_count=c,
        )
        for uid, email, i, o, cr, cw, t, c in (await session.execute(by_user_stmt)).all()
    ]

    by_model = await _breakdown_by(session, TokenUsageRecord.model, where)
    by_provider = await _breakdown_by(session, TokenUsageRecord.provider, where)

    # --- Daily series ----------------------------------------------------- #
    day = func.date(TokenUsageRecord.created_at)
    daily_stmt = select(day, *_sums()).where(*where).group_by(day).order_by(day)
    daily = [
        UsageDailyPoint(
            day=str(d),
            input_tokens=i,
            output_tokens=o,
            cache_read_tokens=cr,
            cache_write_tokens=cw,
            total_tokens=t,
        )
        for d, i, o, cr, cw, t in (await session.execute(daily_stmt)).all()
    ]

    return UsageReport(
        totals=totals,
        by_user=by_user,
        by_model=by_model,
        by_provider=by_provider,
        daily=daily,
    )


async def _breakdown_by(
    session: SessionDep,
    column: InstrumentedAttribute[str | None],
    where: list[ColumnElement[bool]],
) -> list[UsageByKey]:
    """Group totals by a single string column (model or provider)."""
    stmt = (
        select(column, *_sums(), func.count())
        .where(*where)
        .group_by(column)
        .order_by(func.sum(TokenUsageRecord.total_tokens).desc())
    )
    out: list[UsageByKey] = []
    for key, i, o, cr, cw, t, c in (await session.execute(stmt)).all():
        label = key if key is not None else "unknown"
        out.append(
            UsageByKey(
                key=label,
                label=label,
                input_tokens=i,
                output_tokens=o,
                cache_read_tokens=cr,
                cache_write_tokens=cw,
                total_tokens=t,
                call_count=c,
            )
        )
    return out
