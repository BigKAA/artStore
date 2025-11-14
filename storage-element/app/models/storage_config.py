"""
Storage Configuration model для хранения текущего режима работы.

Текущее состояние модуля хранится в базе данных.
Если конфигурация не соответствует состоянию в БД, используется значение из БД.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column, declared_attr
from sqlalchemy import func

from app.core.config import StorageMode
from app.db.base import Base


class StorageConfig(Base):
    """
    Модель конфигурации Storage Element.

    Singleton таблица - всегда только одна строка с id=1.

    Поля:
    - id: Primary key (всегда 1)
    - current_mode: Текущий режим работы (edit, rw, ro, ar)
    - mode_changed_at: Время последнего изменения режима
    - mode_changed_by: User ID кто изменил режим
    - is_master: Текущий узел является мастером (для edit/rw режимов)
    - master_elected_at: Время выбора текущего мастера
    - total_files: Количество файлов в хранилище
    - total_size_bytes: Общий размер файлов в байтах
    - last_cache_rebuild: Время последней пересборки кеша
    """

    @declared_attr
    def __tablename__(cls) -> str:
        """Dynamic table name based on configuration."""
        from app.core.config import settings
        return f"{settings.database.table_prefix}_config"

    # Singleton primary key
    id: Mapped[int] = mapped_column(
        primary_key=True,
        default=1,
        comment="Primary key (всегда 1 для singleton)"
    )

    # Storage mode
    current_mode: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default=StorageMode.RW.value,
        comment="Текущий режим работы (edit/rw/ro/ar)"
    )

    mode_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Время последнего изменения режима"
    )

    mode_changed_by: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="User ID кто изменил режим"
    )

    # Master election (для edit/rw режимов)
    is_master: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Текущий узел является мастером"
    )

    master_elected_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Время выбора текущего мастера"
    )

    # Statistics
    total_files: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        comment="Количество файлов в хранилище"
    )

    total_size_bytes: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        comment="Общий размер файлов в байтах"
    )

    last_cache_rebuild: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Время последней пересборки кеша"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Время создания записи"
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="Время последнего обновления"
    )

    def __repr__(self) -> str:
        return (
            f"<StorageConfig("
            f"mode={self.current_mode}, "
            f"is_master={self.is_master}, "
            f"files={self.total_files}, "
            f"size_gb={self.total_size_bytes / (1024**3):.2f}"
            f")>"
        )
