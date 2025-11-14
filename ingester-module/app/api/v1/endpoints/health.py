"""
Ingester Module - Health Check Endpoints.

Liveness и Readiness probes для Kubernetes/Docker health monitoring.
"""

import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, status
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


class ReadinessResponse(BaseModel):
    """Ответ readiness check."""
    status: str
    timestamp: datetime
    checks: dict


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
    response_model=ReadinessResponse,
    status_code=status.HTTP_200_OK,
    summary="Readiness Probe",
    description="Проверка что приложение готово принимать трафик"
)
async def readiness():
    """
    Readiness probe - проверка что приложение готово к работе.

    Проверяет:
    - Доступность Storage Element
    - Доступность Redis (TODO)

    Возвращает 200 OK если все dependencies доступны.
    Используется load balancer для routing трафика.
    """
    checks = {}

    # Проверка Storage Element
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{settings.storage_element.base_url}/api/v1/health/live"
            )
            checks['storage_element'] = 'ok' if response.status_code == 200 else 'fail'
    except Exception as e:
        logger.warning(
            "Storage Element health check failed",
            extra={"error": str(e)}
        )
        checks['storage_element'] = 'fail'

    # TODO: Добавить проверку Redis
    # TODO: Добавить проверку других dependencies

    # Определение общего статуса
    overall_status = 'ok' if all(v == 'ok' for v in checks.values()) else 'degraded'

    return ReadinessResponse(
        status=overall_status,
        timestamp=datetime.now(timezone.utc),
        checks=checks
    )
