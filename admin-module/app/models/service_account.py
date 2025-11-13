"""
Модель Service Account для OAuth 2.0 Client Credentials authentication.

Service Accounts предназначены для machine-to-machine аутентификации,
заменяя User model с LDAP интеграцией для API клиентов.
"""

from datetime import datetime, timedelta, timezone
from sqlalchemy import String, Boolean, Enum as SQLEnum, Index, UniqueConstraint, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional
import enum
import uuid

from .base import Base, TimestampMixin


class ServiceAccountRole(str, enum.Enum):
    """Роли Service Accounts в системе."""

    ADMIN = "admin"           # Полный доступ ко всем функциям системы
    USER = "user"             # Базовый доступ (загрузка и скачивание файлов)
    AUDITOR = "auditor"       # Доступ только для чтения и аудита
    READONLY = "readonly"     # Только чтение метаданных и файлов


class ServiceAccountStatus(str, enum.Enum):
    """Статусы Service Accounts."""

    ACTIVE = "active"         # Активный Service Account
    SUSPENDED = "suspended"   # Приостановлен (временно отключен)
    EXPIRED = "expired"       # Истек срок действия (требуется ротация secret)
    DELETED = "deleted"       # Помечен как удаленный (soft delete)


class ServiceAccount(Base, TimestampMixin):
    """
    Модель Service Account для OAuth 2.0 Client Credentials.

    Service Accounts используются для machine-to-machine (M2M) аутентификации
    через OAuth 2.0 Client Credentials flow. Заменяют User model с LDAP
    для API клиентов.

    Attributes:
        id: Уникальный UUID идентификатор Service Account
        name: Человекочитаемое название Service Account (например, "Production App")
        client_id: Уникальный client_id для OAuth 2.0 (автогенерируемый)
        client_secret_hash: Bcrypt хеш client_secret
        role: Роль Service Account в системе
        status: Текущий статус Service Account
        rate_limit: Лимит запросов в минуту (default 100)
        is_system: Флаг системного Service Account (не может быть удален)
        secret_expires_at: Дата истечения срока действия client_secret (ротация каждые 90 дней)
        last_used_at: Дата и время последнего использования
        description: Описание назначения Service Account
        created_at: Дата создания (из TimestampMixin)
        updated_at: Дата обновления (из TimestampMixin)
    """

    __tablename__ = "service_accounts"

    # Primary key - UUID для безопасности
    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
        comment="Уникальный UUID идентификатор Service Account"
    )

    # Basic information
    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        unique=True,
        index=True,
        comment="Человекочитаемое название Service Account"
    )

    description: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Описание назначения Service Account"
    )

    # OAuth 2.0 Client Credentials
    client_id: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
        comment="Уникальный client_id для OAuth 2.0 (формат: sa_<environment>_<name>_<random>)"
    )

    client_secret_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Bcrypt хеш client_secret (минимум 32 символа)"
    )

    # Authorization
    role: Mapped[ServiceAccountRole] = mapped_column(
        SQLEnum(ServiceAccountRole, name="service_account_role_enum", create_type=True),
        nullable=False,
        default=ServiceAccountRole.USER,
        comment="Роль Service Account в системе"
    )

    status: Mapped[ServiceAccountStatus] = mapped_column(
        SQLEnum(ServiceAccountStatus, name="service_account_status_enum", create_type=True),
        nullable=False,
        default=ServiceAccountStatus.ACTIVE,
        index=True,
        comment="Текущий статус Service Account"
    )

    is_system: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Флаг системного Service Account (не может быть удален)"
    )

    # Rate Limiting
    rate_limit: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
        comment="Лимит запросов в минуту (default 100 req/min)"
    )

    # Secret Management
    secret_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Дата истечения срока действия client_secret (автоматическая ротация каждые 90 дней)"
    )

    # Usage tracking
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Дата и время последнего использования (последний успешный /api/auth/token)"
    )

    # Indexes для производительности
    __table_args__ = (
        Index("idx_service_account_status_role", "status", "role"),
        Index("idx_service_account_client_id", "client_id"),
        Index("idx_service_account_secret_expiry", "secret_expires_at"),
        UniqueConstraint("name", name="uq_service_account_name"),
        UniqueConstraint("client_id", name="uq_service_account_client_id"),
    )

    def __repr__(self) -> str:
        """Строковое представление Service Account."""
        return f"<ServiceAccount(id={self.id}, name='{self.name}', client_id='{self.client_id}', role={self.role}, status={self.status})>"

    @property
    def is_active(self) -> bool:
        """Проверка активности Service Account."""
        return self.status == ServiceAccountStatus.ACTIVE

    @property
    def is_expired(self) -> bool:
        """Проверка истечения срока действия secret."""
        return datetime.now(timezone.utc) >= self.secret_expires_at

    @property
    def days_until_expiry(self) -> int:
        """Количество дней до истечения срока действия secret."""
        delta = self.secret_expires_at - datetime.now(timezone.utc)
        return max(0, delta.days)

    @property
    def requires_rotation_warning(self) -> bool:
        """Проверка необходимости предупреждения о ротации (за 7 дней)."""
        return self.days_until_expiry <= 7 and self.days_until_expiry > 0

    def can_authenticate(self) -> bool:
        """
        Проверка возможности аутентификации Service Account.

        Returns:
            bool: True если Service Account может пройти аутентификацию, False иначе
        """
        # Проверка статуса
        if self.status != ServiceAccountStatus.ACTIVE:
            return False

        # Проверка истечения срока secret
        if self.is_expired:
            return False

        return True

    def update_last_used(self) -> None:
        """Обновление времени последнего использования."""
        self.last_used_at = datetime.now(timezone.utc)

    def mark_as_expired(self) -> None:
        """Пометить Service Account как expired из-за истечения secret."""
        self.status = ServiceAccountStatus.EXPIRED

    def suspend(self) -> None:
        """Приостановить Service Account."""
        if self.status == ServiceAccountStatus.ACTIVE:
            self.status = ServiceAccountStatus.SUSPENDED

    def activate(self) -> None:
        """Активировать Service Account."""
        if self.status == ServiceAccountStatus.SUSPENDED and not self.is_expired:
            self.status = ServiceAccountStatus.ACTIVE

    @classmethod
    def generate_client_id(cls, name: str, environment: str = "prod") -> str:
        """
        Генерация уникального client_id.

        Args:
            name: Название Service Account
            environment: Окружение (prod, staging, dev)

        Returns:
            str: Уникальный client_id в формате sa_<env>_<name>_<random>

        Example:
            >>> ServiceAccount.generate_client_id("myapp", "prod")
            'sa_prod_myapp_a1b2c3d4'
        """
        # Очистка названия от недопустимых символов
        clean_name = "".join(c if c.isalnum() else "_" for c in name.lower())
        clean_name = clean_name[:20]  # Ограничение длины

        # Генерация случайного суффикса
        random_suffix = uuid.uuid4().hex[:8]

        return f"sa_{environment}_{clean_name}_{random_suffix}"

    @classmethod
    def calculate_secret_expiry(cls, days: int = 90) -> datetime:
        """
        Расчет даты истечения secret.

        Args:
            days: Количество дней до истечения (default 90)

        Returns:
            datetime: Дата истечения срока действия
        """
        return datetime.now(timezone.utc) + timedelta(days=days)
