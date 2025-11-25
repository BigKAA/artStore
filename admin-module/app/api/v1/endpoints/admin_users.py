"""
Admin Users CRUD API endpoints для управления администраторами через Admin UI.

Все endpoints требуют аутентификацию через JWT (Admin User).
Большинство операций требует роль SUPER_ADMIN.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
import logging

from app.api.dependencies.admin_auth import get_current_admin_user, require_role
from app.core.database import get_db
from app.models.admin_user import AdminUser, AdminRole
from app.services.admin_user_service import (
    AdminUserService,
    AdminUserServiceError,
    AdminUserNotFoundError,
    AdminUserAlreadyExistsError,
    SystemAdminProtectedError,
    InsufficientPermissionsError
)
from app.schemas.admin_user import (
    AdminUserCreateRequest,
    AdminUserUpdateRequest,
    AdminUserPasswordResetRequest,
    AdminUserResponse,
    AdminUserListResponse,
    AdminUserDeleteResponse,
    AdminUserPasswordResetResponse
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin-users",
    responses={
        401: {"description": "Unauthorized - Invalid or missing JWT token"},
        403: {"description": "Forbidden - Insufficient permissions"}
    }
)


@router.post(
    "/",
    response_model=AdminUserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create new admin user",
    description="Create a new administrator (SUPER_ADMIN only)",
    responses={
        201: {"description": "Admin user created successfully"},
        400: {"description": "Validation error or user already exists"},
        403: {"description": "Only SUPER_ADMIN can create admin users"}
    }
)
async def create_admin_user(
    request: AdminUserCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_role(AdminRole.SUPER_ADMIN))
):
    """
    Создать нового администратора.

    **Требования**:
    - Роль SUPER_ADMIN
    - JWT токен в Authorization header

    **Валидация**:
    - Username: 3-100 символов, уникальный, латиница + цифры + дефис + underscore
    - Email: валидный email, уникальный
    - Password: минимум 8 символов, заглавная буква, строчная буква, цифра
    - Role: super_admin | admin | readonly

    **Примеры**:
    ```bash
    curl -X POST http://localhost:8000/api/v1/admin-users/ \\
      -H "Authorization: Bearer $TOKEN" \\
      -H "Content-Type: application/json" \\
      -d '{
        "username": "john_doe",
        "email": "john.doe@artstore.local",
        "password": "SecurePassword123",
        "role": "admin",
        "enabled": true
      }'
    ```
    """
    service = AdminUserService()

    try:
        admin_user = await service.create_admin_user(db, request, current_admin)
        return admin_user

    except InsufficientPermissionsError as e:
        logger.warning(f"Permission denied for admin user creation: {e}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )

    except AdminUserAlreadyExistsError as e:
        logger.warning(f"Admin user creation failed - user exists: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    except AdminUserServiceError as e:
        logger.error(f"Admin user creation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get(
    "/",
    response_model=AdminUserListResponse,
    summary="Get admin users list",
    description="Get paginated list of administrators with optional filters",
    responses={
        200: {"description": "List of admin users"}
    }
)
async def get_admin_users_list(
    page: int = Query(1, ge=1, description="Page number (starting from 1)"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page (1-100)"),
    role: Optional[AdminRole] = Query(None, description="Filter by role"),
    enabled: Optional[bool] = Query(None, description="Filter by enabled status"),
    search: Optional[str] = Query(None, description="Search by username or email"),
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin_user)
):
    """
    Получить список администраторов с пагинацией и фильтрацией.

    **Требования**:
    - JWT токен в Authorization header
    - Любая роль (SUPER_ADMIN, ADMIN, READONLY)

    **Фильтры**:
    - `page`: Номер страницы (по умолчанию 1)
    - `page_size`: Размер страницы (по умолчанию 10, максимум 100)
    - `role`: Фильтр по роли (super_admin | admin | readonly)
    - `enabled`: Фильтр по статусу (true | false)
    - `search`: Поиск по username или email (case-insensitive)

    **Примеры**:
    ```bash
    # Все администраторы (первая страница)
    curl http://localhost:8000/api/v1/admin-users/ \\
      -H "Authorization: Bearer $TOKEN"

    # Только SUPER_ADMIN (вторая страница, 20 элементов)
    curl "http://localhost:8000/api/v1/admin-users/?page=2&page_size=20&role=super_admin" \\
      -H "Authorization: Bearer $TOKEN"

    # Поиск по username/email
    curl "http://localhost:8000/api/v1/admin-users/?search=john" \\
      -H "Authorization: Bearer $TOKEN"

    # Только активные администраторы
    curl "http://localhost:8000/api/v1/admin-users/?enabled=true" \\
      -H "Authorization: Bearer $TOKEN"
    ```
    """
    service = AdminUserService()

    try:
        admin_users = await service.get_admin_user_list(
            db=db,
            page=page,
            page_size=page_size,
            role_filter=role,
            enabled_filter=enabled,
            search_query=search
        )
        return admin_users

    except AdminUserServiceError as e:
        logger.error(f"Admin user list retrieval failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve admin users list"
        )


@router.get(
    "/{admin_id}",
    response_model=AdminUserResponse,
    summary="Get admin user by ID",
    description="Get detailed information about specific administrator",
    responses={
        200: {"description": "Admin user information"},
        404: {"description": "Admin user not found"}
    }
)
async def get_admin_user_by_id(
    admin_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin_user)
):
    """
    Получить информацию об администраторе по ID.

    **Требования**:
    - JWT токен в Authorization header
    - Любая роль (SUPER_ADMIN, ADMIN, READONLY)

    **Примеры**:
    ```bash
    curl http://localhost:8000/api/v1/admin-users/550e8400-e29b-41d4-a716-446655440000 \\
      -H "Authorization: Bearer $TOKEN"
    ```
    """
    service = AdminUserService()

    try:
        admin_user = await service.get_admin_user_by_id(db, admin_id)
        return admin_user

    except AdminUserNotFoundError as e:
        logger.warning(f"Admin user not found: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

    except AdminUserServiceError as e:
        logger.error(f"Admin user retrieval failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve admin user"
        )


@router.put(
    "/{admin_id}",
    response_model=AdminUserResponse,
    summary="Update admin user",
    description="Update administrator information (SUPER_ADMIN only)",
    responses={
        200: {"description": "Admin user updated successfully"},
        400: {"description": "Validation error or email already exists"},
        403: {"description": "Only SUPER_ADMIN can update admin users or system admin protected"},
        404: {"description": "Admin user not found"}
    }
)
async def update_admin_user(
    admin_id: uuid.UUID,
    request: AdminUserUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_role(AdminRole.SUPER_ADMIN))
):
    """
    Обновить администратора.

    **Требования**:
    - Роль SUPER_ADMIN
    - JWT токен в Authorization header

    **Обновляемые поля**:
    - `email`: Новый email (должен быть уникальным)
    - `role`: Новая роль (super_admin | admin | readonly)
    - `enabled`: Статус активности (true | false)

    **Ограничения**:
    - Системный администратор (is_system=true) не может быть изменен
    - Все поля опциональные - обновляются только указанные

    **Примеры**:
    ```bash
    # Изменить роль
    curl -X PUT http://localhost:8000/api/v1/admin-users/550e8400-e29b-41d4-a716-446655440000 \\
      -H "Authorization: Bearer $TOKEN" \\
      -H "Content-Type: application/json" \\
      -d '{"role": "readonly"}'

    # Отключить аккаунт
    curl -X PUT http://localhost:8000/api/v1/admin-users/550e8400-e29b-41d4-a716-446655440000 \\
      -H "Authorization: Bearer $TOKEN" \\
      -H "Content-Type: application/json" \\
      -d '{"enabled": false}'

    # Обновить email и роль
    curl -X PUT http://localhost:8000/api/v1/admin-users/550e8400-e29b-41d4-a716-446655440000 \\
      -H "Authorization: Bearer $TOKEN" \\
      -H "Content-Type: application/json" \\
      -d '{"email": "new.email@artstore.local", "role": "admin"}'
    ```
    """
    service = AdminUserService()

    try:
        admin_user = await service.update_admin_user(db, admin_id, request, current_admin)
        return admin_user

    except InsufficientPermissionsError as e:
        logger.warning(f"Permission denied for admin user update: {e}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )

    except AdminUserNotFoundError as e:
        logger.warning(f"Admin user not found: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

    except SystemAdminProtectedError as e:
        logger.warning(f"System admin protection: {e}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )

    except AdminUserAlreadyExistsError as e:
        logger.warning(f"Admin user update failed - email exists: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    except AdminUserServiceError as e:
        logger.error(f"Admin user update failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete(
    "/{admin_id}",
    response_model=AdminUserDeleteResponse,
    summary="Delete admin user",
    description="Delete administrator (SUPER_ADMIN only)",
    responses={
        200: {"description": "Admin user deleted successfully"},
        403: {"description": "Only SUPER_ADMIN can delete admin users or system admin protected"},
        404: {"description": "Admin user not found"}
    }
)
async def delete_admin_user(
    admin_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_role(AdminRole.SUPER_ADMIN))
):
    """
    Удалить администратора.

    **Требования**:
    - Роль SUPER_ADMIN
    - JWT токен в Authorization header

    **Ограничения**:
    - Системный администратор (is_system=true) не может быть удален
    - Нельзя удалить самого себя

    **Примеры**:
    ```bash
    curl -X DELETE http://localhost:8000/api/v1/admin-users/550e8400-e29b-41d4-a716-446655440000 \\
      -H "Authorization: Bearer $TOKEN"
    ```
    """
    service = AdminUserService()

    try:
        result = await service.delete_admin_user(db, admin_id, current_admin)
        return result

    except InsufficientPermissionsError as e:
        logger.warning(f"Permission denied for admin user deletion: {e}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )

    except AdminUserNotFoundError as e:
        logger.warning(f"Admin user not found: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

    except SystemAdminProtectedError as e:
        logger.warning(f"System admin protection: {e}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )

    except AdminUserServiceError as e:
        logger.error(f"Admin user deletion failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post(
    "/{admin_id}/reset-password",
    response_model=AdminUserPasswordResetResponse,
    summary="Reset admin user password",
    description="Reset administrator password (SUPER_ADMIN only)",
    responses={
        200: {"description": "Password reset successfully"},
        400: {"description": "Password validation failed"},
        403: {"description": "Only SUPER_ADMIN can reset passwords or system admin protected"},
        404: {"description": "Admin user not found"}
    }
)
async def reset_admin_password(
    admin_id: uuid.UUID,
    request: AdminUserPasswordResetRequest,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_role(AdminRole.SUPER_ADMIN))
):
    """
    Сбросить пароль администратора (SUPER_ADMIN only).

    **Требования**:
    - Роль SUPER_ADMIN
    - JWT токен в Authorization header

    **Валидация пароля**:
    - Минимум 8 символов
    - Минимум одна заглавная буква
    - Минимум одна строчная буква
    - Минимум одна цифра

    **Эффекты**:
    - Пароль обновляется
    - Сбрасывается блокировка аккаунта (если была)
    - Сбрасывается счетчик неудачных попыток логина
    - Обновляется история паролей

    **Ограничения**:
    - Системный администратор (is_system=true) не может быть изменен другими администраторами

    **Примеры**:
    ```bash
    curl -X POST http://localhost:8000/api/v1/admin-users/550e8400-e29b-41d4-a716-446655440000/reset-password \\
      -H "Authorization: Bearer $TOKEN" \\
      -H "Content-Type: application/json" \\
      -d '{"new_password": "NewSecurePassword123"}'
    ```
    """
    service = AdminUserService()

    try:
        result = await service.reset_admin_password(db, admin_id, request, current_admin)
        return result

    except InsufficientPermissionsError as e:
        logger.warning(f"Permission denied for password reset: {e}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )

    except AdminUserNotFoundError as e:
        logger.warning(f"Admin user not found: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

    except SystemAdminProtectedError as e:
        logger.warning(f"System admin protection: {e}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )

    except AdminUserServiceError as e:
        logger.error(f"Password reset failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
