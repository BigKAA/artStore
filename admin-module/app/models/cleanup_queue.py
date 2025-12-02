"""
Admin Module - File Cleanup Queue Model.

Модель для очереди Garbage Collection (GC) задач.

GC Job стратегии:
1. TTL-based cleanup: удаление temporary файлов с истекшим TTL
2. Finalized files cleanup: удаление из Edit SE после успешной финализации (+24h safety)
3. Orphaned files cleanup: удаление файлов без записей в DB (age > 7 days)

Cleanup Reasons:
- ttl_expired: TTL файла истёк
- finalized: файл успешно финализирован (скопирован на RW SE)
- orphaned: файл без записи в DB (data inconsistency)
- manual: ручное удаление администратором

Safety Features:
- 24-hour safety margin после финализации
- 7-day grace period для orphaned файлов
- Retry logic для transient failures
- Priority queue для срочных удалений
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class FileCleanupQueue(Base):
    """
    Очередь задач для Garbage Collection.

    GC job периодически (каждые 6 часов) обрабатывает записи из этой очереди,
    удаляя файлы с Storage Elements когда наступает scheduled_at время.

    Attributes:
        id: Уникальный ID записи
        file_id: UUID файла для удаления
        storage_element_id: ID Storage Element где находится файл
        storage_path: Путь к файлу
        scheduled_at: Дата когда файл должен быть удалён
        priority: Приоритет (выше = раньше)
        cleanup_reason: Причина cleanup
        processed_at: Дата обработки
        success: Успешность операции
        error_message: Сообщение об ошибке
        retry_count: Количество retry attempts
        created_at: Дата добавления в очередь
    """

    __tablename__ = "file_cleanup_queue"

    # Primary Key
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="Уникальный ID записи"
    )

    # File reference
    file_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        comment="UUID файла для удаления"
    )

    # Storage location
    storage_element_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="ID Storage Element где находится файл"
    )

    storage_path: Mapped[Optional[str]] = mapped_column(
        String(1000),
        nullable=True,
        comment="Путь к файлу в Storage Element"
    )

    # Scheduling
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Дата когда файл должен быть удалён"
    )

    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        comment="Приоритет (выше = раньше, default 0)"
    )

    # Reason tracking
    cleanup_reason: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Причина: ttl_expired, finalized, orphaned, manual"
    )

    # Processing status
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Дата обработки"
    )

    success: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True,
        comment="Успешность операции"
    )

    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Сообщение об ошибке"
    )

    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        comment="Количество retry attempts"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Дата добавления в очередь"
    )

    def __repr__(self) -> str:
        """Строковое представление записи."""
        return (
            f"<FileCleanupQueue(id={self.id}, "
            f"file_id={self.file_id}, "
            f"reason={self.cleanup_reason}, "
            f"scheduled={self.scheduled_at}, "
            f"processed={self.processed_at is not None})>"
        )

    @property
    def is_pending(self) -> bool:
        """Проверка, ожидает ли запись обработки."""
        return self.processed_at is None

    @property
    def is_ready(self) -> bool:
        """Проверка, готова ли запись к обработке (scheduled_at <= now)."""
        if not self.is_pending:
            return False
        return datetime.utcnow() >= self.scheduled_at.replace(tzinfo=None)

    @property
    def is_failed(self) -> bool:
        """Проверка, завершилась ли обработка с ошибкой."""
        return self.processed_at is not None and not self.success


class CleanupReason:
    """Константы для причин cleanup."""
    TTL_EXPIRED = "ttl_expired"     # TTL истёк
    FINALIZED = "finalized"         # Файл финализирован
    ORPHANED = "orphaned"           # Orphaned файл
    MANUAL = "manual"               # Ручное удаление


class CleanupPriority:
    """Константы для приоритетов cleanup."""
    LOW = 0        # Стандартный приоритет
    NORMAL = 10    # Обычная очистка
    HIGH = 50      # Срочная очистка
    URGENT = 100   # Критически важное удаление
