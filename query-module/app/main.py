"""
Query Module - FastAPI Application.

Entry point для Query Module с:
- Lifespan management (database, cache initialization)
- CORS middleware
- JWT authentication
- Health checks
- Prometheus metrics
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from app.core.config import settings
from app.core.logging import setup_logging
from app.core.observability import setup_observability
from app.core.redis import close_redis
from app.db.database import init_db, close_db
from app.services.cache_service import cache_service
from app.services.download_service import download_service
from app.services.event_subscriber import event_subscriber

# Настройка логирования
setup_logging(level=settings.log_level, log_format=settings.log_format)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager для инициализации и cleanup ресурсов.

    Выполняется:
    - При старте: инициализация БД, cache, HTTP clients
    - При остановке: закрытие соединений, cleanup ресурсов
    """
    # Startup
    logger.info(
        "Starting Query Module",
        extra={
            "version": "1.0.0",
            "environment": "development" if settings.debug else "production"
        }
    )

    try:
        # Инициализация database
        await init_db()
        logger.info("Database initialized")

        # Cache уже инициализирован (singleton)
        logger.info("Cache service initialized")

        # HTTP client для download service инициализируется lazy

        # Запуск JWT key file watcher для hot-reload
        from app.core.jwt_key_manager import get_jwt_key_manager
        jwt_key_manager = get_jwt_key_manager()
        jwt_key_manager.start_watching()
        logger.info("JWT key file watcher started for hot-reload support")

        # PHASE 2: Запуск Event Subscriber для Redis Pub/Sub синхронизации
        await event_subscriber.initialize()
        logger.info("Event subscriber initialized for cache sync")

    except Exception as e:
        logger.error(
            "Failed to initialize Query Module",
            extra={"error": str(e)}
        )
        raise

    yield

    # Shutdown
    logger.info("Shutting down Query Module")

    try:
        # Закрытие database connections
        await close_db()
        logger.info("Database closed")

        # Закрытие cache connections
        cache_service.close()
        logger.info("Cache service closed")

        # Закрытие HTTP client
        await download_service.close()
        logger.info("Download service closed")

        # PHASE 2: Закрытие Event Subscriber
        await event_subscriber.close()
        logger.info("Event subscriber closed")

        # Закрытие Redis connections
        await close_redis()
        logger.info("Redis connections closed")

    except Exception as e:
        logger.warning(
            "Error during shutdown",
            extra={"error": str(e)}
        )


# FastAPI application
app = FastAPI(
    title="ArtStore Query Module",
    description="File search and download service with Full-Text Search and multi-level caching",
    version="1.0.0",
    debug=settings.debug,
    lifespan=lifespan,
    docs_url="/docs" if settings.swagger_enabled else None,
    redoc_url="/redoc" if settings.swagger_enabled else None
)

# Логирование статуса Swagger
if settings.swagger_enabled:
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
    service_name="artstore-query-module",
    service_version="1.0.0",
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
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# API routers
from app.api import search, download

app.include_router(search.router)
app.include_router(download.router)


# Health check endpoints
@app.get("/health/live", tags=["Health"])
async def liveness_check():
    """
    Liveness check для Kubernetes.

    Returns:
        dict: Статус приложения (всегда успешный если сервер запущен)
    """
    return {"status": "alive"}


@app.get("/health/ready", tags=["Health"])
async def readiness_check():
    """
    Readiness check для Kubernetes.

    Проверяет доступность критических dependencies:
    - PostgreSQL database
    - Redis cache (опционально)

    Returns:
        dict: Статус готовности с деталями
    """
    from app.db.database import check_db_health

    health_status = {
        "status": "ready",
        "database": "unknown",
        "cache": "unknown"
    }

    # Проверка database
    try:
        db_healthy = await check_db_health()
        health_status["database"] = "healthy" if db_healthy else "unhealthy"
    except Exception as e:
        health_status["database"] = "unhealthy"
        health_status["status"] = "not_ready"
        logger.error(
            "Database health check failed",
            extra={"error": str(e)}
        )

    # Проверка Redis cache (non-critical)
    try:
        if cache_service.redis_cache:
            redis_healthy = cache_service.redis_cache.is_available()
            health_status["cache"] = "healthy" if redis_healthy else "degraded"
        else:
            health_status["cache"] = "disabled"
    except Exception as e:
        health_status["cache"] = "degraded"
        logger.warning(
            "Cache health check failed",
            extra={"error": str(e)}
        )

    # Определение итогового статуса
    if health_status["database"] == "unhealthy":
        health_status["status"] = "not_ready"

    return health_status


# Root endpoint
@app.get("/", tags=["Root"])
async def root():
    """
    Root endpoint с информацией о сервисе.

    Returns:
        dict: Информация о Query Module
    """
    return {
        "service": "ArtStore Query Module",
        "version": "1.0.0",
        "description": "File search and download service",
        "features": [
            "PostgreSQL Full-Text Search",
            "Multi-level caching (Local + Redis)",
            "Resumable downloads",
            "JWT authentication"
        ],
        "endpoints": {
            "health": "/health/live, /health/ready",
            "metrics": "/metrics",
            "docs": "/docs",
            "search": "/api/search (coming soon)",
            "download": "/api/download (coming soon)"
        }
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )
