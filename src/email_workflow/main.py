from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from email_workflow.api.health import router as health_router
from email_workflow.core.catalogs import validate_versioned_configs
from email_workflow.core.config import Settings, get_settings
from email_workflow.core.errors import AppError, register_error_handlers
from email_workflow.core.logging import configure_logging
from email_workflow.core.middleware import request_id_middleware


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or get_settings()
    configure_logging(active_settings.app_log_level)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        validate_versioned_configs(active_settings.config_dir)
        active_settings.data_dir.mkdir(parents=True, exist_ok=True)
        yield

    app = FastAPI(title=active_settings.app_name, version="0.1.0", lifespan=lifespan)
    app.middleware("http")(request_id_middleware)
    register_error_handlers(app)
    app.include_router(health_router, prefix="/api/v1")

    frontend_dir = active_settings.frontend_dist_dir
    assets_dir = frontend_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
    index_file = frontend_dir / "index.html"
    if index_file.is_file():
        register_spa_fallback(app, index_file)
    return app


def register_spa_fallback(app: FastAPI, index_file: Path) -> None:
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        if full_path == "api" or full_path.startswith("api/"):
            raise AppError(code="not_found", message="资源不存在", status_code=404)
        return FileResponse(index_file)


app = create_app()
