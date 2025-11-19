"""
API endpoints для управления Storage Elements.

Предоставляет REST API для полного CRUD управления Storage Elements:
- Создание нового Storage Element (SUPER_ADMIN only)
- Получение списка Storage Elements с фильтрацией и пагинацией
- Получение детальной информации о Storage Element
- Обновление Storage Element (SUPER_ADMIN only)
- Удаление Storage Element (SUPER_ADMIN only)
- Мониторинг статуса и метрик использования

RBAC: Доступно всем аутентифицированным админам для чтения
       SUPER_ADMIN требуется для write операций (создание, обновление, удаление)

Sprint 19 Phase 1: Full CRUD implementation
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.dependencies.admin_auth import get_current_admin_user, require_role
from app.models.admin_user import AdminUser, AdminRole
from app.models.storage_element import StorageElement, StorageMode, StorageStatus, StorageType
from app.schemas.storage_element import (
    StorageElementResponse,
    StorageElementListResponse,
    StorageElementCreate,
    StorageElementUpdate
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

    # Вычисляем is_available и is_writable без использования @property
    # чтобы избежать проблем с detached SQLAlchemy objects
    is_available = storage.status == StorageStatus.ONLINE
    is_writable = storage.mode in (StorageMode.EDIT, StorageMode.RW) and is_available

    return {
        "capacity_gb": round(capacity_gb, 2) if capacity_gb else None,
        "used_gb": round(used_gb, 2),
        "usage_percent": round(usage_percent, 2) if usage_percent else None,
        "is_available": is_available,
        "is_writable": is_writable
    }


@router.post(
    "/",
    response_model=StorageElementResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create new Storage Element",
    description=(
        "Создание нового Storage Element. Требуется роль SUPER_ADMIN. "
        "После создания storage element автоматически получает статус ONLINE "
        "и начальные метрики (used_bytes=0, file_count=0)."
    )
)
async def create_storage_element(
    request: StorageElementCreate,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_role(AdminRole.SUPER_ADMIN))
):
    """
    Создание нового Storage Element.

    **Request Body:**
    - **name**: Название storage element (уникальное, 3-100 символов)
    - **description**: Описание назначения (опционально, до 500 символов)
    - **mode**: Режим работы (edit/rw/ro/ar, default: edit)
    - **storage_type**: Тип хранилища (local/s3, default: local)
    - **base_path**: Базовый путь или bucket name (обязательно)
    - **api_url**: URL API storage element (обязательно)
    - **api_key**: API ключ для аутентификации (опционально)
    - **capacity_bytes**: Общая емкость в байтах (опционально)
    - **retention_days**: Срок хранения в днях (опционально, >= 1)
    - **is_replicated**: Флаг репликации (default: false)
    - **replica_count**: Количество реплик (default: 0, >= 0)

    **Response:**
    - Storage Element с вычисленными метриками
    - Автоматически установленные значения: status=ONLINE, used_bytes=0, file_count=0

    **RBAC:** Только SUPER_ADMIN

    **Validation:**
    - name должен быть уникальным
    - api_url должен быть валидным URL
    - capacity_bytes >= 0 (если указано)
    - retention_days >= 1 (если указано)
    - replica_count >= 0
    """
    try:
        # Проверка уникальности name
        existing_query = select(StorageElement).where(StorageElement.name == request.name)
        existing_result = await db.execute(existing_query)
        if existing_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Storage Element with name '{request.name}' already exists"
            )

        # Проверка уникальности api_url
        url_query = select(StorageElement).where(StorageElement.api_url == request.api_url)
        url_result = await db.execute(url_query)
        if url_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Storage Element with api_url '{request.api_url}' already exists"
            )

        # Создание Storage Element
        storage_element = StorageElement(
            name=request.name,
            description=request.description,
            mode=request.mode,
            storage_type=request.storage_type,
            base_path=request.base_path,
            api_url=request.api_url,
            api_key=request.api_key,
            status=StorageStatus.ONLINE,  # Автоматически ONLINE при создании
            capacity_bytes=request.capacity_bytes,
            used_bytes=0,  # Начальное значение
            file_count=0,  # Начальное значение
            retention_days=request.retention_days,
            last_health_check=None,  # Будет обновлено при первой health check
            is_replicated=request.is_replicated,
            replica_count=request.replica_count
        )

        db.add(storage_element)
        await db.commit()
        await db.refresh(storage_element)

        logger.info(
            f"Storage Element created: {request.name} by {current_admin.username}",
            extra={
                "storage_element_id": storage_element.id,
                "storage_element_name": storage_element.name,
                "mode": storage_element.mode.value,
                "storage_type": storage_element.storage_type.value,
                "admin_id": str(current_admin.id),
                "admin_username": current_admin.username
            }
        )

        # Формирование response с computed fields
        computed = calculate_computed_fields(storage_element)
        item_dict = {
            **{c.name: getattr(storage_element, c.name) for c in StorageElement.__table__.columns},
            **computed
        }

        return StorageElementResponse.model_validate(item_dict)

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(
            f"Failed to create Storage Element: {e}",
            extra={"admin_username": current_admin.username}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create Storage Element"
        )


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


@router.put(
    "/{storage_element_id}",
    response_model=StorageElementResponse,
    summary="Update Storage Element",
    description="Обновление параметров Storage Element. Требуется роль SUPER_ADMIN."
)
async def update_storage_element(
    storage_element_id: int,
    request: StorageElementUpdate,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_role(AdminRole.SUPER_ADMIN))
):
    """
    Обновление параметров Storage Element.

    **Path Parameters:**
    - **storage_element_id**: ID storage element

    **Request Body (все поля опциональны):**
    - **name**: Новое название (уникальное, 3-100 символов)
    - **description**: Новое описание (до 500 символов)
    - **mode**: Новый режим работы (edit/rw/ro/ar)
    - **api_url**: Новый URL API
    - **api_key**: Новый API ключ
    - **status**: Новый статус (online/offline/degraded/maintenance)
    - **capacity_bytes**: Новая емкость в байтах (>= 0)
    - **retention_days**: Новый срок хранения в днях (>= 1)
    - **replica_count**: Новое количество реплик (>= 0)

    **Response:**
    - Storage Element с обновленными параметрами и вычисленными метриками

    **RBAC:** Только SUPER_ADMIN

    **Ограничения:**
    - Нельзя изменить storage_type и base_path после создания
    - Нельзя изменить used_bytes и file_count (управляется системой)
    - name и api_url должны быть уникальными
    - Mode transitions: edit (фиксированный) → rw → ro → ar
    """
    try:
        # Получение существующего Storage Element
        query = select(StorageElement).where(StorageElement.id == storage_element_id)
        result = await db.execute(query)
        storage_element = result.scalar_one_or_none()

        if not storage_element:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Storage Element {storage_element_id} not found"
            )

        # Проверка уникальности name (если изменяется)
        if request.name and request.name != storage_element.name:
            name_query = select(StorageElement).where(StorageElement.name == request.name)
            name_result = await db.execute(name_query)
            if name_result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Storage Element with name '{request.name}' already exists"
                )
            storage_element.name = request.name

        # Проверка уникальности api_url (если изменяется)
        if request.api_url and request.api_url != storage_element.api_url:
            url_query = select(StorageElement).where(StorageElement.api_url == request.api_url)
            url_result = await db.execute(url_query)
            if url_result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Storage Element with api_url '{request.api_url}' already exists"
                )
            storage_element.api_url = request.api_url

        # Обновление полей
        if request.description is not None:
            storage_element.description = request.description
        if request.mode:
            storage_element.mode = request.mode
        if request.api_key is not None:
            storage_element.api_key = request.api_key
        if request.status:
            storage_element.status = request.status
        if request.capacity_bytes is not None:
            storage_element.capacity_bytes = request.capacity_bytes
        if request.retention_days is not None:
            storage_element.retention_days = request.retention_days
        if request.replica_count is not None:
            storage_element.replica_count = request.replica_count

        await db.commit()
        await db.refresh(storage_element)

        logger.info(
            f"Storage Element updated: {storage_element.name} by {current_admin.username}",
            extra={
                "storage_element_id": storage_element_id,
                "admin_id": str(current_admin.id),
                "admin_username": current_admin.username,
                "changes": request.model_dump(exclude_unset=True)
            }
        )

        # Формирование response с computed fields
        computed = calculate_computed_fields(storage_element)
        item_dict = {
            **{c.name: getattr(storage_element, c.name) for c in StorageElement.__table__.columns},
            **computed
        }

        return StorageElementResponse.model_validate(item_dict)

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(
            f"Failed to update Storage Element {storage_element_id}: {e}",
            extra={"admin_username": current_admin.username}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update Storage Element"
        )


@router.delete(
    "/{storage_element_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Storage Element",
    description="Удаление Storage Element. Требуется роль SUPER_ADMIN."
)
async def delete_storage_element(
    storage_element_id: int,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_role(AdminRole.SUPER_ADMIN))
):
    """
    Удаление Storage Element.

    **Path Parameters:**
    - **storage_element_id**: ID storage element

    **Response:**
    - 204 No Content при успешном удалении

    **RBAC:** Только SUPER_ADMIN

    **Ограничения:**
    - Нельзя удалить storage element с файлами (file_count > 0)
    - Нельзя удалить storage element в режиме edit (должен быть переведен в другой режим)
    - Перед удалением рекомендуется перевести в режим maintenance

    **Warning:** Удаление storage element не удаляет физические файлы!
    Необходимо выполнить очистку файловой системы вручную.
    """
    try:
        # Получение Storage Element
        query = select(StorageElement).where(StorageElement.id == storage_element_id)
        result = await db.execute(query)
        storage_element = result.scalar_one_or_none()

        if not storage_element:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Storage Element {storage_element_id} not found"
            )

        # Проверка: нельзя удалить storage element с файлами
        if storage_element.file_count > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Cannot delete Storage Element with {storage_element.file_count} files. "
                    "Please migrate or delete all files first."
                )
            )

        # Проверка: нельзя удалить storage element в режиме edit
        if storage_element.mode == StorageMode.EDIT:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Cannot delete Storage Element in EDIT mode. "
                    "Please change mode to RW, RO, or AR first."
                )
            )

        # Удаление Storage Element
        await db.delete(storage_element)
        await db.commit()

        logger.info(
            f"Storage Element deleted: {storage_element.name} by {current_admin.username}",
            extra={
                "storage_element_id": storage_element_id,
                "storage_element_name": storage_element.name,
                "mode": storage_element.mode.value,
                "admin_id": str(current_admin.id),
                "admin_username": current_admin.username
            }
        )

        return None

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(
            f"Failed to delete Storage Element {storage_element_id}: {e}",
            extra={"admin_username": current_admin.username}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete Storage Element"
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
