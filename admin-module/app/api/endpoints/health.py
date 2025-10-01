"""
API endpoints для health checks и метрик.
"""
from typing import Any, Dict

from fastapi import APIRouter, Depends, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.config import settings
from app.db.session import get_db
from app.services.redis_service import redis_service
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("/live", status_code=status.HTTP_200_OK)
async def liveness_probe() -> Dict[str, str]:
    """
    Liveness probe для Kubernetes/Docker.

    Проверяет, что приложение запущено и отвечает на запросы.
    Не проверяет зависимости (БД, Redis), только базовую работоспособность.

    **Returns**:
    - **status**: "ok" если приложение работает

    **Note**: Этот endpoint всегда возвращает 200 OK если приложение запущено.
    """
    return {"status": "ok", "service": "admin-module"}


@router.get("/ready", status_code=status.HTTP_200_OK)
async def readiness_probe(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """
    Readiness probe для Kubernetes/Docker.

    Проверяет, что приложение готово обрабатывать запросы:
    - Подключение к базе данных работает
    - Подключение к Redis работает

    **Returns**:
    - **status**: "ready" или "not_ready"
    - **checks**: Результаты проверок отдельных компонентов

    **Errors**:
    - **503**: Если какой-либо компонент недоступен
    """
    checks = {}

    # Проверка подключения к базе данных
    try:
        result = await db.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok"}
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        checks["database"] = {"status": "error", "message": str(e)}

    # Проверка подключения к Redis
    try:
        await redis_service.ping()
        checks["redis"] = {"status": "ok"}
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        checks["redis"] = {"status": "error", "message": str(e)}

    # Определяем общий статус
    all_ok = all(check["status"] == "ok" for check in checks.values())

    if all_ok:
        return {
            "status": "ready",
            "service": "admin-module",
            "checks": checks,
        }
    else:
        # Возвращаем 503 если какой-то компонент недоступен
        return {
            "status": "not_ready",
            "service": "admin-module",
            "checks": checks,
        }


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """
    Полная проверка здоровья сервиса.

    Проверяет все компоненты системы и возвращает детальную информацию.

    **Returns**:
    - **status**: "healthy" или "unhealthy"
    - **version**: Версия приложения
    - **components**: Статус каждого компонента

    **Note**: Возвращает 200 OK даже если компоненты недоступны,
    но с соответствующим статусом в ответе.
    """
    components = {}

    # Проверка базы данных
    try:
        result = await db.execute(text("SELECT 1"))
        components["database"] = {
            "status": "healthy",
            "type": "postgresql",
        }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        components["database"] = {
            "status": "unhealthy",
            "type": "postgresql",
            "error": str(e),
        }

    # Проверка Redis
    try:
        await redis_service.ping()
        components["redis"] = {
            "status": "healthy",
            "type": "redis",
        }
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        components["redis"] = {
            "status": "unhealthy",
            "type": "redis",
            "error": str(e),
        }

    # Проверка JWT ключей
    try:
        from app.core.security import PRIVATE_KEY, PUBLIC_KEY

        if PRIVATE_KEY and PUBLIC_KEY:
            components["jwt_keys"] = {"status": "healthy"}
        else:
            components["jwt_keys"] = {
                "status": "unhealthy",
                "error": "JWT keys not initialized",
            }
    except Exception as e:
        components["jwt_keys"] = {"status": "unhealthy", "error": str(e)}

    # Определяем общий статус
    all_healthy = all(
        comp["status"] == "healthy" for comp in components.values()
    )

    return {
        "status": "healthy" if all_healthy else "unhealthy",
        "service": "admin-module",
        "version": settings.server.version,
        "components": components,
    }


@router.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> str:
    """
    Prometheus metrics endpoint.

    Возвращает метрики в формате Prometheus.

    **Returns**:
    - Метрики в текстовом формате Prometheus

    **Note**: Для полной реализации используйте prometheus-client библиотеку.
    """
    # TODO: Реализовать сбор метрик через prometheus-client
    # Пример метрик:
    metrics_data = """# HELP admin_module_up Admin Module is up and running
# TYPE admin_module_up gauge
admin_module_up 1

# HELP admin_module_requests_total Total number of requests
# TYPE admin_module_requests_total counter
admin_module_requests_total 0

# HELP admin_module_request_duration_seconds Request duration in seconds
# TYPE admin_module_request_duration_seconds histogram
admin_module_request_duration_seconds_bucket{le="0.1"} 0
admin_module_request_duration_seconds_bucket{le="0.5"} 0
admin_module_request_duration_seconds_bucket{le="1.0"} 0
admin_module_request_duration_seconds_bucket{le="+Inf"} 0
admin_module_request_duration_seconds_count 0
admin_module_request_duration_seconds_sum 0
"""
    return metrics_data
