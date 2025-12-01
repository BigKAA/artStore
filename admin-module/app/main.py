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
from app.core.redis import close_redis, check_redis_connection, service_discovery
from app.services.storage_element_publish_service import storage_element_publish_service
from app.core.logging_config import setup_logging, get_logger
from app.core.observability import setup_observability
from app.core.scheduler import init_scheduler, shutdown_scheduler
from app.db.init_db import create_initial_admin_user, create_initial_service_account
from app.api.v1.endpoints import health, auth, jwt_keys, admin_auth, admin_users, service_accounts, storage_elements
from app.middleware import RateLimitMiddleware, AuditMiddleware
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

        # Создание initial пользователей (если необходимо)
        async for db in get_db():
            try:
                # Создание initial admin user для Admin UI
                await create_initial_admin_user(settings, db)
                # Создание initial service account для OAuth 2.0 Client Credentials
                await create_initial_service_account(settings, db)
            finally:
                await db.close()
            break  # Получаем только одну сессию

        # Проверка подключений
        db_ok = await check_db_connection()
        redis_ok = await check_redis_connection()  # Async вызов для Redis

        if not db_ok:
            logger.error("Database connection failed!")
        if not redis_ok:
            logger.warning("Redis connection failed (non-critical)")

        # Инициализация Service Discovery (async)
        await service_discovery.initialize()

        # Публикация начальной конфигурации Storage Elements при startup
        # Используем тот же цикл db session
        async for db in get_db():
            try:
                await storage_element_publish_service.publish_startup(db)
                logger.info("Initial storage element config published to Redis")
            finally:
                await db.close()
            break  # Получаем только одну сессию

        # Инициализация APScheduler для background задач
        init_scheduler()
        logger.info("APScheduler initialized")

        # Запуск первичной проверки готовности сразу при старте
        # Это наполняет HealthStateService начальным состоянием до первого запроса к /health/ready
        # Используем async версию, т.к. мы уже внутри async event loop FastAPI
        from app.core.scheduler import readiness_health_check_async
        await readiness_health_check_async()

        logger.info("Application startup complete")

    except Exception as e:
        logger.error(f"Startup error: {e}")
        raise

    yield

    # Shutdown
    logger.info("Shutting down application")

    try:
        # Остановка APScheduler (с ожиданием завершения running jobs)
        shutdown_scheduler()
        logger.info("APScheduler shut down")

        await service_discovery.close()  # Async вызов
        await close_redis()  # Async вызов
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
    service_name=settings.monitoring.opentelemetry_service_name,
    service_version=settings.app_version,
    enable_tracing=settings.monitoring.opentelemetry_enabled,
    exporter_endpoint=settings.monitoring.opentelemetry_exporter_endpoint
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

# Rate Limiting middleware для Service Accounts
# Middleware создает свой синхронный Redis клиент (будет переделан на async в Фазе 5)
app.add_middleware(RateLimitMiddleware)
logger.info("Rate limiting middleware enabled")

# Audit Logging middleware для security compliance
app.add_middleware(AuditMiddleware)
logger.info("Audit logging middleware enabled")

# Подключаем роутеры
app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["authentication"])
app.include_router(admin_auth.router, prefix="/api/v1", tags=["admin-authentication"])
app.include_router(admin_users.router, prefix="/api/v1", tags=["admin-users-management"])
app.include_router(service_accounts.router, prefix="/api/v1", tags=["service-accounts-management"])
app.include_router(storage_elements.router, prefix="/api/v1", tags=["storage-elements-management"])
app.include_router(jwt_keys.router, prefix="/api/v1/jwt-keys", tags=["jwt-keys"])

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
