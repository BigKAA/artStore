"""
Pydantic schemas для JWT Key Management и Rotation.
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class JWTKeyInfo(BaseModel):
    """Информация о JWT ключе."""

    version: str = Field(..., description="UUID версии ключа")
    algorithm: str = Field(..., description="Алгоритм шифрования (RS256)")
    created_at: datetime = Field(..., description="Время создания ключа")
    expires_at: datetime = Field(..., description="Время истечения ключа")
    is_active: bool = Field(..., description="Активен ли ключ")
    rotation_count: int = Field(..., description="Количество ротаций (для статистики)")

    class Config:
        from_attributes = True


class JWTKeyRotationStatus(BaseModel):
    """Статус JWT key rotation."""

    rotation_enabled: bool = Field(..., description="Включена ли автоматическая ротация")
    rotation_interval_hours: int = Field(..., description="Интервал ротации в часах")
    active_keys_count: int = Field(..., description="Количество активных ключей")
    latest_key: Optional[JWTKeyInfo] = Field(None, description="Последний активный ключ")
    next_rotation_at: Optional[datetime] = Field(None, description="Планируемое время следующей ротации")
    last_rotation_at: Optional[datetime] = Field(None, description="Время последней ротации")
    rotation_in_progress: bool = Field(..., description="Идет ли ротация в данный момент")


class ActiveKeysResponse(BaseModel):
    """Список активных JWT ключей."""

    total: int = Field(..., description="Общее количество активных ключей")
    keys: List[JWTKeyInfo] = Field(..., description="Список активных ключей")


class RotationTriggerRequest(BaseModel):
    """Запрос на ручную ротацию ключей."""

    force: bool = Field(
        default=False,
        description="Принудительная ротация даже если недавно была выполнена"
    )


class RotationTriggerResponse(BaseModel):
    """Ответ на запрос ручной ротации."""

    success: bool = Field(..., description="Успешность ротации")
    message: str = Field(..., description="Сообщение о результате")
    new_key_version: Optional[str] = Field(None, description="UUID новой версии ключа")
    deactivated_keys: int = Field(default=0, description="Количество деактивированных ключей")


class RotationHistoryEntry(BaseModel):
    """Запись истории ротации."""

    key_version: str = Field(..., description="UUID версии ключа")
    created_at: datetime = Field(..., description="Время создания ключа")
    expires_at: datetime = Field(..., description="Время истечения ключа")
    is_active: bool = Field(..., description="Активен ли ключ сейчас")
    rotation_count: int = Field(..., description="Порядковый номер ротации")


class RotationHistoryResponse(BaseModel):
    """История ротаций ключей."""

    total: int = Field(..., description="Общее количество записей")
    entries: List[RotationHistoryEntry] = Field(..., description="Записи истории")
    oldest_active_key: Optional[datetime] = Field(
        None,
        description="Дата создания самого старого активного ключа"
    )
    newest_key: Optional[datetime] = Field(
        None,
        description="Дата создания самого нового ключа"
    )
