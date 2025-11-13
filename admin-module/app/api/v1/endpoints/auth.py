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
from app.schemas.service_account import (
    OAuth2TokenRequest,
    OAuth2TokenResponse,
    OAuth2ErrorResponse
)
from app.services.auth_service import auth_service
from app.services.token_service import token_service
from app.services.ldap_service import ldap_service
from app.services.service_account_service import ServiceAccountService
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


# ========================================================================
# OAUTH 2.0 CLIENT CREDENTIALS GRANT (RFC 6749 Section 4.4)
# ========================================================================

@router.post(
    "/token",
    response_model=OAuth2TokenResponse,
    responses={
        401: {"model": OAuth2ErrorResponse, "description": "Invalid client credentials"},
        403: {"model": OAuth2ErrorResponse, "description": "Access denied"},
    },
    summary="OAuth 2.0 Token Endpoint (Client Credentials Grant)"
)
async def oauth2_token(
    request: OAuth2TokenRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    OAuth 2.0 Client Credentials Grant для Service Accounts.

    Соответствует стандарту RFC 6749 Section 4.4:
    https://datatracker.ietf.org/doc/html/rfc6749#section-4.4

    **Request:**
    - **client_id**: Client ID Service Account
    - **client_secret**: Client Secret Service Account

    **Response:**
    - **access_token**: JWT access токен
    - **refresh_token**: JWT refresh токен
    - **token_type**: "Bearer"
    - **expires_in**: Время жизни access токена в секундах
    - **issued_at**: Время выдачи токена (ISO 8601)

    **Security:**
    - Client Secret передается один раз и хранится в bcrypt hash
    - Access токен живет 30 минут
    - Refresh токен живет 7 дней
    - Автоматическая ротация secret каждые 90 дней
    - Rate limiting: 100 запросов в минуту (по умолчанию)

    **Error Responses (RFC 6749 Section 5.2):**
    - `invalid_client`: Неверный client_id или client_secret
    - `access_denied`: Service Account заблокирован или истек
    """
    # Инициализируем сервис
    service_account_service = ServiceAccountService()

    # Аутентификация Service Account
    service_account = await service_account_service.authenticate_service_account(
        db=db,
        client_id=request.client_id,
        client_secret=request.client_secret
    )

    if not service_account:
        # RFC 6749 Section 5.2 - invalid_client
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid client_id or client_secret",
            headers={
                "WWW-Authenticate": 'Bearer error="invalid_client"',
                "Cache-Control": "no-store",
                "Pragma": "no-cache"
            }
        )

    # Проверяем что Service Account может аутентифицироваться
    if not service_account.can_authenticate():
        # RFC 6749 Section 5.2 - access_denied
        error_detail = "Access denied"
        if service_account.is_expired:
            error_detail = "Service Account secret has expired. Please rotate your secret."
        elif service_account.status.value != "ACTIVE":
            error_detail = f"Service Account is {service_account.status.value}"

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_detail,
            headers={
                "WWW-Authenticate": 'Bearer error="access_denied"',
                "Cache-Control": "no-store",
                "Pragma": "no-cache"
            }
        )

    # Создаем токены
    from datetime import datetime as dt, timezone
    issued_at = dt.now(timezone.utc)

    access_token, refresh_token = token_service.create_service_account_token_pair(
        service_account
    )

    return OAuth2TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="Bearer",
        expires_in=settings.jwt.access_token_expire_minutes * 60,
        issued_at=issued_at
    )
