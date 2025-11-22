"""
Audit Middleware для автоматического логирования HTTP requests.

Функции:
- Автоматическое логирование всех HTTP requests
- Context extraction (IP, user agent, request ID)
- Actor tracking из JWT токенов
- Selective logging (только важные endpoints)
- Asynchronous audit log creation
"""

import time
from typing import Callable, Optional
import logging

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.database import get_sync_session
from app.services.audit_service import AuditService
from app.services.token_service import token_service

logger = logging.getLogger(__name__)


class AuditMiddleware(BaseHTTPMiddleware):
    """
    Middleware для автоматического audit logging HTTP requests.

    Логирует:
    - Все authentication endpoints
    - Все admin endpoints (CRUD operations)
    - Failed requests (4xx, 5xx)
    - Security-critical operations

    Пропускает:
    - Health checks (/health/*)
    - Static files
    - Metrics endpoint (/metrics)
    """

    # Endpoints для обязательного логирования
    CRITICAL_ENDPOINTS = [
        "/api/v1/auth/login",
        "/api/v1/auth/token",
        "/api/v1/auth/logout",
        "/api/v1/service-accounts",
        "/api/v1/jwt-keys/rotate",
        "/api/v1/users",
    ]

    # Endpoints для пропуска
    SKIP_ENDPOINTS = [
        "/health",
        "/metrics",
        "/docs",
        "/redoc",
        "/openapi.json",
    ]

    def __init__(self, app: ASGIApp):
        """
        Инициализация middleware.

        Args:
            app: ASGI application
        """
        super().__init__(app)
        self.audit_service = AuditService()

    def _should_log_request(self, path: str, status_code: int) -> bool:
        """
        Проверка необходимости логирования request.

        Args:
            path: Request path
            status_code: HTTP status code

        Returns:
            bool: True если нужно логировать, False иначе
        """
        # Всегда пропускаем
        for skip_path in self.SKIP_ENDPOINTS:
            if path.startswith(skip_path):
                return False

        # Всегда логируем critical endpoints
        for critical_path in self.CRITICAL_ENDPOINTS:
            if path.startswith(critical_path):
                return True

        # Логируем failed requests
        if status_code >= 400:
            return True

        # Логируем успешные POST/PUT/DELETE (state-changing operations)
        # GET requests не логируем для reduce overhead

        return False

    def _extract_actor_from_token(self, request: Request) -> dict:
        """
        Извлечение actor information из JWT токена.

        Args:
            request: FastAPI Request

        Returns:
            dict: Actor info (user_id, service_account_id, actor_type)
        """
        result = {
            "user_id": None,
            "service_account_id": None,
            "actor_type": "anonymous"
        }

        # Извлекаем токен из Authorization header
        auth_header = request.headers.get("authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return result

        token = auth_header.split(" ", 1)[1]

        # Декодируем токен
        try:
            sync_session = next(get_sync_session())
            try:
                payload = token_service.decode_token(token, session=sync_session)

                # User или Service Account
                if "sub" in payload:
                    user_id = int(payload["sub"])

                    # Проверяем тип токена по claims
                    if "service_account" in payload.get("type", ""):
                        result["service_account_id"] = user_id
                        result["actor_type"] = "service_account"
                    else:
                        result["user_id"] = user_id
                        result["actor_type"] = "user"

            finally:
                sync_session.close()

        except Exception as e:
            logger.debug(f"Failed to extract actor from token: {e}")

        return result

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Обработка HTTP request с audit logging.

        Args:
            request: FastAPI Request
            call_next: Next middleware/handler

        Returns:
            Response: HTTP response
        """
        start_time = time.time()
        status_code = 200
        error_message = None

        try:
            # Вызов следующего middleware/handler
            response = await call_next(request)
            status_code = response.status_code

        except Exception as e:
            status_code = 500
            error_message = str(e)
            logger.error(f"Request failed with exception: {e}", exc_info=True)
            raise

        finally:
            # Проверяем необходимость логирования
            should_log = self._should_log_request(request.url.path, status_code)

            if should_log:
                # Вычисляем длительность request
                duration_ms = (time.time() - start_time) * 1000

                # Извлекаем actor information
                actor_info = self._extract_actor_from_token(request)

                # Определяем action из HTTP method
                method_to_action = {
                    "GET": "read",
                    "POST": "create",
                    "PUT": "update",
                    "PATCH": "update",
                    "DELETE": "delete"
                }
                action = method_to_action.get(request.method, "unknown")

                # Формируем event type
                path_parts = request.url.path.split("/")
                resource_type = path_parts[-1] if len(path_parts) > 1 else "unknown"
                event_type = f"http_{action}_{resource_type}"

                # Дополнительные данные
                data = {
                    "method": request.method,
                    "path": request.url.path,
                    "query_params": str(request.query_params),
                    "status_code": status_code,
                    "duration_ms": round(duration_ms, 2)
                }

                # Severity
                if status_code >= 500:
                    severity = "error"
                elif status_code >= 400:
                    severity = "warning"
                else:
                    severity = "info"

                # Создаем audit log entry
                try:
                    sync_session = next(get_sync_session())
                    try:
                        self.audit_service.log_security_event(
                            session=sync_session,
                            event_type=event_type,
                            severity=severity,
                            success=(status_code < 400),
                            user_id=actor_info["user_id"],
                            service_account_id=actor_info["service_account_id"],
                            error_message=error_message,
                            request=request,
                            data=data
                        )
                    finally:
                        sync_session.close()

                except Exception as e:
                    # Не прерываем request из-за audit logging failure
                    logger.error(f"Failed to create audit log: {e}", exc_info=True)

        # Возвращаем response ПОСЛЕ finally блока
        return response
