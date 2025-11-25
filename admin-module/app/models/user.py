"""
Модель пользователя для Admin Module.
Поддерживает локальную аутентификацию через OAuth 2.0.
"""

from datetime import datetime, timedelta
from sqlalchemy import String, Boolean, Enum as SQLEnum, Index, UniqueConstraint, Column, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional
import enum

from .base import Base, TimestampMixin


class UserRole(str, enum.Enum):
    """Роли пользователей в системе."""

    ADMIN = "admin"           # Полный доступ ко всем функциям системы
    OPERATOR = "operator"     # Управление файлами и storage elements
    USER = "user"             # Базовый доступ (загрузка и скачивание файлов)


class UserStatus(str, enum.Enum):
    """Статусы пользователей."""

    ACTIVE = "active"         # Активный пользователь
    INACTIVE = "inactive"     # Неактивный пользователь (временно отключен)
    LOCKED = "locked"         # Заблокирован (например, после множественных неудачных попыток входа)
    DELETED = "deleted"       # Помечен как удаленный (soft delete)


class User(Base, TimestampMixin):
    """
    Модель пользователя.

    Поддерживает локальную аутентификацию (OAuth 2.0).

    Attributes:
        id: Уникальный идентификатор пользователя
        username: Имя пользователя (уникальное)
        email: Email адрес (уникальный)
        first_name: Имя
        last_name: Фамилия
        hashed_password: Хеш пароля для локальной аутентификации
        role: Роль пользователя в системе
        status: Текущий статус пользователя
        is_system: Флаг системного пользователя (не может быть удален)
        last_login: Дата и время последнего входа
        failed_login_attempts: Количество неудачных попыток входа
        lockout_until: Дата и время до которого аккаунт заблокирован
        created_at: Дата создания (из TimestampMixin)
        updated_at: Дата обновления (из TimestampMixin)
    """

    __tablename__ = "users"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Basic information
    username: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
        comment="Имя пользователя (уникальное)"
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="Email адрес (уникальный)"
    )

    first_name: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Имя"
    )

    last_name: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Фамилия"
    )

    # Authentication
    hashed_password: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Хеш пароля для локальной аутентификации"
    )

    # Authorization
    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole, name="user_role_enum", create_type=True),
        nullable=False,
        default=UserRole.USER,
        comment="Роль пользователя в системе"
    )

    status: Mapped[UserStatus] = mapped_column(
        SQLEnum(UserStatus, name="user_status_enum", create_type=True),
        nullable=False,
        default=UserStatus.ACTIVE,
        index=True,
        comment="Текущий статус пользователя"
    )

    is_system: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Флаг системного пользователя (не может быть удален или понижен)"
    )

    # Security tracking
    last_login: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Дата и время последнего входа"
    )

    failed_login_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Количество неудачных попыток входа"
    )

    lockout_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Дата и время до которой аккаунт заблокирован"
    )

    # Indexes для производительности
    __table_args__ = (
        Index("idx_user_status_role", "status", "role"),
        UniqueConstraint("username", name="uq_username"),
        UniqueConstraint("email", name="uq_email"),
    )

    def __repr__(self) -> str:
        """Строковое представление пользователя."""
        return f"<User(id={self.id}, username='{self.username}', role={self.role}, status={self.status})>"

    @property
    def full_name(self) -> str:
        """Полное имя пользователя."""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        elif self.first_name:
            return self.first_name
        elif self.last_name:
            return self.last_name
        return self.username

    @property
    def is_active(self) -> bool:
        """Проверка активности пользователя."""
        return self.status == UserStatus.ACTIVE

    @property
    def is_local_user(self) -> bool:
        """Проверка является ли пользователь локальным пользователем."""
        return self.hashed_password is not None

    def can_login(self) -> bool:
        """
        Проверка возможности входа пользователя.

        Returns:
            bool: True если пользователь может войти, False иначе
        """
        # Проверка статуса
        if self.status != UserStatus.ACTIVE:
            return False

        # Проверка блокировки
        if self.lockout_until and datetime.utcnow() < self.lockout_until:
            return False

        # Проверка наличия метода аутентификации
        if not self.is_local_user:
            return False

        return True

    def reset_failed_attempts(self) -> None:
        """Сброс счетчика неудачных попыток входа."""
        self.failed_login_attempts = 0
        self.lockout_until = None

    def increment_failed_attempts(self, lockout_threshold: int = 5, lockout_duration_minutes: int = 30) -> None:
        """
        Увеличение счетчика неудачных попыток входа.
        Блокировка аккаунта при превышении порога.

        Args:
            lockout_threshold: Порог неудачных попыток для блокировки
            lockout_duration_minutes: Длительность блокировки в минутах
        """
        self.failed_login_attempts += 1

        if self.failed_login_attempts >= lockout_threshold:
            self.lockout_until = datetime.utcnow() + timedelta(minutes=lockout_duration_minutes)
            self.status = UserStatus.LOCKED
