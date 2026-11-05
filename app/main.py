"""Точка входу: фабрика застосунку FastAPI."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import __version__
from app.config import Settings
from app.database import Base, make_engine, make_session_factory
from app.errors import too_large
from app.routers import auth, files
from app.services.storage import FileStorage

logger = logging.getLogger("app")

MULTIPART_OVERHEAD = 64 * 1024  # запас на межі multipart і службові поля


def create_app(settings: Settings | None = None) -> FastAPI:
    """Створює та налаштовує застосунок. Параметр дозволяє підставляти налаштування в тестах."""
    settings = settings or Settings.from_env()
    if settings.uses_default_secret:
        logger.warning("SECRET_KEY is not set: using an insecure development default.")

    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    storage = FileStorage(settings.storage_dir)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        engine.dispose()

    app = FastAPI(
        title="File Upload Service",
        description="Серверний застосунок для завантаження та обробки файлів (курсова робота).",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.storage = storage

    @app.middleware("http")
    async def guard_and_harden(request: Request, call_next):
        # Рання відмова за заголовком Content-Length, до того як тіло буде прочитане.
        if request.method == "POST" and request.url.path == "/files":
            length = request.headers.get("content-length")
            if length and length.isdigit() and int(length) > settings.max_upload_bytes + MULTIPART_OVERHEAD:
                exc = too_large(settings.max_upload_bytes)
                return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        return response

    @app.get("/health", tags=["service"])
    def health() -> dict[str, str]:
        """Перевірка працездатності сервісу."""
        return {"status": "ok", "version": __version__}

    app.include_router(auth.router)
    app.include_router(files.router)
    return app


