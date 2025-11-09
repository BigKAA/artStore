"""
Authentication endpoints.
Логин, рефреш токенов, получение информации о пользователе.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.schemas.auth import (
    LoginRequest,
    TokenResponse,
    RefreshTokenRequest,
    UserResponse,
    PasswordResetRequest,
    PasswordResetConfirm,
    MessageResponse
)
from app.services.auth_service import auth_service
from app.services.token_service import token_service
from app.services.ldap_service import ldap_service
from app.api.dependencies.auth import get_current_active_user
from app.models.user import User

router = APIRouter()


@router.post("/login", response_model=TokenResponse, summary="Логин пользователя")
async def login(
    credentials: LoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Аутентификация пользователя (локальная или LDAP).

    - **username**: Имя пользователя или email
    - **password**: Пароль

    Возвращает access и refresh токены.
    """
    # Аутентификация пользователя
    user = await auth_service.authenticate(
        db=db,
        username=credentials.username,
        password=credentials.password,
        ldap_service=ldap_service
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Создаем токены
    access_token, refresh_token = token_service.create_token_pair(user)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.jwt.access_token_expire_minutes * 60
    )


@router.post("/refresh", response_model=TokenResponse, summary="Обновление access токена")
async def refresh_token(
    request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Обновление access токена используя refresh токен.

    - **refresh_token**: Валидный refresh токен

    Возвращает новый access токен и тот же refresh токен.
    """
    # Валидируем refresh токен
    payload = token_service.validate_token(request.refresh_token, token_type="refresh")
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Получаем пользователя
    user_id = int(payload.get("sub"))
    user = await auth_service.get_user_by_id(db, user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Проверяем что пользователь активен
    if not user.can_login():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"User is {user.status.value}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Создаем новый access токен
    new_access_token = token_service.refresh_access_token(request.refresh_token, user)
    if not new_access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Failed to refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=request.refresh_token,  # Возвращаем тот же refresh токен
        token_type="bearer",
        expires_in=settings.jwt.access_token_expire_minutes * 60
    )


@router.post("/logout", response_model=MessageResponse, summary="Выход из системы")
async def logout(
    current_user: User = Depends(get_current_active_user)
):
    """
    Выход пользователя из системы.

    **Note**: В текущей реализации JWT токены stateless,
    поэтому фактического invalidate токена не происходит.
    Клиент должен удалить токен на своей стороне.

    Для полноценного logout можно:
    - Добавить blacklist токенов в Redis
    - Использовать token rotation
    - Реализовать refresh token invalidation
    """
    # TODO: Добавить токен в blacklist (Redis)
    # TODO: Invalidate refresh токен

    return MessageResponse(
        message=f"User {current_user.username} logged out successfully"
    )


@router.get("/me", response_model=UserResponse, summary="Получить текущего пользователя")
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user)
):
    """
    Получение информации о текущем аутентифицированном пользователе.

    Требуется валидный access токен в заголовке Authorization.
    """
    return UserResponse.model_validate(current_user)


@router.post("/password-reset-request", response_model=MessageResponse, summary="Запрос сброса пароля")
async def request_password_reset(
    request: PasswordResetRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Запрос на сброс пароля.

    - **email**: Email пользователя

    Отправляет email с токеном сброса пароля (если пользователь существует).

    **Note**: По соображениям безопасности всегда возвращает success,
    даже если пользователь не найден.
    """
    # Создаем reset токен
    reset_token = await auth_service.create_password_reset_token(db, request.email)

    # TODO: Отправить email с токеном
    # TODO: Сохранить токен в Redis с TTL

    return MessageResponse(
        message="If the email exists, password reset instructions have been sent"
    )


@router.post("/password-reset-confirm", response_model=MessageResponse, summary="Подтверждение сброса пароля")
async def confirm_password_reset(
    request: PasswordResetConfirm,
    db: AsyncSession = Depends(get_db)
):
    """
    Подтверждение сброса пароля с новым паролем.

    - **reset_token**: Токен сброса из email
    - **new_password**: Новый пароль (минимум 6 символов)
    """
    # Валидируем токен и сбрасываем пароль
    success = await auth_service.reset_password(
        db,
        request.reset_token,
        request.new_password
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )

    return MessageResponse(
        message="Password has been reset successfully"
    )
