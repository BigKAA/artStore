"""
Info API Endpoint - информация о Storage Element для auto-discovery.

Предоставляет полную информацию о storage element для автоматического
обнаружения и регистрации в Admin Module.

Этот endpoint НЕ требует аутентификации, так как используется
для первичного обнаружения storage element.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import settings, StorageMode, StorageType
from app.models.file_metadata import FileMetadata

logger = logging.getLogger(__name__)

router = APIRouter()


class StorageElementInfoResponse(BaseModel):
    """
    Информация о Storage Element для auto-discovery.

    Содержит все необходимые данные для автоматической регистрации
    storage element в Admin Module.
    """
    # Идентификация
    name: str = Field(..., description="Техническое имя storage element")
    display_name: str = Field(..., description="Читаемое имя для отображения")
    version: str = Field(..., description="Версия приложения")

    # Режим работы (определяется только конфигурацией)
    mode: str = Field(..., description="Режим работы: edit, rw, ro, ar")

    # Тип хранилища
    storage_type: str = Field(..., description="Тип хранилища: local, s3")
    base_path: str = Field(..., description="Базовый путь хранилища")

    # Емкость и использование
    capacity_bytes: int = Field(..., description="Максимальная емкость в байтах")
    used_bytes: int = Field(0, description="Использовано байтов")
    file_count: int = Field(0, description="Количество файлов")

    # Статус
    status: str = Field("operational", description="Статус: operational, degraded, maintenance")

    # Временные метки
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Время генерации ответа")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "storage-element",
                "display_name": "Storage Element 01",
                "version": "1.0.0",
                "mode": "rw",
                "storage_type": "local",
                "base_path": "/data/storage",
                "capacity_bytes": 1099511627776,
                "used_bytes": 549755813888,
                "file_count": 1234,
                "status": "operational",
                "timestamp": "2025-01-15T10:30:00Z"
            }
        }


def _get_base_path() -> str:
    """
    Получить базовый путь хранилища в зависимости от типа.

    Returns:
        str: Путь к локальному хранилищу или bucket name для S3
    """
    if settings.storage.type == StorageType.LOCAL:
        return str(settings.storage.local.base_path.absolute())
    else:
        # Для S3 возвращаем bucket/folder
        return f"{settings.storage.s3.bucket_name}/{settings.storage.s3.app_folder}"


async def _get_storage_stats(db: AsyncSession) -> tuple[int, int]:
    """
    Получить статистику использования хранилища из БД.

    Args:
        db: Сессия базы данных

    Returns:
        tuple[int, int]: (общий размер файлов, количество файлов)
    """
    try:
        # Получаем сумму размеров и количество файлов одним запросом
        result = await db.execute(
            select(
                func.coalesce(func.sum(FileMetadata.file_size), 0),
                func.count(FileMetadata.file_id)
            )
        )
        row = result.one()
        return int(row[0]), int(row[1])
    except Exception as e:
        logger.warning(f"Не удалось получить статистику из БД: {e}")
        return 0, 0


def _determine_status() -> str:
    """
    Определить текущий статус storage element.

    Returns:
        str: operational, degraded или maintenance
    """
    # В будущем здесь можно добавить более сложную логику
    # проверки состояния (диск, подключения и т.д.)

    # Если режим archive - считаем maintenance
    if settings.app.mode == StorageMode.AR:
        return "maintenance"

    return "operational"


@router.get(
    "",
    response_model=StorageElementInfoResponse,
    summary="Получить информацию о Storage Element",
    description="""
    Возвращает полную информацию о storage element для auto-discovery.

    Этот endpoint используется Admin Module для автоматического
    обнаружения и регистрации storage elements в системе.

    **Важно**: Endpoint НЕ требует аутентификации, так как используется
    для первичного обнаружения до регистрации в системе.

    **Поля ответа**:
    - `name`, `display_name` - идентификация storage element
    - `mode` - текущий режим работы (определяется конфигурацией)
    - `storage_type`, `base_path` - тип и расположение хранилища
    - `capacity_bytes`, `used_bytes`, `file_count` - статистика использования
    - `status` - текущий статус работоспособности
    """
)
async def get_storage_element_info(
    db: AsyncSession = Depends(get_db)
) -> StorageElementInfoResponse:
    """
    Получить полную информацию о storage element.

    Используется для auto-discovery при добавлении storage element
    в Admin Module. Возвращает все необходимые данные для регистрации.
    """
    # Получаем статистику из БД
    used_bytes, file_count = await _get_storage_stats(db)

    # Формируем ответ
    return StorageElementInfoResponse(
        name=settings.app.name,
        display_name=settings.app.display_name,
        version=settings.app.version,
        mode=settings.app.mode.value,
        storage_type=settings.storage.type.value,
        base_path=_get_base_path(),
        capacity_bytes=settings.storage.max_size_bytes,
        used_bytes=used_bytes,
        file_count=file_count,
        status=_determine_status()
    )
