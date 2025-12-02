"""
Admin Module - File Finalize Transaction Model.

Модель для логирования Two-Phase Commit транзакций финализации файлов.

Two-Phase Commit Process:
1. COPYING: Начало копирования файла с Edit SE на RW SE
2. COPIED: Файл скопирован на target SE
3. VERIFYING: Проверка checksum source == target
4. COMPLETED: Успешная финализация (metadata обновлена)
5. FAILED: Ошибка на любом этапе
6. ROLLED_BACK: Откат транзакции (удаление файла с target SE)

Safety Features:
- Checksum verification предотвращает data corruption
- Retry logic для transient failures
- 24-hour safety margin перед cleanup источника
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ENUM, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.base import Base


class FinalizeTransactionStatus(str, Enum):
    """
    Статусы транзакции финализации.

    Workflow:
    COPYING → COPIED → VERIFYING → COMPLETED
                                 ↘ FAILED → ROLLED_BACK
    """
    COPYING = "copying"       # Фаза 1: копирование на target SE
    COPIED = "copied"         # Фаза 1 завершена: файл на target SE
    VERIFYING = "verifying"   # Фаза 2: проверка checksums
    COMPLETED = "completed"   # Успешная финализация
    FAILED = "failed"         # Ошибка (checksum mismatch, network, etc.)
    ROLLED_BACK = "rolled_back"  # Откат (файл удалён с target SE)


class FileFinalizeTransaction(Base):
    """
    Лог транзакций финализации файлов (Two-Phase Commit).

    Эта таблица хранит полную историю всех операций финализации,
    включая успешные, неудачные и откаченные транзакции.

    Attributes:
        transaction_id: UUID транзакции
        file_id: ID финализируемого файла
        source_se: ID исходного Storage Element (Edit SE)
        target_se: ID целевого Storage Element (RW SE)
        status: Текущий статус транзакции
        checksum_source: SHA-256 checksum на source SE
        checksum_target: SHA-256 checksum на target SE
        file_size: Размер файла
        error_message: Сообщение об ошибке
        error_code: Код ошибки для categorization
        retry_count: Количество retry attempts
        initiated_by: ID инициатора финализации
        created_at: Дата создания транзакции
        updated_at: Дата последнего обновления
        completed_at: Дата завершения (success или failure)
    """

    __tablename__ = "file_finalize_transactions"

    # Primary Key
    transaction_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
        comment="Уникальный UUID идентификатор транзакции"
    )

    # File reference
    file_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("files.file_id", ondelete="CASCADE"),
        nullable=False,
        comment="ID файла который финализируется"
    )

    # Storage Elements
    source_se: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="ID исходного Storage Element (Edit SE)"
    )

    target_se: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="ID целевого Storage Element (RW SE)"
    )

    # Transaction Status
    # create_type=True для автоматического создания ENUM при create_all
    status: Mapped[FinalizeTransactionStatus] = mapped_column(
        ENUM(FinalizeTransactionStatus, name='finalize_transaction_status_enum', create_type=True),
        nullable=False,
        server_default='copying',
        comment="Статус транзакции"
    )

    # Checksums для verification
    checksum_source: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="SHA-256 checksum на source SE"
    )

    checksum_target: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="SHA-256 checksum на target SE"
    )

    # File details
    file_size: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Размер файла в байтах"
    )

    # Error handling
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Сообщение об ошибке"
    )

    error_code: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Код ошибки"
    )

    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        comment="Количество retry attempts"
    )

    # Initiator tracking
    initiated_by: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Client ID или User ID инициатора"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Дата создания транзакции"
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="Дата последнего обновления"
    )

    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Дата завершения транзакции"
    )

    # Relationship
    file = relationship("File", back_populates="finalize_transactions")

    def __repr__(self) -> str:
        """Строковое представление транзакции."""
        return (
            f"<FileFinalizeTransaction(id={self.transaction_id}, "
            f"file_id={self.file_id}, "
            f"status={self.status.value}, "
            f"source={self.source_se} → target={self.target_se})>"
        )

    @property
    def is_pending(self) -> bool:
        """Проверка, находится ли транзакция в процессе."""
        return self.status in (
            FinalizeTransactionStatus.COPYING,
            FinalizeTransactionStatus.COPIED,
            FinalizeTransactionStatus.VERIFYING
        )

    @property
    def is_completed(self) -> bool:
        """Проверка, завершена ли транзакция успешно."""
        return self.status == FinalizeTransactionStatus.COMPLETED

    @property
    def is_failed(self) -> bool:
        """Проверка, завершена ли транзакция с ошибкой."""
        return self.status in (
            FinalizeTransactionStatus.FAILED,
            FinalizeTransactionStatus.ROLLED_BACK
        )

    @property
    def checksums_match(self) -> Optional[bool]:
        """
        Проверка совпадения checksums source и target.

        Returns:
            True если совпадают, False если нет, None если один из них отсутствует
        """
        if not self.checksum_source or not self.checksum_target:
            return None
        return self.checksum_source == self.checksum_target
