"""
Admin Module - File Model.

Модель для центрального реестра файлов с поддержкой retention policy.
Этот реестр используется для tracking файлов между всеми модулями системы.

Retention Policies:
- TEMPORARY: файлы в Edit SE с TTL (автоматическое удаление через GC)
- PERMANENT: файлы в RW SE (долгосрочное хранение)

Lifecycle Flow:
Upload (temporary) → Finalize (Two-Phase Commit) → Cleanup (GC job)
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.base import Base, TimestampMixin


class RetentionPolicy(str, Enum):
    """
    Политика хранения файлов.

    TEMPORARY: Временные файлы в Edit SE с автоматическим TTL.
               Используются для документов "в работе" (drafts, work-in-progress).
               По умолчанию TTL = 30 дней.

    PERMANENT: Постоянные файлы в RW SE для долгосрочного хранения.
               Используются для финализированных документов.
               Нет автоматического удаления.
    """
    TEMPORARY = "temporary"
    PERMANENT = "permanent"


class File(Base, TimestampMixin):
    """
    Центральный реестр файлов системы.

    Эта модель является единственным источником истины о файлах в системе.
    Все модули (Ingester, Query, Storage Element) синхронизируются с этим реестром.

    Attributes:
        file_id: Уникальный UUID идентификатор файла
        original_filename: Оригинальное имя файла при загрузке
        storage_filename: Имя файла в storage (может отличаться)
        file_size: Размер файла в байтах
        checksum_sha256: SHA-256 checksum для integrity verification
        content_type: MIME type файла
        description: Описание файла
        retention_policy: Политика хранения (temporary/permanent)
        ttl_expires_at: Дата истечения TTL (для temporary файлов)
        ttl_days: Количество дней TTL при создании
        finalized_at: Дата финализации (переход temporary → permanent)
        storage_element_id: ID Storage Element где хранится файл
        storage_path: Полный путь к файлу в Storage Element
        compressed: Флаг сжатия
        compression_algorithm: Алгоритм сжатия (gzip/brotli)
        original_size: Оригинальный размер до сжатия
        uploaded_by: Client ID или User ID загрузившего файл
        upload_source_ip: IP адрес загрузки
        user_metadata: Пользовательские метаданные (JSON)
        deleted_at: Дата мягкого удаления
        deletion_reason: Причина удаления
    """

    __tablename__ = "files"

    # Primary Key
    file_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
        comment="Уникальный UUID идентификатор файла"
    )

    # Метаданные файла
    original_filename: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Оригинальное имя файла при загрузке"
    )

    storage_filename: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Имя файла в storage"
    )

    file_size: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="Размер файла в байтах"
    )

    checksum_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA-256 checksum файла"
    )

    content_type: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="MIME type файла"
    )

    description: Mapped[Optional[str]] = mapped_column(
        String(1000),
        nullable=True,
        comment="Описание файла"
    )

    # Retention Policy
    # create_type=True для автоматического создания ENUM при create_all
    retention_policy: Mapped[RetentionPolicy] = mapped_column(
        ENUM(RetentionPolicy, name='retention_policy_enum', create_type=True),
        nullable=False,
        server_default='permanent',
        comment="Политика хранения: temporary или permanent"
    )

    ttl_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Дата истечения TTL (для temporary файлов)"
    )

    ttl_days: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Количество дней TTL при создании"
    )

    finalized_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Дата финализации (temporary → permanent)"
    )

    # Storage Location
    storage_element_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="ID Storage Element где хранится файл"
    )

    storage_path: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
        comment="Полный путь к файлу в Storage Element"
    )

    # Compression
    compressed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
        comment="Флаг сжатия файла"
    )

    compression_algorithm: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Алгоритм сжатия: gzip, brotli"
    )

    original_size: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Оригинальный размер до сжатия"
    )

    # Ownership and audit
    uploaded_by: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Client ID или User ID загрузившего"
    )

    upload_source_ip: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
        comment="IP адрес загрузки"
    )

    # User-defined metadata (переименовано из metadata т.к. это reserved name в SQLAlchemy)
    user_metadata: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        server_default="{}",
        comment="Пользовательские метаданные (JSON)"
    )

    # Deletion tracking
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Дата мягкого удаления"
    )

    deletion_reason: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Причина удаления: ttl_expired, gc_cleanup, manual, finalized"
    )

    # Relationships
    finalize_transactions = relationship(
        "FileFinalizeTransaction",
        back_populates="file",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """Строковое представление файла."""
        return (
            f"<File(file_id={self.file_id}, "
            f"filename={self.original_filename}, "
            f"retention={self.retention_policy.value}, "
            f"se={self.storage_element_id})>"
        )

    @property
    def is_deleted(self) -> bool:
        """Проверка, удалён ли файл (soft delete)."""
        return self.deleted_at is not None

    @property
    def is_finalized(self) -> bool:
        """Проверка, финализирован ли файл."""
        return self.finalized_at is not None

    @property
    def is_temporary(self) -> bool:
        """Проверка, является ли файл временным."""
        return self.retention_policy == RetentionPolicy.TEMPORARY

    @property
    def is_ttl_expired(self) -> bool:
        """Проверка, истёк ли TTL (для temporary файлов)."""
        if not self.is_temporary or not self.ttl_expires_at:
            return False
        return datetime.utcnow() > self.ttl_expires_at.replace(tzinfo=None)
