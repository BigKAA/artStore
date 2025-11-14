"""
Template Schema v2.0 для attr.json файлов.

Изменения от v1.0:
- Добавлен schema_version field для эволюции формата
- Добавлен custom_attributes раздел для клиент-специфичных метаданных
- Backward compatibility через auto-migration v1→v2
- Поддержка schema validation с версионированием

Структура v2.0:
{
    "schema_version": "2.0",
    "file_id": "...",
    "original_filename": "...",
    ... (все поля из v1.0) ...
    "custom_attributes": {
        "department": "Engineering",
        "project_code": "PROJ-123",
        "classification": "internal",
        ... любые дополнительные поля ...
    }
}

Migration Strategy:
- v1.0 файлы: schema_version отсутствует → auto-migrate при чтении
- v2.0 файлы: schema_version="2.0" → native read
- Forward compatibility: v2.0 readers игнорируют unknown fields
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.core.exceptions import InvalidAttributeFileException

logger = logging.getLogger(__name__)

# Текущая версия schema
CURRENT_SCHEMA_VERSION = "2.0"

# Поддерживаемые версии (для backward compatibility)
SUPPORTED_SCHEMA_VERSIONS = ["1.0", "2.0"]


class FileAttributesV2(BaseModel):
    """
    Template Schema v2.0 для attr.json файлов.

    Расширение v1.0 с добавлением:
    - schema_version: Версия схемы для эволюции формата
    - custom_attributes: Гибкие клиент-специфичные метаданные

    Backward Compatibility:
    - Читает v1.0 файлы через auto-migration
    - v1.0 files: schema_version отсутствует → добавляется при миграции
    - v2.0 files: schema_version="2.0" → native parsing
    """

    # Schema versioning (новое в v2.0)
    schema_version: str = Field(
        default=CURRENT_SCHEMA_VERSION,
        description="Версия схемы attr.json файла"
    )

    # Core fields (из v1.0)
    file_id: UUID = Field(..., description="Уникальный идентификатор файла")
    original_filename: str = Field(..., description="Оригинальное имя файла")
    storage_filename: str = Field(..., description="Имя файла в хранилище")
    file_size: int = Field(..., gt=0, description="Размер файла в байтах")
    content_type: str = Field(..., description="MIME type файла")

    # Timestamps
    created_at: datetime = Field(..., description="Время создания файла")
    updated_at: datetime = Field(..., description="Время последнего обновления")

    # User information
    created_by_id: str = Field(..., description="User ID создателя")
    created_by_username: str = Field(..., description="Username создателя")
    created_by_fullname: Optional[str] = Field(None, description="ФИО создателя")

    # Content metadata
    description: Optional[str] = Field(None, description="Описание содержимого")
    version: Optional[str] = Field(None, description="Версия документа")

    # Storage information
    storage_path: str = Field(..., description="Относительный путь в хранилище")
    checksum: str = Field(..., description="SHA256 checksum файла")

    # Extended metadata (из v1.0, сохраняется для backward compatibility)
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Дополнительные метаданные (legacy, используйте custom_attributes в v2.0)"
    )

    # Custom attributes (новое в v2.0)
    custom_attributes: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Клиент-специфичные метаданные (гибкая структура)"
    )

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, v):
        """Валидация версии schema"""
        if v not in SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError(
                f"Unsupported schema version: {v}. "
                f"Supported versions: {', '.join(SUPPORTED_SCHEMA_VERSIONS)}"
            )
        return v

    @field_validator("file_size")
    @classmethod
    def validate_file_size(cls, v):
        """Валидация размера файла"""
        if v <= 0:
            raise ValueError("File size must be positive")
        return v

    @field_validator("checksum")
    @classmethod
    def validate_checksum(cls, v):
        """Валидация SHA256 checksum"""
        if len(v) != 64:
            raise ValueError("Checksum must be 64 characters (SHA256)")
        try:
            int(v, 16)
        except ValueError:
            raise ValueError("Checksum must be hexadecimal string")
        return v

    @field_validator("custom_attributes")
    @classmethod
    def validate_custom_attributes(cls, v):
        """
        Валидация custom_attributes.

        Ограничения:
        - Ключи должны быть строками
        - Значения должны быть JSON-serializable
        - Общий размер не должен превышать лимит attr.json (4KB)
        """
        if v is None:
            return {}

        if not isinstance(v, dict):
            raise ValueError("custom_attributes must be a dictionary")

        # Проверка что все ключи - строки
        for key in v.keys():
            if not isinstance(key, str):
                raise ValueError(f"custom_attributes keys must be strings, got {type(key)}")

        # Проверка JSON serializability
        try:
            json.dumps(v)
        except (TypeError, ValueError) as e:
            raise ValueError(f"custom_attributes must be JSON serializable: {e}")

        return v

    class Config:
        json_encoders = {
            UUID: str,
            datetime: lambda v: v.isoformat()
        }


def migrate_v1_to_v2(v1_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Миграция attr.json из v1.0 в v2.0.

    Процесс:
    1. Добавить schema_version="2.0"
    2. Инициализировать custom_attributes как пустой dict
    3. Сохранить все существующие поля

    Args:
        v1_data: Raw JSON data из v1.0 attr.json файла

    Returns:
        Dict[str, Any]: Migrated data в v2.0 формате

    Example:
        >>> v1_data = {"file_id": "...", "original_filename": "..."}
        >>> v2_data = migrate_v1_to_v2(v1_data)
        >>> assert v2_data["schema_version"] == "2.0"
        >>> assert "custom_attributes" in v2_data
    """
    logger.info(
        "Migrating attr.json from v1.0 to v2.0",
        extra={"file_id": v1_data.get("file_id")}
    )

    # Копирование всех полей из v1.0
    v2_data = v1_data.copy()

    # Добавление schema_version
    v2_data["schema_version"] = CURRENT_SCHEMA_VERSION

    # Инициализация custom_attributes если отсутствует
    if "custom_attributes" not in v2_data:
        v2_data["custom_attributes"] = {}

    logger.debug(
        "Migration v1→v2 complete",
        extra={
            "file_id": v2_data.get("file_id"),
            "schema_version": v2_data["schema_version"]
        }
    )

    return v2_data


def detect_schema_version(data: Dict[str, Any]) -> str:
    """
    Определение версии schema из raw JSON data.

    Logic:
    - Если schema_version присутствует → возвращаем его
    - Если отсутствует → предполагаем v1.0 (legacy format)

    Args:
        data: Raw JSON data из attr.json файла

    Returns:
        str: Версия schema ("1.0" или "2.0")

    Example:
        >>> data_v1 = {"file_id": "...", "original_filename": "..."}
        >>> detect_schema_version(data_v1)
        "1.0"
        >>> data_v2 = {"schema_version": "2.0", "file_id": "..."}
        >>> detect_schema_version(data_v2)
        "2.0"
    """
    if "schema_version" in data:
        version = data["schema_version"]
        logger.debug(f"Detected schema_version: {version}")
        return version
    else:
        logger.debug("No schema_version found, assuming v1.0 (legacy)")
        return "1.0"


def read_and_migrate_if_needed(data: Dict[str, Any]) -> FileAttributesV2:
    """
    Чтение attr.json с автоматической миграцией v1→v2 если необходимо.

    Process:
    1. Определить версию schema
    2. Если v1.0 → мигрировать в v2.0
    3. Если v2.0 → native parsing
    4. Валидировать через Pydantic

    Args:
        data: Raw JSON data из attr.json файла

    Returns:
        FileAttributesV2: Валидированные атрибуты в v2.0 формате

    Raises:
        ValueError: Если unsupported schema version
        InvalidAttributeFileException: Если validation failed

    Example:
        >>> data = json.loads(attr_file.read_text())
        >>> attributes = read_and_migrate_if_needed(data)
        >>> assert attributes.schema_version == "2.0"
    """
    try:
        # Определение версии schema
        version = detect_schema_version(data)

        if version == "1.0":
            # Auto-migration v1→v2
            logger.info("Auto-migrating attr.json from v1.0 to v2.0")
            data = migrate_v1_to_v2(data)
        elif version not in SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError(
                f"Unsupported schema version: {version}. "
                f"Supported: {', '.join(SUPPORTED_SCHEMA_VERSIONS)}"
            )

        # Валидация через Pydantic
        attributes = FileAttributesV2(**data)

        logger.debug(
            "Attr.json read and validated",
            extra={
                "file_id": str(attributes.file_id),
                "schema_version": attributes.schema_version,
                "has_custom_attributes": bool(attributes.custom_attributes)
            }
        )

        return attributes

    except Exception as e:
        logger.error(
            f"Failed to read/migrate attr.json: {e}",
            extra={"error": str(e)}
        )
        raise InvalidAttributeFileException(
            file_path="<in-memory>",
            reason=f"Failed to parse/migrate attr.json: {e}"
        )


def to_v1_compatible(v2_attributes: FileAttributesV2) -> Dict[str, Any]:
    """
    Конвертация v2.0 attributes обратно в v1.0 формат для backward compatibility.

    ВАЖНО: Это lossy conversion - custom_attributes будут потеряны!
    Используется только для совместимости со старыми системами.

    Args:
        v2_attributes: FileAttributesV2 объект

    Returns:
        Dict[str, Any]: Data в v1.0 формате (без schema_version и custom_attributes)

    Example:
        >>> v2_attrs = FileAttributesV2(...)
        >>> v1_data = to_v1_compatible(v2_attrs)
        >>> assert "schema_version" not in v1_data
        >>> assert "custom_attributes" not in v1_data
    """
    logger.warning(
        "Converting v2.0 to v1.0 format - custom_attributes will be lost!",
        extra={"file_id": str(v2_attributes.file_id)}
    )

    # Получение all data с сериализацией UUID в строку
    data = json.loads(v2_attributes.model_dump_json())

    # Удаление v2.0-specific полей
    data.pop("schema_version", None)
    data.pop("custom_attributes", None)

    return data
