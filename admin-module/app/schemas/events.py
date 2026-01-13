"""
Event schemas для Redis Pub/Sub синхронизации.

PHASE 1: Sprint 16 - Query Module Sync Repair.

Схемы для events, публикуемых Admin Module после успешных операций с файлами.
Query Module подписывается на эти events и обновляет свой cache.
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, Field


class FileMetadataEvent(BaseModel):
    """
    Метаданные файла для event payload.

    Содержит все необходимые данные для синхронизации cache Query Module.
    """

    file_id: UUID = Field(..., description="Уникальный ID файла")
    original_filename: str = Field(..., description="Оригинальное имя файла")
    storage_filename: str = Field(..., description="Имя файла в Storage Element")
    file_size: int = Field(..., gt=0, description="Размер файла в байтах")
    checksum_sha256: str = Field(..., description="SHA-256 checksum файла")
    content_type: str = Field(..., description="MIME тип файла")
    description: Optional[str] = Field(None, description="Описание файла")
    storage_element_id: str = Field(..., description="ID Storage Element где хранится файл")
    storage_path: str = Field(..., description="Путь к файлу в Storage Element")
    compressed: bool = Field(default=False, description="Файл сжат")
    compression_algorithm: Optional[str] = Field(None, description="Алгоритм сжатия (brotli/gzip)")
    original_size: Optional[int] = Field(None, description="Оригинальный размер до сжатия")
    uploaded_by: str = Field(..., description="Username пользователя загрузившего файл")
    upload_source_ip: Optional[str] = Field(None, description="IP адрес источника загрузки")
    created_at: datetime = Field(..., description="Дата создания файла")
    updated_at: Optional[datetime] = Field(None, description="Дата обновления файла")
    retention_policy: str = Field(..., description="Политика хранения (standard/archive)")
    ttl_expires_at: Optional[datetime] = Field(None, description="Дата истечения TTL")
    ttl_days: Optional[int] = Field(None, description="TTL в днях")
    user_metadata: dict = Field(default_factory=dict, description="Пользовательские метаданные")
    tags: Optional[List[str]] = Field(None, description="Теги файла")


class FileCreatedEvent(BaseModel):
    """
    Event публикуемый после успешной регистрации файла.

    Триггер: FileService.register_file() успешно завершился.
    Подписчик: Query Module EventSubscriber.
    """

    event_type: str = Field(default="file:created", description="Тип события")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Timestamp события")
    file_id: UUID = Field(..., description="ID созданного файла")
    storage_element_id: str = Field(..., description="ID Storage Element")
    metadata: FileMetadataEvent = Field(..., description="Полные метаданные файла")


class FileUpdatedEvent(BaseModel):
    """
    Event публикуемый после обновления файла.

    Триггер: FileService.update_file() успешно завершился.
    Подписчик: Query Module EventSubscriber.
    """

    event_type: str = Field(default="file:updated", description="Тип события")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Timestamp события")
    file_id: UUID = Field(..., description="ID обновленного файла")
    storage_element_id: str = Field(..., description="ID Storage Element")
    metadata: FileMetadataEvent = Field(..., description="Обновленные метаданные файла")


class FileDeletedEvent(BaseModel):
    """
    Event публикуемый после удаления файла (soft delete).

    Триггер: FileService.delete_file() успешно завершился.
    Подписчик: Query Module EventSubscriber.
    """

    event_type: str = Field(default="file:deleted", description="Тип события")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Timestamp события")
    file_id: UUID = Field(..., description="ID удаленного файла")
    storage_element_id: str = Field(..., description="ID Storage Element")
    deleted_at: datetime = Field(default_factory=datetime.utcnow, description="Timestamp удаления")
