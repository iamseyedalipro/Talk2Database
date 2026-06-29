"""Manual backup uploads and import-run history (admin only)."""

from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile, status
from sqlalchemy import select

from app.config import ImportMode, get_settings
from app.deps import AdminUser, SessionDep
from app.importers.manual import process_manual_import
from app.models.import_run import ImportKind, ImportRun, ImportStatus
from app.schemas.imports import ImportRunOut, UploadAccepted

router = APIRouter(prefix="/imports", tags=["imports"])

_UPLOAD_DIR = Path("uploads")
_CHUNK = 1024 * 1024  # 1 MiB


@router.post("/upload", response_model=UploadAccepted, status_code=status.HTTP_202_ACCEPTED)
async def upload_backup(
    admin: AdminUser,
    session: SessionDep,
    background: BackgroundTasks,
    file: UploadFile = File(...),
) -> UploadAccepted:
    if get_settings().import_mode is not ImportMode.MANUAL:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Manual upload is disabled; this deployment uses scheduled sync.",
        )

    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = _UPLOAD_DIR / f"upload_{secrets.token_hex(8)}"

    size = 0
    with temp_path.open("wb") as out:
        while chunk := await file.read(_CHUNK):
            out.write(chunk)
            size += len(chunk)

    if size == 0:
        temp_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty."
        )

    run = ImportRun(
        kind=ImportKind.MANUAL,
        status=ImportStatus.RUNNING,
        filename=file.filename,
        bytes=size,
        triggered_by=admin.id,
    )
    session.add(run)
    await session.flush()
    run_id = run.id
    await session.commit()

    background.add_task(process_manual_import, run_id, str(temp_path), file.filename or "upload")
    return UploadAccepted(import_run_id=run_id, status=ImportStatus.RUNNING)


@router.get("", response_model=list[ImportRunOut])
async def list_imports(_: AdminUser, session: SessionDep) -> list[ImportRun]:
    result = await session.execute(
        select(ImportRun).order_by(ImportRun.started_at.desc()).limit(50)
    )
    return list(result.scalars().all())


@router.get("/{run_id}", response_model=ImportRunOut)
async def get_import(run_id: int, _: AdminUser, session: SessionDep) -> ImportRun:
    run = await session.get(ImportRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import run not found.")
    return run
