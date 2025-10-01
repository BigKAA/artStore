"""
API endpoints для управления элементами хранения (storage elements).
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.db.models.storage_element import StorageElement, StorageMode
from app.db.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.storage_element import (
    StorageElementChangeModeRequest,
    StorageElementCreate,
    StorageElementResponse,
    StorageElementUpdate,
)
from app.services.audit_service import audit_service
from app.services.redis_service import redis_service
from app.services.storage_service import storage_service
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("", response_model=PaginatedResponse)
async def list_storage_elements(
    page: int = Query(1, ge=1, description="Номер страницы"),
    size: int = Query(20, ge=1, le=100, description="Размер страницы"),
    search: Optional[str] = Query(None, description="Поиск по имени и описанию"),
    mode: Optional[StorageMode] = Query(None, description="Фильтр по режиму"),
    is_active: Optional[bool] = Query(None, description="Фильтр по статусу активности"),
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin_user),
) -> Dict[str, Any]:
    """
    Получение списка элементов хранения с пагинацией и фильтрацией.

    **Требует**: Роль admin

    **Args**:
    - **page**: Номер страницы (начиная с 1)
    - **size**: Количество элементов на странице (1-100)
    - **search**: Текст для поиска в имени и описании
    - **mode**: Фильтр по режиму работы (edit, rw, ro, ar)
    - **is_active**: Фильтр по активности (true/false)

    **Returns**:
    - Список элементов хранения с пагинацией

    **Errors**:
    - **401**: Не аутентифицирован
    - **403**: Недостаточно прав
    """
    elements, total = await storage_service.get_storage_elements(
        db,
        skip=(page - 1) * size,
        limit=size,
        search=search,
        mode=mode,
        is_active=is_active,
    )

    return {
        "items": [
            {
                "id": el.id,
                "name": el.name,
                "description": el.description,
                "mode": el.mode,
                "base_url": el.base_url,
                "health_check_url": el.health_check_url,
                "storage_type": el.storage_type,
                "max_size_gb": el.max_size_gb,
                "retention_days": el.retention_days,
                "is_active": el.is_active,
                "can_write": el.can_write,
                "can_delete": el.can_delete,
                "is_archived": el.is_archived,
                "metadata": el.metadata,
                "created_at": el.created_at,
                "updated_at": el.updated_at,
            }
            for el in elements
        ],
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size if total > 0 else 0,
    }


@router.get("/{element_id}", response_model=StorageElementResponse)
async def get_storage_element(
    element_id: str,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin_user),
) -> Dict[str, Any]:
    """
    Получение элемента хранения по ID.

    **Требует**: Роль admin

    **Args**:
    - **element_id**: ID элемента хранения (UUID)

    **Returns**:
    - Информация об элементе хранения

    **Errors**:
    - **401**: Не аутентифицирован
    - **403**: Недостаточно прав
    - **404**: Элемент хранения не найден
    """
    element = await storage_service.get_storage_element_by_id(db, element_id)
    if element is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Элемент хранения не найден",
        )

    return {
        "id": element.id,
        "name": element.name,
        "description": element.description,
        "mode": element.mode,
        "base_url": element.base_url,
        "health_check_url": element.health_check_url,
        "storage_type": element.storage_type,
        "max_size_gb": element.max_size_gb,
        "retention_days": element.retention_days,
        "is_active": element.is_active,
        "can_write": element.can_write,
        "can_delete": element.can_delete,
        "is_archived": element.is_archived,
        "metadata": element.metadata,
        "created_at": element.created_at,
        "updated_at": element.updated_at,
    }


@router.post("", response_model=StorageElementResponse, status_code=status.HTTP_201_CREATED)
async def create_storage_element(
    element_data: StorageElementCreate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin_user),
) -> Dict[str, Any]:
    """
    Создание нового элемента хранения.

    **Требует**: Роль admin

    **Args**:
    - **name**: Имя элемента (уникальное)
    - **description**: Описание (опционально)
    - **mode**: Режим работы (edit, rw, ro, ar)
    - **base_url**: URL для доступа
    - **health_check_url**: URL для health check (опционально)
    - **storage_type**: Тип хранения (local или s3)
    - **max_size_gb**: Максимальный размер в ГБ (опционально)
    - **retention_days**: Срок хранения в днях (по умолчанию 0 = без ограничений)
    - **metadata**: Дополнительные метаданные JSON (опционально)

    **Returns**:
    - Созданный элемент хранения

    **Errors**:
    - **400**: Элемент с таким именем уже существует
    - **401**: Не аутентифицирован
    - **403**: Недостаточно прав
    """
    try:
        element = await storage_service.create_storage_element(db, element_data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Публикуем в Redis для Service Discovery
    await redis_service.publish_storage_element(element)

    # Логируем создание
    await audit_service.log_action(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        action="storage_element_created",
        resource_type="storage_element",
        resource_id=element.id,
        details={"name": element.name, "mode": element.mode.value},
        success=True,
    )

    return {
        "id": element.id,
        "name": element.name,
        "description": element.description,
        "mode": element.mode,
        "base_url": element.base_url,
        "health_check_url": element.health_check_url,
        "storage_type": element.storage_type,
        "max_size_gb": element.max_size_gb,
        "retention_days": element.retention_days,
        "is_active": element.is_active,
        "can_write": element.can_write,
        "can_delete": element.can_delete,
        "is_archived": element.is_archived,
        "metadata": element.metadata,
        "created_at": element.created_at,
        "updated_at": element.updated_at,
    }


@router.patch("/{element_id}", response_model=StorageElementResponse)
async def update_storage_element(
    element_id: str,
    element_data: StorageElementUpdate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin_user),
) -> Dict[str, Any]:
    """
    Обновление элемента хранения.

    **Требует**: Роль admin

    **Args**:
    - **element_id**: ID элемента хранения (UUID)
    - **description**: Новое описание (опционально)
    - **base_url**: Новый URL (опционально)
    - **health_check_url**: Новый health check URL (опционально)
    - **max_size_gb**: Новый максимальный размер (опционально)
    - **retention_days**: Новый срок хранения (опционально)
    - **is_active**: Новый статус активности (опционально)
    - **metadata**: Новые метаданные (опционально)

    **Returns**:
    - Обновленный элемент хранения

    **Errors**:
    - **400**: Некорректные данные
    - **401**: Не аутентифицирован
    - **403**: Недостаточно прав
    - **404**: Элемент хранения не найден
    """
    element = await storage_service.get_storage_element_by_id(db, element_id)
    if element is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Элемент хранения не найден",
        )

    try:
        updated_element = await storage_service.update_storage_element(
            db, element_id, element_data
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Публикуем обновление в Redis
    await redis_service.publish_storage_element(updated_element)

    # Логируем обновление
    await audit_service.log_action(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        action="storage_element_updated",
        resource_type="storage_element",
        resource_id=element_id,
        details=element_data.model_dump(exclude_unset=True),
        success=True,
    )

    return {
        "id": updated_element.id,
        "name": updated_element.name,
        "description": updated_element.description,
        "mode": updated_element.mode,
        "base_url": updated_element.base_url,
        "health_check_url": updated_element.health_check_url,
        "storage_type": updated_element.storage_type,
        "max_size_gb": updated_element.max_size_gb,
        "retention_days": updated_element.retention_days,
        "is_active": updated_element.is_active,
        "can_write": updated_element.can_write,
        "can_delete": updated_element.can_delete,
        "is_archived": updated_element.is_archived,
        "metadata": updated_element.metadata,
        "created_at": updated_element.created_at,
        "updated_at": updated_element.updated_at,
    }


@router.post("/{element_id}/change-mode", response_model=StorageElementResponse)
async def change_storage_element_mode(
    element_id: str,
    mode_change: StorageElementChangeModeRequest,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin_user),
) -> Dict[str, Any]:
    """
    Изменение режима работы элемента хранения.

    **Важно**: Переходы режимов подчиняются правилам:
    - edit → НЕ МОЖЕТ быть изменен через API (только конфигурация + рестарт)
    - rw → ro (разрешено)
    - ro → ar (разрешено)
    - ar → other (только конфигурация + рестарт)

    **Требует**: Роль admin

    **Args**:
    - **element_id**: ID элемента хранения (UUID)
    - **new_mode**: Новый режим работы

    **Returns**:
    - Обновленный элемент хранения

    **Errors**:
    - **400**: Недопустимый переход режимов
    - **401**: Не аутентифицирован
    - **403**: Недостаточно прав
    - **404**: Элемент хранения не найден
    """
    element = await storage_service.get_storage_element_by_id(db, element_id)
    if element is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Элемент хранения не найден",
        )

    # Проверка допустимых переходов режимов
    current_mode = element.mode
    new_mode = mode_change.new_mode

    # Правила переходов
    if current_mode == StorageMode.EDIT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Режим EDIT не может быть изменен через API. Используйте конфигурацию.",
        )

    if current_mode == StorageMode.AR:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Режим AR не может быть изменен через API. Используйте конфигурацию.",
        )

    # Допустимые переходы: rw -> ro, ro -> ar
    valid_transitions = {
        StorageMode.RW: [StorageMode.RO],
        StorageMode.RO: [StorageMode.AR],
    }

    if new_mode not in valid_transitions.get(current_mode, []):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Недопустимый переход режима: {current_mode.value} → {new_mode.value}",
        )

    try:
        updated_element = await storage_service.change_storage_element_mode(
            db, element_id, new_mode
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Публикуем обновление в Redis
    await redis_service.publish_storage_element(updated_element)

    # Логируем изменение режима
    await audit_service.log_action(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        action="storage_element_mode_changed",
        resource_type="storage_element",
        resource_id=element_id,
        details={"old_mode": current_mode.value, "new_mode": new_mode.value},
        success=True,
    )

    return {
        "id": updated_element.id,
        "name": updated_element.name,
        "description": updated_element.description,
        "mode": updated_element.mode,
        "base_url": updated_element.base_url,
        "health_check_url": updated_element.health_check_url,
        "storage_type": updated_element.storage_type,
        "max_size_gb": updated_element.max_size_gb,
        "retention_days": updated_element.retention_days,
        "is_active": updated_element.is_active,
        "can_write": updated_element.can_write,
        "can_delete": updated_element.can_delete,
        "is_archived": updated_element.is_archived,
        "metadata": updated_element.metadata,
        "created_at": updated_element.created_at,
        "updated_at": updated_element.updated_at,
    }


@router.delete("/{element_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_storage_element(
    element_id: str,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin_user),
):
    """
    Удаление элемента хранения.

    **Требует**: Роль admin

    **Note**: Физические данные на элементе хранения НЕ удаляются.
    Удаляется только запись в Admin Module.

    **Args**:
    - **element_id**: ID элемента хранения (UUID)

    **Errors**:
    - **401**: Не аутентифицирован
    - **403**: Недостаточно прав
    - **404**: Элемент хранения не найден
    """
    element = await storage_service.get_storage_element_by_id(db, element_id)
    if element is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Элемент хранения не найден",
        )

    await storage_service.delete_storage_element(db, element_id)

    # Удаляем из Redis
    await redis_service.remove_storage_element(element_id)

    # Логируем удаление
    await audit_service.log_action(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        action="storage_element_deleted",
        resource_type="storage_element",
        resource_id=element_id,
        details={"name": element.name},
        success=True,
    )

    return None
