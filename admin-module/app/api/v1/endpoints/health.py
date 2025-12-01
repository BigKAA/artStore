"""
Health check endpoints для Admin Module.

Поддерживает liveness, readiness проверки и Prometheus metrics.

ВАЖНО: Readiness probe использует асинхронную архитектуру:
- Background job (APScheduler) периодически проверяет состояние БД и Redis
- Результат сохраняется в HealthStateService
- Endpoint /health/ready читает из кеша и отвечает мгновенно (без I/O операций)

Это обеспечивает стабильный и быстрый ответ readiness probe без нагрузки
на зависимости при каждом запросе.
"""

from fastapi import APIRouter, Response, status
from datetime import datetime
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST
import logging

from app.core.config import settings
from app.services.health_state_service import health_state_service

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
    Возвращает кешированное состояние (проверки выполняются в background job).

    Критерии успешности:
    1. Приложение слушает порт (по определению - endpoint отвечает)
    2. Успешное подключение к БД + наличие всех необходимых таблиц (критично)
    3. Подключение к Redis (опционально - warning, но не блокирует readiness)

    При недоступности БД возвращается 503 с указанием причины в поле "reason".

    Returns:
        dict: Статус readiness, состояние зависимостей, причина (при ошибке)
    """
    # Получаем кешированное состояние (мгновенный ответ без I/O)
    state = health_state_service.get_state()

    # Обновляем Prometheus метрики
    database_status_gauge.set(1 if state.database.ok else 0)
    redis_status_gauge.set(1 if state.redis.ok else 0)

    # Определяем HTTP статус
    if state.is_ready:
        health_check_counter.labels(type="readiness", status="success").inc()
        response.status_code = status.HTTP_200_OK
    else:
        health_check_counter.labels(type="readiness", status="failure").inc()
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    # Формируем базовый ответ
    result = {
        "status": "ready" if state.is_ready else "not_ready",
        "timestamp": datetime.utcnow().isoformat(),
        "service": settings.app_name,
        "version": settings.app_version,
        "last_check": state.last_check.isoformat() if state.last_check else None,
        "dependencies": {
            "database": {
                "status": "up" if state.database.ok else "down",
                "critical": True,
            },
            "redis": {
                "status": "up" if state.redis.ok else "down",
                "critical": False,
            }
        }
    }

    # Добавляем детали ошибок в dependencies
    if state.database.error:
        result["dependencies"]["database"]["error"] = state.database.error
    if state.database.missing_tables:
        result["dependencies"]["database"]["missing_tables"] = state.database.missing_tables
    if state.redis.error:
        result["dependencies"]["redis"]["error"] = state.redis.error

    # Добавляем причину неготовности (для 503)
    if state.reason:
        result["reason"] = state.reason

    # Добавляем предупреждения (Redis недоступен, но приложение готово)
    if state.warnings:
        result["warnings"] = state.warnings

    return result


@router.get("/metrics", summary="Prometheus metrics", description="Метрики для мониторинга")
async def metrics():
    """
    Prometheus metrics endpoint.
    Возвращает метрики в формате Prometheus.

    Использует кешированное состояние из HealthStateService.

    Returns:
        Response: Prometheus metrics в text формате
    """
    if not settings.monitoring.prometheus_enabled:
        return Response(
            content="Prometheus metrics disabled",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )

    # Обновляем метрики из кешированного состояния (без I/O операций)
    state = health_state_service.get_state()
    database_status_gauge.set(1 if state.database.ok else 0)
    redis_status_gauge.set(1 if state.redis.ok else 0)

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

    Использует кешированное состояние из HealthStateService.

    Returns:
        dict: Статус startup
    """
    # Получаем кешированное состояние
    state = health_state_service.get_state()

    # Для startup достаточно проверить БД
    if state.database.ok:
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
