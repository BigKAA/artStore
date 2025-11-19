"""
API endpoints для управления Storage Elements.

Предоставляет REST API для просмотра и мониторинга Storage Elements:
- Получение списка Storage Elements с фильтрацией и пагинацией
- Получение детальной информации о Storage Element
- Мониторинг статуса и метрик использования

RBAC: Доступно всем аутентифицированным админам для чтения
       SUPER_ADMIN требуется для write операций (создание, обновление, удаление)

Note: Полный CRUD будет реализован в Sprint 19. Сейчас только read-only endpoints.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.dependencies.admin_auth import get_current_admin_user
from app.models.admin_user import AdminUser
from app.models.storage_element import StorageElement, StorageMode, StorageStatus, StorageType
from app.schemas.storage_element import (
    StorageElementResponse,
    StorageElementListResponse
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/storage-elements")


def calculate_computed_fields(storage: StorageElement) -> dict:
    """
    Вычисление дополнительных полей для Storage Element.

    Computed fields:
    - capacity_gb: Емкость в гигабайтах
    - used_gb: Использовано гигабайт
    - usage_percent: Процент использования
    - is_available: Доступен ли storage
    - is_writable: Доступен ли для записи
    """
    capacity_gb = storage.capacity_bytes / (1024**3) if storage.capacity_bytes else None
    used_gb = storage.used_bytes / (1024**3)
    usage_percent = (storage.used_bytes / storage.capacity_bytes * 100) if storage.capacity_bytes else None

    return {
        "capacity_gb": round(capacity_gb, 2) if capacity_gb else None,
        "used_gb": round(used_gb, 2),
        "usage_percent": round(usage_percent, 2) if usage_percent else None,
        "is_available": storage.is_available,
        "is_writable": storage.is_writable
    }


@router.get(
    "/",
    response_model=StorageElementListResponse,
    summary="Get Storage Elements list",
    description="Получение списка Storage Elements с фильтрацией и пагинацией"
)
async def get_storage_elements_list(
    skip: int = Query(0, ge=0, description="Offset пагинации"),
    limit: int = Query(100, ge=1, le=1000, description="Лимит записей"),
    mode: Optional[StorageMode] = Query(None, description="Фильтр по режиму работы"),
    status_filter: Optional[StorageStatus] = Query(None, alias="status", description="Фильтр по статусу"),
    storage_type: Optional[StorageType] = Query(None, description="Фильтр по типу хранилища"),
    search: Optional[str] = Query(None, description="Поиск по name или api_url"),
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin_user)
):
    """
    Получение списка Storage Elements с фильтрацией и пагинацией.

    **Query Parameters:**
    - **skip**: Offset для пагинации (default: 0)
    - **limit**: Количество записей (default: 100, max: 1000)
    - **mode**: Фильтр по режиму работы (edit, rw, ro, ar)
    - **status**: Фильтр по статусу (online, offline, degraded, maintenance)
    - **storage_type**: Фильтр по типу хранилища (local, s3)
    - **search**: Поиск по name или api_url

    **Response:**
    - **total**: Общее количество storage elements
    - **items**: Список Storage Elements с вычисленными метриками
    - **skip**: Текущий offset
    - **limit**: Текущий limit

    **RBAC:** Доступно всем аутентифицированным админам
    """
    try:
        # Построение запроса с фильтрами
        query = select(StorageElement)

        # Применение фильтров
        if mode:
            query = query.where(StorageElement.mode == mode)
        if status_filter:
            query = query.where(StorageElement.status == status_filter)
        if storage_type:
            query = query.where(StorageElement.storage_type == storage_type)
        if search:
            search_pattern = f"%{search}%"
            query = query.where(
                or_(
                    StorageElement.name.ilike(search_pattern),
                    StorageElement.api_url.ilike(search_pattern)
                )
            )

        # Подсчет total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Применение пагинации и сортировки
        query = query.order_by(StorageElement.id).offset(skip).limit(limit)

        # Выполнение запроса
        result = await db.execute(query)
        storage_elements = result.scalars().all()

        # Формирование response с computed fields
        items = []
        for storage in storage_elements:
            computed = calculate_computed_fields(storage)
            item_dict = {
                **{c.name: getattr(storage, c.name) for c in StorageElement.__table__.columns},
                **computed
            }
            items.append(StorageElementResponse.model_validate(item_dict))

        return StorageElementListResponse(
            total=total,
            items=items,
            skip=skip,
            limit=limit
        )

    except Exception as e:
        logger.error(
            f"Failed to get Storage Elements list: {e}",
            extra={"admin_username": current_admin.username}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve Storage Elements"
        )


@router.get(
    "/{storage_element_id}",
    response_model=StorageElementResponse,
    summary="Get Storage Element by ID",
    description="Получение детальной информации о Storage Element"
)
async def get_storage_element_by_id(
    storage_element_id: int,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin_user)
):
    """
    Получение Storage Element по ID.

    **Path Parameters:**
    - **storage_element_id**: ID storage element

    **Response:**
    - Storage Element с полной информацией и вычисленными метриками
    - Включает: capacity_gb, used_gb, usage_percent, is_available, is_writable

    **RBAC:** Доступно всем аутентифицированным админам
    """
    try:
        # Получение storage element
        query = select(StorageElement).where(StorageElement.id == storage_element_id)
        result = await db.execute(query)
        storage = result.scalar_one_or_none()

        if not storage:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Storage Element {storage_element_id} not found"
            )

        # Формирование response с computed fields
        computed = calculate_computed_fields(storage)
        item_dict = {
            **{c.name: getattr(storage, c.name) for c in StorageElement.__table__.columns},
            **computed
        }

        return StorageElementResponse.model_validate(item_dict)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to get Storage Element {storage_element_id}: {e}",
            extra={"admin_username": current_admin.username}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve Storage Element"
        )


@router.get(
    "/stats/summary",
    summary="Get Storage Elements summary statistics",
    description="Получение сводной статистики по всем Storage Elements"
)
async def get_storage_elements_summary(
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin_user)
):
    """
    Получение сводной статистики по Storage Elements.

    **Response:**
    - **total_count**: Общее количество storage elements
    - **by_status**: Количество по статусам
    - **by_mode**: Количество по режимам работы
    - **by_type**: Количество по типам хранилища
    - **total_capacity_gb**: Общая емкость в GB
    - **total_used_gb**: Всего использовано GB
    - **total_files**: Общее количество файлов
    - **average_usage_percent**: Средний процент использования

    **RBAC:** Доступно всем аутентифицированным админам
    """
    try:
        # Получение всех storage elements
        query = select(StorageElement)
        result = await db.execute(query)
        storage_elements = result.scalars().all()

        # Подсчет статистики
        total_count = len(storage_elements)

        # Группировка по статусам
        by_status = {}
        for status_value in StorageStatus:
            count = sum(1 for s in storage_elements if s.status == status_value)
            by_status[status_value.value] = count

        # Группировка по режимам
        by_mode = {}
        for mode_value in StorageMode:
            count = sum(1 for s in storage_elements if s.mode == mode_value)
            by_mode[mode_value.value] = count

        # Группировка по типам
        by_type = {}
        for type_value in StorageType:
            count = sum(1 for s in storage_elements if s.storage_type == type_value)
            by_type[type_value.value] = count

        # Вычисление метрик использования
        total_capacity_bytes = sum(s.capacity_bytes or 0 for s in storage_elements)
        total_used_bytes = sum(s.used_bytes for s in storage_elements)
        total_files = sum(s.file_count for s in storage_elements)

        total_capacity_gb = round(total_capacity_bytes / (1024**3), 2) if total_capacity_bytes > 0 else 0
        total_used_gb = round(total_used_bytes / (1024**3), 2)

        # Средний процент использования (только для storage с известной емкостью)
        storage_with_capacity = [s for s in storage_elements if s.capacity_bytes]
        if storage_with_capacity:
            avg_usage = sum(s.used_bytes / s.capacity_bytes for s in storage_with_capacity) / len(storage_with_capacity) * 100
            average_usage_percent = round(avg_usage, 2)
        else:
            average_usage_percent = 0

        return {
            "total_count": total_count,
            "by_status": by_status,
            "by_mode": by_mode,
            "by_type": by_type,
            "total_capacity_gb": total_capacity_gb,
            "total_used_gb": total_used_gb,
            "total_files": total_files,
            "average_usage_percent": average_usage_percent
        }

    except Exception as e:
        logger.error(
            f"Failed to get Storage Elements summary: {e}",
            extra={"admin_username": current_admin.username}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve Storage Elements summary"
        )
