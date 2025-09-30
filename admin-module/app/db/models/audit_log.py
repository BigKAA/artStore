"""
Модель журнала аудита (audit log).
"""
import uuid

from sqlalchemy import Boolean, Column, DateTime, Index, JSON, String, Text
from sqlalchemy.sql import func

from app.db.session import Base


def generate_uuid():
    return str(uuid.uuid4())


class AuditLog(Base):
    """
    Журнал аудита всех операций в системе.

    Атрибуты:
        id: Уникальный идентификатор
        user_id: ID пользователя, выполнившего действие
        username: Имя пользователя (денормализация для быстрого поиска)
        action: Тип действия (login, create_user, delete_file, etc.)
        resource_type: Тип ресурса (user, storage_element, file)
        resource_id: ID ресурса
        details: Дополнительные детали операции (JSON)
        ip_address: IP адрес клиента
        user_agent: User-Agent браузера/клиента
        success: Успешно ли выполнена операция
        error_message: Сообщение об ошибке (если success=False)
        timestamp: Время операции
    """

    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)

    # Информация о пользователе
    user_id = Column(
        String(36), nullable=True, index=True
    )  # NULL для анонимных действий
    username = Column(String(100), nullable=True, index=True)

    # Информация о действии
    action = Column(String(100), nullable=False, index=True)
    resource_type = Column(String(50), nullable=True, index=True)
    resource_id = Column(String(36), nullable=True, index=True)

    # Детали
    details = Column(JSON, nullable=True)

    # Информация о клиенте
    ip_address = Column(String(45), nullable=True)  # IPv6 поддержка
    user_agent = Column(Text, nullable=True)

    # Результат
    success = Column(Boolean, nullable=False, default=True, index=True)
    error_message = Column(Text, nullable=True)

    # Временная метка
    timestamp = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # Композитные индексы для частых запросов
    __table_args__ = (
        Index("ix_audit_user_timestamp", "user_id", "timestamp"),
        Index("ix_audit_resource_timestamp", "resource_type", "resource_id", "timestamp"),
        Index("ix_audit_action_timestamp", "action", "timestamp"),
    )

    def __repr__(self):
        return f"<AuditLog(id={self.id}, action={self.action}, user={self.username})>"
