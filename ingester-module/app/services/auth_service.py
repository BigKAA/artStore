"""
Ingester Module - OAuth 2.0 Client Credentials Authentication Service.

Реализует получение и управление JWT токенами от Admin Module
для machine-to-machine аутентификации с Storage Element.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from app.core.config import settings
from app.core.exceptions import AuthenticationException
from app.core.tls_utils import create_ssl_context

logger = logging.getLogger(__name__)


class AuthService:
    """
    OAuth 2.0 Client Credentials authentication сервис.

    Управляет JWT токенами для аутентификации Ingester Module
    в Storage Element через Service Account credentials.

    Features:
    - Automatic token refresh при истечении
    - Token caching для снижения нагрузки на Admin Module
    - Proactive refresh за 5 минут до истечения
    - Thread-safe token management
    """

    def __init__(
        self,
        admin_module_url: str,
        client_id: str,
        client_secret: str,
        timeout: int = 10
    ):
        """
        Инициализация AuthService.

        Args:
            admin_module_url: URL Admin Module (e.g., http://admin_module:8000)
            client_id: Service Account Client ID
            client_secret: Service Account Client Secret
            timeout: HTTP request timeout в секундах
        """
        self.admin_module_url = admin_module_url.rstrip('/')
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout

        # Token state
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

        # HTTP client для Admin Module (async)
        self._client: Optional[httpx.AsyncClient] = None

        logger.info(
            "AuthService initialized",
            extra={
                "admin_module_url": self.admin_module_url,
                "client_id": self.client_id,
                "timeout": self.timeout
            }
        )

    def _get_client(self) -> httpx.AsyncClient:
        """
        Получить HTTP client для Admin Module с mTLS support.

        Returns:
            httpx.AsyncClient instance с SSL context если TLS enabled
        """
        if self._client is None:
            client_config = {
                "base_url": self.admin_module_url,
                "timeout": self.timeout,
                "follow_redirects": True,
                "http2": True,  # HTTP/2 для лучшей производительности
            }

            # Apply mTLS configuration если TLS enabled
            ssl_context = create_ssl_context()
            if ssl_context:
                client_config["verify"] = ssl_context
                logger.info("mTLS enabled for Admin Module authentication")

            self._client = httpx.AsyncClient(**client_config)
            logger.debug(
                "HTTP client created for Admin Module",
                extra={
                    "base_url": self.admin_module_url,
                    "mtls_enabled": ssl_context is not None
                }
            )

        return self._client

    async def get_access_token(self) -> str:
        """
        Получить действующий JWT access token.

        Автоматически обновляет токен если он истек или истекает скоро (< 5 минут).

        Returns:
            Действующий JWT access token

        Raises:
            AuthenticationException: Если не удалось получить токен
        """
        if self._is_token_valid():
            logger.debug(
                "Using cached access token",
                extra={
                    "expires_in": int((self._token_expires_at - datetime.now(timezone.utc)).total_seconds())
                }
            )
            return self._access_token

        logger.info("Access token expired or missing, refreshing")
        return await self._refresh_token()

    def _is_token_valid(self) -> bool:
        """
        Проверить, что cached токен еще валиден.

        Токен считается валидным если:
        1. Токен существует
        2. Срок истечения известен
        3. До истечения осталось больше 5 минут (проактивный refresh)

        Returns:
            True если токен валиден, False если нужен refresh
        """
        if not self._access_token or not self._token_expires_at:
            return False

        # Проактивный refresh за 5 минут до истечения
        refresh_threshold = timedelta(minutes=5)
        now = datetime.now(timezone.utc)
        time_until_expiry = self._token_expires_at - now

        return time_until_expiry > refresh_threshold

    async def _refresh_token(self) -> str:
        """
        Получить новый JWT токен от Admin Module через OAuth 2.0 Client Credentials.

        Flow:
        1. POST /api/auth/token с client_id и client_secret
        2. Получить access_token и expires_in
        3. Сохранить в cache с timestamp истечения

        Returns:
            Новый JWT access token

        Raises:
            AuthenticationException: Если authentication failed
        """
        try:
            client = self._get_client()

            # OAuth 2.0 Client Credentials request
            response = await client.post(
                "/api/v1/auth/token",
                json={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret
                },
                headers={"Content-Type": "application/json"}
            )

            response.raise_for_status()
            data = response.json()

            # Извлечь токен и срок действия
            self._access_token = data["access_token"]
            expires_in = data.get("expires_in", 1800)  # Default 30 минут

            # Вычислить timestamp истечения
            self._token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

            logger.info(
                "Access token refreshed successfully",
                extra={
                    "expires_in": expires_in,
                    "expires_at": self._token_expires_at.isoformat()
                }
            )

            return self._access_token

        except httpx.HTTPStatusError as e:
            logger.error(
                "Authentication failed - HTTP error",
                extra={
                    "status_code": e.response.status_code,
                    "error": str(e),
                    "response_body": e.response.text
                }
            )
            raise AuthenticationException(
                f"Failed to authenticate with Admin Module: {e.response.status_code}"
            ) from e

        except httpx.RequestError as e:
            logger.error(
                "Authentication failed - connection error",
                extra={"error": str(e)}
            )
            raise AuthenticationException(
                f"Cannot connect to Admin Module at {self.admin_module_url}"
            ) from e

        except (KeyError, ValueError) as e:
            logger.error(
                "Authentication failed - invalid response",
                extra={"error": str(e)}
            )
            raise AuthenticationException(
                "Invalid token response from Admin Module"
            ) from e

    async def close(self):
        """Закрыть HTTP client и очистить состояние."""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.debug("HTTP client closed")

        self._access_token = None
        self._token_expires_at = None
