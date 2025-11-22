"""
Admin Authentication Endpoints для Admin UI.

Предоставляет endpoints для:
- Login (username/password → JWT tokens)
- Refresh (refresh token → new access token)
- Logout (token invalidation)
- Get current admin user info
- Change password

Отдельно от OAuth 2.0 Service Account authentication.
"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.admin_auth import (
    AdminLoginRequest,
    AdminRefreshRequest,
    AdminChangePasswordRequest,
    AdminTokenResponse,
    AdminUserResponse,
    AdminLogoutResponse,
    AdminChangePasswordResponse
)
from app.services.admin_auth_service import (
    AdminAuthService,
    InvalidCredentialsError,
    AccountLockedError,
    AccountDisabledError,
    PasswordInHistoryError
)
from app.models.admin_user import AdminUser
from app.api.dependencies.admin_auth import get_current_admin_user

router = APIRouter(prefix="/admin-auth", tags=["Admin Authentication"])


# Dependency для получения AdminAuthService
def get_admin_auth_service() -> AdminAuthService:
    """
    Dependency для получения AdminAuthService instance.

    Returns:
        AdminAuthService: Сервис аутентификации администраторов
    """
    return AdminAuthService()


@router.post(
    "/login",
    response_model=AdminTokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Admin Login",
    description="Аутентификация администратора по username и password. Возвращает JWT access и refresh токены."
)
async def login(
    request: Request,
    credentials: AdminLoginRequest,
    db: AsyncSession = Depends(get_db),
    auth_service: AdminAuthService = Depends(get_admin_auth_service)
) -> AdminTokenResponse:
    """
    Вход администратора в систему.

    Процесс:
    1. Проверка username и password
    2. Проверка что аккаунт активен и не заблокирован
    3. Генерация JWT access (30 мин) и refresh (7 дней) токенов
    4. Обновление last_login_at
    5. Audit logging

    Args:
        request: FastAPI Request для audit logging
        credentials: Username и password
        db: Database session
        auth_service: AdminAuthService instance

    Returns:
        AdminTokenResponse: JWT токены и метаданные

    Raises:
        HTTPException: 401 при неверных credentials или заблокированном аккаунте
    """
    try:
        access_token, refresh_token = await auth_service.authenticate(
            db=db,
            username=credentials.username,
            password=credentials.password
        )

        return AdminTokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="Bearer",
            expires_in=1800  # 30 minutes
        )

    except InvalidCredentialsError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"}
        )

    except AccountLockedError as e:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"}
        )

    except AccountDisabledError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"}
        )


@router.post(
    "/refresh",
    response_model=AdminTokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Refresh Access Token",
    description="Обновление access token через refresh token. Возвращает новые access и refresh токены."
)
async def refresh(
    refresh_request: AdminRefreshRequest,
    db: AsyncSession = Depends(get_db),
    auth_service: AdminAuthService = Depends(get_admin_auth_service)
) -> AdminTokenResponse:
    """
    Обновление access token через refresh token.

    Процесс:
    1. Валидация refresh token
    2. Проверка что аккаунт активен
    3. Генерация новых JWT токенов

    Args:
        refresh_request: Refresh token
        db: Database session
        auth_service: AdminAuthService instance

    Returns:
        AdminTokenResponse: Новые JWT токены

    Raises:
        HTTPException: 401 при невалидном refresh token
    """
    try:
        access_token, new_refresh_token = await auth_service.refresh_token(
            db=db,
            refresh_token=refresh_request.refresh_token
        )

        return AdminTokenResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
            token_type="Bearer",
            expires_in=1800  # 30 minutes
        )

    except (InvalidCredentialsError, AccountDisabledError) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"}
        )


@router.post(
    "/logout",
    response_model=AdminLogoutResponse,
    status_code=status.HTTP_200_OK,
    summary="Admin Logout",
    description="Выход администратора из системы. Client-side token invalidation (в будущем - server-side revocation)."
)
async def logout(
    current_admin: AdminUser = Depends(get_current_admin_user)
) -> AdminLogoutResponse:
    """
    Выход администратора из системы.

    Note:
        В текущей реализации используется client-side token invalidation.
        В будущем будет добавлена server-side token revocation через Redis blacklist.

    Args:
        current_admin: Текущий аутентифицированный администратор

    Returns:
        AdminLogoutResponse: Подтверждение успешного выхода
    """
    # TODO: Добавить server-side token revocation через Redis
    # При наличии jti в токене можно добавить его в blacklist

    return AdminLogoutResponse(
        success=True,
        message="Successfully logged out"
    )


@router.get(
    "/me",
    response_model=AdminUserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Current Admin User",
    description="Получение информации о текущем аутентифицированном администраторе."
)
async def get_me(
    current_admin: AdminUser = Depends(get_current_admin_user)
) -> AdminUserResponse:
    """
    Получение информации о текущем администраторе.

    Args:
        current_admin: Текущий аутентифицированный администратор

    Returns:
        AdminUserResponse: Информация об администраторе
    """
    return AdminUserResponse(
        id=current_admin.id,
        username=current_admin.username,
        email=current_admin.email,
        role=current_admin.role,
        enabled=current_admin.enabled,
        last_login_at=current_admin.last_login_at,
        created_at=current_admin.created_at
    )


@router.post(
    "/change-password",
    response_model=AdminChangePasswordResponse,
    status_code=status.HTTP_200_OK,
    summary="Change Admin Password",
    description="Смена пароля администратора. Требует текущий пароль и валидацию нового пароля."
)
async def change_password(
    request: Request,
    password_change: AdminChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin_user),
    auth_service: AdminAuthService = Depends(get_admin_auth_service)
) -> AdminChangePasswordResponse:
    """
    Смена пароля администратора.

    Процесс:
    1. Проверка текущего пароля
    2. Валидация нового пароля (strength policy)
    3. Проверка что новый пароль не в истории
    4. Добавление текущего пароля в историю
    5. Обновление password_hash
    6. Обновление password_changed_at
    7. Audit logging

    Args:
        request: FastAPI Request для audit logging
        password_change: Текущий и новый пароли
        db: Database session
        current_admin: Текущий администратор
        auth_service: AdminAuthService instance

    Returns:
        AdminChangePasswordResponse: Подтверждение смены пароля

    Raises:
        HTTPException: 400 при валидационных ошибках, 401 при неверном текущем пароле
    """
    # Проверка что новый пароль и подтверждение совпадают
    if not password_change.passwords_match():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password and confirmation do not match"
        )

    try:
        await auth_service.change_password(
            db=db,
            admin_user=current_admin,
            current_password=password_change.current_password,
            new_password=password_change.new_password
        )

        return AdminChangePasswordResponse(
            success=True,
            message="Password changed successfully",
            password_changed_at=current_admin.password_changed_at or datetime.now(timezone.utc)
        )

    except InvalidCredentialsError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )

    except PasswordInHistoryError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    except ValueError as e:
        # Password policy validation errors
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
