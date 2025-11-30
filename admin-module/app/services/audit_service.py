"""
Audit Service для комплексного security audit trail.

Предоставляет:
- Helper методы для common audit scenarios
- Автоматическая интеграция с AuditLog model
- Context extraction из FastAPI Request
- Structured event logging с HMAC signatures
"""

from datetime import datetime, timezone
from typing import Dict, Optional, Any
import logging

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.service_account import ServiceAccount
from app.models.admin_user import AdminUser
import uuid

logger = logging.getLogger(__name__)


class AuditService:
    """
    Сервис для security audit logging с автоматической HMAC подписью.

    Все методы создают audit log entries с:
    - HMAC-SHA256 signature для tamper protection
    - Request context (IP, user agent, request_id)
    - Structured event data
    - Actor tracking (user/service_account/system)
    """

    @staticmethod
    def _extract_request_context(request: Optional[Request] = None) -> Dict[str, Optional[str]]:
        """
        Извлечение контекста из FastAPI Request.

        Args:
            request: FastAPI Request object (опционально)

        Returns:
            Dict: Контекст запроса (ip_address, user_agent, request_id)
        """
        if not request:
            return {
                "ip_address": None,
                "user_agent": None,
                "request_id": None
            }

        # IP address
        ip_address = None
        if request.client:
            ip_address = request.client.host

        # User agent
        user_agent = request.headers.get("user-agent")

        # Request ID (OpenTelemetry trace_id или custom header)
        request_id = (
            request.headers.get("x-request-id") or
            request.headers.get("x-trace-id") or
            request.state.__dict__.get("request_id")
        )

        return {
            "ip_address": ip_address,
            "user_agent": user_agent,
            "request_id": request_id
        }

    @classmethod
    def log_authentication(
        cls,
        session: Session,
        success: bool,
        username: Optional[str] = None,
        user_id: Optional[int] = None,
        service_account_id: Optional[int] = None,
        admin_user_id: Optional[uuid.UUID] = None,
        error_message: Optional[str] = None,
        request: Optional[Request] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> AuditLog:
        """
        Логирование попытки аутентификации.

        Args:
            session: Database session
            success: Успешность аутентификации
            username: Username пользователя (опционально)
            user_id: ID пользователя (опционально)
            service_account_id: ID service account (опционально)
            admin_user_id: ID admin user (опционально)
            error_message: Текст ошибки (опционально)
            request: FastAPI Request (опционально)
            data: Дополнительные данные (опционально)

        Returns:
            AuditLog: Созданный audit log entry

        Example:
            audit_log = AuditService.log_authentication(
                session=db,
                success=True,
                username="ivanov",
                user_id=user.id,
                request=request
            )
        """
        context = cls._extract_request_context(request)

        # Определяем тип актора
        if user_id:
            actor_type = "user"
        elif service_account_id:
            actor_type = "service_account"
        elif admin_user_id:
            actor_type = "admin_user"
        else:
            actor_type = "system"

        # Формируем event type
        event_type = "login_success" if success else "login_failed"

        # Добавляем username в data
        event_data = data or {}
        if username:
            event_data["username"] = username

        # Severity
        severity = "info" if success else "warning"

        return AuditLog.create_entry(
            session=session,
            event_type=event_type,
            action="login",
            success=success,
            actor_type=actor_type,
            service_account_id=service_account_id,
            admin_user_id=admin_user_id,
            ip_address=context["ip_address"],
            user_agent=context["user_agent"],
            request_id=context["request_id"],
            data=event_data,
            severity=severity,
            error_message=error_message
        )

    @classmethod
    def log_logout(
        cls,
        session: Session,
        user_id: Optional[int] = None,
        service_account_id: Optional[int] = None,
        admin_user_id: Optional[uuid.UUID] = None,
        request: Optional[Request] = None
    ) -> AuditLog:
        """
        Логирование выхода из системы.

        Args:
            session: Database session
            user_id: ID пользователя (опционально)
            service_account_id: ID service account (опционально)
            admin_user_id: ID admin user (опционально)
            request: FastAPI Request (опционально)

        Returns:
            AuditLog: Созданный audit log entry
        """
        context = cls._extract_request_context(request)

        # Определяем тип актора
        if user_id:
            actor_type = "user"
        elif service_account_id:
            actor_type = "service_account"
        elif admin_user_id:
            actor_type = "admin_user"
        else:
            actor_type = "system"

        return AuditLog.create_entry(
            session=session,
            event_type="logout",
            action="logout",
            success=True,
            actor_type=actor_type,
            service_account_id=service_account_id,
            admin_user_id=admin_user_id,
            ip_address=context["ip_address"],
            user_agent=context["user_agent"],
            request_id=context["request_id"],
            severity="info"
        )

    @classmethod
    def log_resource_access(
        cls,
        session: Session,
        action: str,
        resource_type: str,
        resource_id: str,
        success: bool,
        user_id: Optional[int] = None,
        service_account_id: Optional[int] = None,
        error_message: Optional[str] = None,
        request: Optional[Request] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> AuditLog:
        """
        Логирование доступа к ресурсу (CRUD операции).

        Args:
            session: Database session
            action: Действие (create, read, update, delete)
            resource_type: Тип ресурса (user, service_account, jwt_key, etc.)
            resource_id: ID ресурса
            success: Успешность операции
            user_id: ID пользователя (опционально)
            service_account_id: ID service account (опционально)
            error_message: Текст ошибки (опционально)
            request: FastAPI Request (опционально)
            data: Дополнительные данные (опционально)

        Returns:
            AuditLog: Созданный audit log entry

        Example:
            audit_log = AuditService.log_resource_access(
                session=db,
                action="update",
                resource_type="service_account",
                resource_id="123",
                success=True,
                user_id=admin.id,
                request=request,
                data={"changed_fields": ["status", "role"]}
            )
        """
        context = cls._extract_request_context(request)

        # Определяем тип актора
        if user_id:
            actor_type = "user"
        elif service_account_id:
            actor_type = "service_account"
        else:
            actor_type = "system"

        # Event type
        event_type = f"{resource_type}_{action}"

        # Severity
        if not success:
            severity = "warning"
        elif action == "delete":
            severity = "warning"
        else:
            severity = "info"

        return AuditLog.create_entry(
            session=session,
            event_type=event_type,
            action=action,
            success=success,
            actor_type=actor_type,
            service_account_id=service_account_id,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=context["ip_address"],
            user_agent=context["user_agent"],
            request_id=context["request_id"],
            data=data,
            severity=severity,
            error_message=error_message
        )

    @classmethod
    def log_security_event(
        cls,
        session: Session,
        event_type: str,
        severity: str,
        success: bool,
        user_id: Optional[int] = None,
        service_account_id: Optional[int] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        error_message: Optional[str] = None,
        request: Optional[Request] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> AuditLog:
        """
        Логирование security события.

        Args:
            session: Database session
            event_type: Тип события (jwt_rotation, secret_rotation, etc.)
            severity: Уровень важности (debug, info, warning, error, critical)
            success: Успешность операции
            user_id: ID пользователя (опционально)
            service_account_id: ID service account (опционально)
            resource_type: Тип ресурса (опционально)
            resource_id: ID ресурса (опционально)
            error_message: Текст ошибки (опционально)
            request: FastAPI Request (опционально)
            data: Дополнительные данные (опционально)

        Returns:
            AuditLog: Созданный audit log entry

        Example:
            audit_log = AuditService.log_security_event(
                session=db,
                event_type="jwt_rotation",
                severity="info",
                success=True,
                data={
                    "old_key_version": "abc123",
                    "new_key_version": "def456",
                    "deactivated_keys": 1
                }
            )
        """
        context = cls._extract_request_context(request)

        # Определяем тип актора
        if user_id:
            actor_type = "user"
        elif service_account_id:
            actor_type = "service_account"
        else:
            actor_type = "system"

        # Action из event_type (последняя часть после underscore)
        parts = event_type.split("_")
        action = parts[-1] if len(parts) > 1 else event_type

        return AuditLog.create_entry(
            session=session,
            event_type=event_type,
            action=action,
            success=success,
            actor_type=actor_type,
            service_account_id=service_account_id,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=context["ip_address"],
            user_agent=context["user_agent"],
            request_id=context["request_id"],
            data=data,
            severity=severity,
            error_message=error_message
        )

    @classmethod
    def log_permission_denied(
        cls,
        session: Session,
        action: str,
        resource_type: str,
        resource_id: str,
        user_id: Optional[int] = None,
        service_account_id: Optional[int] = None,
        reason: Optional[str] = None,
        request: Optional[Request] = None
    ) -> AuditLog:
        """
        Логирование отказа в доступе (authorization failure).

        Args:
            session: Database session
            action: Попытка действия (read, update, delete, etc.)
            resource_type: Тип ресурса
            resource_id: ID ресурса
            user_id: ID пользователя (опционально)
            service_account_id: ID service account (опционально)
            reason: Причина отказа (опционально)
            request: FastAPI Request (опционально)

        Returns:
            AuditLog: Созданный audit log entry

        Example:
            audit_log = AuditService.log_permission_denied(
                session=db,
                action="delete",
                resource_type="service_account",
                resource_id="123",
                user_id=user.id,
                reason="Insufficient permissions: ADMIN role required",
                request=request
            )
        """
        context = cls._extract_request_context(request)

        # Определяем тип актора
        if user_id:
            actor_type = "user"
        elif service_account_id:
            actor_type = "service_account"
        else:
            actor_type = "system"

        return AuditLog.create_entry(
            session=session,
            event_type="permission_denied",
            action=action,
            success=False,
            actor_type=actor_type,
            service_account_id=service_account_id,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=context["ip_address"],
            user_agent=context["user_agent"],
            request_id=context["request_id"],
            severity="warning",
            error_message=reason or "Access denied"
        )

    @classmethod
    def log_admin_login_attempt(
        cls,
        session: Session,
        admin_user_id: uuid.UUID,
        success: bool,
        reason: Optional[str] = None,
        request: Optional[Request] = None
    ) -> AuditLog:
        """
        Логирование попытки входа администратора Admin UI.

        Args:
            session: Database session
            admin_user_id: ID admin user
            success: Успешность входа
            reason: Причина (если неудача)
            request: FastAPI Request (опционально)

        Returns:
            AuditLog: Созданный audit log entry

        Example:
            audit_log = AuditService.log_admin_login_attempt(
                session=db,
                admin_user_id=admin.id,
                success=False,
                reason="Account locked",
                request=request
            )
        """
        context = cls._extract_request_context(request)

        event_type = "admin_login_success" if success else "admin_login_failed"
        severity = "info" if success else "warning"

        return AuditLog.create_entry(
            session=session,
            event_type=event_type,
            action="login",
            success=success,
            actor_type="admin_user",
            admin_user_id=admin_user_id,
            ip_address=context["ip_address"],
            user_agent=context["user_agent"],
            request_id=context["request_id"],
            data={"reason": reason} if reason else None,
            severity=severity,
            error_message=reason if not success else None
        )

    @classmethod
    def log_password_change(
        cls,
        session: Session,
        admin_user_id: uuid.UUID,
        message: str,
        request: Optional[Request] = None
    ) -> AuditLog:
        """
        Логирование смены пароля администратора.

        Args:
            session: Database session
            admin_user_id: ID admin user
            message: Сообщение о результате смены пароля
            request: FastAPI Request (опционально)

        Returns:
            AuditLog: Созданный audit log entry

        Example:
            audit_log = AuditService.log_password_change(
                session=db,
                admin_user_id=admin.id,
                message="Admin password changed successfully",
                request=request
            )
        """
        context = cls._extract_request_context(request)

        return AuditLog.create_entry(
            session=session,
            event_type="admin_password_change",
            action="update",
            success=True,
            actor_type="admin_user",
            admin_user_id=admin_user_id,
            resource_type="admin_user",
            resource_id=str(admin_user_id),
            ip_address=context["ip_address"],
            user_agent=context["user_agent"],
            request_id=context["request_id"],
            data={"message": message},
            severity="info"
        )


# Singleton instance (опционально)
_audit_service: Optional[AuditService] = None


def get_audit_service() -> AuditService:
    """
    Получение singleton instance AuditService.

    Returns:
        AuditService: Audit service instance

    Example:
        audit = get_audit_service()
        audit.log_authentication(...)
    """
    global _audit_service

    if _audit_service is None:
        _audit_service = AuditService()
        logger.info("Audit Service initialized")

    return _audit_service
