"""
Ingester Module - FastAPI Application Entry Point.

Высокопроизводительное отказоустойчивое добавление и управление файлами.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app
from app.core.config import settings
from app.core.logging import setup_logging, get_logger
from app.core.observability import setup_observability
from app.core.exceptions import NoAvailableStorageException
from app.api.v1.router import api_router
from app.services.auth_service import AuthService
from app.services.upload_service import UploadService
from app.services.storage_selector import init_storage_selector, close_storage_selector
from app.services.admin_client import init_admin_client, close_admin_client
from app.core.redis import get_redis_client, close_redis_client
# Sprint 15: FinalizeService для Two-Phase Commit
from app.services.finalize_service import FinalizeService, set_finalize_service
# Sprint 17: AdaptiveCapacityMonitor для geo-distributed SE
from app.services.capacity_monitor import (
    init_capacity_monitor,
    close_capacity_monitor,
    CapacityMonitorConfig,
)

# Import metrics modules to register with Prometheus
from app.services import auth_metrics  # noqa: F401
from app.core import metrics as ingester_metrics  # noqa: F401  # Sprint 17: Storage Selection & Finalize metrics

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

# Sprint 15: Инициализация FinalizeService для Two-Phase Commit
finalize_service = FinalizeService(auth_service=auth_service)


async def _fetch_storage_endpoints_from_admin(admin_client) -> tuple[dict[str, str], dict[str, int]]:
    """
    Получение endpoints и priorities SE из Admin Module.

    Sprint 18 Phase 3: Интеграция с Admin Module для инициализации endpoints.

    Args:
        admin_client: Инициализированный AdminClient

    Returns:
        tuple: (endpoints dict {se_id: endpoint_url}, priorities dict {se_id: priority})
    """
    endpoints: dict[str, str] = {}
    priorities: dict[str, int] = {}

    try:
        # Получаем все доступные SE (edit + rw режимы)
        storage_elements = await admin_client.get_available_storage_elements()

        for se in storage_elements:
            endpoints[se.element_id] = se.endpoint
            priorities[se.element_id] = se.priority

        logger.info(
            "Fetched SE endpoints from Admin Module",
            extra={
                "count": len(endpoints),
                "se_ids": list(endpoints.keys()),
            }
        )

    except Exception as e:
        logger.warning(
            "Failed to fetch SE endpoints from Admin Module",
            extra={"error": str(e)}
        )

    return endpoints, priorities


async def _fetch_storage_endpoints_from_redis(redis_client) -> tuple[dict[str, str], dict[str, int]]:
    """
    Получение endpoints и priorities SE из Redis Service Discovery.

    Sprint 20: Читает данные из ключа artstore:storage_elements,
    куда Admin Module публикует конфигурацию Storage Elements.

    Формат данных в Redis (JSON):
    {
        "version": 1,
        "timestamp": "...",
        "count": N,
        "storage_elements": [
            {"element_id": "se-01", "api_url": "http://...", "priority": 100, "mode": "edit", ...},
            ...
        ]
    }

    Args:
        redis_client: Async Redis client

    Returns:
        tuple: (endpoints dict {se_id: endpoint_url}, priorities dict {se_id: priority})
    """
    import json

    endpoints: dict[str, str] = {}
    priorities: dict[str, int] = {}

    # Ключ, куда Admin Module публикует конфигурацию SE
    # Соответствует settings.service_discovery.storage_element_config_key в Admin Module
    redis_key = "artstore:storage_elements"

    try:
        # Читаем JSON конфигурацию из Redis
        config_json = await redis_client.get(redis_key)

        if not config_json:
            logger.debug(
                "No SE config found in Redis",
                extra={"redis_key": redis_key}
            )
            return endpoints, priorities

        # Парсим JSON
        config = json.loads(config_json)
        storage_elements = config.get("storage_elements", [])

        for se in storage_elements:
            element_id = se.get("element_id")
            api_url = se.get("api_url")
            priority = se.get("priority", 100)
            mode = se.get("mode")
            is_available = se.get("is_available", True)
            is_writable = se.get("is_writable", False)

            # Фильтруем только writable SE (edit, rw) которые доступны
            if not element_id or not api_url:
                continue

            if not is_available:
                continue

            # Включаем только SE с режимами edit/rw
            if mode not in ("edit", "rw"):
                continue

            endpoints[element_id] = api_url
            priorities[element_id] = priority

        logger.info(
            "Fetched SE endpoints from Redis Service Discovery",
            extra={
                "count": len(endpoints),
                "se_ids": list(endpoints.keys()),
                "config_version": config.get("version"),
                "redis_key": redis_key,
            }
        )

    except json.JSONDecodeError as e:
        logger.warning(
            "Failed to parse SE config from Redis - invalid JSON",
            extra={"error": str(e), "redis_key": redis_key}
        )
    except Exception as e:
        logger.warning(
            "Failed to fetch SE endpoints from Redis",
            extra={"error": str(e), "redis_key": redis_key}
        )

    return endpoints, priorities


async def _periodic_se_config_reload(
    capacity_monitor,
    redis_client,
    admin_client,
    interval: int = 60
) -> None:
    """
    Background task для периодического обновления SE конфигурации.

    Sprint 21: Читает данные из Redis (или Admin Module fallback) каждые `interval` секунд
    и обновляет AdaptiveCapacityMonitor через reload_storage_endpoints().

    Источники данных (fallback chain):
    1. Redis: artstore:storage_elements (primary)
    2. Admin Module API: /api/v1/internal/storage-elements/available (fallback)

    Graceful degradation:
    - Redis недоступен → Admin Module API
    - Оба недоступны → используется last known config
    - Ошибки логируются, но task продолжает работать

    Args:
        capacity_monitor: AdaptiveCapacityMonitor instance для обновления
        redis_client: Async Redis client для чтения конфигурации
        admin_client: Admin Module HTTP client (fallback source)
        interval: Интервал обновления в секундах (default: 60)
    """
    import asyncio
    import time

    logger.info(
        "SE config reload task started",
        extra={
            "interval_seconds": interval,
            "reload_enabled": True,
        }
    )

    while True:
        try:
            # Ждём интервал перед следующим обновлением
            await asyncio.sleep(interval)

            reload_start = time.perf_counter()
            endpoints: dict[str, str] = {}
            priorities: dict[str, int] = {}
            source = "unknown"

            # Попытка 1: Redis (primary source)
            if redis_client:
                try:
                    endpoints, priorities = await _fetch_storage_endpoints_from_redis(redis_client)
                    if endpoints:
                        source = "redis"
                except Exception as e:
                    logger.warning(
                        "Failed to fetch SE from Redis",
                        extra={"error": str(e)}
                    )

            # Попытка 2: Admin Module API (fallback)
            if not endpoints and admin_client:
                try:
                    endpoints, priorities = await _fetch_storage_endpoints_from_admin(admin_client)
                    if endpoints:
                        source = "admin_module"
                except Exception as e:
                    logger.warning(
                        "Failed to fetch SE from Admin Module",
                        extra={"error": str(e)}
                    )

            # Применяем обновления если есть данные
            if endpoints and capacity_monitor:
                await capacity_monitor.reload_storage_endpoints(endpoints, priorities)

                reload_duration = time.perf_counter() - reload_start

                # Метрики
                from app.core.metrics import (
                    record_se_config_reload,
                    record_se_config_reload_duration,
                )
                record_se_config_reload(source, "success")
                record_se_config_reload_duration(source, reload_duration)

                logger.debug(
                    "SE config reload completed",
                    extra={
                        "source": source,
                        "se_count": len(endpoints),
                        "duration_ms": round(reload_duration * 1000, 2),
                    }
                )
            else:
                # Нет данных от источников
                logger.warning(
                    "No SE endpoints available from any source",
                    extra={
                        "redis_available": redis_client is not None,
                        "admin_available": admin_client is not None,
                    }
                )

                # Метрики
                from app.core.metrics import record_se_config_reload
                record_se_config_reload("none", "failed")

        except asyncio.CancelledError:
            logger.info("SE config reload task cancelled")
            break
        except Exception as e:
            logger.error(
                "SE config reload task error",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                }
            )

            # Метрики
            from app.core.metrics import record_se_config_reload
            record_se_config_reload("unknown", "failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle events для FastAPI application.

    Startup:
    - Инициализация HTTP клиента для Storage Element
    - Инициализация Redis client для Storage Registry
    - Инициализация Admin Client для fallback
    - Инициализация StorageSelector
    - Проверка конфигурации
    - Загрузка публичного ключа для JWT
    - Запуск JWT key file watcher для hot-reload (Sprint: JWT Hot-Reload)

    Shutdown:
    - Закрытие HTTP connections
    - Cleanup resources
    """
    # Startup
    # Sprint 16: Удалён storage_element_url из логирования (Service Discovery обязателен)
    logger.info(
        "Starting Ingester Module",
        extra={
            "app_name": settings.app.name,
            "version": settings.app.version,
            "service_discovery": "redis+admin_module",
            "redis_url": f"{settings.redis.host}:{settings.redis.port}",
            "admin_module_url": settings.auth.admin_module_url
        }
    )

    # Sprint 14: Инициализация Redis и StorageSelector
    redis_client = None
    admin_client = None

    try:
        # Инициализация Redis client для Storage Registry
        redis_client = await get_redis_client()
        logger.info(
            "Redis client connected",
            extra={
                "host": settings.redis.host,
                "port": settings.redis.port,
            }
        )
    except Exception as e:
        # Graceful degradation - продолжаем работу без Redis
        logger.warning(
            "Failed to initialize Redis - running in fallback mode",
            extra={"error": str(e)}
        )

    try:
        # Инициализация Admin Client для fallback
        admin_client = await init_admin_client()
        logger.info("Admin Module client initialized")
    except Exception as e:
        # Graceful degradation - продолжаем без Admin fallback
        logger.warning(
            "Failed to initialize Admin client - fallback disabled",
            extra={"error": str(e)}
        )

    # Инициализация StorageSelector с Redis и Admin clients
    storage_selector = await init_storage_selector(
        redis_client=redis_client,
        admin_client=admin_client
    )
    logger.info("StorageSelector initialized")

    # Передаём storage_selector в upload_service
    upload_service.set_storage_selector(storage_selector)

    # Sprint 15: Настройка FinalizeService
    finalize_service.set_storage_selector(storage_selector)
    set_finalize_service(finalize_service)
    logger.info("FinalizeService initialized")

    # Sprint 17: Инициализация AdaptiveCapacityMonitor (если включен)
    capacity_monitor = None
    storage_priorities: dict[str, int] = {}  # Sprint 18 Phase 3: Priorities для sorted set

    if settings.capacity_monitor.enabled and redis_client:
        try:
            # Sprint 18 Phase 3: Получаем endpoints SE с fallback chain
            # 1. Пробуем Admin Module
            # 2. Fallback на Redis PUSH модель
            storage_endpoints: dict[str, str] = {}

            if admin_client:
                storage_endpoints, storage_priorities = await _fetch_storage_endpoints_from_admin(admin_client)

            if not storage_endpoints and redis_client:
                # Fallback на Redis PUSH модель
                storage_endpoints, storage_priorities = await _fetch_storage_endpoints_from_redis(redis_client)

            if not storage_endpoints:
                logger.warning(
                    "No SE endpoints available - AdaptiveCapacityMonitor will start without endpoints"
                )

            # Конфигурация из settings
            monitor_config = CapacityMonitorConfig(
                leader_lock_key=settings.capacity_monitor.leader_lock_key,
                leader_ttl=settings.capacity_monitor.leader_ttl,
                leader_renewal_interval=settings.capacity_monitor.leader_renewal_interval,
                base_interval=settings.capacity_monitor.base_interval,
                max_interval=settings.capacity_monitor.max_interval,
                min_interval=settings.capacity_monitor.min_interval,
                http_timeout=settings.capacity_monitor.http_timeout,
                http_retries=settings.capacity_monitor.http_retries,
                retry_base_delay=settings.capacity_monitor.retry_base_delay,
                cache_ttl=settings.capacity_monitor.cache_ttl,
                health_ttl=settings.capacity_monitor.health_ttl,
                failure_threshold=settings.capacity_monitor.failure_threshold,
                recovery_threshold=settings.capacity_monitor.recovery_threshold,
                stability_threshold=settings.capacity_monitor.stability_threshold,
                change_threshold=settings.capacity_monitor.change_threshold,
            )

            capacity_monitor = await init_capacity_monitor(
                redis_client=redis_client,
                storage_endpoints=storage_endpoints,
                config=monitor_config,
                storage_priorities=storage_priorities,  # Sprint 18 Phase 3
            )
            logger.info(
                "AdaptiveCapacityMonitor initialized",
                extra={
                    "role": capacity_monitor.role.value,
                    "instance_id": capacity_monitor.instance_id,
                }
            )

            # Sprint 17: Инъекция CapacityMonitor в UploadService для lazy update
            upload_service.set_capacity_monitor(capacity_monitor)

        except Exception as e:
            logger.warning(
                "Failed to initialize AdaptiveCapacityMonitor - continuing without it",
                extra={"error": str(e)}
            )

    # Sprint 21: Background task для периодического reload SE config
    reload_task = None

    if capacity_monitor and settings.capacity_monitor.config_reload_enabled:
        import asyncio

        reload_task = asyncio.create_task(
            _periodic_se_config_reload(
                capacity_monitor=capacity_monitor,
                redis_client=redis_client,
                admin_client=admin_client,
                interval=settings.capacity_monitor.config_reload_interval
            )
        )
        logger.info(
            "SE config reload task started",
            extra={
                "interval": settings.capacity_monitor.config_reload_interval,
                "enabled": settings.capacity_monitor.config_reload_enabled,
            }
        )

    # JWT Hot-Reload: Запуск file watcher для автоматической перезагрузки ключей
    try:
        from app.core.jwt_key_manager import get_jwt_key_manager

        jwt_key_manager = get_jwt_key_manager()
        jwt_key_manager.start_watching()
        logger.info("JWT key file watcher started (hot-reload enabled)")
    except Exception as e:
        logger.warning(
            "Failed to start JWT key watcher - hot-reload disabled",
            extra={"error": str(e)}
        )

    yield

    # Shutdown
    logger.info("Shutting down Ingester Module")

    # Sprint 21: Остановка reload task
    if reload_task:
        import asyncio

        reload_task.cancel()
        try:
            await reload_task
        except asyncio.CancelledError:
            pass
        logger.info("SE config reload task stopped")

    # Закрытие в обратном порядке
    # Sprint 17: Остановка AdaptiveCapacityMonitor
    await close_capacity_monitor()

    await close_storage_selector()
    await close_admin_client()
    await close_redis_client()
    await finalize_service.close()  # Sprint 15: Закрытие FinalizeService
    await upload_service.close()
    await auth_service.close()
    logger.info("All connections closed")


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

# Sprint 16: Health endpoints на /health (стандарт системы, без /api/v1)
from app.api.v1.endpoints import health as health_router
app.include_router(health_router.router, prefix="/health", tags=["health"])
logger.info("Health endpoints registered: /health/live, /health/ready")

# Подключение API router
app.include_router(api_router, prefix="/api/v1")

# Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


# Sprint 20 Fix 3: Exception handler для NoAvailableStorageException → HTTP 503
@app.exception_handler(NoAvailableStorageException)
async def no_available_storage_exception_handler(
    request: Request, exc: NoAvailableStorageException
) -> JSONResponse:
    """
    Обработчик NoAvailableStorageException.

    Возвращает HTTP 503 Service Unavailable вместо 500 Internal Server Error,
    что корректно указывает клиенту на временную недоступность сервиса
    и позволяет применить retry логику.

    Args:
        request: FastAPI Request объект
        exc: NoAvailableStorageException исключение

    Returns:
        JSONResponse с кодом 503 и информацией об ошибке
    """
    logger.warning(
        "No available Storage Element for upload",
        extra={
            "path": request.url.path,
            "method": request.method,
            "error": exc.message,
            "details": exc.details,
        }
    )
    return JSONResponse(
        status_code=503,
        content={
            "detail": exc.message,
            "error_type": "NoAvailableStorageException",
            "retry_after": 30,  # Рекомендация клиенту подождать 30 секунд
        },
        headers={
            "Retry-After": "30",  # Стандартный HTTP header для 503
        }
    )


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
