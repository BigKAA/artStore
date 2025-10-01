"""
API endpoints для управления пользователями.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.config import settings
from app.db.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.user import UserCreate, UserResponse, UserUpdate
from app.services.audit_service import audit_service
from app.services.user_service import user_service
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("", response_model=PaginatedResponse)
async def list_users(
    page: int = Query(1, ge=1, description="Номер страницы"),
    size: int = Query(20, ge=1, le=100, description="Размер страницы"),
    search: Optional[str] = Query(None, description="Поиск по username, email, full_name"),
    is_active: Optional[bool] = Query(None, description="Фильтр по статусу активности"),
    is_admin: Optional[bool] = Query(None, description="Фильтр по роли администратора"),
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin_user),
) -> Dict[str, Any]:
    """
    Получение списка пользователей с пагинацией и фильтрацией.

    **Требует**: Роль admin

    **Args**:
    - **page**: Номер страницы (начиная с 1)
    - **size**: Количество элементов на странице (1-100)
    - **search**: Текст для поиска в username, email, full_name
    - **is_active**: Фильтр по активности (true/false)
    - **is_admin**: Фильтр по роли администратора (true/false)

    **Returns**:
    - Список пользователей с пагинацией

    **Errors**:
    - **401**: Не аутентифицирован
    - **403**: Недостаточно прав
    """
    users, total = await user_service.get_users(
        db,
        skip=(page - 1) * size,
        limit=size,
        search=search,
        is_active=is_active,
        is_admin=is_admin,
    )

    return {
        "items": [
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "last_name": u.last_name,
                "first_name": u.first_name,
                "middle_name": u.middle_name,
                "is_admin": u.is_admin,
                "is_active": u.is_active,
                "is_system": u.is_system,
                "auth_provider": u.auth_provider,
                "description": u.description,
                "created_at": u.created_at,
                "updated_at": u.updated_at,
            }
            for u in users
        ],
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size if total > 0 else 0,
    }


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin_user),
) -> Dict[str, Any]:
    """
    Получение пользователя по ID.

    **Требует**: Роль admin

    **Args**:
    - **user_id**: ID пользователя (UUID)

    **Returns**:
    - Информация о пользователе

    **Errors**:
    - **401**: Не аутентифицирован
    - **403**: Недостаточно прав
    - **404**: Пользователь не найден
    """
    user = await user_service.get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден"
        )

    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "last_name": user.last_name,
        "first_name": user.first_name,
        "middle_name": user.middle_name,
        "is_admin": user.is_admin,
        "is_active": user.is_active,
        "is_system": user.is_system,
        "auth_provider": user.auth_provider,
        "external_id": user.external_id,
        "description": user.description,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "last_synced_at": user.last_synced_at,
    }


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin_user),
) -> Dict[str, Any]:
    """
    Создание нового пользователя.

    **Требует**: Роль admin

    **Args**:
    - **username**: Имя пользователя (уникальное)
    - **email**: Email (уникальный)
    - **password**: Пароль (минимум 8 символов)
    - **last_name**: Фамилия
    - **first_name**: Имя
    - **middle_name**: Отчество (опционально)
    - **is_admin**: Является ли администратором (по умолчанию false)
    - **description**: Описание пользователя (опционально)

    **Returns**:
    - Созданный пользователь

    **Errors**:
    - **400**: Пользователь уже существует или слабый пароль
    - **401**: Не аутентифицирован
    - **403**: Недостаточно прав
    """
    try:
        user = await user_service.create_user(
            db,
            username=user_data.username,
            email=user_data.email,
            password=user_data.password,
            last_name=user_data.last_name,
            first_name=user_data.first_name,
            middle_name=user_data.middle_name,
            is_admin=user_data.is_admin,
            description=user_data.description,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Логируем создание пользователя
    await audit_service.log_action(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        action="user_created",
        resource_type="user",
        resource_id=user.id,
        details={"username": user.username, "is_admin": user.is_admin},
        success=True,
    )

    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "last_name": user.last_name,
        "first_name": user.first_name,
        "middle_name": user.middle_name,
        "is_admin": user.is_admin,
        "is_active": user.is_active,
        "is_system": user.is_system,
        "auth_provider": user.auth_provider,
        "description": user.description,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    user_data: UserUpdate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin_user),
) -> Dict[str, Any]:
    """
    Обновление пользователя.

    **Требует**: Роль admin

    **Args**:
    - **user_id**: ID пользователя (UUID)
    - **email**: Новый email (опционально)
    - **last_name**: Новая фамилия (опционально)
    - **first_name**: Новое имя (опционально)
    - **middle_name**: Новое отчество (опционально)
    - **is_admin**: Новая роль администратора (опционально)
    - **is_active**: Новый статус активности (опционально)
    - **description**: Новое описание (опционально)

    **Returns**:
    - Обновленный пользователь

    **Errors**:
    - **400**: Email уже используется
    - **401**: Не аутентифицирован
    - **403**: Недостаточно прав или попытка изменить системного администратора
    - **404**: Пользователь не найден
    """
    user = await user_service.get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден"
        )

    # Проверка защиты системного администратора
    if user.is_system and settings.security.protect_default_admin:
        # Системному администратору нельзя убрать права администратора или деактивировать
        if user_data.is_admin is False:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Невозможно убрать права администратора у системного пользователя",
            )
        if user_data.is_active is False:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Невозможно деактивировать системного администратора",
            )

    try:
        updated_user = await user_service.update_user(db, user_id, user_data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Логируем обновление
    await audit_service.log_action(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        action="user_updated",
        resource_type="user",
        resource_id=user_id,
        details=user_data.model_dump(exclude_unset=True),
        success=True,
    )

    return {
        "id": updated_user.id,
        "username": updated_user.username,
        "email": updated_user.email,
        "last_name": updated_user.last_name,
        "first_name": updated_user.first_name,
        "middle_name": updated_user.middle_name,
        "is_admin": updated_user.is_admin,
        "is_active": updated_user.is_active,
        "is_system": updated_user.is_system,
        "auth_provider": updated_user.auth_provider,
        "description": updated_user.description,
        "created_at": updated_user.created_at,
        "updated_at": updated_user.updated_at,
    }


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin_user),
):
    """
    Удаление пользователя.

    **Требует**: Роль admin

    **Note**: Системный администратор не может быть удален.

    **Args**:
    - **user_id**: ID пользователя (UUID)

    **Errors**:
    - **401**: Не аутентифицирован
    - **403**: Недостаточно прав или попытка удалить системного администратора
    - **404**: Пользователь не найден
    """
    user = await user_service.get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден"
        )

    # Проверка защиты системного администратора
    if user.is_system and settings.security.protect_default_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Невозможно удалить системного администратора",
        )

    # Нельзя удалить самого себя
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Невозможно удалить собственную учетную запись",
        )

    await user_service.delete_user(db, user_id)

    # Логируем удаление
    await audit_service.log_action(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        action="user_deleted",
        resource_type="user",
        resource_id=user_id,
        details={"username": user.username},
        success=True,
    )

    return None
