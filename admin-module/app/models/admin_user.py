"""
Модель Admin User для аутентификации администраторов Admin UI.

Admin Users предназначены для человеко-машинной аутентификации через
login/password в веб-интерфейсе администратора. Отдельно от Service Accounts
(OAuth 2.0 Client Credentials для machine-to-machine).
"""

from datetime import datetime, timedelta, timezone
from sqlalchemy import String, Boolean, Enum as SQLEnum, Index, UniqueConstraint, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional
import enum
import uuid

from .base import Base, TimestampMixin


class AdminRole(str, enum.Enum):
    """Роли администраторов в системе."""

    SUPER_ADMIN = "super_admin"  # Полный доступ, включая управление другими админами
    ADMIN = "admin"              # Полный доступ к управлению системой
    READONLY = "readonly"        # Только чтение (мониторинг, просмотр)


class AdminUser(Base, TimestampMixin):
    """
    Модель Admin User для аутентификации в Admin UI.

    Admin Users используются для human-to-machine аутентификации через
    login/password форму в веб-интерфейсе. Отдельно от Service Accounts,
    которые используют OAuth 2.0 Client Credentials.

    JWT токены Admin Users имеют тип 'admin_user' (vs 'service_account').

    Attributes:
        id: Уникальный UUID идентификатор Admin User
        username: Уникальное имя пользователя для логина
        email: Уникальный email адрес
        password_hash: Bcrypt хеш пароля
        password_history: История предыдущих password hashes (максимум 5)
        password_changed_at: Дата последней смены пароля
        role: Роль администратора в системе
        enabled: Флаг активности аккаунта
        is_system: Флаг системного Admin User (не может быть удален)
        last_login_at: Дата и время последнего успешного логина
        login_attempts: Счетчик неудачных попыток логина (для rate limiting)
        locked_until: Дата до которой аккаунт заблокирован (после 5 неудачных попыток)
        created_at: Дата создания (из TimestampMixin)
        updated_at: Дата обновления (из TimestampMixin)
    """

    __tablename__ = "admin_users"

    # Primary key - UUID для безопасности
    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
        comment="Уникальный UUID идентификатор Admin User"
    )

    # Credentials
    username: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
        comment="Уникальное имя пользователя для логина"
    )

    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
        comment="Уникальный email адрес администратора"
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Bcrypt хеш пароля (work factor 12)"
    )

    # Password security tracking (Sprint 16 Phase 1 pattern)
    password_history: Mapped[Optional[list[str]]] = mapped_column(
        JSON,
        nullable=True,
        comment="История предыдущих password hashes (максимум 5)"
    )

    password_changed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Дата последней смены пароля"
    )

    # Role and status
    role: Mapped[AdminRole] = mapped_column(
        SQLEnum(AdminRole, name="admin_role", native_enum=True, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=AdminRole.ADMIN,
        index=True,
        comment="Роль администратора в системе"
    )

    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
        comment="Флаг активности аккаунта (True = активен)"
    )

    is_system: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Флаг системного Admin User (не может быть удален через API)"
    )

    # Login tracking
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Дата и время последнего успешного логина"
    )

    login_attempts: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        comment="Счетчик неудачных попыток логина (для rate limiting)"
    )

    locked_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Дата до которой аккаунт заблокирован (после 5 неудачных попыток)"
    )

    # Indexes для производительности
    __table_args__ = (
        Index('idx_admin_users_username', 'username'),
        Index('idx_admin_users_email', 'email'),
        Index('idx_admin_users_enabled', 'enabled'),
        Index('idx_admin_users_role', 'role'),
        Index('idx_admin_users_last_login', 'last_login_at'),
    )

    def __repr__(self) -> str:
        return (
            f"<AdminUser(id={self.id}, username='{self.username}', "
            f"role={self.role.value}, enabled={self.enabled})>"
        )

    def is_locked(self) -> bool:
        """
        Проверка, заблокирован ли аккаунт из-за множественных неудачных попыток.

        Returns:
            True если аккаунт заблокирован, False иначе
        """
        if self.locked_until is None:
            return False

        now = datetime.now(timezone.utc)
        return now < self.locked_until

    def reset_login_attempts(self) -> None:
        """
        Сброс счетчика неудачных попыток логина после успешного входа.
        """
        self.login_attempts = 0
        self.locked_until = None

    def increment_login_attempts(self, lock_duration_minutes: int = 15) -> None:
        """
        Увеличение счетчика неудачных попыток логина.
        После 5 попыток - блокировка аккаунта на lock_duration_minutes.

        Args:
            lock_duration_minutes: Длительность блокировки в минутах (default: 15)
        """
        self.login_attempts += 1

        # После 5 неудачных попыток - блокировка
        if self.login_attempts >= 5:
            now = datetime.now(timezone.utc)
            self.locked_until = now + timedelta(minutes=lock_duration_minutes)

    def can_login(self) -> bool:
        """
        Проверка, может ли пользователь войти в систему.

        Returns:
            True если пользователь может войти, False иначе
        """
        return self.enabled and not self.is_locked()

    def add_password_to_history(self, password_hash: str, max_history: int = 5) -> None:
        """
        Добавление текущего пароля в историю перед сменой.

        Args:
            password_hash: Bcrypt хеш текущего пароля
            max_history: Максимальное количество паролей в истории (default: 5)
        """
        if self.password_history is None:
            self.password_history = []

        # Добавляем текущий хеш в начало списка
        self.password_history.insert(0, password_hash)

        # Обрезаем до максимального размера
        self.password_history = self.password_history[:max_history]

    def is_password_in_history(self, password_hash: str) -> bool:
        """
        Проверка, использовался ли пароль ранее (в истории).

        Args:
            password_hash: Bcrypt хеш пароля для проверки

        Returns:
            True если пароль был использован ранее, False иначе
        """
        if self.password_history is None:
            return False

        return password_hash in self.password_history
