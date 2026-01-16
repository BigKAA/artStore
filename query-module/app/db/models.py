"""
Query Module - Database Models.

SQLAlchemy модели для PostgreSQL с поддержкой Full-Text Search (GIN индексы).
Используются для кеширования метаданных файлов из Storage Elements.
"""

from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    Column,
    String,
    Integer,
    BigInteger,
    DateTime,
    Text,
    ARRAY,
    Index,
    func,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class FileMetadata(Base):
    """
    Модель метаданных файла для кеширования в PostgreSQL.

    Используется для:
    - Быстрого поиска файлов (Full-Text Search с GIN индексами)
    - Кеширования метаданных из Storage Elements
    - Снижения нагрузки на Storage Elements при частых запросах

    Источник истины: attr.json файлы в Storage Element
    Обновление: При каждом запросе или по расписанию (TTL-based)
    """

    __tablename__ = "file_metadata_cache"

    # Primary Key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        comment="UUID файла (совпадает с ID в Storage Element)"
    )

    # File Information
    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Оригинальное имя файла (для отображения пользователю)"
    )

    storage_filename: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        comment="Имя файла в Storage Element (с username_timestamp_uuid)"
    )

    file_size: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="Размер файла в bytes"
    )

    mime_type: Mapped[Optional[str]] = mapped_column(
        String(127),
        nullable=True,
        index=True,
        comment="MIME тип файла (image/jpeg, application/pdf, etc.)"
    )

    sha256_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,  # Index без unique - позволяет duplicate content
        comment="SHA256 хеш файла для верификации целостности"
    )

    # User Information
    username: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Владелец файла (из JWT sub или username)"
    )

    # Metadata Fields
    tags: Mapped[Optional[List[str]]] = mapped_column(
        ARRAY(String(50)),
        nullable=True,
        comment="Теги файла для поиска (максимум 50 тегов)"
    )

    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Описание файла"
    )

    # Storage Information
    storage_element_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="ID Storage Element где хранится файл"
    )

    storage_element_url: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        comment="URL Storage Element для скачивания файла"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="Дата создания файла в Storage Element"
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="Дата последнего обновления метаданных"
    )

    # Cache Management
    cache_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="Дата последнего обновления кеша"
    )

    # Full-Text Search (PostgreSQL TSVECTOR)
    search_vector: Mapped[Optional[str]] = mapped_column(
        TSVECTOR,
        nullable=True,
        comment="Полнотекстовый поисковый вектор (auto-generated)"
    )

    # Constraints
    __table_args__ = (
        CheckConstraint('file_size >= 0', name='check_file_size_positive'),
        CheckConstraint('array_length(tags, 1) <= 50', name='check_tags_count'),

        # GIN индекс для Full-Text Search (русский язык)
        Index(
            'idx_file_metadata_search_vector',
            'search_vector',
            postgresql_using='gin'
        ),

        # GIN индекс для поиска по тегам
        Index(
            'idx_file_metadata_tags',
            'tags',
            postgresql_using='gin'
        ),

        # B-tree индексы для частых запросов
        Index('idx_file_metadata_username_created', 'username', 'created_at'),
        Index('idx_file_metadata_storage_elem', 'storage_element_id', 'created_at'),
        Index('idx_file_metadata_mime_type', 'mime_type', 'created_at'),

        # Composite индекс для фильтрации по размеру
        Index('idx_file_metadata_file_size', 'file_size', 'created_at'),

        {'comment': 'Кеш метаданных файлов для быстрого поиска и снижения нагрузки на Storage Elements'}
    )

    @hybrid_property
    def is_cache_stale(self, ttl_seconds: int = 3600) -> bool:
        """
        Проверка устарелости кеша.

        Args:
            ttl_seconds: TTL кеша в секундах (по умолчанию 1 час)

        Returns:
            bool: True если кеш устарел и требует обновления
        """
        if not self.cache_updated_at:
            return True

        now = datetime.utcnow()
        cache_age = (now - self.cache_updated_at).total_seconds()
        return cache_age > ttl_seconds

    def __repr__(self) -> str:
        return (
            f"<FileMetadata(id='{self.id}', "
            f"filename='{self.filename}', "
            f"username='{self.username}', "
            f"storage_element='{self.storage_element_id}')>"
        )


class SearchHistory(Base):
    """
    История поисковых запросов для аналитики и оптимизации.

    Используется для:
    - Анализа популярных поисковых запросов
    - Автодополнения (autocomplete)
    - Оптимизации индексов на основе реальных запросов
    - Мониторинга производительности поиска
    """

    __tablename__ = "search_history"

    # Primary Key
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Auto-increment ID записи"
    )

    # Search Query Information
    query_text: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Текст поискового запроса"
    )

    search_mode: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Режим поиска (exact, partial, fulltext)"
    )

    # Search Filters (JSON-like storage)
    filters_applied: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Примененные фильтры (JSON строка)"
    )

    # Results Information
    results_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Количество найденных результатов"
    )

    response_time_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Время ответа в миллисекундах"
    )

    # User Information
    username: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
        comment="Пользователь выполнивший поиск"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
        comment="Дата и время выполнения поиска"
    )

    # Constraints
    __table_args__ = (
        CheckConstraint('results_count >= 0', name='check_results_count_positive'),
        CheckConstraint('response_time_ms >= 0', name='check_response_time_positive'),

        # Индексы для аналитики
        Index('idx_search_history_created', 'created_at'),
        Index('idx_search_history_username_created', 'username', 'created_at'),
        Index('idx_search_history_mode', 'search_mode', 'created_at'),

        {'comment': 'История поисковых запросов для аналитики и оптимизации'}
    )

    def __repr__(self) -> str:
        return (
            f"<SearchHistory(id={self.id}, "
            f"query='{self.query_text[:50] if self.query_text else None}...', "
            f"mode='{self.search_mode}', "
            f"results={self.results_count}, "
            f"time={self.response_time_ms}ms)>"
        )


class DownloadStatistics(Base):
    """
    Статистика скачивания файлов для мониторинга и аналитики.

    Используется для:
    - Мониторинга популярности файлов
    - CDN pre-caching решений
    - Capacity planning
    - Billing и usage metrics
    """

    __tablename__ = "download_statistics"

    # Primary Key
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Auto-increment ID записи"
    )

    # File Information
    file_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
        comment="UUID файла (FK к FileMetadata)"
    )

    # Download Information
    bytes_transferred: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="Количество переданных bytes"
    )

    download_time_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Время скачивания в миллисекундах"
    )

    was_resumed: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        comment="Было ли скачивание resumed (HTTP Range request)"
    )

    # User Information
    username: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
        comment="Пользователь скачавший файл"
    )

    # Storage Information
    storage_element_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="ID Storage Element с которого скачан файл"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
        comment="Дата и время скачивания"
    )

    # Constraints
    __table_args__ = (
        CheckConstraint('bytes_transferred >= 0', name='check_bytes_positive'),
        CheckConstraint('download_time_ms >= 0', name='check_download_time_positive'),

        # Индексы для аналитики
        Index('idx_download_stats_file_created', 'file_id', 'created_at'),
        Index('idx_download_stats_storage_created', 'storage_element_id', 'created_at'),
        Index('idx_download_stats_username_created', 'username', 'created_at'),

        {'comment': 'Статистика скачивания файлов для мониторинга и capacity planning'}
    )

    def __repr__(self) -> str:
        return (
            f"<DownloadStatistics(id={self.id}, "
            f"file_id='{self.file_id}', "
            f"bytes={self.bytes_transferred}, "
            f"time={self.download_time_ms}ms, "
            f"resumed={self.was_resumed})>"
        )
