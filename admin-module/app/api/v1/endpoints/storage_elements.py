"""
API endpoints для управления Storage Elements.

Предоставляет REST API для управления Storage Elements с auto-discovery:
- Discovery нового Storage Element по URL
- Создание Storage Element с автоматическим получением информации
- Синхронизация данных Storage Element
- Получение списка Storage Elements с фильтрацией и пагинацией
- Получение детальной информации о Storage Element
- Обновление Storage Element (SUPER_ADMIN only)
- Удаление Storage Element (SUPER_ADMIN only)
- Мониторинг статуса и метрик использования

ВАЖНО: Mode Storage Element определяется ТОЛЬКО его конфигурацией при запуске.
       Изменить mode можно только через изменение конфигурации и перезапуск storage element.
       Admin Module НЕ МОЖЕТ изменять mode через API.

RBAC: Доступно всем аутентифицированным админам для чтения
      SUPER_ADMIN требуется для write операций (создание, обновление, удаление)

Sprint 19 Phase 2: Auto-discovery implementation
"""

import logging
from datetime import datetime
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
    StorageElementUpdate,
    StorageElementDiscoverRequest,
    StorageElementDiscoverResponse,
    StorageElementSyncResponse,
    StorageElementSyncAllResponse
)
from app.services.storage_discovery_service import (
    storage_discovery_service,
    StorageElementDiscoveryResult
)
from app.services.storage_sync_service import storage_sync_service
from app.services.storage_element_publish_service import storage_element_publish_service
from app.core.exceptions import (
    StorageElementDiscoveryError,
    StorageElementAlreadyExistsError
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


def _discovery_result_to_response(
    result: StorageElementDiscoveryResult,
    already_registered: bool = False,
    existing_id: Optional[int] = None
) -> StorageElementDiscoverResponse:
    """
    Преобразование результата discovery в response модель.

    Args:
        result: Результат discovery от storage element
        already_registered: Флаг - уже зарегистрирован в системе
        existing_id: ID существующего storage element (если зарегистрирован)

    Returns:
        StorageElementDiscoverResponse: Модель для API response
    """
    capacity_gb = result.capacity_bytes / (1024**3)
    used_gb = result.used_bytes / (1024**3)
    usage_percent = (result.used_bytes / result.capacity_bytes * 100) if result.capacity_bytes > 0 else None

    return StorageElementDiscoverResponse(
        name=result.name,
        display_name=result.display_name,
        version=result.version,
        mode=result.mode,
        storage_type=result.storage_type,
        base_path=result.base_path,
        capacity_bytes=result.capacity_bytes,
        used_bytes=result.used_bytes,
        file_count=result.file_count,
        status=result.status,
        api_url=result.api_url,
        capacity_gb=round(capacity_gb, 2),
        used_gb=round(used_gb, 2),
        usage_percent=round(usage_percent, 2) if usage_percent else None,
        already_registered=already_registered,
        existing_id=existing_id
    )


# =============================================================================
# Discovery и Sync endpoints (должны быть перед динамическими маршрутами)
# =============================================================================

@router.post(
    "/discover",
    response_model=StorageElementDiscoverResponse,
    summary="Discover Storage Element by URL",
    description=(
        "Получение информации о Storage Element по его URL без регистрации. "
        "Используйте этот endpoint для preview перед добавлением в систему."
    )
)
async def discover_storage_element(
    request: StorageElementDiscoverRequest,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin_user)
):
    """
    Discovery Storage Element по URL.

    Выполняет запрос к /api/v1/info endpoint storage element
    и возвращает полученную информацию. Не создает записи в БД.

    **Request Body:**
    - **api_url**: URL API storage element

    **Response:**
    - Полная информация о storage element
    - Флаг already_registered если уже зарегистрирован

    **RBAC:** Доступно всем аутентифицированным админам

    **Errors:**
    - 400: Storage element недоступен или невалидный ответ
    - 408: Timeout при подключении
    """
    try:
        # Выполняем discovery
        result = await storage_discovery_service.discover_storage_element(request.api_url)

        # Проверяем, зарегистрирован ли уже этот storage element
        existing_query = select(StorageElement).where(
            StorageElement.api_url == result.api_url
        )
        existing_result = await db.execute(existing_query)
        existing = existing_result.scalar_one_or_none()

        already_registered = existing is not None
        existing_id = existing.id if existing else None

        logger.info(
            f"Discovery performed for {result.api_url} by {current_admin.username}",
            extra={
                "api_url": result.api_url,
                "storage_name": result.display_name,
                "mode": result.mode,
                "already_registered": already_registered,
                "admin_username": current_admin.username
            }
        )

        return _discovery_result_to_response(result, already_registered, existing_id)

    except StorageElementDiscoveryError as e:
        logger.warning(
            f"Discovery failed for {request.api_url}: {e}",
            extra={
                "api_url": request.api_url,
                "admin_username": current_admin.username
            }
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post(
    "/sync/{storage_element_id}",
    response_model=StorageElementSyncResponse,
    summary="Sync Storage Element",
    description=(
        "Ручная синхронизация данных Storage Element с актуальными значениями. "
        "Обновляет: mode, capacity, used_bytes, file_count, status."
    )
)
async def sync_storage_element(
    storage_element_id: int,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin_user)
):
    """
    Ручная синхронизация Storage Element.

    Выполняет запрос к storage element и обновляет данные в БД.
    Синхронизируются: mode, capacity_bytes, used_bytes, file_count, status.

    **Path Parameters:**
    - **storage_element_id**: ID storage element

    **Response:**
    - Результат синхронизации с списком изменений

    **RBAC:** Доступно всем аутентифицированным админам
    """
    try:
        sync_result = await storage_sync_service.sync_storage_element(
            storage_element_id=storage_element_id,
            db=db
        )

        # Формируем список изменений в читаемом виде
        changes_list = [
            f"{change.field}: {change.old_value} → {change.new_value}"
            for change in sync_result.changes
        ]

        logger.info(
            f"Storage Element {storage_element_id} synced by {current_admin.username}",
            extra={
                "storage_element_id": storage_element_id,
                "success": sync_result.success,
                "changes_count": len(sync_result.changes),
                "admin_username": current_admin.username
            }
        )

        # Публикуем обновленную конфигурацию в Redis для Service Discovery
        # Получаем storage element для публикации
        query = select(StorageElement).where(StorageElement.id == storage_element_id)
        result = await db.execute(query)
        storage_element = result.scalar_one_or_none()
        if storage_element:
            await storage_element_publish_service.publish_on_sync(db, storage_element)

        return StorageElementSyncResponse(
            storage_element_id=sync_result.storage_element_id,
            name=sync_result.name,
            success=sync_result.success,
            changes=changes_list,
            error_message=sync_result.error_message,
            synced_at=sync_result.synced_at
        )

    except Exception as e:
        logger.error(
            f"Failed to sync Storage Element {storage_element_id}: {e}",
            extra={"admin_username": current_admin.username}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync Storage Element: {e}"
        )


@router.post(
    "/sync-all",
    response_model=StorageElementSyncAllResponse,
    summary="Sync all Storage Elements",
    description="Массовая синхронизация всех Storage Elements."
)
async def sync_all_storage_elements(
    only_online: bool = Query(
        default=True,
        description="Синхронизировать только ONLINE storage elements"
    ),
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_role(AdminRole.SUPER_ADMIN))
):
    """
    Массовая синхронизация всех Storage Elements.

    **Query Parameters:**
    - **only_online**: Синхронизировать только ONLINE (default: true)

    **Response:**
    - Сводка по синхронизации всех storage elements

    **RBAC:** Только SUPER_ADMIN
    """
    try:
        results = await storage_sync_service.sync_all_storage_elements(
            db=db,
            only_online=only_online
        )

        # Формируем response
        response_results = []
        synced_count = 0
        failed_count = 0

        for result in results:
            changes_list = [
                f"{change.field}: {change.old_value} → {change.new_value}"
                for change in result.changes
            ]

            response_results.append(StorageElementSyncResponse(
                storage_element_id=result.storage_element_id,
                name=result.name,
                success=result.success,
                changes=changes_list,
                error_message=result.error_message,
                synced_at=result.synced_at
            ))

            if result.success:
                synced_count += 1
            else:
                failed_count += 1

        logger.info(
            f"Mass sync completed by {current_admin.username}: "
            f"{synced_count} synced, {failed_count} failed",
            extra={
                "total": len(results),
                "synced": synced_count,
                "failed": failed_count,
                "admin_username": current_admin.username
            }
        )

        # Публикуем обновленную конфигурацию в Redis для Service Discovery
        # после массовой синхронизации - публикуем без конкретного storage element
        await storage_element_publish_service.publish_on_sync(db)

        return StorageElementSyncAllResponse(
            total=len(results),
            synced=synced_count,
            failed=failed_count,
            results=response_results
        )

    except Exception as e:
        logger.error(
            f"Failed to sync all Storage Elements: {e}",
            extra={"admin_username": current_admin.username}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync Storage Elements: {e}"
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


# =============================================================================
# CRUD endpoints
# =============================================================================

@router.post(
    "/",
    response_model=StorageElementResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create new Storage Element with auto-discovery",
    description=(
        "Создание нового Storage Element с автоматическим получением информации. "
        "Требуется только URL - mode, storage_type, base_path, capacity получаются автоматически. "
        "Требуется роль SUPER_ADMIN."
    )
)
async def create_storage_element(
    request: StorageElementCreate,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_role(AdminRole.SUPER_ADMIN))
):
    """
    Создание нового Storage Element с auto-discovery.

    При создании выполняется автоматический discovery storage element
    для получения: mode, storage_type, base_path, capacity_bytes, used_bytes, file_count.

    **Request Body:**
    - **api_url**: URL API storage element (ОБЯЗАТЕЛЬНО)
    - **name**: Название (опционально - если не указано, используется из discovery)
    - **description**: Описание назначения (опционально)
    - **api_key**: API ключ для аутентификации (опционально)
    - **retention_days**: Срок хранения в днях (опционально)
    - **is_replicated**: Флаг репликации (default: false)
    - **replica_count**: Количество реплик (default: 0)

    **Auto-discovered fields (НЕ указываются в запросе):**
    - mode: Режим работы (edit/rw/ro/ar)
    - storage_type: Тип хранилища (local/s3)
    - base_path: Базовый путь
    - capacity_bytes: Емкость
    - used_bytes: Использовано
    - file_count: Количество файлов

    **Response:**
    - Storage Element с вычисленными метриками

    **RBAC:** Только SUPER_ADMIN

    **Errors:**
    - 400: Storage element недоступен или невалидный ответ
    - 409: Storage element с таким URL уже зарегистрирован
    """
    try:
        # Проверка уникальности api_url перед discovery
        url_query = select(StorageElement).where(StorageElement.api_url == request.api_url)
        url_result = await db.execute(url_query)
        if url_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Storage Element with api_url '{request.api_url}' already exists"
            )

        # Выполняем discovery для получения информации
        try:
            discovery_result = await storage_discovery_service.discover_storage_element(
                request.api_url
            )
        except StorageElementDiscoveryError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to discover storage element: {e}"
            )

        # Определяем name: из запроса или из discovery
        name = request.name if request.name else discovery_result.display_name

        # Проверка уникальности name
        existing_query = select(StorageElement).where(StorageElement.name == name)
        existing_result = await db.execute(existing_query)
        if existing_result.scalar_one_or_none():
            # Если имя из discovery занято, добавляем суффикс
            if not request.name:
                timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
                name = f"{discovery_result.display_name}_{timestamp}"
            else:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Storage Element with name '{name}' already exists"
                )

        # Преобразуем mode и storage_type в enum
        try:
            mode = StorageMode(discovery_result.mode)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid mode from storage element: {discovery_result.mode}"
            )

        try:
            storage_type = StorageType(discovery_result.storage_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid storage_type from storage element: {discovery_result.storage_type}"
            )

        # Создание Storage Element с данными из discovery
        storage_element = StorageElement(
            name=name,
            description=request.description,
            # Данные из discovery (read-only из конфигурации storage element)
            mode=mode,
            storage_type=storage_type,
            base_path=discovery_result.base_path,
            capacity_bytes=discovery_result.capacity_bytes,
            used_bytes=discovery_result.used_bytes,
            file_count=discovery_result.file_count,
            # Данные из запроса
            api_url=discovery_result.api_url,  # Нормализованный URL
            api_key=request.api_key,
            retention_days=request.retention_days,
            is_replicated=request.is_replicated,
            replica_count=request.replica_count,
            # Автоматически устанавливаемые значения
            status=StorageStatus.ONLINE,
            last_health_check=datetime.utcnow()
        )

        db.add(storage_element)
        await db.commit()
        await db.refresh(storage_element)

        logger.info(
            f"Storage Element created via auto-discovery: {name} by {current_admin.username}",
            extra={
                "storage_element_id": storage_element.id,
                "storage_element_name": storage_element.name,
                "api_url": storage_element.api_url,
                "mode": storage_element.mode.value,
                "storage_type": storage_element.storage_type.value,
                "admin_id": str(current_admin.id),
                "admin_username": current_admin.username
            }
        )

        # Публикуем обновленную конфигурацию в Redis для Service Discovery
        await storage_element_publish_service.publish_on_create(db, storage_element)

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
    description=(
        "Обновление параметров Storage Element. Требуется роль SUPER_ADMIN. "
        "ВАЖНО: Mode НЕ может быть изменен через API - только через конфигурацию storage element."
    )
)
async def update_storage_element(
    storage_element_id: int,
    request: StorageElementUpdate,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_role(AdminRole.SUPER_ADMIN))
):
    """
    Обновление параметров Storage Element.

    **ВАЖНО:** Mode НЕ может быть изменен через API!
    Mode определяется конфигурацией storage element при запуске.
    Для изменения mode необходимо изменить конфигурацию storage element и перезапустить его.

    **Path Parameters:**
    - **storage_element_id**: ID storage element

    **Request Body (все поля опциональны):**
    - **name**: Новое название (уникальное, 3-100 символов)
    - **description**: Новое описание (до 500 символов)
    - **api_url**: Новый URL API
    - **api_key**: Новый API ключ
    - **status**: Новый статус (online/offline/degraded/maintenance)
    - **retention_days**: Новый срок хранения в днях (>= 1)
    - **replica_count**: Новое количество реплик (>= 0)

    **Неизменяемые поля (управляются storage element):**
    - mode: Определяется конфигурацией storage element
    - storage_type: Определяется при создании
    - base_path: Определяется конфигурацией storage element
    - capacity_bytes: Синхронизируется из storage element
    - used_bytes: Синхронизируется из storage element
    - file_count: Синхронизируется из storage element

    **Response:**
    - Storage Element с обновленными параметрами и вычисленными метриками

    **RBAC:** Только SUPER_ADMIN
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

        # Обновление разрешенных полей (mode ИСКЛЮЧЕН)
        if request.description is not None:
            storage_element.description = request.description
        if request.api_key is not None:
            storage_element.api_key = request.api_key
        if request.status:
            storage_element.status = request.status
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

        # Публикуем обновленную конфигурацию в Redis для Service Discovery
        await storage_element_publish_service.publish_on_update(db, storage_element)

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

        # Сохраняем имя для публикации (объект будет удален)
        deleted_name = storage_element.name

        # Удаление Storage Element
        await db.delete(storage_element)
        await db.commit()

        logger.info(
            f"Storage Element deleted: {deleted_name} by {current_admin.username}",
            extra={
                "storage_element_id": storage_element_id,
                "storage_element_name": deleted_name,
                "mode": storage_element.mode.value,
                "admin_id": str(current_admin.id),
                "admin_username": current_admin.username
            }
        )

        # Публикуем обновленную конфигурацию в Redis для Service Discovery
        await storage_element_publish_service.publish_on_delete(
            db, storage_element_id, deleted_name
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
