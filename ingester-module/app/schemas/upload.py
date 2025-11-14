"""
Ingester Module - Upload Schemas.

Pydantic models для upload операций.
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class StorageMode(str, Enum):
    """Режимы storage element."""
    EDIT = "edit"
    RW = "rw"
    RO = "ro"
    AR = "ar"


class CompressionAlgorithm(str, Enum):
    """Алгоритмы сжатия."""
    NONE = "none"
    GZIP = "gzip"
    BROTLI = "brotli"


class UploadRequest(BaseModel):
    """
    Запрос на загрузку файла.

    Attributes:
        description: Описание файла (опционально)
        storage_mode: Целевой режим storage element (edit или rw)
        compress: Использовать сжатие при загрузке
        compression_algorithm: Алгоритм сжатия (если compress=True)
    """
    description: Optional[str] = Field(None, max_length=500)
    storage_mode: StorageMode = Field(StorageMode.EDIT, description="Target storage mode")
    compress: bool = Field(False, description="Enable compression")
    compression_algorithm: CompressionAlgorithm = Field(
        CompressionAlgorithm.GZIP,
        description="Compression algorithm (if compress=True)"
    )

    @field_validator('storage_mode')
    @classmethod
    def validate_storage_mode(cls, v: StorageMode) -> StorageMode:
        """Валидация storage mode - только edit или rw."""
        if v not in (StorageMode.EDIT, StorageMode.RW):
            raise ValueError(f"Upload only allowed to EDIT or RW modes, got: {v}")
        return v


class UploadResponse(BaseModel):
    """
    Ответ после успешной загрузки файла.

    Attributes:
        file_id: UUID загруженного файла
        original_filename: Оригинальное имя файла
        storage_filename: Имя файла в storage
        file_size: Размер файла в байтах
        compressed: Был ли файл сжат
        compression_ratio: Коэффициент сжатия (если сжат)
        checksum: SHA256 checksum файла
        uploaded_at: Timestamp загрузки
        storage_element_url: URL storage element где хранится файл
    """
    file_id: UUID
    original_filename: str
    storage_filename: str
    file_size: int = Field(..., gt=0, description="File size in bytes (must be positive)")
    compressed: bool = False
    compression_ratio: Optional[float] = None
    checksum: str
    uploaded_at: datetime
    storage_element_url: str

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class UploadProgress(BaseModel):
    """
    Прогресс загрузки файла (для streaming uploads).

    Attributes:
        upload_id: ID операции загрузки
        bytes_uploaded: Количество загруженных байт
        total_bytes: Общий размер файла
        progress_percent: Процент завершения
        status: Статус загрузки
    """
    upload_id: UUID
    bytes_uploaded: int
    total_bytes: int
    progress_percent: float
    status: str = Field(..., pattern="^(uploading|completed|failed)$")


class UploadError(BaseModel):
    """
    Ошибка загрузки файла.

    Attributes:
        error_code: Код ошибки
        error_message: Сообщение об ошибке
        details: Дополнительная информация
    """
    error_code: str
    error_message: str
    details: Optional[dict] = None
