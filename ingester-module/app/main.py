"""
Ingester Module - FastAPI Application Entry Point.

Высокопроизводительное отказоустойчивое добавление и управление файлами.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from app.core.config import settings
from app.core.logging import setup_logging, get_logger
from app.api.v1.router import api_router
from app.services.upload_service import upload_service

# Инициализация логирования
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle events для FastAPI application.

    Startup:
    - Инициализация HTTP клиента для Storage Element
    - Проверка конфигурации
    - Загрузка публичного ключа для JWT

    Shutdown:
    - Закрытие HTTP connections
    - Cleanup resources
    """
    # Startup
    logger.info(
        "Starting Ingester Module",
        extra={
            "app_name": settings.app.name,
            "version": settings.app.version,
            "storage_element_url": settings.storage_element.base_url
        }
    )

    # TODO: Инициализация Redis client для Service Discovery
    # TODO: Инициализация Circuit Breaker
    # TODO: Проверка доступности Storage Element

    yield

    # Shutdown
    logger.info("Shutting down Ingester Module")
    await upload_service.close()
    logger.info("HTTP connections closed")


# Создание FastAPI application
app = FastAPI(
    title="ArtStore Ingester Module",
    description="High-performance file upload orchestration with saga coordination and circuit breaker",
    version=settings.app.version,
    lifespan=lifespan,
    docs_url="/docs" if settings.app.debug else None,
    redoc_url="/redoc" if settings.app.debug else None
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Настроить для production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключение API router
app.include_router(api_router, prefix="/api/v1")

# Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


@app.get("/", include_in_schema=False)
async def root():
    """Root endpoint с информацией о сервисе."""
    return {
        "service": settings.app.name,
        "version": settings.app.version,
        "status": "running",
        "docs": "/docs" if settings.app.debug else "disabled in production"
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.app.host,
        port=settings.app.port,
        reload=settings.app.debug,
        log_level=settings.logging.level.value.lower()
    )
