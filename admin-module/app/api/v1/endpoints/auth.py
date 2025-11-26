"""
OAuth 2.0 Token Endpoint for Service Accounts.
Provides OAuth 2.0 Client Credentials Grant (RFC 6749 Section 4.4) for machine-to-machine authentication.

NOTE: Human-to-machine authentication for AdminUser goes through /api/v1/admin-auth/ endpoints instead.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime as dt, timezone

from app.core.database import get_db, get_sync_session
from app.core.config import settings
from app.schemas.service_account import (
    OAuth2TokenRequest,
    OAuth2TokenResponse,
    OAuth2ErrorResponse
)
from app.services.token_service import token_service
from app.services.service_account_service import ServiceAccountService

router = APIRouter()


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

    # Создаем токены с database-backed keys
    issued_at = dt.now(timezone.utc)

    sync_session = next(get_sync_session())
    try:
        access_token, refresh_token = token_service.create_service_account_token_pair(
            service_account,
            session=sync_session
        )
    finally:
        sync_session.close()

    return OAuth2TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="Bearer",
        expires_in=settings.jwt.access_token_expire_minutes * 60,
        issued_at=issued_at
    )
