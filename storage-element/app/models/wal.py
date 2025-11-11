"""
Write-Ahead Log (WAL) model для обеспечения атомарности операций.

WAL используется для:
- Запись намерения перед операцией
- Возможность отката при сбое
- Аудит всех операций с файлами
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import String, DateTime, Text, Index
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import func

from app.core.config import settings
from app.db.base import Base


class WALOperationType(str, Enum):
    """Типы операций WAL"""
    FILE_CREATE = "file_create"
    FILE_UPDATE = "file_update"
    FILE_DELETE = "file_delete"
    CACHE_REBUILD = "cache_rebuild"
    MODE_CHANGE = "mode_change"


class WALStatus(str, Enum):
    """Статусы транзакции WAL"""
    PENDING = "pending"      # Начато, не завершено
    COMMITTED = "committed"  # Успешно завершено
    ROLLED_BACK = "rolled_back"  # Откачено из-за ошибки
    FAILED = "failed"        # Ошибка выполнения


class WALTransaction(Base):
    """
    Модель транзакции Write-Ahead Log.

    Каждая операция с файлами записывается в WAL перед выполнением.

    Поля:
    - transaction_id: UUID транзакции
    - operation_type: Тип операции (create, update, delete, etc.)
    - status: Статус транзакции
    - file_id: UUID файла (для файловых операций)
    - operation_data: Данные операции (JSONB)
    - error_message: Сообщение об ошибке (если failed)
    - started_at: Время начала операции
    - completed_at: Время завершения операции
    - duration_ms: Длительность в миллисекундах
    """

    __tablename__ = f"{settings.database.table_prefix}_wal"

    # Primary Key
    transaction_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        comment="UUID транзакции"
    )

    # Operation details
    operation_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Тип операции (file_create, file_update, etc.)"
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=WALStatus.PENDING.value,
        index=True,
        comment="Статус транзакции (pending, committed, rolled_back, failed)"
    )

    # File reference (опционально, не для всех операций)
    file_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        index=True,
        comment="UUID файла (для файловых операций)"
    )

    # Operation data (JSONB для гибкости)
    operation_data: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Данные операции (файл, путь, метаданные и т.д.)"
    )

    # Error handling
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Сообщение об ошибке (если failed)"
    )

    # Timestamps
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Время начала операции"
    )

    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Время завершения операции"
    )

    duration_ms: Mapped[Optional[int]] = mapped_column(
        nullable=True,
        comment="Длительность операции в миллисекундах"
    )

    # User context
    user_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
        comment="User ID инициатора операции"
    )

    # Indexes для оптимизации запросов
    __table_args__ = (
        # Composite index для поиска по статусу и времени
        Index(
            f"idx_{settings.database.table_prefix}_wal_status_time",
            "status",
            "started_at"
        ),
        # Index для поиска по файлу
        Index(
            f"idx_{settings.database.table_prefix}_wal_file",
            "file_id",
            "started_at"
        ),
        # Index для JSONB поиска
        Index(
            f"idx_{settings.database.table_prefix}_wal_data",
            "operation_data",
            postgresql_using="gin"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<WALTransaction("
            f"id={self.transaction_id}, "
            f"type={self.operation_type}, "
            f"status={self.status}, "
            f"file_id={self.file_id}"
            f")>"
        )
