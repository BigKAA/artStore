"""
AuditLog Model для комплексного security audit trail.

Поддерживает:
- Tamper-proof logging с HMAC-SHA256 signatures
- Comprehensive event tracking (auth, CRUD, system events)
- Request correlation через OpenTelemetry trace_id
- Actor tracking (users, service accounts, system)
- Resource tracking с type/id
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
import hashlib
import hmac
import json

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, ForeignKey, Integer,
    String, Text, select, desc
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, relationship

from app.models.base import Base
from app.core.config import settings


class AuditLog(Base):
    """
    Audit log entry для security monitoring и compliance.

    Attributes:
        id: Primary key (автоинкремент BigInteger для долгосрочного хранения)
        event_type: Тип события (login_success, jwt_rotation, etc.)
        severity: Уровень важности (debug, info, warning, error, critical)

        user_id: Foreign key к users (NULL для system events)
        service_account_id: Foreign key к service_accounts (NULL для user events)
        actor_type: Тип актора (user, service_account, system)

        resource_type: Тип ресурса (user, service_account, jwt_key, etc.)
        resource_id: ID ресурса
        action: Действие (create, read, update, delete, rotate, login, logout)

        ip_address: IP адрес клиента
        user_agent: User agent string
        request_id: OpenTelemetry trace_id для корреляции
        session_id: Session identifier

        data: Дополнительные данные (JSONB)
        success: Успешность операции
        error_message: Текст ошибки (если failed)

        hmac_signature: HMAC-SHA256 signature для tamper protection
        created_at: Timestamp события
    """

    __tablename__ = "audit_logs"

    # Primary Key (BigInteger для долгосрочного хранения)
    id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        nullable=False,
        comment="Уникальный идентификатор audit log entry"
    )

    # Event Classification
    event_type = Column(
        String(100),
        nullable=False,
        index=True,
        comment="Тип security события"
    )
    severity = Column(
        String(20),
        nullable=False,
        default="info",
        index=True,
        comment="Severity level: debug, info, warning, error, critical"
    )

    # Actor Information
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="ID пользователя (NULL для system events)"
    )
    service_account_id = Column(
        Integer,
        ForeignKey("service_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="ID service account (NULL для user events)"
    )
    actor_type = Column(
        String(20),
        nullable=False,
        comment="Тип актора: user, service_account, system"
    )

    # Resource Information
    resource_type = Column(
        String(50),
        nullable=True,
        comment="Тип ресурса: user, service_account, jwt_key, storage_element"
    )
    resource_id = Column(
        String(100),
        nullable=True,
        comment="ID затронутого ресурса"
    )
    action = Column(
        String(50),
        nullable=False,
        comment="Действие: create, read, update, delete, rotate, login, logout"
    )

    # Request Context
    ip_address = Column(
        String(45),
        nullable=True,
        comment="IP адрес клиента (IPv4 или IPv6)"
    )
    user_agent = Column(
        Text,
        nullable=True,
        comment="User agent string"
    )
    request_id = Column(
        String(36),
        nullable=True,
        index=True,
        comment="Correlation ID для трассировки (OpenTelemetry trace_id)"
    )
    session_id = Column(
        String(100),
        nullable=True,
        comment="Session identifier для корреляции событий"
    )

    # Event Data
    data = Column(
        JSONB,
        nullable=True,
        comment="Дополнительные данные события (JSON format)"
    )
    success = Column(
        Boolean,
        nullable=False,
        index=True,
        comment="Успешность операции"
    )
    error_message = Column(
        Text,
        nullable=True,
        comment="Текст ошибки (если success=false)"
    )

    # Tamper Protection
    hmac_signature = Column(
        String(64),
        nullable=False,
        comment="HMAC-SHA256 signature для защиты от изменения"
    )

    # Timestamp
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
        comment="Timestamp события"
    )

    # Relationships
    user = relationship("User", foreign_keys=[user_id], lazy="joined")
    service_account = relationship("ServiceAccount", foreign_keys=[service_account_id], lazy="joined")

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<AuditLog(id={self.id}, event_type={self.event_type}, "
            f"actor={self.actor_type}, action={self.action}, "
            f"success={self.success}, created_at={self.created_at})>"
        )

    @staticmethod
    def _compute_hmac(data: Dict[str, Any]) -> str:
        """
        Вычисление HMAC-SHA256 signature для event data.

        Args:
            data: Словарь с данными события для подписи

        Returns:
            str: Hex-encoded HMAC signature (64 символа)

        Note:
            Использует секретный ключ из settings.security.audit_hmac_secret
        """
        # Сортируем ключи для консистентности
        canonical = json.dumps(data, sort_keys=True, ensure_ascii=False)

        # Вычисляем HMAC-SHA256
        signature = hmac.new(
            settings.security.audit_hmac_secret.encode('utf-8'),
            canonical.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        return signature

    @classmethod
    def create_entry(
        cls,
        session: Session,
        event_type: str,
        action: str,
        success: bool,
        actor_type: str = "system",
        user_id: Optional[int] = None,
        service_account_id: Optional[int] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
        session_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        severity: str = "info",
        error_message: Optional[str] = None
    ) -> "AuditLog":
        """
        Создание audit log entry с автоматической HMAC подписью.

        Args:
            session: Database session
            event_type: Тип события (e.g., "login_success")
            action: Действие (e.g., "login")
            success: Успешность операции
            actor_type: Тип актора (user, service_account, system)
            user_id: ID пользователя (опционально)
            service_account_id: ID service account (опционально)
            resource_type: Тип ресурса (опционально)
            resource_id: ID ресурса (опционально)
            ip_address: IP адрес (опционально)
            user_agent: User agent (опционально)
            request_id: Request ID для корреляции (опционально)
            session_id: Session ID (опционально)
            data: Дополнительные данные (опционально)
            severity: Уровень важности (default: "info")
            error_message: Текст ошибки (опционально)

        Returns:
            AuditLog: Созданный audit log entry

        Example:
            audit_log = AuditLog.create_entry(
                session=db,
                event_type="login_success",
                action="login",
                success=True,
                actor_type="user",
                user_id=user.id,
                ip_address="192.168.1.1",
                data={"username": user.username}
            )
        """
        # Подготовка данных для HMAC signature
        signature_data = {
            "event_type": event_type,
            "action": action,
            "success": success,
            "actor_type": actor_type,
            "user_id": user_id,
            "service_account_id": service_account_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "severity": severity,
            "data": data if data else {},
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        # Вычисляем HMAC signature
        hmac_signature = cls._compute_hmac(signature_data)

        # Создаем audit log entry
        audit_log = cls(
            event_type=event_type,
            severity=severity,
            user_id=user_id,
            service_account_id=service_account_id,
            actor_type=actor_type,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            session_id=session_id,
            data=data,
            success=success,
            error_message=error_message,
            hmac_signature=hmac_signature
        )

        session.add(audit_log)
        session.commit()

        return audit_log

    def verify_signature(self) -> bool:
        """
        Верификация HMAC signature для проверки целостности.

        Returns:
            bool: True если signature валидна, False если tampering обнаружен

        Example:
            is_valid = audit_log.verify_signature()
            if not is_valid:
                logger.warning(f"Tampering detected in audit log {audit_log.id}")
        """
        # Восстанавливаем данные для signature
        signature_data = {
            "event_type": self.event_type,
            "action": self.action,
            "success": self.success,
            "actor_type": self.actor_type,
            "user_id": self.user_id,
            "service_account_id": self.service_account_id,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "severity": self.severity,
            "data": self.data if self.data else {},
            "timestamp": self.created_at.isoformat()
        }

        # Вычисляем expected signature
        expected_signature = self._compute_hmac(signature_data)

        # Constant-time comparison для защиты от timing attacks
        return hmac.compare_digest(expected_signature, self.hmac_signature)

    @classmethod
    def get_by_event_type(
        cls,
        session: Session,
        event_type: str,
        limit: int = 100
    ) -> List["AuditLog"]:
        """
        Получение audit logs по типу события.

        Args:
            session: Database session
            event_type: Тип события для поиска
            limit: Максимальное количество записей (default: 100)

        Returns:
            List[AuditLog]: Список audit logs отсортированных по created_at (desc)
        """
        stmt = (
            select(cls)
            .where(cls.event_type == event_type)
            .order_by(desc(cls.created_at))
            .limit(limit)
        )
        result = session.execute(stmt)
        return result.scalars().all()

    @classmethod
    def get_by_actor(
        cls,
        session: Session,
        actor_type: str,
        actor_id: int,
        limit: int = 100
    ) -> List["AuditLog"]:
        """
        Получение audit logs по актору.

        Args:
            session: Database session
            actor_type: Тип актора (user, service_account)
            actor_id: ID актора
            limit: Максимальное количество записей (default: 100)

        Returns:
            List[AuditLog]: Список audit logs отсортированных по created_at (desc)
        """
        if actor_type == "user":
            stmt = (
                select(cls)
                .where(cls.user_id == actor_id)
                .order_by(desc(cls.created_at))
                .limit(limit)
            )
        elif actor_type == "service_account":
            stmt = (
                select(cls)
                .where(cls.service_account_id == actor_id)
                .order_by(desc(cls.created_at))
                .limit(limit)
            )
        else:
            return []

        result = session.execute(stmt)
        return result.scalars().all()

    @classmethod
    def get_failed_events(
        cls,
        session: Session,
        hours: int = 24,
        limit: int = 100
    ) -> List["AuditLog"]:
        """
        Получение failed events за последние N hours.

        Args:
            session: Database session
            hours: Количество часов назад (default: 24)
            limit: Максимальное количество записей (default: 100)

        Returns:
            List[AuditLog]: Список failed events отсортированных по created_at (desc)
        """
        since = datetime.now(timezone.utc) - timedelta(hours=hours)

        stmt = (
            select(cls)
            .where(cls.success == False)
            .where(cls.created_at >= since)
            .order_by(desc(cls.created_at))
            .limit(limit)
        )

        result = session.execute(stmt)
        return result.scalars().all()

    @classmethod
    def get_security_events(
        cls,
        session: Session,
        severity: str = "warning",
        hours: int = 24,
        limit: int = 100
    ) -> List["AuditLog"]:
        """
        Получение security events (severity >= warning) за последние N hours.

        Args:
            session: Database session
            severity: Минимальный уровень severity (warning, error, critical)
            hours: Количество часов назад (default: 24)
            limit: Максимальное количество записей (default: 100)

        Returns:
            List[AuditLog]: Список security events отсортированных по created_at (desc)
        """
        since = datetime.now(timezone.utc) - timedelta(hours=hours)

        severity_order = {"debug": 0, "info": 1, "warning": 2, "error": 3, "critical": 4}
        min_severity_level = severity_order.get(severity, 2)

        severity_filter = [
            s for s, level in severity_order.items()
            if level >= min_severity_level
        ]

        stmt = (
            select(cls)
            .where(cls.severity.in_(severity_filter))
            .where(cls.created_at >= since)
            .order_by(desc(cls.created_at))
            .limit(limit)
        )

        result = session.execute(stmt)
        return result.scalars().all()
