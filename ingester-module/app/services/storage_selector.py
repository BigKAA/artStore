"""
StorageSelector - Сервис выбора Storage Element для загрузки файлов.

Sprint 14: Redis Storage Registry & Adaptive Capacity.

Алгоритм Sequential Fill:
1. Получаем список доступных SE из Redis sorted set (отсортированы по priority)
2. Для каждого SE (в порядке priority) проверяем:
   - capacity_status != FULL
   - can_accept_file(file_size)
3. Возвращаем первый подходящий SE

Fallback Pattern:
- Redis → Admin Module HTTP API → Local config

ВАЖНО: Использует redis.asyncio (async), НЕ синхронный redis-py!
"""

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import record_storage_selection

logger = get_logger(__name__)


class RetentionPolicy(str, Enum):
    """
    Политика хранения файлов.

    Определяет в какой тип SE будет загружен файл:
    - TEMPORARY: файлы с ограниченным сроком хранения → Edit Storage (mode=edit)
    - PERMANENT: файлы для долгосрочного хранения → RW Storage (mode=rw)
    """
    TEMPORARY = "temporary"
    PERMANENT = "permanent"


class CapacityStatus(str, Enum):
    """
    Статус емкости Storage Element.

    Соответствует статусам из storage-element/app/core/capacity_calculator.py
    """
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"
    FULL = "full"


@dataclass
class StorageElementInfo:
    """
    Информация о Storage Element для выбора.

    Получается из Redis Hash storage:elements:{se_id}
    """
    element_id: str
    mode: str  # edit, rw, ro, ar
    endpoint: str
    priority: int
    capacity_total: int  # bytes
    capacity_used: int  # bytes
    capacity_free: int  # bytes
    capacity_percent: float
    capacity_status: CapacityStatus
    health_status: str
    last_updated: datetime

    @property
    def is_writable(self) -> bool:
        """SE доступен для записи."""
        return self.mode in ("edit", "rw") and self.health_status == "healthy"

    @property
    def can_accept_files(self) -> bool:
        """SE может принимать новые файлы."""
        return self.is_writable and self.capacity_status != CapacityStatus.FULL

    def can_accept_file(self, file_size: int) -> bool:
        """
        Проверка возможности принять файл заданного размера.

        Args:
            file_size: Размер файла в байтах

        Returns:
            bool: True если SE может принять файл
        """
        if not self.can_accept_files:
            return False

        # Проверяем что хватает места
        return self.capacity_free >= file_size


class StorageSelector:
    """
    Сервис выбора Storage Element для загрузки файлов.

    Реализует Sequential Fill алгоритм с fallback на Admin Module API.

    Usage:
        selector = StorageSelector()
        await selector.initialize()

        se = await selector.select_storage_element(
            file_size=1024 * 1024,  # 1MB
            retention_policy=RetentionPolicy.TEMPORARY
        )

        if se:
            # Upload to se.endpoint
            pass
    """

    def __init__(self):
        """Инициализация StorageSelector."""
        self._redis_client = None
        self._admin_client = None  # Будет инициализирован в Task 6
        self._local_config: Optional[dict] = None  # Fallback config
        self._initialized = False

        # Кеш SE для уменьшения нагрузки на Redis
        self._cache: dict[str, StorageElementInfo] = {}
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl_seconds = 5  # Кеш на 5 секунд

    async def initialize(self, redis_client=None, admin_client=None) -> None:
        """
        Инициализация сервиса.

        Args:
            redis_client: Async Redis клиент (опционально, если None - будет создан)
            admin_client: Admin Module HTTP клиент (опционально, для fallback)
        """
        self._redis_client = redis_client
        self._admin_client = admin_client
        self._initialized = True

        logger.info("StorageSelector initialized")

    async def close(self) -> None:
        """Закрытие ресурсов."""
        self._initialized = False
        self._cache.clear()
        logger.info("StorageSelector closed")

    async def select_storage_element(
        self,
        file_size: int,
        retention_policy: RetentionPolicy = RetentionPolicy.TEMPORARY
    ) -> Optional[StorageElementInfo]:
        """
        Выбор Storage Element для загрузки файла.

        Реализует Sequential Fill алгоритм:
        1. Получаем SE из Redis sorted set по priority
        2. Фильтруем по mode (edit для TEMPORARY, rw для PERMANENT)
        3. Выбираем первый SE с достаточной емкостью

        Fallback:
        - Redis недоступен → Admin Module API
        - Admin Module недоступен → Local config

        Args:
            file_size: Размер файла в байтах
            retention_policy: Политика хранения (определяет тип SE)

        Returns:
            StorageElementInfo или None если нет подходящего SE
        """
        if not self._initialized:
            raise RuntimeError("StorageSelector not initialized. Call initialize() first.")

        # Определяем требуемый mode на основе retention_policy
        required_mode = "edit" if retention_policy == RetentionPolicy.TEMPORARY else "rw"
        start_time = time.perf_counter()
        source = "unknown"
        status = "failed"

        try:
            # Попытка 1: Redis Registry
            se = await self._select_from_redis(file_size, required_mode)
            if se:
                source = "redis"
                status = "success"
                logger.info(
                    f"Selected SE from Redis",
                    extra={
                        "se_id": se.element_id,
                        "mode": se.mode,
                        "file_size": file_size,
                        "retention_policy": retention_policy.value,
                        "source": "redis"
                    }
                )
                return se

            # Попытка 2: Admin Module Fallback API
            se = await self._select_from_admin_module(file_size, required_mode)
            if se:
                source = "admin_module"
                status = "fallback"
                logger.info(
                    f"Selected SE from Admin Module fallback",
                    extra={
                        "se_id": se.element_id,
                        "mode": se.mode,
                        "file_size": file_size,
                        "retention_policy": retention_policy.value,
                        "source": "admin_module"
                    }
                )
                return se

            # Попытка 3: Local config fallback
            se = await self._select_from_local_config(file_size, required_mode)
            if se:
                source = "local_config"
                status = "fallback"
                logger.warning(
                    f"Selected SE from local config fallback",
                    extra={
                        "se_id": se.element_id,
                        "mode": se.mode,
                        "file_size": file_size,
                        "retention_policy": retention_policy.value,
                        "source": "local_config"
                    }
                )
                return se

            # Нет подходящего SE
            source = "none"
            status = "failed"
            logger.error(
                f"No suitable Storage Element found",
                extra={
                    "file_size": file_size,
                    "retention_policy": retention_policy.value,
                    "required_mode": required_mode
                }
            )
            return None

        finally:
            # Записываем метрики
            duration = time.perf_counter() - start_time
            record_storage_selection(
                retention_policy=retention_policy.value,
                status=status,
                source=source,
                duration_seconds=duration,
                storage_element_id=se.element_id if se else None,
                mode=se.mode if se else None
            )

    async def _select_from_redis(
        self,
        file_size: int,
        required_mode: str
    ) -> Optional[StorageElementInfo]:
        """
        Выбор SE из Redis Registry.

        Использует sorted set storage:{mode}:by_priority для Sequential Fill.

        Args:
            file_size: Размер файла в байтах
            required_mode: Требуемый режим SE (edit или rw)

        Returns:
            StorageElementInfo или None
        """
        if not self._redis_client:
            logger.debug("Redis client not available for storage selection")
            return None

        try:
            # Получаем отсортированный список SE ID из sorted set
            sorted_set_key = f"storage:{required_mode}:by_priority"

            # ZRANGE возвращает элементы в порядке возрастания score (priority)
            se_ids = await self._redis_client.zrange(sorted_set_key, 0, -1)

            if not se_ids:
                logger.debug(
                    f"No SE found in Redis sorted set",
                    extra={"sorted_set_key": sorted_set_key}
                )
                return None

            # Проверяем каждый SE в порядке priority
            for se_id in se_ids:
                se_info = await self._get_se_info_from_redis(se_id)

                if se_info is None:
                    continue

                # Проверяем что SE подходит
                if se_info.can_accept_file(file_size):
                    return se_info

                logger.debug(
                    f"SE {se_id} skipped",
                    extra={
                        "capacity_status": se_info.capacity_status.value,
                        "capacity_free": se_info.capacity_free,
                        "file_size": file_size
                    }
                )

            return None

        except Exception as e:
            logger.warning(
                f"Redis selection failed, falling back",
                extra={"error": str(e)}
            )
            return None

    async def _get_se_info_from_redis(self, se_id: str) -> Optional[StorageElementInfo]:
        """
        Получение информации о SE из Redis Hash.

        Args:
            se_id: ID Storage Element

        Returns:
            StorageElementInfo или None
        """
        # Проверяем кеш
        if self._is_cache_valid() and se_id in self._cache:
            return self._cache[se_id]

        try:
            hash_key = f"storage:elements:{se_id}"
            data = await self._redis_client.hgetall(hash_key)

            if not data:
                return None

            se_info = StorageElementInfo(
                element_id=data.get("id", se_id),
                mode=data.get("mode", "unknown"),
                endpoint=data.get("endpoint", ""),
                priority=int(data.get("priority", 100)),
                capacity_total=int(data.get("capacity_total", 0)),
                capacity_used=int(data.get("capacity_used", 0)),
                capacity_free=int(data.get("capacity_free", 0)),
                capacity_percent=float(data.get("capacity_percent", 0.0)),
                capacity_status=CapacityStatus(data.get("capacity_status", "ok")),
                health_status=data.get("health_status", "unknown"),
                last_updated=datetime.fromisoformat(
                    data.get("last_updated", datetime.now(timezone.utc).isoformat())
                )
            )

            # Кешируем
            self._cache[se_id] = se_info
            self._cache_timestamp = datetime.now(timezone.utc)

            return se_info

        except Exception as e:
            logger.warning(
                f"Failed to get SE info from Redis",
                extra={"se_id": se_id, "error": str(e)}
            )
            return None

    def _is_cache_valid(self) -> bool:
        """Проверка валидности кеша."""
        if not self._cache_timestamp:
            return False

        age = (datetime.now(timezone.utc) - self._cache_timestamp).total_seconds()
        return age < self._cache_ttl_seconds

    async def _select_from_admin_module(
        self,
        file_size: int,
        required_mode: str
    ) -> Optional[StorageElementInfo]:
        """
        Выбор SE через Admin Module Fallback API.

        Используется когда Redis недоступен.

        Args:
            file_size: Размер файла в байтах
            required_mode: Требуемый режим SE

        Returns:
            StorageElementInfo или None
        """
        if not self._admin_client:
            logger.debug("Admin client not available for fallback")
            return None

        try:
            # Запрос к Admin Module Fallback API (будет реализовано в Task 6-7)
            se_list = await self._admin_client.get_available_storage_elements(
                mode=required_mode,
                min_free_bytes=file_size
            )

            if se_list:
                # Первый SE уже отсортирован по priority
                return se_list[0]

            return None

        except Exception as e:
            logger.warning(
                f"Admin Module fallback failed",
                extra={"error": str(e)}
            )
            return None

    async def _select_from_local_config(
        self,
        file_size: int,
        required_mode: str
    ) -> Optional[StorageElementInfo]:
        """
        Выбор SE из локальной конфигурации.

        Последний fallback когда ни Redis, ни Admin Module недоступны.

        Args:
            file_size: Размер файла в байтах
            required_mode: Требуемый режим SE

        Returns:
            StorageElementInfo или None
        """
        # Используем конфигурацию из settings
        # Это простой fallback на единственный SE из environment
        try:
            base_url = settings.storage_element.base_url

            # Создаём базовую информацию из config
            # При fallback мы не знаем точную емкость, поэтому устанавливаем placeholder
            se_info = StorageElementInfo(
                element_id="local-fallback",
                mode=required_mode,
                endpoint=base_url,
                priority=100,
                capacity_total=0,  # Неизвестно
                capacity_used=0,
                capacity_free=0,
                capacity_percent=0.0,
                capacity_status=CapacityStatus.OK,  # Предполагаем что OK
                health_status="unknown",
                last_updated=datetime.now(timezone.utc)
            )

            logger.warning(
                "Using local config fallback - capacity checks disabled",
                extra={"endpoint": base_url}
            )

            return se_info

        except Exception as e:
            logger.error(
                f"Local config fallback failed",
                extra={"error": str(e)}
            )
            return None

    async def get_all_available_storage_elements(
        self,
        mode: Optional[str] = None
    ) -> list[StorageElementInfo]:
        """
        Получение списка всех доступных SE.

        Args:
            mode: Фильтр по режиму (опционально)

        Returns:
            Список StorageElementInfo
        """
        result = []

        if not self._redis_client:
            return result

        try:
            # Если mode указан, берем только из соответствующего sorted set
            if mode:
                sorted_set_key = f"storage:{mode}:by_priority"
                se_ids = await self._redis_client.zrange(sorted_set_key, 0, -1)
            else:
                # Собираем из обоих sorted sets
                edit_ids = await self._redis_client.zrange("storage:edit:by_priority", 0, -1)
                rw_ids = await self._redis_client.zrange("storage:rw:by_priority", 0, -1)
                se_ids = list(set(edit_ids + rw_ids))

            for se_id in se_ids:
                se_info = await self._get_se_info_from_redis(se_id)
                if se_info:
                    result.append(se_info)

        except Exception as e:
            logger.error(f"Failed to get all SE: {e}")

        return result

    def invalidate_cache(self) -> None:
        """Инвалидация кеша SE."""
        self._cache.clear()
        self._cache_timestamp = None
        logger.debug("SE cache invalidated")


# Глобальный singleton экземпляр
_storage_selector: Optional[StorageSelector] = None


async def get_storage_selector() -> StorageSelector:
    """
    Получение singleton экземпляра StorageSelector.

    Returns:
        StorageSelector: Инициализированный selector
    """
    global _storage_selector

    if _storage_selector is None:
        _storage_selector = StorageSelector()

    return _storage_selector


async def init_storage_selector(redis_client=None, admin_client=None) -> StorageSelector:
    """
    Инициализация глобального StorageSelector.

    Вызывается при startup приложения.

    Args:
        redis_client: Async Redis клиент
        admin_client: Admin Module HTTP клиент

    Returns:
        StorageSelector: Инициализированный экземпляр
    """
    global _storage_selector

    _storage_selector = StorageSelector()
    await _storage_selector.initialize(redis_client, admin_client)

    return _storage_selector


async def close_storage_selector() -> None:
    """
    Закрытие StorageSelector при shutdown.
    """
    global _storage_selector

    if _storage_selector:
        await _storage_selector.close()
        _storage_selector = None
