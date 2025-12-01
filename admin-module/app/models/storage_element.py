"""
Модель Storage Element для Admin Module.
Хранит информацию о физических хранилищах файлов.
"""

from datetime import datetime
from sqlalchemy import String, Integer, Enum as SQLEnum, Boolean, Index, DateTime, BigInteger
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional
import enum

from .base import Base, TimestampMixin


class StorageMode(str, enum.Enum):
    """
    Режимы работы Storage Element.

    Transitions:
        edit (fixed) → rw → ro → ar
    """

    EDIT = "edit"  # Полный CRUD (default для активного хранения)
    RW = "rw"      # Read-write, удаление запрещено (transitional state)
    RO = "ro"      # Read-only (archived но доступно)
    AR = "ar"      # Archive mode (только метаданные, файлы на холодном хранилище)


class StorageType(str, enum.Enum):
    """Типы физического хранилища."""

    LOCAL = "local"  # Локальная файловая система
    S3 = "s3"        # S3-совместимое хранилище (MinIO, AWS S3)


class StorageStatus(str, enum.Enum):
    """Статусы Storage Element."""

    ONLINE = "online"      # Доступен и работает
    OFFLINE = "offline"    # Недоступен
    DEGRADED = "degraded"  # Работает с ограничениями
    MAINTENANCE = "maintenance"  # На обслуживании


class StorageElement(Base, TimestampMixin):
    """
    Модель Storage Element - физическое хранилище файлов.

    Attributes:
        id: Уникальный идентификатор (auto-increment)
        element_id: Строковый ID для Redis Registry (например: se-01) - Sprint 14
        name: Человекочитаемое имя (уникальное)
        description: Описание хранилища
        mode: Режим работы (edit/rw/ro/ar)
        priority: Приоритет для Sequential Fill (меньше = выше приоритет) - Sprint 14
        storage_type: Тип физического хранилища (local/s3)
        base_path: Базовый путь для local или bucket name для s3
        api_url: URL для API доступа к storage element
        api_key: API ключ для аутентификации (хешированный)
        status: Текущий статус
        capacity_bytes: Общая емкость в байтах
        used_bytes: Использовано байтов
        file_count: Количество файлов
        retention_days: Срок хранения файлов в днях (None = бессрочно)
        last_health_check: Время последней проверки health
        is_replicated: Флаг репликации (для будущего использования)
        replica_count: Количество реплик
        created_at: Дата создания (из TimestampMixin)
        updated_at: Дата обновления (из TimestampMixin)
    """

    __tablename__ = "storage_elements"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Unique identifier for Redis Registry (Sprint 14)
    element_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        unique=True,
        nullable=True,
        index=True,
        comment="Уникальный строковый ID для Redis Registry (например: se-01)"
    )

    # Basic information
    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
        comment="Человекочитаемое имя storage element (уникальное)"
    )

    description: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Описание хранилища"
    )

    # Operation mode
    mode: Mapped[StorageMode] = mapped_column(
        SQLEnum(StorageMode, name="storage_mode_enum", create_type=True),
        nullable=False,
        default=StorageMode.EDIT,
        index=True,
        comment="Режим работы storage element"
    )

    # Priority for Sequential Fill algorithm (Sprint 14)
    # Меньше значение = выше приоритет (100 = default, 1-99 = high priority, 101+ = low priority)
    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
        comment="Приоритет для Sequential Fill алгоритма (меньше = выше приоритет)"
    )

    # Storage configuration
    storage_type: Mapped[StorageType] = mapped_column(
        SQLEnum(StorageType, name="storage_type_enum", create_type=True),
        nullable=False,
        default=StorageType.LOCAL,
        comment="Тип физического хранилища"
    )

    base_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Базовый путь (local) или bucket name (s3)"
    )

    api_url: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="URL для API доступа к storage element"
    )

    api_key: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="API ключ для аутентификации (хешированный)"
    )

    # Status and monitoring
    status: Mapped[StorageStatus] = mapped_column(
        SQLEnum(StorageStatus, name="storage_status_enum", create_type=True),
        nullable=False,
        default=StorageStatus.ONLINE,
        index=True,
        comment="Текущий статус storage element"
    )

    capacity_bytes: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Общая емкость в байтах"
    )

    used_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        comment="Использовано байтов"
    )

    file_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Количество файлов"
    )

    retention_days: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Срок хранения файлов в днях (None = бессрочно)"
    )

    last_health_check: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Время последней проверки health"
    )

    # Replication (для будущего использования)
    is_replicated: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Флаг репликации"
    )

    replica_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Количество реплик"
    )

    # Indexes для производительности
    __table_args__ = (
        Index("idx_storage_mode_status", "mode", "status"),
        Index("idx_storage_status", "status"),
        Index("idx_storage_mode_priority", "mode", "priority"),  # Sprint 14: Sequential Fill
    )

    def __repr__(self) -> str:
        """Строковое представление storage element."""
        return f"<StorageElement(id={self.id}, element_id='{self.element_id}', name='{self.name}', mode={self.mode}, priority={self.priority}, status={self.status})>"

    @property
    def is_available(self) -> bool:
        """Проверка доступности storage element."""
        return self.status == StorageStatus.ONLINE

    @property
    def is_writable(self) -> bool:
        """Проверка возможности записи в storage element."""
        return self.mode in (StorageMode.EDIT, StorageMode.RW) and self.is_available

    @property
    def is_deletable(self) -> bool:
        """Проверка возможности удаления файлов из storage element."""
        return self.mode == StorageMode.EDIT and self.is_available

    @property
    def usage_percentage(self) -> Optional[float]:
        """Процент использования емкости."""
        if self.capacity_bytes and self.capacity_bytes > 0:
            return (self.used_bytes / self.capacity_bytes) * 100
        return None

    @property
    def available_bytes(self) -> Optional[int]:
        """Доступное место в байтах."""
        if self.capacity_bytes:
            return max(0, self.capacity_bytes - self.used_bytes)
        return None

    def can_transition_to(self, new_mode: StorageMode) -> bool:
        """
        Проверка возможности перехода в новый режим.

        Allowed transitions:
            edit → CANNOT BE CHANGED (fixed)
            rw → ro
            ro → ar
            ar → other modes (только через config + restart)

        Args:
            new_mode: Новый режим

        Returns:
            bool: True если переход возможен
        """
        if self.mode == StorageMode.EDIT:
            # edit режим не может быть изменен через API
            return False

        if self.mode == StorageMode.RW:
            return new_mode == StorageMode.RO

        if self.mode == StorageMode.RO:
            return new_mode == StorageMode.AR

        if self.mode == StorageMode.AR:
            # ar может быть изменен только через конфигурацию и рестарт
            return False

        return False

    def has_sufficient_space(self, required_bytes: int) -> bool:
        """
        Проверка наличия достаточного свободного места.

        Args:
            required_bytes: Требуемое количество байт

        Returns:
            bool: True если достаточно места
        """
        if not self.capacity_bytes:
            # Если capacity не задан, считаем что места достаточно
            return True

        available = self.available_bytes
        if available is None:
            return True

        return available >= required_bytes

    def update_usage(self, bytes_delta: int, files_delta: int = 0) -> None:
        """
        Обновление статистики использования.

        Args:
            bytes_delta: Изменение использованного места (может быть отрицательным)
            files_delta: Изменение количества файлов (может быть отрицательным)
        """
        self.used_bytes = max(0, self.used_bytes + bytes_delta)
        self.file_count = max(0, self.file_count + files_delta)
