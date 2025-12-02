"""
Ingester Module - Upload Schemas.

Pydantic models для upload операций.

Sprint 15: Добавлена поддержка Retention Policy:
- RetentionPolicy enum для определения типа хранения
- ttl_days для временных файлов (default: 30 дней)
- Маппинг retention_policy → storage_mode:
  - TEMPORARY → edit SE
  - PERMANENT → rw SE
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class StorageMode(str, Enum):
    """Режимы storage element."""
    EDIT = "edit"
    RW = "rw"
    RO = "ro"
    AR = "ar"


class RetentionPolicy(str, Enum):
    """
    Политика хранения файлов (Sprint 15).

    TEMPORARY: Временные файлы в Edit SE с автоматическим TTL.
               Подходит для документов "в работе" (drafts, work-in-progress).
               По умолчанию TTL = 30 дней, затем GC удаляет файл.
               Можно финализировать через /finalize endpoint для перехода в PERMANENT.

    PERMANENT: Постоянные файлы в RW SE для долгосрочного хранения.
               Подходит для финализированных документов.
               Нет автоматического удаления.
    """
    TEMPORARY = "temporary"
    PERMANENT = "permanent"


class CompressionAlgorithm(str, Enum):
    """Алгоритмы сжатия."""
    NONE = "none"
    GZIP = "gzip"
    BROTLI = "brotli"


# Константы для TTL
DEFAULT_TTL_DAYS = 30
MIN_TTL_DAYS = 1
MAX_TTL_DAYS = 365


class UploadRequest(BaseModel):
    """
    Запрос на загрузку файла.

    Sprint 15: Добавлена поддержка retention_policy и ttl_days.
    Поле storage_mode автоматически определяется из retention_policy:
    - TEMPORARY → edit SE
    - PERMANENT → rw SE

    Attributes:
        description: Описание файла (опционально)
        retention_policy: Политика хранения (temporary/permanent)
        ttl_days: TTL в днях для temporary файлов (1-365, default: 30)
        compress: Использовать сжатие при загрузке
        compression_algorithm: Алгоритм сжатия (если compress=True)
        metadata: Пользовательские метаданные (JSON)
    """
    description: Optional[str] = Field(None, max_length=1000)

    # Sprint 15: Retention Policy
    retention_policy: RetentionPolicy = Field(
        RetentionPolicy.TEMPORARY,
        description="Политика хранения: temporary (Edit SE) или permanent (RW SE)"
    )

    ttl_days: Optional[int] = Field(
        DEFAULT_TTL_DAYS,
        ge=MIN_TTL_DAYS,
        le=MAX_TTL_DAYS,
        description=f"TTL в днях для temporary файлов ({MIN_TTL_DAYS}-{MAX_TTL_DAYS})"
    )

    # Legacy поле для обратной совместимости (deprecated)
    storage_mode: Optional[StorageMode] = Field(
        None,
        description="[DEPRECATED] Используйте retention_policy. Автоопределяется из retention_policy."
    )

    compress: bool = Field(False, description="Enable compression")
    compression_algorithm: CompressionAlgorithm = Field(
        CompressionAlgorithm.GZIP,
        description="Compression algorithm (if compress=True)"
    )

    # Sprint 15: Пользовательские метаданные
    metadata: Optional[dict] = Field(
        None,
        description="Пользовательские метаданные (JSON)"
    )

    @model_validator(mode='after')
    def set_storage_mode_from_retention(self) -> 'UploadRequest':
        """
        Автоматическое определение storage_mode из retention_policy.

        Маппинг:
        - TEMPORARY → edit SE (для работы над документами)
        - PERMANENT → rw SE (для долгосрочного хранения)
        """
        if self.retention_policy == RetentionPolicy.TEMPORARY:
            self.storage_mode = StorageMode.EDIT
        else:  # PERMANENT
            self.storage_mode = StorageMode.RW
            # TTL не нужен для permanent файлов
            self.ttl_days = None

        return self

    @field_validator('ttl_days', mode='before')
    @classmethod
    def validate_ttl_days(cls, v, info):
        """Валидация TTL - устанавливаем default если не указан."""
        if v is None:
            return DEFAULT_TTL_DAYS
        return v

    @property
    def effective_storage_mode(self) -> StorageMode:
        """
        Получение эффективного storage_mode.

        Returns:
            StorageMode: edit для TEMPORARY, rw для PERMANENT
        """
        return StorageMode.EDIT if self.retention_policy == RetentionPolicy.TEMPORARY else StorageMode.RW


class UploadResponse(BaseModel):
    """
    Ответ после успешной загрузки файла.

    Sprint 15: Добавлена информация о retention policy.

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
        retention_policy: Политика хранения (Sprint 15)
        ttl_expires_at: Дата истечения TTL для temporary файлов (Sprint 15)
        storage_element_id: ID Storage Element (Sprint 15)
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

    # Sprint 15: Retention Policy информация
    retention_policy: RetentionPolicy = Field(
        RetentionPolicy.TEMPORARY,
        description="Политика хранения файла"
    )
    ttl_expires_at: Optional[datetime] = Field(
        None,
        description="Дата истечения TTL (только для temporary файлов)"
    )
    storage_element_id: Optional[str] = Field(
        None,
        description="ID Storage Element где хранится файл"
    )

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


# =============================================================================
# Sprint 15: Finalize API Schemas
# =============================================================================

class FinalizeTransactionStatus(str, Enum):
    """
    Статусы транзакции финализации (Two-Phase Commit).

    Workflow:
    COPYING → COPIED → VERIFYING → COMPLETED
                                 ↘ FAILED → ROLLED_BACK
    """
    COPYING = "copying"       # Фаза 1: копирование на target SE
    COPIED = "copied"         # Фаза 1 завершена: файл на target SE
    VERIFYING = "verifying"   # Фаза 2: проверка checksums
    COMPLETED = "completed"   # Успешная финализация
    FAILED = "failed"         # Ошибка (checksum mismatch, network, etc.)
    ROLLED_BACK = "rolled_back"  # Откат (файл удалён с target SE)


class FinalizeRequest(BaseModel):
    """
    Запрос на финализацию temporary файла.

    Sprint 15: Two-Phase Commit процесс для переноса файла из Edit SE в RW SE.

    Attributes:
        target_storage_element_id: ID целевого RW Storage Element (опционально, auto-select)
        description: Обновлённое описание файла (опционально)
        metadata: Обновлённые метаданные (опционально)
    """
    target_storage_element_id: Optional[str] = Field(
        None,
        description="ID целевого RW Storage Element. Если не указан - автовыбор."
    )
    description: Optional[str] = Field(
        None,
        max_length=1000,
        description="Обновлённое описание файла"
    )
    metadata: Optional[dict] = Field(
        None,
        description="Обновлённые метаданные"
    )


class FinalizeResponse(BaseModel):
    """
    Ответ после финализации файла.

    Sprint 15: Информация о результате Two-Phase Commit.

    Attributes:
        transaction_id: UUID транзакции финализации
        file_id: UUID файла
        status: Статус транзакции
        source_storage_element_id: ID исходного Edit SE
        target_storage_element_id: ID целевого RW SE
        checksum_verified: Результат проверки checksum
        finalized_at: Дата финализации
        new_storage_path: Путь к файлу в новом SE
        cleanup_scheduled_at: Дата когда источник будет удалён (+24h)
    """
    transaction_id: UUID
    file_id: UUID
    status: FinalizeTransactionStatus
    source_storage_element_id: str
    target_storage_element_id: str
    checksum_verified: bool = False
    finalized_at: Optional[datetime] = None
    new_storage_path: Optional[str] = None
    cleanup_scheduled_at: Optional[datetime] = None
    error_message: Optional[str] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class FinalizeStatus(BaseModel):
    """
    Статус транзакции финализации.

    Sprint 15: Для polling endpoint GET /finalize/{transaction_id}/status.

    Attributes:
        transaction_id: UUID транзакции
        file_id: UUID файла
        status: Текущий статус
        progress_percent: Процент завершения (0-100)
        created_at: Дата начала транзакции
        completed_at: Дата завершения (если завершена)
        error_message: Сообщение об ошибке (если failed)
    """
    transaction_id: UUID
    file_id: UUID
    status: FinalizeTransactionStatus
    progress_percent: float = Field(ge=0, le=100)
    created_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
