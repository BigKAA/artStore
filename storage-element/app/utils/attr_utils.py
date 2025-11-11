"""
Утилиты для работы с файлами атрибутов (*.attr.json).

Файлы атрибутов:
- Единственный источник истины для метаданных файлов
- Максимальный размер 4KB для гарантии атомарности записи
- Атомарная запись через temp file + fsync + atomic rename
- JSON формат с валидацией схемы

Критично:
- ВСЕГДА записывать атомарно (temp → fsync → rename)
- ВСЕГДА валидировать размер перед записью
- НИКОГДА не редактировать напрямую (только через эти утилиты)
"""

import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.core.exceptions import InvalidAttributeFileException

logger = logging.getLogger(__name__)

# Максимальный размер attr.json файла (4KB)
MAX_ATTR_FILE_SIZE = 4 * 1024  # 4KB


class FileAttributes(BaseModel):
    """
    Схема файла атрибутов (*.attr.json).

    Содержит все метаданные файла.
    Источник истины для системы.

    Поля соответствуют FileMetadata модели из БД.
    """
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

    # Extended metadata (JSONB in DB)
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Дополнительные метаданные"
    )

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
        # Проверка что это hex string
        try:
            int(v, 16)
        except ValueError:
            raise ValueError("Checksum must be hexadecimal string")
        return v

    class Config:
        json_encoders = {
            UUID: str,
            datetime: lambda v: v.isoformat()
        }


async def write_attr_file(
    file_path: Path,
    attributes: FileAttributes
) -> None:
    """
    Атомарная запись файла атрибутов.

    Процесс:
    1. Сериализация в JSON
    2. Проверка размера (<= 4KB)
    3. Запись во временный файл
    4. fsync для гарантии записи на диск
    5. Atomic rename временного файла в целевой

    Args:
        file_path: Путь к файлу атрибутов (*.attr.json)
        attributes: Объект атрибутов файла

    Raises:
        InvalidAttributeFileException: Если размер превышает 4KB
        OSError: Если ошибка записи на диск

    Примеры:
        >>> attrs = FileAttributes(
        ...     file_id=uuid4(),
        ...     original_filename="report.pdf",
        ...     ...
        ... )
        >>> await write_attr_file(Path("file.pdf.attr.json"), attrs)
    """
    # Сериализация в JSON
    json_data = attributes.model_dump_json(indent=2)
    json_bytes = json_data.encode('utf-8')

    # Проверка размера
    if len(json_bytes) > MAX_ATTR_FILE_SIZE:
        raise InvalidAttributeFileException(
            file_path=str(file_path),
            reason=f"Attribute file size ({len(json_bytes)} bytes) exceeds maximum ({MAX_ATTR_FILE_SIZE} bytes)"
        )

    # Создание директории если не существует
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # Запись через временный файл для атомарности
    # Временный файл в той же директории что и целевой (для atomic rename)
    temp_fd, temp_path = tempfile.mkstemp(
        dir=file_path.parent,
        prefix=".tmp_attr_",
        suffix=".json"
    )

    try:
        # Запись данных во временный файл
        os.write(temp_fd, json_bytes)

        # fsync для гарантии записи на диск
        os.fsync(temp_fd)

        # Закрытие файла
        os.close(temp_fd)

        # Atomic rename (POSIX гарантирует атомарность)
        os.replace(temp_path, file_path)

        logger.debug(
            "Attribute file written atomically",
            extra={
                "file_path": str(file_path),
                "size_bytes": len(json_bytes),
                "file_id": str(attributes.file_id)
            }
        )

    except Exception as e:
        # Очистка временного файла при ошибке
        try:
            os.close(temp_fd)
        except OSError:
            pass
        try:
            os.unlink(temp_path)
        except OSError:
            pass

        logger.error(
            f"Failed to write attribute file: {e}",
            extra={
                "file_path": str(file_path),
                "error": str(e)
            }
        )
        raise


async def read_attr_file(file_path: Path) -> FileAttributes:
    """
    Чтение и валидация файла атрибутов.

    Args:
        file_path: Путь к файлу атрибутов (*.attr.json)

    Returns:
        FileAttributes: Валидированные атрибуты файла

    Raises:
        FileNotFoundError: Если файл не найден
        InvalidAttributeFileException: Если JSON невалиден или схема неверна

    Примеры:
        >>> attrs = await read_attr_file(Path("file.pdf.attr.json"))
        >>> print(attrs.file_id, attrs.original_filename)
    """
    # Проверка существования файла
    if not file_path.exists():
        raise FileNotFoundError(f"Attribute file not found: {file_path}")

    # Проверка размера перед чтением
    file_size = file_path.stat().st_size
    if file_size > MAX_ATTR_FILE_SIZE:
        raise InvalidAttributeFileException(
            file_path=str(file_path),
            reason=f"Attribute file size ({file_size} bytes) exceeds maximum ({MAX_ATTR_FILE_SIZE} bytes)"
        )

    try:
        # Чтение файла
        json_data = file_path.read_text(encoding='utf-8')

        # Парсинг JSON
        data = json.loads(json_data)

        # Валидация через Pydantic
        attributes = FileAttributes(**data)

        logger.debug(
            "Attribute file read successfully",
            extra={
                "file_path": str(file_path),
                "file_id": str(attributes.file_id)
            }
        )

        return attributes

    except json.JSONDecodeError as e:
        raise InvalidAttributeFileException(
            file_path=str(file_path),
            reason=f"Invalid JSON format: {e}"
        )

    except Exception as e:
        raise InvalidAttributeFileException(
            file_path=str(file_path),
            reason=f"Failed to parse attributes: {e}"
        )


async def delete_attr_file(file_path: Path) -> None:
    """
    Удаление файла атрибутов.

    Args:
        file_path: Путь к файлу атрибутов (*.attr.json)

    Raises:
        FileNotFoundError: Если файл не найден
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Attribute file not found: {file_path}")

    file_path.unlink()

    logger.debug(
        "Attribute file deleted",
        extra={"file_path": str(file_path)}
    )


def get_attr_file_path(data_file_path: Path) -> Path:
    """
    Получение пути к файлу атрибутов для данного файла.

    Args:
        data_file_path: Путь к файлу данных

    Returns:
        Path: Путь к файлу атрибутов (data_file_path + ".attr.json")

    Примеры:
        >>> get_attr_file_path(Path("/storage/file.pdf"))
        Path("/storage/file.pdf.attr.json")
    """
    return Path(str(data_file_path) + ".attr.json")


async def verify_attr_file_consistency(
    data_file_path: Path,
    attr_file_path: Optional[Path] = None
) -> bool:
    """
    Проверка консистентности между файлом данных и файлом атрибутов.

    Проверки:
    - Файл атрибутов существует
    - Размер файла в атрибутах совпадает с реальным
    - Checksum совпадает (опционально, требует вычисления)

    Args:
        data_file_path: Путь к файлу данных
        attr_file_path: Путь к файлу атрибутов (опционально, вычисляется автоматически)

    Returns:
        bool: True если консистентны, False иначе
    """
    if attr_file_path is None:
        attr_file_path = get_attr_file_path(data_file_path)

    try:
        # Проверка существования обоих файлов
        if not data_file_path.exists():
            logger.warning(f"Data file not found: {data_file_path}")
            return False

        if not attr_file_path.exists():
            logger.warning(f"Attribute file not found: {attr_file_path}")
            return False

        # Чтение атрибутов
        attributes = await read_attr_file(attr_file_path)

        # Проверка размера файла
        actual_size = data_file_path.stat().st_size
        if actual_size != attributes.file_size:
            logger.warning(
                f"File size mismatch: expected {attributes.file_size}, actual {actual_size}",
                extra={
                    "data_file": str(data_file_path),
                    "expected_size": attributes.file_size,
                    "actual_size": actual_size
                }
            )
            return False

        # TODO: Проверка checksum (требует вычисления, медленно для больших файлов)

        return True

    except Exception as e:
        logger.error(
            f"Failed to verify attribute file consistency: {e}",
            extra={
                "data_file": str(data_file_path),
                "attr_file": str(attr_file_path),
                "error": str(e)
            }
        )
        return False
