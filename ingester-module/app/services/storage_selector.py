"""
StorageSelector - Сервис выбора Storage Element для загрузки файлов.

Sprint 19 Phase 4: HTTP Polling модель (AdaptiveCapacityMonitor) как основной источник.

Алгоритм Sequential Fill:
1. Получаем список доступных SE из AdaptiveCapacityMonitor (sorted set capacity:{mode}:available)
2. Для каждого SE (в порядке priority) проверяем:
   - capacity_status != FULL
   - can_accept_file(file_size)
3. Возвращаем первый подходящий SE

Fallback Pattern (Sprint 19):
- POLLING (AdaptiveCapacityMonitor) → Admin Module HTTP API
- Legacy Redis PUSH модель УДАЛЕНА (Phase 4 Cutover)

ВАЖНО: Использует redis.asyncio (async) для кеширования внутри AdaptiveCapacityMonitor.
"""

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import record_storage_selection, record_selection_source
# Sprint 18 Phase 3: Import для POLLING модели (AdaptiveCapacityMonitor)
from app.services.capacity_monitor import (
    get_capacity_monitor,
    StorageCapacityInfo,
    HealthStatus,
)

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
        """
        Инициализация StorageSelector.

        Sprint 19 Phase 4: Redis client больше не требуется.
        Выбор SE через AdaptiveCapacityMonitor (POLLING) или Admin Module API.
        """
        self._admin_client = None  # Admin Module HTTP клиент для fallback
        self._redis_client = None  # DEPRECATED (Sprint 19) - оставлен для совместимости legacy методов
        self._initialized = False
        self._cache = {}  # Локальный кеш SE
        self._cache_timestamp = None

    async def initialize(self, redis_client=None, admin_client=None) -> None:
        """
        Инициализация сервиса.

        Args:
            redis_client: DEPRECATED (Sprint 19) - не используется, оставлен для совместимости
            admin_client: Admin Module HTTP клиент (опционально, для fallback)
        """
        # Sprint 19 Phase 4: redis_client больше не используется
        # Параметр оставлен для обратной совместимости сигнатуры
        self._admin_client = admin_client
        self._initialized = True

        logger.info("StorageSelector initialized (POLLING mode)")

    async def close(self) -> None:
        """Закрытие ресурсов."""
        self._initialized = False
        logger.info("StorageSelector closed")

    async def select_storage_element(
        self,
        file_size: int,
        retention_policy: RetentionPolicy = RetentionPolicy.TEMPORARY,
        excluded_se_ids: Optional[set[str]] = None,
    ) -> Optional[StorageElementInfo]:
        """
        Выбор Storage Element для загрузки файла.

        Реализует Sequential Fill алгоритм:
        1. Получаем SE из Redis sorted set по priority
        2. Фильтруем по mode (edit для TEMPORARY, rw для PERMANENT)
        3. Выбираем первый SE с достаточной емкостью

        Fallback (Sprint 16):
        - Redis недоступен → Admin Module API
        - Если оба недоступны → RuntimeError (Service Discovery обязателен)

        Sprint 17: Добавлен excluded_se_ids для поддержки retry logic.
        SE из этого множества пропускаются при выборе.

        Args:
            file_size: Размер файла в байтах
            retention_policy: Политика хранения (определяет тип SE)
            excluded_se_ids: Множество ID SE для исключения из выбора (Sprint 17)

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
        se = None  # Инициализируем для использования в finally блоке

        try:
            # Sprint 19 Phase 4: Fallback chain POLLING → Admin Module
            # Legacy Redis PUSH модель удалена

            # Попытка 1: POLLING модель (AdaptiveCapacityMonitor)
            se = await self._select_from_adaptive_monitor(file_size, required_mode, excluded_se_ids)
            if se:
                source = "adaptive_monitor"
                status = "success"
                logger.info(
                    f"Selected SE from POLLING model",
                    extra={
                        "se_id": se.element_id,
                        "mode": se.mode,
                        "file_size": file_size,
                        "retention_policy": retention_policy.value,
                        "source": "adaptive_monitor",
                        "excluded_se_ids": list(excluded_se_ids) if excluded_se_ids else [],
                    }
                )
                return se

            # Попытка 2: Admin Module Fallback API
            se = await self._select_from_admin_module(file_size, required_mode, excluded_se_ids)
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
                        "source": "admin_module",
                        "excluded_se_ids": list(excluded_se_ids) if excluded_se_ids else [],
                    }
                )
                return se

            # Все источники исчерпаны
            source = "none"
            status = "failed"
            logger.error(
                "No suitable Storage Element found - all sources exhausted",
                extra={
                    "file_size": file_size,
                    "retention_policy": retention_policy.value,
                    "required_mode": required_mode,
                    "polling_enabled": settings.capacity_monitor.use_for_selection,
                    "admin_available": self._admin_client is not None
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
            # Sprint 19 Phase 4: Метрика источника для мониторинга
            record_selection_source(source=source, success=(se is not None))

    # Sprint 19 Phase 4: Методы _select_from_redis, _get_se_info_from_redis, _is_cache_valid
    # УДАЛЕНЫ - legacy Redis PUSH модель больше не используется.
    # Используется только POLLING через AdaptiveCapacityMonitor.

    async def _select_from_admin_module(
        self,
        file_size: int,
        required_mode: str,
        excluded_se_ids: Optional[set[str]] = None,
    ) -> Optional[StorageElementInfo]:
        """
        Выбор SE через Admin Module Fallback API.

        Используется когда Redis недоступен.

        Sprint 17: Добавлен excluded_se_ids для поддержки retry logic.

        Args:
            file_size: Размер файла в байтах
            required_mode: Требуемый режим SE
            excluded_se_ids: Множество ID SE для исключения из выбора

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
                # Sprint 17: Фильтруем excluded SE
                for se in se_list:
                    if excluded_se_ids and se.element_id in excluded_se_ids:
                        continue
                    return se

            return None

        except Exception as e:
            logger.warning(
                f"Admin Module fallback failed",
                extra={"error": str(e)}
            )
            return None

    # Sprint 16: метод _select_from_local_config() УДАЛЁН
    # Service Discovery через Redis или Admin Module обязателен

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

    # ========== Sprint 18 Phase 3: POLLING модель (AdaptiveCapacityMonitor) ==========

    def _convert_capacity_to_element_info(
        self,
        capacity_info: StorageCapacityInfo,
        priority: int = 100
    ) -> StorageElementInfo:
        """
        Конвертация StorageCapacityInfo (POLLING модель) в StorageElementInfo.

        Sprint 18 Phase 3: Маппинг типов между AdaptiveCapacityMonitor и StorageSelector.

        Args:
            capacity_info: Данные из POLLING модели
            priority: Priority SE (из Admin Module)

        Returns:
            StorageElementInfo: Конвертированный объект для Sequential Fill
        """
        # Конвертация percent_used в CapacityStatus
        percent_used = capacity_info.percent_used
        if percent_used >= 98:
            capacity_status = CapacityStatus.FULL
        elif percent_used >= 92:
            capacity_status = CapacityStatus.CRITICAL
        elif percent_used >= 85:
            capacity_status = CapacityStatus.WARNING
        else:
            capacity_status = CapacityStatus.OK

        # Конвертация HealthStatus enum в string
        health_mapping = {
            HealthStatus.HEALTHY: "healthy",
            HealthStatus.DEGRADED: "degraded",
            HealthStatus.UNHEALTHY: "unhealthy",
        }
        health_status = health_mapping.get(capacity_info.health, "unknown")

        # Парсинг last_poll из ISO 8601
        try:
            last_updated = datetime.fromisoformat(capacity_info.last_poll.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            last_updated = datetime.now(timezone.utc)

        return StorageElementInfo(
            element_id=capacity_info.storage_id,
            mode=capacity_info.mode,
            endpoint=capacity_info.endpoint,
            priority=priority,
            capacity_total=capacity_info.total,
            capacity_used=capacity_info.used,
            capacity_free=capacity_info.available,
            capacity_percent=percent_used,
            capacity_status=capacity_status,
            health_status=health_status,
            last_updated=last_updated,
        )

    async def _select_from_adaptive_monitor(
        self,
        file_size: int,
        required_mode: str,
        excluded_se_ids: Optional[set[str]] = None,
    ) -> Optional[StorageElementInfo]:
        """
        Выбор SE из AdaptiveCapacityMonitor (POLLING модель).

        Sprint 18 Phase 3: Primary источник данных о capacity.

        Использует sorted set capacity:{mode}:available для Sequential Fill.

        Args:
            file_size: Размер файла в байтах
            required_mode: Требуемый режим SE (edit или rw)
            excluded_se_ids: Множество ID SE для исключения из выбора

        Returns:
            StorageElementInfo или None
        """
        # Проверяем, включена ли POLLING модель
        if not settings.capacity_monitor.use_for_selection:
            logger.debug("POLLING model disabled in config")
            return None

        # Получаем CapacityMonitor
        capacity_monitor = await get_capacity_monitor()
        if not capacity_monitor:
            logger.debug("AdaptiveCapacityMonitor not available")
            return None

        try:
            # Sprint 19 Phase 4: Используем AdaptiveCapacityMonitor напрямую
            # вместо legacy Redis sorted sets
            available_se = await capacity_monitor.get_available_storage_elements(
                mode=required_mode
            )

            if not available_se:
                logger.debug(
                    f"No SE available in POLLING model",
                    extra={"required_mode": required_mode}
                )
                return None

            # Sequential Fill: SE отсортированы по priority (низший = высший приоритет)
            for capacity_info in available_se:
                se_id = capacity_info.storage_id

                # Пропускаем excluded SE
                if excluded_se_ids and se_id in excluded_se_ids:
                    continue

                # Конвертируем в StorageElementInfo
                se_info = self._convert_capacity_to_element_info(
                    capacity_info, priority=100  # TODO: получить priority из config
                )

                # Проверяем, может ли SE принять файл
                if se_info.can_accept_file(file_size):
                    logger.debug(
                        f"Selected SE from POLLING model",
                        extra={
                            "se_id": se_id,
                            "capacity_percent": se_info.capacity_percent,
                            "mode": se_info.mode,
                            "source": "adaptive_monitor",
                        }
                    )
                    return se_info

            logger.debug("No suitable SE found in POLLING model (all full or wrong mode)")
            return None

        except Exception as e:
            logger.warning(
                f"POLLING model selection failed",
                extra={"error": str(e)}
            )
            return None


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
