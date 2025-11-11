"""
File Metadata model для кеширования метаданных в PostgreSQL.

Кеш для быстрого поиска файлов. Источник истины - *.attr.json файлы.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import String, Integer, BigInteger, DateTime, Index, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import func

from app.core.config import settings
from app.db.base import Base


class FileMetadata(Base):
    """
    Модель метаданных файла (кеш из *.attr.json).

    Таблица создается с префиксом из конфигурации для уникальности
    в shared database.

    Поля:
    - file_id: UUID уникального идентификатора
    - original_filename: Оригинальное имя файла
    - storage_filename: Имя в хранилище (с username, timestamp, uuid)
    - file_size: Размер в байтах
    - content_type: MIME type
    - created_at: Время создания
    - created_by_id: User ID создателя
    - created_by_username: Username создателя
    - created_by_fullname: ФИО создателя (опционально)
    - description: Описание содержимого
    - version: Версия документа
    - storage_path: Относительный путь в хранилище
    - checksum: SHA256 checksum файла
    - search_vector: PostgreSQL full-text search vector
    - metadata_json: Дополнительные метаданные (JSONB)
    """

    __tablename__ = f"{settings.database.table_prefix}_files"

    # Primary Key
    file_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        index=True,
        comment="Уникальный идентификатор файла"
    )

    # File information
    original_filename: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True,
        comment="Оригинальное имя файла"
    )

    storage_filename: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        unique=True,
        index=True,
        comment="Имя файла в хранилище (с username, timestamp, uuid)"
    )

    file_size: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="Размер файла в байтах"
    )

    content_type: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="MIME type файла"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Время создания файла"
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="Время последнего обновления метаданных"
    )

    # User information
    created_by_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="User ID создателя файла"
    )

    created_by_username: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Username создателя"
    )

    created_by_fullname: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="ФИО создателя (опционально)"
    )

    # Content description
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Описание содержимого файла"
    )

    version: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Версия документа"
    )

    # Storage location
    storage_path: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
        comment="Относительный путь в хранилище (year/month/day/hour/)"
    )

    checksum: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA256 checksum файла"
    )

    # Full-text search vector (PostgreSQL)
    search_vector: Mapped[Optional[str]] = mapped_column(
        TSVECTOR,
        nullable=True,
        comment="Full-text search vector (auto-generated)"
    )

    # Additional metadata as JSONB
    metadata_json: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Дополнительные метаданные (расширяемое поле)"
    )

    # Indexes для оптимизации поиска
    __table_args__ = (
        # Full-text search index (GIN)
        Index(
            f"idx_{settings.database.table_prefix}_search_vector",
            "search_vector",
            postgresql_using="gin"
        ),
        # Composite index для поиска по пользователю и дате
        Index(
            f"idx_{settings.database.table_prefix}_user_date",
            "created_by_id",
            "created_at"
        ),
        # Index для поиска по оригинальному имени
        Index(
            f"idx_{settings.database.table_prefix}_filename",
            "original_filename"
        ),
        # JSONB index для поиска по metadata
        Index(
            f"idx_{settings.database.table_prefix}_metadata",
            "metadata_json",
            postgresql_using="gin"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<FileMetadata("
            f"file_id={self.file_id}, "
            f"filename={self.original_filename}, "
            f"size={self.file_size}, "
            f"created_by={self.created_by_username}"
            f")>"
        )
