"""
Pydantic схемы для работы с элементами хранения.
"""
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.db.models.storage_element import StorageMode
from app.schemas.common import IDMixin, TimestampMixin


class StorageElementBase(BaseModel):
    """
    Базовая схема элемента хранения с общими полями.
    """

    name: str = Field(..., min_length=3, max_length=100, description="Имя элемента хранения")
    description: Optional[str] = Field(None, description="Описание элемента")
    base_url: str = Field(..., description="URL для доступа к элементу")
    health_check_url: Optional[str] = Field(None, description="URL для проверки здоровья")
    storage_type: str = Field(default="local", description="Тип хранения (local или s3)")
    max_size_gb: Optional[int] = Field(None, ge=1, description="Максимальный размер в ГБ")
    retention_days: int = Field(default=0, ge=0, description="Срок хранения в днях (0 = без ограничений)")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Дополнительные метаданные (JSON)")


class StorageElementCreate(StorageElementBase):
    """
    Схема для создания элемента хранения.

    Используется в POST /api/storage-elements/
    """

    mode: StorageMode = Field(default=StorageMode.EDIT, description="Режим работы")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "storage-01",
                "description": "Основное хранилище для текущих документов",
                "mode": "edit",
                "base_url": "http://storage-01.local:8010",
                "health_check_url": "http://storage-01.local:8010/health",
                "storage_type": "local",
                "max_size_gb": 1000,
                "retention_days": 365,
                "metadata": {
                    "location": "datacenter-1",
                    "rack": "A-12",
                },
            }
        }
    )


class StorageElementUpdate(BaseModel):
    """
    Схема для обновления элемента хранения.

    Используется в PUT/PATCH /api/storage-elements/{element_id}
    Все поля опциональны - обновляются только переданные.
    """

    description: Optional[str] = Field(None, description="Описание элемента")
    base_url: Optional[str] = Field(None, description="URL для доступа к элементу")
    health_check_url: Optional[str] = Field(None, description="URL для проверки здоровья")
    max_size_gb: Optional[int] = Field(None, ge=1, description="Максимальный размер в ГБ")
    retention_days: Optional[int] = Field(None, ge=0, description="Срок хранения в днях")
    is_active: Optional[bool] = Field(None, description="Активен ли элемент")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Дополнительные метаданные")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "description": "Обновленное описание хранилища",
                "max_size_gb": 2000,
                "retention_days": 730,
                "is_active": True,
                "metadata": {
                    "location": "datacenter-2",
                },
            }
        }
    )


class StorageElementChangeModeRequest(BaseModel):
    """
    Схема для изменения режима элемента хранения.

    Используется в POST /api/storage-elements/{element_id}/change-mode
    """

    new_mode: StorageMode = Field(..., description="Новый режим работы")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "new_mode": "ro",
            }
        }
    )


class StorageElementResponse(StorageElementBase, IDMixin, TimestampMixin):
    """
    Схема элемента хранения в ответе API.

    Используется в GET /api/storage-elements/, GET /api/storage-elements/{element_id}
    """

    mode: StorageMode = Field(description="Режим работы (edit, rw, ro, ar)")
    is_active: bool = Field(description="Активен ли элемент")
    can_write: bool = Field(description="Можно ли записывать файлы")
    can_delete: bool = Field(description="Можно ли удалять файлы")
    is_archived: bool = Field(description="Находится ли в архивном режиме")

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "456e7890-e89b-12d3-a456-426614174001",
                "name": "storage-01",
                "description": "Основное хранилище для текущих документов",
                "mode": "edit",
                "base_url": "http://storage-01.local:8010",
                "health_check_url": "http://storage-01.local:8010/health",
                "storage_type": "local",
                "max_size_gb": 1000,
                "retention_days": 365,
                "is_active": True,
                "can_write": True,
                "can_delete": True,
                "is_archived": False,
                "metadata": {
                    "location": "datacenter-1",
                    "rack": "A-12",
                },
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-01-15T10:30:00Z",
            }
        },
    )


class StorageElementInDB(StorageElementResponse):
    """
    Схема элемента хранения как в БД.

    Используется внутри приложения для работы с полными данными.
    """

    model_config = ConfigDict(from_attributes=True)
