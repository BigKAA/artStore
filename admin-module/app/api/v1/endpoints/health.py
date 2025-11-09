"""
Health check endpoints для Admin Module.
Поддерживает liveness, readiness проверки и Prometheus metrics.
"""

from fastapi import APIRouter, Response, status
from datetime import datetime
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST
import logging

from app.core.database import check_db_connection
from app.core.redis import check_redis_connection
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# Prometheus metrics
health_check_counter = Counter(
    "admin_module_health_checks_total",
    "Total number of health checks",
    ["type", "status"]
)

database_status_gauge = Gauge(
    "admin_module_database_status",
    "Database connection status (1=up, 0=down)"
)

redis_status_gauge = Gauge(
    "admin_module_redis_status",
    "Redis connection status (1=up, 0=down)"
)

application_info = Gauge(
    "admin_module_info",
    "Application information",
    ["version", "name"]
)

# Устанавливаем информацию о приложении
application_info.labels(version=settings.app_version, name=settings.app_name).set(1)


@router.get("/live", summary="Liveness probe", description="Проверка что приложение работает")
async def liveness():
    """
    Liveness probe для Kubernetes.
    Проверяет что приложение запущено и отвечает на запросы.

    Returns:
        dict: Статус liveness
    """
    health_check_counter.labels(type="liveness", status="success").inc()

    return {
        "status": "alive",
        "timestamp": datetime.utcnow().isoformat(),
        "service": settings.app_name,
        "version": settings.app_version
    }


@router.get("/ready", summary="Readiness probe", description="Проверка готовности принимать трафик")
async def readiness(response: Response):
    """
    Readiness probe для Kubernetes.
    Проверяет что приложение готово обрабатывать запросы.
    Проверяет подключения к зависимостям (PostgreSQL, Redis).

    Returns:
        dict: Статус readiness и статусы зависимостей
    """
    # Проверяем подключения
    db_ok = await check_db_connection()
    redis_ok = check_redis_connection()  # Синхронный вызов

    # Обновляем метрики
    database_status_gauge.set(1 if db_ok else 0)
    redis_status_gauge.set(1 if redis_ok else 0)

    # Готовы если PostgreSQL доступен (Redis не критичен)
    is_ready = db_ok

    if is_ready:
        health_check_counter.labels(type="readiness", status="success").inc()
        response.status_code = status.HTTP_200_OK
    else:
        health_check_counter.labels(type="readiness", status="failure").inc()
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ready" if is_ready else "not_ready",
        "timestamp": datetime.utcnow().isoformat(),
        "service": settings.app_name,
        "version": settings.app_version,
        "dependencies": {
            "database": {
                "status": "up" if db_ok else "down",
                "critical": True
            },
            "redis": {
                "status": "up" if redis_ok else "down",
                "critical": False
            }
        }
    }


@router.get("/metrics", summary="Prometheus metrics", description="Метрики для мониторинга")
async def metrics():
    """
    Prometheus metrics endpoint.
    Возвращает метрики в формате Prometheus.

    Returns:
        Response: Prometheus metrics в text формате
    """
    if not settings.monitoring.prometheus_enabled:
        return Response(
            content="Prometheus metrics disabled",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )

    # Обновляем метрики перед отдачей
    db_ok = await check_db_connection()
    redis_ok = check_redis_connection()  # Синхронный вызов

    database_status_gauge.set(1 if db_ok else 0)
    redis_status_gauge.set(1 if redis_ok else 0)

    # Генерируем метрики
    metrics_output = generate_latest()

    return Response(
        content=metrics_output,
        media_type=CONTENT_TYPE_LATEST
    )


@router.get("/startup", summary="Startup probe", description="Проверка что приложение стартовало")
async def startup(response: Response):
    """
    Startup probe для Kubernetes.
    Проверяет что приложение успешно стартовало.

    Returns:
        dict: Статус startup
    """
    # Проверяем базовые подключения
    db_ok = await check_db_connection()  # Async для DB

    if db_ok:
        health_check_counter.labels(type="startup", status="success").inc()
        response.status_code = status.HTTP_200_OK
        startup_status = "started"
    else:
        health_check_counter.labels(type="startup", status="failure").inc()
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        startup_status = "starting"

    return {
        "status": startup_status,
        "timestamp": datetime.utcnow().isoformat(),
        "service": settings.app_name,
        "version": settings.app_version
    }
