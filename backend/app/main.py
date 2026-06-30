"""FastAPI application: JSON API under ``/api`` plus the built React SPA."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.config import get_settings
from app.routers import (
    ask,
    auth,
    connections,
    execute,
    history,
    results,
    saved_queries,
    system,
    users,
)

_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend_dist"


def _build_api_router() -> APIRouter:
    api = APIRouter(prefix="/api")

    @api.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    api.include_router(auth.router)
    api.include_router(users.router)
    api.include_router(connections.router)
    api.include_router(ask.router)
    api.include_router(execute.router)
    api.include_router(history.router)
    api.include_router(saved_queries.router)
    api.include_router(results.router)
    api.include_router(system.router)
    return api


def _mount_spa(app: FastAPI) -> None:
    """Serve the built SPA, falling back to index.html for client-side routes."""
    if not _FRONTEND_DIR.is_dir():
        return

    assets_dir = _FRONTEND_DIR / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    index_file = _FRONTEND_DIR / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        if full_path.startswith("api"):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = _FRONTEND_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index_file)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Talk2Database",
        version=__version__,
        description="Ask questions in plain language; get previewable, read-only SQL.",
    )

    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(_build_api_router())
    _mount_spa(app)
    return app


app = create_app()
