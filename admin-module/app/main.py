"""
Admin Module главное приложение FastAPI.
Центральный модуль аутентификации и управления системой ArtStore.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from datetime import datetime

from app.core.config import settings
from app.core.database import init_db, close_db, check_db_connection, get_db
from app.core.redis import close_redis, check_redis_connection, service_discovery, redis_client
from app.core.logging_config import setup_logging, get_logger
from app.core.observability import setup_observability
from app.db.init_db import create_initial_admin
from app.api.v1.endpoints import health, auth
from app.middleware import RateLimitMiddleware
from prometheus_client import make_asgi_app

# Настройка логирования (JSON формат по умолчанию)
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager для инициализации и завершения приложения.
    Вызывается при startup и shutdown.
    """
    # Startup
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")

    try:
        # Инициализация базы данных
        await init_db()
        logger.info("Database initialized")

        # Создание initial admin пользователя (если необходимо)
        async for db in get_db():
            try:
                await create_initial_admin(settings, db)
            finally:
                await db.close()
            break  # Получаем только одну сессию

        # Проверка подключений
        db_ok = await check_db_connection()
        redis_ok = check_redis_connection()  # Синхронный вызов для Redis

        if not db_ok:
            logger.error("Database connection failed!")
        if not redis_ok:
            logger.warning("Redis connection failed (non-critical)")

        # Инициализация Service Discovery
        service_discovery.initialize()  # Синхронный вызов

        logger.info("Application startup complete")

    except Exception as e:
        logger.error(f"Startup error: {e}")
        raise

    yield

    # Shutdown
    logger.info("Shutting down application")

    try:
        service_discovery.close()  # Синхронный вызов
        close_redis()  # Синхронный вызов
        await close_db()
        logger.info("Application shutdown complete")

    except Exception as e:
        logger.error(f"Shutdown error: {e}")


# Создаем FastAPI приложение
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Центральный модуль аутентификации и управления системой ArtStore",
    debug=settings.debug,
    lifespan=lifespan,
)

# Настройка OpenTelemetry observability
setup_observability(
    app=app,
    service_name=settings.monitoring.opentelemetry_service_name,
    service_version=settings.app_version,
    enable_tracing=settings.monitoring.opentelemetry_enabled,
    exporter_endpoint=settings.monitoring.opentelemetry_exporter_endpoint
)
logger.info("OpenTelemetry observability configured")

# CORS middleware
if settings.cors.enabled:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors.allow_origins,
        allow_credentials=settings.cors.allow_credentials,
        allow_methods=settings.cors.allow_methods,
        allow_headers=settings.cors.allow_headers,
    )
    logger.info("CORS enabled")

# Rate Limiting middleware для Service Accounts
app.add_middleware(RateLimitMiddleware, redis_client=redis_client)
logger.info("Rate limiting middleware enabled")

# Подключаем роутеры
app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["authentication"])

# Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
logger.info("Prometheus metrics endpoint mounted at /metrics")

# TODO: Добавить роутеры для:
# - /api/v1/users (управление пользователями)
# - /api/v1/storage-elements (управление storage elements)
# - /api/v1/transactions (Saga оркестрация)
# - /api/v1/batch (batch операции)


@app.get("/", tags=["root"])
async def root():
    """
    Root endpoint.
    Возвращает информацию о приложении.
    """
    return {
        "application": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "timestamp": datetime.utcnow().isoformat(),
        "docs_url": "/docs",
        "health_check": "/health/live"
    }


@app.exception_handler(404)
async def not_found_handler(request, exc):
    """Handler для 404 ошибок."""
    return JSONResponse(
        status_code=404,
        content={
            "detail": "Resource not found",
            "path": str(request.url.path)
        }
    )


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    """Handler для 500 ошибок."""
    logger.error(f"Internal server error: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error": str(exc) if settings.debug else "An error occurred"
        }
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.logging.level.lower()
    )
