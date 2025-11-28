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
from app.core.observability import setup_observability
from app.api.v1.router import api_router
from app.services.auth_service import AuthService
from app.services.upload_service import UploadService

# Import metrics modules to register with Prometheus (Sprint 23)
from app.services import auth_metrics  # noqa: F401

# Инициализация логирования
setup_logging()
logger = get_logger(__name__)

# Инициализация OAuth 2.0 Client Credentials authentication
auth_service = AuthService(
    admin_module_url=settings.service_account.admin_module_url,
    client_id=settings.service_account.client_id,
    client_secret=settings.service_account.client_secret,
    timeout=settings.service_account.timeout
)

# Инициализация Upload Service с аутентификацией
upload_service = UploadService(auth_service=auth_service)


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
    await auth_service.close()
    logger.info("HTTP connections closed")


# Создание FastAPI application
app = FastAPI(
    title="ArtStore Ingester Module",
    description="High-performance file upload orchestration with saga coordination and circuit breaker",
    version=settings.app.version,
    lifespan=lifespan,
    docs_url="/docs" if settings.app.swagger_enabled else None,
    redoc_url="/redoc" if settings.app.swagger_enabled else None
)

# Логирование статуса Swagger
if settings.app.swagger_enabled:
    logger.info(
        "Swagger UI enabled",
        extra={
            "docs_url": "/docs",
            "redoc_url": "/redoc"
        }
    )
else:
    logger.info("Swagger UI disabled (production mode)")

# Настройка OpenTelemetry observability
setup_observability(
    app=app,
    service_name="artstore-ingester-module",
    service_version=settings.app.version,
    enable_tracing=True  # TODO: добавить в конфигурацию
)
logger.info("OpenTelemetry observability configured")

# CORS middleware (Sprint 16 Phase 1: Enhanced CORS security)
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
            "cors_origins": settings.cors.allow_origins,
            "cors_credentials": settings.cors.allow_credentials,
            "cors_max_age": settings.cors.max_age
        }
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
