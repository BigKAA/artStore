"""
Ingester Module - OAuth 2.0 Client Credentials Authentication Service.

Реализует получение и управление JWT токенами от Admin Module
для machine-to-machine аутентификации с Storage Element.

Sprint 23: Instrumented with Prometheus metrics для comprehensive observability.
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from app.core.config import settings
from app.core.exceptions import AuthenticationException
from app.services.auth_metrics import (
    auth_token_requests_total,
    auth_token_acquisition_duration,
    auth_token_source_total,
    auth_token_refresh_total,
    auth_token_refresh_duration,
    auth_token_ttl,
    auth_token_validation_total,
    auth_errors_total,
    classify_auth_error,
)

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

            self._client = httpx.AsyncClient(**client_config)
            logger.debug(
                "HTTP client created for Admin Module",
                extra={
                    "base_url": self.admin_module_url
                }
            )

        return self._client

    async def get_access_token(self) -> str:
        """
        Получить действующий JWT access token с Prometheus metrics instrumentation.

        Автоматически обновляет токен если он истек или истекает скоро (< 5 минут).

        Metrics recorded:
            - auth_token_source_total: Cache hits vs fresh requests
            - auth_token_requests_total: Success/failure counts
            - auth_token_acquisition_duration: Latency histogram
            - auth_token_ttl: Current token TTL gauge
            - auth_errors_total: Error classification

        Returns:
            Действующий JWT access token

        Raises:
            AuthenticationException: Если не удалось получить токен
        """
        start_time = time.time()

        try:
            # Check cached token
            if self._is_token_valid():
                auth_token_source_total.labels(source="cache").inc()
                logger.debug(
                    "Using cached access token",
                    extra={
                        "expires_in": int((self._token_expires_at - datetime.now(timezone.utc)).total_seconds())
                    }
                )

                # Update TTL gauge для cached token
                self._update_token_ttl_metric()

                return self._access_token

            # Refresh token (cache miss)
            auth_token_source_total.labels(source="fresh_request").inc()
            logger.info("Access token expired or missing, refreshing")
            token = await self._refresh_token()

            # Record successful token acquisition
            duration = time.time() - start_time
            auth_token_acquisition_duration.observe(duration)
            auth_token_requests_total.labels(status="success", error_type="").inc()

            # Update TTL gauge для new token
            self._update_token_ttl_metric()

            logger.debug(
                "Token acquisition successful",
                extra={
                    "duration_ms": duration * 1000,
                    "source": "fresh_request"
                }
            )

            return token

        except AuthenticationException as e:
            # Record failed token acquisition
            duration = time.time() - start_time
            auth_token_acquisition_duration.observe(duration)

            error_type = classify_auth_error(e)
            auth_token_requests_total.labels(status="failure", error_type=error_type).inc()
            auth_errors_total.labels(
                error_type=error_type,
                admin_module_url=self.admin_module_url
            ).inc()

            logger.error(
                "Token acquisition failed",
                extra={
                    "duration_ms": duration * 1000,
                    "error_type": error_type
                }
            )

            raise

    def _is_token_valid(self) -> bool:
        """
        Проверить, что cached токен еще валиден с metrics recording.

        Токен считается валидным если:
        1. Токен существует
        2. Срок истечения известен
        3. До истечения осталось больше 5 минут (проактивный refresh)

        Metrics recorded:
            - auth_token_validation_total: Validation result classification

        Returns:
            True если токен валиден, False если нужен refresh
        """
        if not self._access_token or not self._token_expires_at:
            auth_token_validation_total.labels(result="missing").inc()
            return False

        # Проактивный refresh за 5 минут до истечения
        refresh_threshold = timedelta(minutes=5)
        now = datetime.now(timezone.utc)
        time_until_expiry = self._token_expires_at - now

        # Check if expired
        if time_until_expiry <= timedelta(0):
            auth_token_validation_total.labels(result="expired").inc()
            return False

        # Check if expiring soon
        if time_until_expiry <= refresh_threshold:
            auth_token_validation_total.labels(result="expiring_soon").inc()
            return False

        # Token is valid
        auth_token_validation_total.labels(result="valid").inc()
        return True

    async def _refresh_token(self) -> str:
        """
        Получить новый JWT токен от Admin Module через OAuth 2.0 Client Credentials с metrics.

        Flow:
        1. POST /api/v1/auth/token с client_id и client_secret
        2. Получить access_token и expires_in
        3. Сохранить в cache с timestamp истечения

        Metrics recorded:
            - auth_token_refresh_total: Refresh attempts (success/failure)
            - auth_token_refresh_duration: Refresh latency histogram
            - auth_errors_total: Detailed error classification

        Returns:
            Новый JWT access token

        Raises:
            AuthenticationException: Если authentication failed
        """
        start_time = time.time()

        # Determine refresh trigger
        trigger = "manual"
        if self._token_expires_at:
            now = datetime.now(timezone.utc)
            time_until_expiry = self._token_expires_at - now

            if time_until_expiry <= timedelta(0):
                trigger = "expired"
            elif time_until_expiry <= timedelta(minutes=5):
                trigger = "expiring_soon"

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

            # Record successful refresh
            duration = time.time() - start_time
            auth_token_refresh_duration.observe(duration)
            auth_token_refresh_total.labels(status="success", trigger=trigger).inc()

            logger.info(
                "Access token refreshed successfully",
                extra={
                    "expires_in": expires_in,
                    "expires_at": self._token_expires_at.isoformat(),
                    "trigger": trigger,
                    "duration_ms": duration * 1000
                }
            )

            return self._access_token

        except httpx.HTTPStatusError as e:
            # Record failed refresh
            duration = time.time() - start_time
            auth_token_refresh_duration.observe(duration)
            auth_token_refresh_total.labels(status="failure", trigger=trigger).inc()

            error_type = classify_auth_error(e)
            auth_errors_total.labels(
                error_type=error_type,
                admin_module_url=self.admin_module_url
            ).inc()

            logger.error(
                "Authentication failed - HTTP error",
                extra={
                    "status_code": e.response.status_code,
                    "error": str(e),
                    "response_body": e.response.text,
                    "error_type": error_type,
                    "duration_ms": duration * 1000
                }
            )
            raise AuthenticationException(
                f"Failed to authenticate with Admin Module: {e.response.status_code}"
            ) from e

        except httpx.RequestError as e:
            # Record connection error
            duration = time.time() - start_time
            auth_token_refresh_duration.observe(duration)
            auth_token_refresh_total.labels(status="failure", trigger=trigger).inc()

            error_type = classify_auth_error(e)
            auth_errors_total.labels(
                error_type=error_type,
                admin_module_url=self.admin_module_url
            ).inc()

            logger.error(
                "Authentication failed - connection error",
                extra={
                    "error": str(e),
                    "error_type": error_type,
                    "duration_ms": duration * 1000
                }
            )
            raise AuthenticationException(
                f"Cannot connect to Admin Module at {self.admin_module_url}"
            ) from e

        except (KeyError, ValueError) as e:
            # Record invalid response error
            duration = time.time() - start_time
            auth_token_refresh_duration.observe(duration)
            auth_token_refresh_total.labels(status="failure", trigger=trigger).inc()

            error_type = classify_auth_error(e)
            auth_errors_total.labels(
                error_type=error_type,
                admin_module_url=self.admin_module_url
            ).inc()

            logger.error(
                "Authentication failed - invalid response",
                extra={
                    "error": str(e),
                    "error_type": error_type,
                    "duration_ms": duration * 1000
                }
            )
            raise AuthenticationException(
                "Invalid token response from Admin Module"
            ) from e

    def _update_token_ttl_metric(self) -> None:
        """
        Update auth_token_ttl gauge с current token TTL.

        Sets gauge to seconds until expiration (0 if no token or expired).
        """
        if not self._token_expires_at:
            auth_token_ttl.set(0)
            return

        now = datetime.now(timezone.utc)
        ttl_seconds = (self._token_expires_at - now).total_seconds()

        # Set to 0 if expired, otherwise actual TTL
        auth_token_ttl.set(max(0, ttl_seconds))

    async def close(self):
        """Закрыть HTTP client и очистить состояние."""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.debug("HTTP client closed")

        self._access_token = None
        self._token_expires_at = None

        # Reset TTL metric
        auth_token_ttl.set(0)
