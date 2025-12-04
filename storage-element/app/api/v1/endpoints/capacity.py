"""
Capacity endpoint для мониторинга состояния Storage Element.

Используется Ingester Module для adaptive polling capacity информации.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.capacity_service import CapacityService, get_capacity_service

logger = logging.getLogger(__name__)

router = APIRouter()


class CapacityInfo(BaseModel):
    """Информация о capacity Storage Element."""

    total: int = Field(..., description="Общий размер хранилища в байтах")
    used: int = Field(..., description="Использованный размер в байтах")
    available: int = Field(..., description="Доступный размер в байтах")
    percent_used: float = Field(..., description="Процент использования (0-100)")

    class Config:
        json_schema_extra = {
            "example": {
                "total": 1099511627776,
                "used": 549755813888,
                "available": 549755813888,
                "percent_used": 50.0
            }
        }


class CapacityResponse(BaseModel):
    """Response модель capacity endpoint."""

    storage_id: str = Field(..., description="Уникальный ID Storage Element")
    mode: str = Field(..., description="Текущий режим работы (edit/rw/ro/ar)")
    capacity: CapacityInfo = Field(..., description="Информация о capacity")
    health: str = Field(..., description="Health status (healthy/degraded/unhealthy)")
    last_update: str = Field(..., description="Timestamp последнего обновления (ISO 8601)")
    backend: str = Field(..., description="Тип backend хранилища (local/s3)")
    location: str = Field(..., description="Географическое расположение (datacenter)")

    class Config:
        json_schema_extra = {
            "example": {
                "storage_id": "se-dc2-01",
                "mode": "rw",
                "capacity": {
                    "total": 1099511627776,
                    "used": 549755813888,
                    "available": 549755813888,
                    "percent_used": 50.0
                },
                "health": "healthy",
                "last_update": "2025-12-04T10:30:00Z",
                "backend": "local",
                "location": "dc2"
            }
        }


@router.get(
    "/capacity",
    response_model=CapacityResponse,
    status_code=200,
    summary="Получить capacity информацию",
    description="""
    Возвращает текущее состояние capacity Storage Element.

    Используется Ingester Module для:
    - Adaptive polling capacity информации
    - Выбора доступных Storage Elements для upload
    - Health monitoring и alerting

    Endpoint доступен без аутентификации для упрощения мониторинга.
    """,
    tags=["Capacity"],
)
async def get_capacity(
    capacity_service: CapacityService = Depends(get_capacity_service),
):
    """
    Получить capacity информацию Storage Element.

    Returns:
        CapacityResponse: Детальная информация о capacity и состоянии
    """
    # Получаем capacity информацию из service
    capacity_info = await capacity_service.get_capacity_info()

    # Формируем response
    response = CapacityResponse(
        storage_id=settings.storage.element_id,
        mode=settings.app.mode.value,
        capacity=CapacityInfo(**capacity_info),
        health="healthy",  # TODO: интеграция с health checks
        last_update=datetime.utcnow().isoformat() + "Z",
        backend=settings.storage.type.value,
        location=settings.storage.datacenter_location,
    )

    logger.debug(
        "Capacity info requested",
        extra={
            "storage_id": response.storage_id,
            "available_bytes": capacity_info["available"],
            "percent_used": capacity_info["percent_used"],
        },
    )

    return response
