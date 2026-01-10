"""
Cache Lock Manager для приоритизации операций синхронизации кеша.

Использует Redis distributed locks для координации между:
- Ручными операциями через API (высокий приоритет)
- Lazy rebuild при запросах (средний приоритет)
- Background cleanup (низкий приоритет, опционально)
"""

import logging
from datetime import timedelta
from enum import Enum
from typing import Optional

import redis.asyncio as aioredis
from redis.asyncio import Redis
from redis.exceptions import LockError

from app.core.config import settings
from app.core.redis import get_redis_client

logger = logging.getLogger(__name__)


class LockType(str, Enum):
    """Типы блокировок для cache sync операций."""

    MANUAL_REBUILD = "manual_rebuild"        # Priority 1: Highest
    MANUAL_CHECK = "manual_check"            # Priority 2: High
    LAZY_REBUILD = "lazy_rebuild"            # Priority 3: Medium
    BACKGROUND_CLEANUP = "background_cleanup"  # Priority 4: Lowest


class LockPriority(int, Enum):
    """Приоритеты блокировок (меньше = выше приоритет)."""

    MANUAL_REBUILD = 1
    MANUAL_CHECK = 2
    LAZY_REBUILD = 3
    BACKGROUND_CLEANUP = 4


LOCK_PRIORITIES = {
    LockType.MANUAL_REBUILD: LockPriority.MANUAL_REBUILD,
    LockType.MANUAL_CHECK: LockPriority.MANUAL_CHECK,
    LockType.LAZY_REBUILD: LockPriority.LAZY_REBUILD,
    LockType.BACKGROUND_CLEANUP: LockPriority.BACKGROUND_CLEANUP,
}


class CacheLockManager:
    """
    Manager для distributed locks операций синхронизации кеша.

    Features:
    - Priority-based locking: высокоприоритетные операции блокируют низкоприоритетные
    - Timeout-based expiration: автоматическое освобождение при зависании
    - Check before acquire: проверка конфликтов перед захватом lock

    Примеры:
        >>> lock_mgr = CacheLockManager()
        >>> async with lock_mgr.acquire_lock(LockType.MANUAL_REBUILD, timeout=600):
        ...     await rebuild_cache_full()
    """

    def __init__(self, redis_client: Optional[Redis] = None):
        """
        Инициализация lock manager.

        Args:
            redis_client: Redis клиент (опционально, по умолчанию из get_redis_client)
        """
        self.redis_client = redis_client
        self._lock_key_prefix = f"cache_lock:{settings.storage.element_id}"

    async def _get_redis(self) -> Redis:
        """Получить Redis клиент (lazy initialization)."""
        if not self.redis_client:
            self.redis_client = await get_redis_client()
        return self.redis_client

    def _get_lock_key(self, lock_type: LockType) -> str:
        """Получить Redis key для lock."""
        return f"{self._lock_key_prefix}:{lock_type.value}"

    async def acquire_lock(
        self,
        lock_type: LockType,
        timeout: int = 300,
        blocking: bool = True,
        blocking_timeout: int = 10
    ) -> bool:
        """
        Захватить distributed lock для cache sync операции.

        Проверяет конфликты с более приоритетными операциями перед захватом.

        Args:
            lock_type: Тип операции (определяет приоритет)
            timeout: Timeout lock в секундах (auto-release)
            blocking: Ждать ли если lock занят
            blocking_timeout: Максимальное время ожидания (сек)

        Returns:
            bool: True если lock захвачен, False если не удалось

        Raises:
            LockError: Если есть конфликт с более приоритетной операцией
        """
        redis = await self._get_redis()

        # Проверка конфликтов с более приоритетными операциями
        if not await self._check_priority_conflicts(lock_type):
            priority = LOCK_PRIORITIES[lock_type]
            logger.warning(
                "Cannot acquire lock: higher priority operation in progress",
                extra={
                    "lock_type": lock_type.value,
                    "priority": priority.value,
                    "element_id": settings.storage.element_id
                }
            )
            raise LockError(
                f"Cannot acquire {lock_type.value} lock: "
                f"higher priority operation in progress"
            )

        # Захват lock
        lock_key = self._get_lock_key(lock_type)

        try:
            # Используем Redis SET NX EX для atomic lock
            acquired = await redis.set(
                lock_key,
                "locked",
                nx=True,  # Only if not exists
                ex=timeout  # Expire after timeout seconds
            )

            if acquired:
                logger.info(
                    "Lock acquired successfully",
                    extra={
                        "lock_type": lock_type.value,
                        "timeout": timeout,
                        "element_id": settings.storage.element_id
                    }
                )
                return True

            elif blocking:
                # Wait for lock to be released
                logger.info(
                    "Waiting for lock to be released",
                    extra={
                        "lock_type": lock_type.value,
                        "blocking_timeout": blocking_timeout
                    }
                )

                # Simple polling-based waiting
                import asyncio
                elapsed = 0
                poll_interval = 0.5

                while elapsed < blocking_timeout:
                    await asyncio.sleep(poll_interval)
                    elapsed += poll_interval

                    # Retry acquiring
                    acquired = await redis.set(lock_key, "locked", nx=True, ex=timeout)
                    if acquired:
                        logger.info("Lock acquired after waiting", extra={"lock_type": lock_type.value})
                        return True

                logger.warning(
                    "Failed to acquire lock within timeout",
                    extra={"lock_type": lock_type.value, "blocking_timeout": blocking_timeout}
                )
                return False

            else:
                logger.info(
                    "Lock already held, skipping (non-blocking)",
                    extra={"lock_type": lock_type.value}
                )
                return False

        except Exception as e:
            logger.error(
                f"Failed to acquire lock: {e}",
                extra={"lock_type": lock_type.value, "error": str(e)}
            )
            return False

    async def release_lock(self, lock_type: LockType) -> bool:
        """
        Освободить distributed lock.

        Args:
            lock_type: Тип операции

        Returns:
            bool: True если lock освобождён, False если ошибка
        """
        redis = await self._get_redis()
        lock_key = self._get_lock_key(lock_type)

        try:
            deleted = await redis.delete(lock_key)

            if deleted:
                logger.info(
                    "Lock released successfully",
                    extra={"lock_type": lock_type.value, "element_id": settings.storage.element_id}
                )
                return True
            else:
                logger.warning(
                    "Lock was not held (already expired or not acquired)",
                    extra={"lock_type": lock_type.value}
                )
                return False

        except Exception as e:
            logger.error(
                f"Failed to release lock: {e}",
                extra={"lock_type": lock_type.value, "error": str(e)}
            )
            return False

    async def check_lock_status(self, lock_type: LockType) -> bool:
        """
        Проверить занят ли lock.

        Args:
            lock_type: Тип операции

        Returns:
            bool: True если lock занят, False если свободен
        """
        redis = await self._get_redis()
        lock_key = self._get_lock_key(lock_type)

        try:
            exists = await redis.exists(lock_key)
            return bool(exists)
        except Exception as e:
            logger.error(
                f"Failed to check lock status: {e}",
                extra={"lock_type": lock_type.value, "error": str(e)}
            )
            return False

    async def _check_priority_conflicts(self, lock_type: LockType) -> bool:
        """
        Проверить конфликты с более приоритетными операциями.

        Args:
            lock_type: Тип операции, которую хотим запустить

        Returns:
            bool: True если нет конфликтов, False если есть блокирующий lock
        """
        current_priority = LOCK_PRIORITIES[lock_type]

        # Проверяем все типы locks с более высоким приоритетом
        for other_type, other_priority in LOCK_PRIORITIES.items():
            if other_priority.value < current_priority.value:
                # Это более приоритетная операция
                if await self.check_lock_status(other_type):
                    logger.debug(
                        "Priority conflict detected",
                        extra={
                            "requesting_lock": lock_type.value,
                            "blocking_lock": other_type.value,
                            "requesting_priority": current_priority.value,
                            "blocking_priority": other_priority.value
                        }
                    )
                    return False

        return True

    async def __aenter__(self):
        """Context manager entry - для использования с async with."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        pass  # Locks auto-expire, но можно добавить cleanup


# Singleton instance для удобства использования
_lock_manager_instance: Optional[CacheLockManager] = None


async def get_cache_lock_manager() -> CacheLockManager:
    """
    Получить singleton instance CacheLockManager.

    Returns:
        CacheLockManager: Shared instance
    """
    global _lock_manager_instance

    if _lock_manager_instance is None:
        _lock_manager_instance = CacheLockManager()

    return _lock_manager_instance
