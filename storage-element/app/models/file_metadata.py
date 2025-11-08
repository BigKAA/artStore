"""
File metadata model для Storage Element.

PostgreSQL table для кеширования метаданных файлов с full-text search support.
"""

from sqlalchemy import (
    Column, String, BigInteger, Integer, TIMESTAMP, Text,
    CheckConstraint, Index, JSON
)
from sqlalchemy.dialects.postgresql import TSVECTOR, ARRAY
from sqlalchemy.sql import func
from datetime import datetime, timezone
import uuid as uuid_lib

from app.db.base import Base
from app.db.types import UUID  # Cross-database UUID type
from app.core.config import get_config


class FileMetadata(Base):
    """
    File metadata cache table.

    Единственный источник истины - это *.attr.json файлы.
    Эта таблица служит кешем для быстрого поиска и фильтрации.

    Таблица имеет динамическое имя через table_prefix для поддержки
    множественных storage elements в одной БД.
    """

    # Динамическое имя таблицы из конфигурации
    config = get_config()
    __tablename__ = f"{config.database.table_prefix}_file_metadata"

    # Primary Key
    file_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid_lib.uuid4,
        comment="Unique file identifier"
    )

    # File Information
    original_filename = Column(
        String(500),
        nullable=False,
        comment="Original filename (может быть длинным, обрезается в storage)"
    )

    storage_filename = Column(
        String(255),
        nullable=False,
        unique=True,
        comment="Actual storage filename (unique, max 200 chars + extension)"
    )

    storage_path = Column(
        String(1000),
        nullable=False,
        comment="Full path to file in storage (year/month/day/hour/)"
    )

    file_size = Column(
        BigInteger,
        nullable=False,
        comment="File size in bytes"
    )

    mime_type = Column(
        String(255),
        comment="MIME type (e.g., application/pdf)"
    )

    sha256 = Column(
        String(64),  # SHA256 hex string is 64 chars
        nullable=False,
        comment="SHA256 checksum for integrity verification"
    )

    # Upload Information
    uploaded_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="Upload timestamp (UTC)"
    )

    uploaded_by = Column(
        String(255),
        nullable=False,
        comment="Username who uploaded the file"
    )

    uploader_full_name = Column(
        String(500),
        comment="Full name of uploader (from LDAP)"
    )

    # Metadata
    description = Column(
        Text,
        comment="File description (searchable)"
    )

    version = Column(
        Integer,
        nullable=False,
        default=1,
        comment="File version number (for updates)"
    )

    tags = Column(
        JSON,  # JSON для совместимости с SQLite в тестах, в PostgreSQL будет JSONB
        comment="Array of tags for categorization"
    )

    # Retention
    retention_days = Column(
        Integer,
        nullable=False,
        comment="Retention period in days"
    )

    retention_expires_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        comment="Retention expiration timestamp (UTC)"
    )

    # Full-Text Search Vector (только для PostgreSQL, не работает с SQLite)
    # В production с PostgreSQL добавится через Alembic migration
    # search_vector = Column(
    #     TSVECTOR,
    #     comment="Full-text search vector (auto-generated from filename + description)"
    # )

    # Timestamps
    created_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="Record creation timestamp"
    )

    updated_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        comment="Record last update timestamp"
    )

    # Constraints
    __table_args__ = (
        CheckConstraint('file_size > 0', name='ck_file_size_positive'),
        CheckConstraint('version >= 1', name='ck_version_minimum'),
        CheckConstraint('retention_days > 0', name='ck_retention_positive'),

        # Indexes
        Index('ix_uploaded_at', 'uploaded_at'),
        Index('ix_uploaded_by', 'uploaded_by'),
        Index('ix_retention_expires_at', 'retention_expires_at'),
        Index('ix_sha256', 'sha256'),

        # GIN index для full-text search (только PostgreSQL, добавится через migration)
        # Index(
        #     'ix_search_vector',
        #     'search_vector',
        #     postgresql_using='gin'
        # ),

        # Partial index для скоро истекающих файлов
        Index(
            'ix_expiring_soon',
            'retention_expires_at',
            postgresql_where=(
                "retention_expires_at < (CURRENT_TIMESTAMP + INTERVAL '30 days')"
            )
        ),
    )

    def __repr__(self):
        return (
            f"<FileMetadata(file_id={self.file_id}, "
            f"original_filename='{self.original_filename}', "
            f"uploaded_by='{self.uploaded_by}')>"
        )

    def to_dict(self):
        """Convert model to dictionary."""
        return {
            "file_id": str(self.file_id),
            "original_filename": self.original_filename,
            "storage_filename": self.storage_filename,
            "storage_path": self.storage_path,
            "file_size": self.file_size,
            "mime_type": self.mime_type,
            "sha256": self.sha256,
            "uploaded_at": self.uploaded_at.isoformat() if self.uploaded_at else None,
            "uploaded_by": self.uploaded_by,
            "uploader_full_name": self.uploader_full_name,
            "description": self.description,
            "version": self.version,
            "tags": self.tags,
            "retention_days": self.retention_days,
            "retention_expires_at": (
                self.retention_expires_at.isoformat()
                if self.retention_expires_at else None
            ),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
