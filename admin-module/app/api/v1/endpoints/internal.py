"""
Internal API endpoints для межсервисного взаимодействия.

Sprint 14: Redis Storage Registry & Adaptive Capacity.

Предоставляет fallback API для Ingester/Query модулей когда Redis недоступен.
Эти endpoints НЕ предназначены для использования Admin UI.

RBAC: Требуется Service Account аутентификация (OAuth 2.0 Client Credentials)
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.api.dependencies.auth import get_current_service_account
from app.models.service_account import ServiceAccount
from app.models.storage_element import StorageElement, StorageMode, StorageStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal")


# =============================================================================
# Pydantic schemas для Internal API
# =============================================================================

class StorageElementAvailableItem(BaseModel):
    """
    Информация о доступном Storage Element для fallback API.

    Содержит минимум полей необходимых для выбора SE.
    """
    id: int = Field(..., description="Database ID")
    element_id: Optional[str] = Field(None, description="String ID для Redis Registry")
    name: str = Field(..., description="Имя Storage Element")
    mode: str = Field(..., description="Режим работы (edit, rw, ro, ar)")
    priority: int = Field(100, description="Приоритет для Sequential Fill")
    api_url: str = Field(..., description="URL API endpoint")
    capacity_bytes: Optional[int] = Field(None, description="Общая емкость в байтах")
    used_bytes: int = Field(0, description="Использовано байтов")
    health_status: str = Field("healthy", description="Статус здоровья")
    capacity_status: str = Field("ok", description="Статус емкости")

    class Config:
        from_attributes = True


class StorageElementAvailableResponse(BaseModel):
    """
    Response для списка доступных Storage Elements.
    """
    storage_elements: list[StorageElementAvailableItem] = Field(
        default_factory=list,
        description="Список доступных SE, отсортированный по priority"
    )
    total: int = Field(0, description="Общее количество найденных SE")


# =============================================================================
# Internal API Endpoints
# =============================================================================

@router.get(
    "/storage-elements/available",
    response_model=StorageElementAvailableResponse,
    summary="Get available Storage Elements (Fallback API)",
    description=(
        "Получение списка доступных Storage Elements для записи файлов. "
        "Используется Ingester/Query модулями как fallback когда Redis недоступен. "
        "Возвращает SE отсортированные по priority (Sequential Fill)."
    )
)
async def get_available_storage_elements(
    mode: Optional[str] = Query(
        None,
        description="Фильтр по режиму работы (edit, rw)"
    ),
    min_free_bytes: Optional[int] = Query(
        None,
        ge=0,
        description="Минимальное свободное место в байтах"
    ),
    db: AsyncSession = Depends(get_db),
    current_service_account: ServiceAccount = Depends(get_current_service_account)
):
    """
    Получение списка доступных Storage Elements.

    Fallback API для случаев когда Redis недоступен.
    Ingester использует этот endpoint для выбора SE когда не может
    получить данные из Redis Registry.

    **Query Parameters:**
    - **mode**: Фильтр по режиму (edit для temporary, rw для permanent)
    - **min_free_bytes**: Минимальное свободное место (для фильтрации)

    **Response:**
    - Список SE отсортированный по priority (меньше = выше приоритет)
    - Включает только ONLINE SE с writable mode (edit, rw)

    **RBAC:** Service Account аутентификация (OAuth 2.0)

    **Sequential Fill Algorithm:**
    SE возвращаются в порядке priority. Ingester должен выбрать
    первый SE с достаточной емкостью.
    """
    try:
        # Базовый запрос: только ONLINE SE
        query = select(StorageElement).where(
            StorageElement.status == StorageStatus.ONLINE
        )

        # Фильтр по mode
        if mode:
            if mode == "edit":
                query = query.where(StorageElement.mode == StorageMode.EDIT)
            elif mode == "rw":
                query = query.where(StorageElement.mode == StorageMode.RW)
            else:
                # Для других режимов (ro, ar) - не подходят для записи
                return StorageElementAvailableResponse(
                    storage_elements=[],
                    total=0
                )
        else:
            # По умолчанию возвращаем writable SE (edit или rw)
            query = query.where(
                StorageElement.mode.in_([StorageMode.EDIT, StorageMode.RW])
            )

        # Сортировка по priority (Sequential Fill)
        query = query.order_by(StorageElement.priority)

        # Выполняем запрос
        result = await db.execute(query)
        storage_elements = result.scalars().all()

        # Фильтруем по min_free_bytes (если указан)
        filtered_elements = []
        for se in storage_elements:
            # Вычисляем свободное место
            free_bytes = None
            if se.capacity_bytes:
                free_bytes = se.capacity_bytes - se.used_bytes

            # Проверяем min_free_bytes
            if min_free_bytes and free_bytes is not None:
                if free_bytes < min_free_bytes:
                    continue

            # Определяем capacity_status на основе использования
            capacity_status = _calculate_capacity_status(se)

            # Формируем item
            item = StorageElementAvailableItem(
                id=se.id,
                element_id=se.element_id,
                name=se.name,
                mode=se.mode.value,
                priority=se.priority,
                api_url=se.api_url,
                capacity_bytes=se.capacity_bytes,
                used_bytes=se.used_bytes,
                health_status="healthy",  # ONLINE = healthy
                capacity_status=capacity_status
            )
            filtered_elements.append(item)

        logger.info(
            f"Internal API: returned {len(filtered_elements)} available SE",
            extra={
                "service_account": current_service_account.name,
                "mode_filter": mode,
                "min_free_bytes": min_free_bytes,
                "total_found": len(filtered_elements)
            }
        )

        return StorageElementAvailableResponse(
            storage_elements=filtered_elements,
            total=len(filtered_elements)
        )

    except Exception as e:
        logger.error(
            f"Internal API error: failed to get available SE: {e}",
            extra={"service_account": current_service_account.name}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve available Storage Elements"
        )


def _calculate_capacity_status(se: StorageElement) -> str:
    """
    Расчет статуса емкости на основе использования.

    Упрощенная версия алгоритма из storage-element/app/core/capacity_calculator.py

    Args:
        se: Storage Element

    Returns:
        str: Статус емкости (ok, warning, critical, full)
    """
    if not se.capacity_bytes or se.capacity_bytes <= 0:
        return "ok"  # Неизвестная емкость - считаем OK

    used_percent = (se.used_bytes / se.capacity_bytes) * 100

    # Пороги для edit mode более строгие чем для rw
    if se.mode == StorageMode.EDIT:
        if used_percent >= 99:
            return "full"
        elif used_percent >= 95:
            return "critical"
        elif used_percent >= 90:
            return "warning"
    else:  # rw mode
        if used_percent >= 98:
            return "full"
        elif used_percent >= 92:
            return "critical"
        elif used_percent >= 85:
            return "warning"

    return "ok"


@router.get(
    "/storage-elements/{element_id}",
    response_model=StorageElementAvailableItem,
    summary="Get Storage Element by element_id (Fallback API)",
    description=(
        "Получение информации о конкретном Storage Element по element_id. "
        "Fallback API для случаев когда Redis недоступен."
    )
)
async def get_storage_element_by_element_id(
    element_id: str,
    db: AsyncSession = Depends(get_db),
    current_service_account: ServiceAccount = Depends(get_current_service_account)
):
    """
    Получение Storage Element по element_id.

    **Path Parameters:**
    - **element_id**: Строковый ID для Redis Registry (например: se-01)

    **Response:**
    - Информация о SE или 404 если не найден

    **RBAC:** Service Account аутентификация (OAuth 2.0)
    """
    try:
        query = select(StorageElement).where(
            StorageElement.element_id == element_id
        )
        result = await db.execute(query)
        se = result.scalar_one_or_none()

        if not se:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Storage Element with element_id '{element_id}' not found"
            )

        capacity_status = _calculate_capacity_status(se)
        health_status = "healthy" if se.status == StorageStatus.ONLINE else "unhealthy"

        return StorageElementAvailableItem(
            id=se.id,
            element_id=se.element_id,
            name=se.name,
            mode=se.mode.value,
            priority=se.priority,
            api_url=se.api_url,
            capacity_bytes=se.capacity_bytes,
            used_bytes=se.used_bytes,
            health_status=health_status,
            capacity_status=capacity_status
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Internal API error: failed to get SE {element_id}: {e}",
            extra={"service_account": current_service_account.name}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve Storage Element"
        )
