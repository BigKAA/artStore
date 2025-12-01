"""
Storage Element - FastAPI Application Entry Point.

Отказоустойчивое физическое хранение файлов с кешированием метаданных.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import HTTPException
from prometheus_client import make_asgi_app

from app.core.config import settings, StorageType
from app.core.logging import setup_logging, get_logger
from app.core.observability import setup_observability
from app.db.session import init_db, close_db

# Sprint 14: Import capacity metrics для регистрации с Prometheus
from app.core import capacity_metrics  # noqa: F401

# Инициализация логирования
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle events для FastAPI application.

    Startup:
    - Инициализация базы данных
    - Инициализация Redis клиента
    - Запуск HealthReporter для публикации статуса в Redis
    - Проверка конфигурации
    - Загрузка текущего режима из БД

    Shutdown:
    - Остановка HealthReporter
    - Закрытие Redis соединений
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
            "storage_type": settings.storage.type.value,
            "element_id": settings.storage.element_id,
        }
    )

    # Инициализация базы данных
    await init_db()
    logger.info("Database initialized")

    # Инициализация Redis и HealthReporter (Sprint 14)
    await _init_redis_and_health_reporter()

    # Проверка доступности хранилища при старте (graceful degradation)
    await _check_storage_on_startup()

    # TODO: Проверка storage mode из БД vs config
    # TODO: Инициализация master election если edit/rw режим

    yield

    # Shutdown
    logger.info("Shutting down Storage Element")

    # Остановка HealthReporter и закрытие Redis (Sprint 14)
    await _shutdown_redis_and_health_reporter()

    await close_db()
    logger.info("Database connections closed")


async def _init_redis_and_health_reporter():
    """
    Инициализация Redis клиента и запуск HealthReporter.

    Sprint 14: Redis Storage Registry & Adaptive Capacity.

    Graceful degradation - при ошибке Redis сервис продолжает работу,
    но не публикует статус в registry (локальная работа).
    """
    from app.core.redis import get_redis_client, close_redis_client
    from app.services.health_reporter import init_health_reporter

    try:
        # Инициализация Redis клиента
        redis_client = await get_redis_client()
        logger.info(
            "Redis client connected",
            extra={
                "host": settings.redis.host,
                "port": settings.redis.port,
            }
        )

        # Запуск HealthReporter для публикации статуса
        await init_health_reporter(redis_client)
        logger.info(
            "HealthReporter started",
            extra={
                "element_id": settings.storage.element_id,
                "interval": settings.storage.health_report_interval,
                "ttl": settings.storage.health_report_ttl,
            }
        )

    except Exception as e:
        # Graceful degradation - продолжаем работу без Redis
        logger.warning(
            "Failed to initialize Redis/HealthReporter - running in standalone mode",
            extra={
                "error": str(e),
                "element_id": settings.storage.element_id,
                "action": "SE will work locally but won't be discoverable via Redis registry"
            }
        )


async def _shutdown_redis_and_health_reporter():
    """
    Остановка HealthReporter и закрытие Redis при shutdown.
    """
    from app.core.redis import close_redis_client
    from app.services.health_reporter import stop_health_reporter

    try:
        # Остановка HealthReporter (удаляет SE из registry)
        await stop_health_reporter()
        logger.info("HealthReporter stopped")

        # Закрытие Redis соединения
        await close_redis_client()
        logger.info("Redis client closed")

    except Exception as e:
        logger.warning(
            f"Error during Redis/HealthReporter shutdown: {e}",
            extra={"error": str(e)}
        )


async def _check_storage_on_startup():
    """
    Проверка доступности хранилища при старте приложения.

    Graceful degradation - логирует ошибки, но НЕ блокирует запуск.
    Readiness probe будет возвращать 503 до исправления проблемы.
    """
    if settings.storage.type == StorageType.S3:
        await _check_s3_storage_on_startup()
    else:
        await _check_local_storage_on_startup()


async def _check_s3_storage_on_startup():
    """
    Проверка доступности S3 хранилища при старте.

    Проверяет:
    1. Существование и доступность бакета
    2. Доступность app_folder (попытка создать если не существует)

    При ошибках логирует warning/error, но не прерывает запуск.
    """
    from app.services.storage_service import S3StorageService

    s3_service = S3StorageService()

    # Проверка бакета
    bucket_exists = await s3_service.check_bucket_exists()

    if not bucket_exists:
        logger.error(
            "S3 bucket not accessible on startup - service will be unhealthy",
            extra={
                "bucket_name": settings.storage.s3.bucket_name,
                "endpoint_url": settings.storage.s3.endpoint_url,
                "action": "Readiness probe will return 503 until bucket is available"
            }
        )
        return

    logger.info(
        "S3 bucket accessible",
        extra={"bucket_name": settings.storage.s3.bucket_name}
    )

    # Проверка/создание app_folder
    folder_ok = await s3_service.check_app_folder_exists()

    if not folder_ok:
        logger.error(
            "Failed to access/create app_folder in S3 - service will be unhealthy",
            extra={
                "bucket_name": settings.storage.s3.bucket_name,
                "app_folder": settings.storage.s3.app_folder,
                "action": "Administrator should create directory manually"
            }
        )
        return

    logger.info(
        "S3 storage check passed",
        extra={
            "bucket_name": settings.storage.s3.bucket_name,
            "app_folder": settings.storage.s3.app_folder
        }
    )


async def _check_local_storage_on_startup():
    """
    Проверка доступности локального хранилища при старте.

    Проверяет:
    1. Существование директории хранилища
    2. Возможность записи в директорию

    При ошибках логирует warning/error, но не прерывает запуск.
    """
    from pathlib import Path

    storage_path = Path(settings.storage.local.base_path)

    try:
        # Создаем директорию если не существует
        storage_path.mkdir(parents=True, exist_ok=True)

        # Проверяем возможность записи
        test_file = storage_path / ".startup_check"
        test_file.write_text("ok")
        test_file.unlink()

        logger.info(
            "Local storage check passed",
            extra={"path": str(storage_path)}
        )

    except Exception as e:
        logger.error(
            "Local storage not accessible on startup - service will be unhealthy",
            extra={
                "path": str(storage_path),
                "error": str(e),
                "action": "Readiness probe will return 503 until storage is available"
            }
        )


# Создание FastAPI application
app = FastAPI(
    title="ArtStore Storage Element",
    description="Distributed file storage with metadata caching and high availability",
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
    service_name="artstore-storage-element",
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

# Prometheus metrics endpoint
if settings.metrics.enabled:
    metrics_app = make_asgi_app()
    app.mount(settings.metrics.path, metrics_app)


# Exception handler для замены 403 на 401 для authentication errors
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """
    Глобальный exception handler для HTTPException.

    Заменяет 403 Forbidden на 401 Unauthorized для ошибок аутентификации.
    FastAPI HTTPBearer по умолчанию возвращает 403, но правильный статус - 401.
    """
    if exc.status_code == status.HTTP_403_FORBIDDEN and exc.detail == "Not authenticated":
        # Заменяем 403 на 401 для authentication errors
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": exc.detail},
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Для остальных HTTPException возвращаем как есть
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers
    )


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
        dict: Статус liveness с полями status, timestamp, checks
    """
    from datetime import datetime, timezone
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": {
            "process": "running"
        }
    }


@app.get(settings.health.readiness_path)
async def health_ready():
    """
    Readiness probe.

    Возвращает HTTP 200 OK если сервис готов принимать запросы.
    Проверяет:
    - Доступность хранилища (S3 bucket + app_folder или Local filesystem)

    Returns:
        dict: Статус readiness с деталями проверок
        HTTP 200 если всё OK
        HTTP 503 если сервис не готов
    """
    from datetime import datetime, timezone
    from fastapi.responses import JSONResponse

    checks = {}
    all_ok = True

    # Проверка хранилища в зависимости от типа
    if settings.storage.type == StorageType.S3:
        storage_ok, storage_checks = await _check_s3_storage_readiness()
    else:
        storage_ok, storage_checks = await _check_local_storage_readiness()

    checks.update(storage_checks)
    if not storage_ok:
        all_ok = False

    # Метаданные о конфигурации
    checks["storage_type"] = settings.storage.type.value
    checks["storage_mode"] = settings.app.mode.value

    response_data = {
        "status": "ready" if all_ok else "not_ready",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks
    }

    if all_ok:
        return response_data
    else:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=response_data
        )


async def _check_s3_storage_readiness() -> tuple[bool, dict]:
    """
    Проверка доступности S3 хранилища для readiness probe.

    Returns:
        tuple[bool, dict]: (успех, детали проверок)
    """
    from app.services.storage_service import S3StorageService

    s3_service = S3StorageService()
    health_status = await s3_service.get_health_status()

    checks = {
        "s3_bucket": "accessible" if health_status["bucket_accessible"] else "not_accessible",
        "s3_app_folder": "accessible" if health_status["app_folder_accessible"] else "not_accessible",
        "s3_endpoint": health_status["endpoint_url"],
        "s3_bucket_name": health_status["bucket_name"],
        "s3_app_folder_name": health_status["app_folder"]
    }

    if health_status["error_message"]:
        checks["s3_error"] = health_status["error_message"]

    is_ok = health_status["bucket_accessible"] and health_status["app_folder_accessible"]

    return is_ok, checks


async def _check_local_storage_readiness() -> tuple[bool, dict]:
    """
    Проверка доступности локального хранилища для readiness probe.

    Returns:
        tuple[bool, dict]: (успех, детали проверок)
    """
    from pathlib import Path

    checks = {}
    storage_path = Path(settings.storage.local.base_path)

    try:
        # Проверяем существование и возможность записи
        storage_path.mkdir(parents=True, exist_ok=True)

        test_file = storage_path / ".health_check"
        test_file.write_text("ok")
        test_file.unlink()

        checks["storage_directory"] = "accessible"
        checks["storage_path"] = str(storage_path)
        return True, checks

    except Exception as e:
        logger.warning(
            "Local storage readiness check failed",
            extra={"path": str(storage_path), "error": str(e)}
        )
        checks["storage_directory"] = "not_accessible"
        checks["storage_path"] = str(storage_path)
        checks["storage_error"] = str(e)
        return False, checks


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
