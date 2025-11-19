"""
Pydantic schemas для Storage Elements.
Request и Response модели для storage element endpoints.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

from app.models.storage_element import StorageMode, StorageType, StorageStatus


class StorageElementResponse(BaseModel):
    """Response модель для Storage Element (без чувствительных данных)."""

    id: int = Field(..., description="Идентификатор storage element")
    name: str = Field(..., description="Название storage element")
    description: Optional[str] = Field(None, description="Описание")
    mode: StorageMode = Field(..., description="Режим работы (edit/rw/ro/ar)")
    storage_type: StorageType = Field(..., description="Тип хранилища (local/s3)")
    base_path: str = Field(..., description="Базовый путь или bucket name")
    api_url: str = Field(..., description="URL API storage element")
    status: StorageStatus = Field(..., description="Текущий статус")
    capacity_bytes: Optional[int] = Field(None, description="Общая емкость в байтах")
    used_bytes: int = Field(..., description="Использовано байтов")
    file_count: int = Field(..., description="Количество файлов")
    retention_days: Optional[int] = Field(None, description="Срок хранения в днях")
    last_health_check: Optional[datetime] = Field(None, description="Последняя проверка health")
    is_replicated: bool = Field(..., description="Флаг репликации")
    replica_count: int = Field(..., description="Количество реплик")
    created_at: datetime = Field(..., description="Дата создания")
    updated_at: datetime = Field(..., description="Дата обновления")

    # Computed properties
    capacity_gb: Optional[float] = Field(None, description="Емкость в GB")
    used_gb: float = Field(..., description="Использовано GB")
    usage_percent: Optional[float] = Field(None, description="Процент использования")
    is_available: bool = Field(..., description="Доступен ли storage element")
    is_writable: bool = Field(..., description="Доступен ли для записи")

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": 1,
                "name": "Storage Element 01",
                "description": "Primary production storage",
                "mode": "edit",
                "storage_type": "local",
                "base_path": "/data/storage01",
                "api_url": "http://storage01.artstore.local:8010",
                "status": "online",
                "capacity_bytes": 1099511627776,  # 1TB
                "used_bytes": 549755813888,       # 500GB
                "file_count": 1234,
                "retention_days": 365,
                "last_health_check": "2025-01-15T10:30:00Z",
                "is_replicated": True,
                "replica_count": 2,
                "created_at": "2025-01-01T00:00:00Z",
                "updated_at": "2025-01-15T10:30:00Z",
                "capacity_gb": 1024.0,
                "used_gb": 512.0,
                "usage_percent": 50.0,
                "is_available": True,
                "is_writable": True
            }
        }
    }


class StorageElementListResponse(BaseModel):
    """Response для списка Storage Elements."""

    total: int = Field(..., description="Общее количество storage elements")
    items: list[StorageElementResponse] = Field(..., description="Список storage elements")
    skip: int = Field(..., description="Offset пагинации")
    limit: int = Field(..., description="Лимит записей")

    model_config = {"json_schema_extra": {
        "example": {
            "total": 5,
            "items": [
                {
                    "id": 1,
                    "name": "Storage Element 01",
                    "description": "Primary production storage",
                    "mode": "edit",
                    "storage_type": "local",
                    "base_path": "/data/storage01",
                    "api_url": "http://storage01.artstore.local:8010",
                    "status": "online",
                    "capacity_bytes": 1099511627776,
                    "used_bytes": 549755813888,
                    "file_count": 1234,
                    "retention_days": 365,
                    "last_health_check": "2025-01-15T10:30:00Z",
                    "is_replicated": True,
                    "replica_count": 2,
                    "created_at": "2025-01-01T00:00:00Z",
                    "updated_at": "2025-01-15T10:30:00Z",
                    "capacity_gb": 1024.0,
                    "used_gb": 512.0,
                    "usage_percent": 50.0,
                    "is_available": True,
                    "is_writable": True
                }
            ],
            "skip": 0,
            "limit": 10
        }
    }}


class StorageElementCreate(BaseModel):
    """Request для создания Storage Element."""

    name: str = Field(..., min_length=3, max_length=100, description="Название")
    description: Optional[str] = Field(None, max_length=500, description="Описание")
    mode: StorageMode = Field(default=StorageMode.EDIT, description="Режим работы")
    storage_type: StorageType = Field(default=StorageType.LOCAL, description="Тип хранилища")
    base_path: str = Field(..., max_length=500, description="Базовый путь")
    api_url: str = Field(..., max_length=255, description="URL API")
    api_key: Optional[str] = Field(None, max_length=255, description="API ключ")
    capacity_bytes: Optional[int] = Field(None, ge=0, description="Общая емкость")
    retention_days: Optional[int] = Field(None, ge=1, description="Срок хранения")
    is_replicated: bool = Field(default=False, description="Флаг репликации")
    replica_count: int = Field(default=0, ge=0, description="Количество реплик")

    model_config = {"json_schema_extra": {
        "example": {
            "name": "Storage Element 02",
            "description": "Secondary archive storage",
            "mode": "edit",
            "storage_type": "local",
            "base_path": "/data/storage02",
            "api_url": "http://storage02.artstore.local:8011",
            "api_key": "secret_key_here",
            "capacity_bytes": 2199023255552,  # 2TB
            "retention_days": 730,
            "is_replicated": True,
            "replica_count": 1
        }
    }}


class StorageElementUpdate(BaseModel):
    """Request для обновления Storage Element."""

    name: Optional[str] = Field(None, min_length=3, max_length=100, description="Новое название")
    description: Optional[str] = Field(None, max_length=500, description="Новое описание")
    mode: Optional[StorageMode] = Field(None, description="Новый режим работы")
    api_url: Optional[str] = Field(None, max_length=255, description="Новый URL API")
    api_key: Optional[str] = Field(None, max_length=255, description="Новый API ключ")
    status: Optional[StorageStatus] = Field(None, description="Новый статус")
    capacity_bytes: Optional[int] = Field(None, ge=0, description="Новая емкость")
    retention_days: Optional[int] = Field(None, ge=1, description="Новый срок хранения")
    replica_count: Optional[int] = Field(None, ge=0, description="Новое количество реплик")

    model_config = {"json_schema_extra": {
        "example": {
            "mode": "ro",
            "status": "maintenance",
            "retention_days": 1095  # 3 years
        }
    }}


class StorageElementHealthResponse(BaseModel):
    """Response для health check storage element."""

    id: int = Field(..., description="Идентификатор storage element")
    name: str = Field(..., description="Название")
    status: StorageStatus = Field(..., description="Текущий статус")
    is_available: bool = Field(..., description="Доступен ли")
    last_health_check: Optional[datetime] = Field(None, description="Время последней проверки")
    response_time_ms: Optional[int] = Field(None, description="Время ответа в мс")
    error_message: Optional[str] = Field(None, description="Сообщение об ошибке")

    model_config = {"json_schema_extra": {
        "example": {
            "id": 1,
            "name": "Storage Element 01",
            "status": "online",
            "is_available": True,
            "last_health_check": "2025-01-15T10:30:00Z",
            "response_time_ms": 150,
            "error_message": None
        }
    }}
