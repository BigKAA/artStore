"""
Модель элемента хранения.
"""
import enum
import uuid

from sqlalchemy import Boolean, Column, DateTime, Enum, Integer, JSON, String, Text
from sqlalchemy.sql import func

from app.db.session import Base


def generate_uuid():
    return str(uuid.uuid4())


class StorageMode(str, enum.Enum):
    """Режимы работы элемента хранения"""

    EDIT = "edit"  # Полный CRUD
    RW = "rw"  # Read-Write без удаления
    RO = "ro"  # Read-Only
    AR = "ar"  # Archive (только метаданные)


class StorageElement(Base):
    """
    Модель элемента хранения.

    Атрибуты:
        id: Уникальный идентификатор
        name: Имя элемента (уникальное)
        description: Описание
        mode: Режим работы (edit, rw, ro, ar)
        base_url: URL для доступа к элементу
        storage_type: Тип хранения (local или s3)
        max_size_gb: Максимальный размер в ГБ
        retention_days: Срок хранения в днях (0 = без ограничений)
        is_active: Активен ли элемент
        health_check_url: URL для проверки здоровья
        metadata: Дополнительные метаданные (JSON)
        created_at: Дата создания
        updated_at: Дата обновления
    """

    __tablename__ = "storage_elements"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)

    # Основные данные
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    mode = Column(
        Enum(StorageMode), default=StorageMode.EDIT, nullable=False, index=True
    )

    # Конфигурация доступа
    base_url = Column(String(500), nullable=False)
    health_check_url = Column(String(500), nullable=True)

    # Параметры хранения
    storage_type = Column(
        String(20), default="local", nullable=False
    )  # local или s3
    max_size_gb = Column(Integer, nullable=True)  # NULL = без ограничений
    retention_days = Column(
        Integer, default=0, nullable=False
    )  # 0 = без ограничений

    # Статус
    is_active = Column(Boolean, default=True, nullable=False)

    # Дополнительные данные
    metadata = Column(JSON, nullable=True)

    # Метаданные
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self):
        return f"<StorageElement(id={self.id}, name={self.name}, mode={self.mode})>"

    @property
    def can_write(self) -> bool:
        """Можно ли записывать файлы"""
        return self.mode in [StorageMode.EDIT, StorageMode.RW]

    @property
    def can_delete(self) -> bool:
        """Можно ли удалять файлы"""
        return self.mode == StorageMode.EDIT

    @property
    def is_archived(self) -> bool:
        """Находится ли в архивном режиме"""
        return self.mode == StorageMode.AR
