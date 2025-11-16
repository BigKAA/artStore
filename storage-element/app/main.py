"""
Storage Element - FastAPI Application Entry Point.

Отказоустойчивое физическое хранение файлов с кешированием метаданных.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from app.core.config import settings
from app.core.logging import setup_logging, get_logger
from app.core.observability import setup_observability
from app.db.session import init_db, close_db

# Инициализация логирования
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle events для FastAPI application.

    Startup:
    - Инициализация базы данных
    - Проверка конфигурации
    - Загрузка текущего режима из БД

    Shutdown:
    - Закрытие соединений с БД
    - Cleanup resources
    """
    # Startup
    logger.info(
        "Starting Storage Element",
        extra={
            "app_name": settings.app.name,
            "version": settings.app.version,
            "mode": settings.app.mode.value,
            "storage_type": settings.storage.type.value
        }
    )

    # Инициализация базы данных
    await init_db()
    logger.info("Database initialized")

    # TODO: Проверка storage mode из БД vs config
    # TODO: Инициализация master election если edit/rw режим
    # TODO: Проверка доступности хранилища

    yield

    # Shutdown
    logger.info("Shutting down Storage Element")
    await close_db()
    logger.info("Database connections closed")


# Создание FastAPI application
app = FastAPI(
    title="ArtStore Storage Element",
    description="Distributed file storage with metadata caching and high availability",
    version=settings.app.version,
    lifespan=lifespan,
    docs_url="/docs" if settings.app.debug else None,
    redoc_url="/redoc" if settings.app.debug else None
)

# Настройка OpenTelemetry observability
setup_observability(
    app=app,
    service_name="artstore-storage-element",
    service_version=settings.app.version,
    enable_tracing=True  # TODO: добавить в конфигурацию
)
logger.info("OpenTelemetry observability configured")

# CORS middleware (защита от CSRF attacks)
if settings.cors.enabled:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors.allow_origins,
        allow_credentials=settings.cors.allow_credentials,
        allow_methods=settings.cors.allow_methods,
        allow_headers=settings.cors.allow_headers,
        expose_headers=settings.cors.expose_headers,
        max_age=settings.cors.max_age,
    )
    logger.info(
        "CORS enabled",
        extra={
            "allowed_origins": settings.cors.allow_origins,
            "allow_credentials": settings.cors.allow_credentials,
        }
    )

# Prometheus metrics endpoint
if settings.metrics.enabled:
    metrics_app = make_asgi_app()
    app.mount(settings.metrics.path, metrics_app)


@app.get("/")
async def root():
    """
    Корневой endpoint с информацией о сервисе.

    Returns:
        dict: Информация о Storage Element
    """
    return {
        "service": "ArtStore Storage Element",
        "version": settings.app.version,
        "mode": settings.app.mode.value,
        "storage_type": settings.storage.type.value,
        "status": "operational"
    }


@app.get(settings.health.liveness_path)
async def health_live():
    """
    Liveness probe.

    Возвращает HTTP 200 OK если сервис работает.

    Returns:
        dict: Статус liveness
    """
    return {"status": "alive"}


@app.get(settings.health.readiness_path)
async def health_ready():
    """
    Readiness probe.

    Возвращает HTTP 200 OK если сервис готов принимать запросы.
    Проверяет подключение к базе данных.

    Returns:
        dict: Статус readiness
    """
    # TODO: Проверить подключение к БД
    # TODO: Проверить доступность хранилища
    return {"status": "ready"}


# Подключение API v1 router
from app.api.v1.router import router as api_v1_router

app.include_router(api_v1_router, prefix="/api/v1")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.server.reload,
        workers=settings.server.workers,
        log_config=None  # Используем нашу систему логирования
    )
