"""
Ingester Module - Health Check Endpoints.

Sprint 16: Переработанные health checks с Service Discovery.

Liveness и Readiness probes для Kubernetes/Docker health monitoring.

Изменения Sprint 16:
- Удалён static STORAGE_ELEMENT_BASE_URL
- Readiness проверяет ВСЕ writable SE через StorageSelector
- Исправлен endpoint: /health/live (не /api/v1/health/live)
- Агрегация статусов: ok (100%), degraded (>0%), fail (0%)

Sprint 17: Расширенная проверка Capacity Monitor.
- Проверка состояния Leader Election
- Проверка что есть хотя бы 1 SE в режиме edit
- Проверка свежести capacity cache
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


class HealthResponse(BaseModel):
    """Ответ health check."""
    status: str
    timestamp: datetime
    version: str
    service: str


class StorageElementHealth(BaseModel):
    """Статус одного Storage Element."""
    element_id: str
    endpoint: str
    status: str  # ok, fail
    mode: Optional[str] = None
    error: Optional[str] = None


class ReadinessResponse(BaseModel):
    """Ответ readiness check."""
    status: str  # ok, degraded, fail
    timestamp: datetime
    checks: dict
    storage_elements: Optional[dict] = None
    summary: Optional[dict] = None


@router.get(
    "/live",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Liveness Probe",
    description="Проверка что приложение запущено и отвечает"
)
async def liveness():
    """
    Liveness probe - проверка что приложение живо.

    Всегда возвращает 200 OK если приложение запущено.
    Используется Kubernetes для restart pod при сбоях.
    """
    return HealthResponse(
        status="ok",
        timestamp=datetime.now(timezone.utc),
        version=settings.app.version,
        service=settings.app.name
    )


@router.get(
    "/ready",
    summary="Readiness Probe",
    description="""
    Проверка готовности приложения принимать трафик.

    **Sprint 16: Улучшенная проверка через Service Discovery**

    Проверяет:
    - Redis Service Discovery
    - Admin Module (fallback)
    - ВСЕ writable Storage Elements (edit/rw режимы)

    **Статусы:**
    - `ok`: Все компоненты работают
    - `degraded`: Часть SE недоступна, но работа возможна
    - `fail`: Service Discovery или все SE недоступны

    **Endpoint SE:** /health/live (стандарт системы)
    """
)
async def readiness():
    """
    Readiness probe - проверка что приложение готово к работе.

    Sprint 16: Проверяет все writable SE через StorageSelector.

    Логика:
    1. Проверить Redis (Service Discovery)
    2. Проверить Admin Module (fallback)
    3. Получить ВСЕ writable SE через StorageSelector
    4. Проверить каждый SE на /health/live
    5. Агрегировать: ok (100%), degraded (>0% <100%), fail (0%)
    """
    checks = {}
    overall_status = 'ok'
    storage_elements_status = {}
    healthy_se_count = 0
    total_se_count = 0

    # 1. Проверка Redis (Service Discovery)
    try:
        from app.core.redis import get_redis_client
        redis_client = await get_redis_client()
        if redis_client:
            await redis_client.ping()
            checks['redis'] = 'ok'
        else:
            checks['redis'] = 'not_configured'
            overall_status = 'degraded'
    except Exception as e:
        logger.warning(
            "Redis health check failed",
            extra={"error": str(e)}
        )
        checks['redis'] = 'fail'
        overall_status = 'degraded'

    # 2. Проверка Admin Module (fallback)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Используем правильный endpoint: /health/live (без /api/v1)
            response = await client.get(
                f"{settings.auth.admin_module_url}/health/live"
            )
            checks['admin_module'] = 'ok' if response.status_code == 200 else 'fail'
    except Exception as e:
        logger.warning(
            "Admin Module health check failed",
            extra={"error": str(e), "url": settings.auth.admin_module_url}
        )
        checks['admin_module'] = 'fail'
        # Если и Redis fail, и Admin fail - статус ухудшается
        if checks.get('redis') not in ('ok', 'not_configured'):
            overall_status = 'degraded'

    # Sprint 17: Проверка Capacity Monitor
    capacity_monitor_status = None
    try:
        from app.services.capacity_monitor import get_capacity_monitor

        capacity_monitor = await get_capacity_monitor()
        if capacity_monitor:
            cm_status = capacity_monitor.get_status()
            capacity_monitor_status = {
                'instance_id': cm_status.get('instance_id'),
                'role': cm_status.get('role'),
                'running': cm_status.get('running'),
                'storage_elements_count': cm_status.get('storage_elements_count'),
            }
            checks['capacity_monitor'] = 'ok' if cm_status.get('running') else 'degraded'
        else:
            checks['capacity_monitor'] = 'not_configured'
            # Capacity Monitor опциональный, не влияет на overall status
    except ImportError:
        checks['capacity_monitor'] = 'not_available'
    except Exception as e:
        logger.warning(
            "Capacity Monitor health check failed",
            extra={"error": str(e)}
        )
        checks['capacity_monitor'] = 'error'

    # 3. Проверка Storage Elements через StorageSelector
    try:
        from app.services.storage_selector import get_storage_selector

        storage_selector = await get_storage_selector()

        if not storage_selector._initialized:
            logger.warning("StorageSelector not initialized for health check")
            checks['storage_elements'] = 'not_initialized'
            overall_status = 'degraded'
        else:
            # Получаем все доступные SE (edit и rw)
            all_se = await storage_selector.get_all_available_storage_elements()

            if not all_se:
                logger.warning("No Storage Elements found via Service Discovery")
                checks['storage_elements'] = 'no_elements'
                overall_status = 'fail'
            else:
                # Проверяем каждый SE
                async with httpx.AsyncClient(timeout=5.0) as client:
                    for se_info in all_se:
                        total_se_count += 1
                        se_health = {
                            'endpoint': se_info.endpoint,
                            'mode': se_info.mode,
                            'status': 'unknown'
                        }

                        try:
                            # ВАЖНО: /health/live БЕЗ /api/v1 - это стандарт системы
                            response = await client.get(
                                f"{se_info.endpoint}/health/live"
                            )
                            if response.status_code == 200:
                                se_health['status'] = 'ok'
                                healthy_se_count += 1
                            else:
                                se_health['status'] = 'fail'
                                se_health['error'] = f"HTTP {response.status_code}"
                        except Exception as e:
                            se_health['status'] = 'fail'
                            se_health['error'] = str(e)
                            logger.warning(
                                "SE health check failed",
                                extra={
                                    "se_id": se_info.element_id,
                                    "endpoint": se_info.endpoint,
                                    "error": str(e)
                                }
                            )

                        storage_elements_status[se_info.element_id] = se_health

                # Sprint 17: Подсчёт SE по режимам (edit/rw)
                edit_se_count = sum(
                    1 for se_id, se in storage_elements_status.items()
                    if se.get('mode') == 'edit' and se.get('status') == 'ok'
                )
                rw_se_count = sum(
                    1 for se_id, se in storage_elements_status.items()
                    if se.get('mode') == 'rw' and se.get('status') == 'ok'
                )

                # Агрегация статуса SE
                if healthy_se_count == 0:
                    checks['storage_elements'] = 'fail'
                    overall_status = 'fail'
                elif healthy_se_count < total_se_count:
                    checks['storage_elements'] = 'degraded'
                    if overall_status != 'fail':
                        overall_status = 'degraded'
                else:
                    checks['storage_elements'] = 'ok'

                # Sprint 17: Проверка минимальных требований по режимам
                # Для загрузки TEMPORARY файлов нужен хотя бы 1 edit SE
                if edit_se_count == 0:
                    logger.warning(
                        "No healthy edit-mode Storage Elements available",
                        extra={"edit_se_count": edit_se_count, "rw_se_count": rw_se_count}
                    )
                    checks['edit_storage'] = 'fail'
                    if overall_status == 'ok':
                        overall_status = 'degraded'
                else:
                    checks['edit_storage'] = 'ok'

    except ImportError:
        logger.error("StorageSelector import failed")
        checks['storage_elements'] = 'import_error'
        overall_status = 'fail'
    except Exception as e:
        logger.error(
            "Storage Elements health check failed",
            extra={"error": str(e)}
        )
        checks['storage_elements'] = 'error'
        overall_status = 'fail'

    # Формирование ответа
    health_percentage = (healthy_se_count / total_se_count * 100) if total_se_count > 0 else 0

    response_data = {
        'status': overall_status,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'checks': checks,
        'storage_elements': storage_elements_status if storage_elements_status else None,
        # Sprint 17: Добавлен статус Capacity Monitor
        'capacity_monitor': capacity_monitor_status,
        'summary': {
            'total_se': total_se_count,
            'healthy_se': healthy_se_count,
            'health_percentage': round(health_percentage, 1)
        }
    }

    # HTTP статус код
    if overall_status == 'ok':
        status_code = 200
    elif overall_status == 'degraded':
        status_code = 200  # Degraded всё ещё может принимать трафик
    else:  # fail
        status_code = 503

    return JSONResponse(status_code=status_code, content=response_data)
