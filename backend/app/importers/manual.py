"""Manual backup import: detect the format and restore into the user-data DB.

Supported uploads:
  * plain SQL dumps      -> restored with ``psql``
  * pg_dump custom/tar   -> restored with ``pg_restore``

Restores use the admin DSN (DDL is required) and run as a background task so the
upload request returns immediately. On success the read-only role is re-granted
and the schema snapshot is rebuilt.
"""

from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.db.panel import get_sessionmaker
from app.models.import_run import ImportRun, ImportStatus
from app.services.pg_version import check_restore_compatibility
from app.services.readonly_role import ensure_readonly_role
from app.services.schema.cache import rebuild_snapshot
from app.services.sql_roles import ensure_roles_for_plain_dump


class BackupFormat(StrEnum):
    PLAIN = "plain"
    CUSTOM = "custom"
    TAR = "tar"


def detect_format(path: str) -> BackupFormat:
    """Detect a backup's format from its leading bytes."""
    with open(path, "rb") as handle:
        head = handle.read(512)
    if head[:5] == b"PGDMP":
        return BackupFormat.CUSTOM
    if len(head) >= 263 and head[257:262] == b"ustar":
        return BackupFormat.TAR
    return BackupFormat.PLAIN


def _restore(path: str, fmt: BackupFormat) -> tuple[bool, str]:
    """Run the restore command; return (success, captured output tail)."""
    dsn = get_settings().userdata_admin_dsn
    note = ""
    if fmt is BackupFormat.PLAIN:
        # A plain dump cannot have ownership stripped at load time, so pre-create
        # any roles it references (e.g. the source DB owner) as NOLOGIN roles.
        try:
            created = ensure_roles_for_plain_dump(path)
        except Exception as exc:
            return False, f"could not pre-create roles referenced by the dump: {exc}"
        if created:
            note = f"pre-created roles: {', '.join(created)}\n"
        cmd = ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-f", path]
    else:
        cmd = [
            "pg_restore",
            "--clean",
            "--if-exists",
            "--no-owner",
            "--no-privileges",
            "-d",
            dsn,
            path,
        ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    output = f"{note}{proc.stdout}\n{proc.stderr}".strip()
    return proc.returncode == 0, output[-4000:]


async def _fail_run(
    sessionmaker: async_sessionmaker[AsyncSession], run_id: int, message: str
) -> None:
    async with sessionmaker() as session:
        run = await session.get(ImportRun, run_id)
        if run is not None:
            run.status = ImportStatus.FAILED
            run.message = message
            run.finished_at = datetime.now(tz=UTC)
        await session.commit()


async def process_manual_import(import_run_id: int, file_path: str, filename: str) -> None:
    """Background task: restore an uploaded backup and update its ImportRun row."""
    sessionmaker = get_sessionmaker()
    try:
        fmt = detect_format(file_path)

        # Preflight: refuse incompatible major versions with an actionable message
        # instead of letting pg_restore fail cryptically partway through.
        incompatible = await run_in_threadpool(
            check_restore_compatibility,
            file_path,
            fmt is BackupFormat.PLAIN,
            get_settings().userdata_admin_dsn,
        )
        if incompatible:
            await _fail_run(sessionmaker, import_run_id, f"Version check failed: {incompatible}")
            return

        success, message = await run_in_threadpool(_restore, file_path, fmt)

        if success:
            await run_in_threadpool(ensure_readonly_role)

        async with sessionmaker() as session:
            run = await session.get(ImportRun, import_run_id)
            if run is not None:
                run.status = ImportStatus.SUCCESS if success else ImportStatus.FAILED
                run.message = message or (f"restored ({fmt})" if success else "restore failed")
                run.finished_at = datetime.now(tz=UTC)
            if success:
                await rebuild_snapshot(session)
            await session.commit()
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
