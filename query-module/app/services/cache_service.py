"""
Query Module - Cache Service.

Реализует Multi-Level Caching стратегию:
- Local Cache (in-memory): Fastest, TTL 300s
- Redis Cache (distributed): Fast, TTL 1800s
- PostgreSQL: Source of truth, fallback при cache miss

ВАЖНО: Redis работает в АСИНХРОННОМ режиме (redis.asyncio)
согласно архитектурным требованиям ArtStore проекта.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import redis.asyncio as aioredis
from redis.asyncio import Redis
from redis.exceptions import RedisError, ConnectionError as RedisConnectionError

from app.core.config import settings
from app.core.exceptions import CacheUnavailableException, CacheCorruptedException

logger = logging.getLogger(__name__)


class LocalCache:
    """
    In-memory LRU кеш для ultra-fast доступа к метаданным.

    Использует простой dict с timestamp для управления TTL.
    Синхронный, так как работает только с локальной памятью.
    """

    def __init__(self, ttl_seconds: int = 300, max_size: int = 1000):
        """
        Инициализация local cache.

        Args:
            ttl_seconds: Time-to-live для записей (по умолчанию 5 минут)
            max_size: Максимальное количество записей в кеше
        """
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self._cache: Dict[str, tuple[Any, datetime]] = {}

        logger.info(
            "Local cache initialized",
            extra={
                "ttl_seconds": ttl_seconds,
                "max_size": max_size
            }
        )

    def get(self, key: str) -> Optional[Any]:
        """Получение значения из local cache."""
        if key not in self._cache:
            return None

        value, timestamp = self._cache[key]

        # Проверка TTL
        if datetime.utcnow() - timestamp > timedelta(seconds=self.ttl_seconds):
            del self._cache[key]
            return None

        return value

    def set(self, key: str, value: Any) -> None:
        """Сохранение значения в local cache."""
        if len(self._cache) >= self.max_size:
            # Удаляем самую старую запись
            oldest_key = min(self._cache.items(), key=lambda x: x[1][1])[0]
            del self._cache[oldest_key]

        self._cache[key] = (value, datetime.utcnow())

    def delete(self, key: str) -> None:
        """Удаление записи из local cache."""
        if key in self._cache:
            del self._cache[key]

    def clear(self) -> None:
        """Очистка всего local cache."""
        self._cache.clear()


class RedisCacheService:
    """
    Distributed cache service через Redis (ASYNC режим).

    Все методы асинхронные для неблокирующей работы с event loop FastAPI.
    """

    def __init__(self):
        """Инициализация Redis async client."""
        self._redis_client: Optional[Redis] = None
        self._is_available = False

    async def initialize(self) -> None:
        """
        Асинхронная инициализация Redis connection.
        Вызывается при startup приложения.
        """
        try:
            self._redis_client = await aioredis.from_url(
                settings.redis.url,
                max_connections=settings.redis.max_connections,
                socket_timeout=settings.redis.socket_timeout,
                socket_connect_timeout=settings.redis.socket_connect_timeout,
                decode_responses=True,
            )

            await self._redis_client.ping()
            self._is_available = True
            logger.info("Redis cache initialized (async mode)")

        except (RedisError, RedisConnectionError) as e:
            logger.warning(f"Redis unavailable: {e}")
            self._is_available = False

    async def is_available(self) -> bool:
        """Асинхронная проверка доступности Redis."""
        if not self._is_available or not self._redis_client:
            return False
        try:
            await self._redis_client.ping()
            return True
        except (RedisError, RedisConnectionError):
            self._is_available = False
            return False

    async def get(self, key: str) -> Optional[str]:
        """Асинхронное получение значения из Redis."""
        if not await self.is_available():
            return None
        try:
            return await self._redis_client.get(key)
        except (RedisError, RedisConnectionError):
            self._is_available = False
            return None

    async def set(self, key: str, value: str, ttl_seconds: Optional[int] = None) -> bool:
        """Асинхронное сохранение значения в Redis."""
        if not await self.is_available():
            return False
        try:
            ttl = ttl_seconds or settings.cache.redis_ttl
            await self._redis_client.setex(name=key, time=ttl, value=value)
            return True
        except (RedisError, RedisConnectionError):
            self._is_available = False
            return False

    async def delete(self, key: str) -> bool:
        """Асинхронное удаление записи из Redis."""
        if not await self.is_available():
            return False
        try:
            result = await self._redis_client.delete(key)
            return result > 0
        except (RedisError, RedisConnectionError):
            self._is_available = False
            return False

    async def close(self) -> None:
        """Асинхронное закрытие Redis connection."""
        if self._redis_client:
            await self._redis_client.close()
            self._redis_client = None
            self._is_available = False
            logger.info("Redis cache closed")


class CacheService:
    """
    Multi-Level Cache Service.

    Все методы работы с Redis асинхронные.
    Local cache остается синхронным (работа с памятью).
    """

    def __init__(self):
        """Инициализация multi-level cache."""
        self.local_cache = LocalCache() if settings.cache.local_enabled else None
        self.redis_cache = RedisCacheService() if settings.cache.redis_enabled else None

    async def initialize(self) -> None:
        """
        Асинхронная инициализация cache service.
        Вызывается при startup приложения.
        """
        if self.redis_cache:
            await self.redis_cache.initialize()
        logger.info("CacheService initialized")

    def _make_file_key(self, file_id: str) -> str:
        """Создание ключа кеша для файла."""
        return f"file:{file_id}"

    async def get_file_metadata(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Асинхронное получение метаданных файла из multi-level cache."""
        cache_key = self._make_file_key(file_id)

        # 1. Local Cache (синхронный)
        if self.local_cache:
            local_value = self.local_cache.get(cache_key)
            if local_value is not None:
                return local_value

        # 2. Redis Cache (асинхронный)
        if self.redis_cache and await self.redis_cache.is_available():
            redis_value = await self.redis_cache.get(cache_key)
            if redis_value:
                try:
                    metadata = json.loads(redis_value)
                    # Обновляем local cache
                    if self.local_cache:
                        self.local_cache.set(cache_key, metadata)
                    return metadata
                except json.JSONDecodeError:
                    await self.redis_cache.delete(cache_key)

        return None

    async def set_file_metadata(self, file_id: str, metadata: Dict[str, Any]) -> None:
        """Асинхронное сохранение метаданных файла в multi-level cache."""
        cache_key = self._make_file_key(file_id)

        # Local cache (синхронный)
        if self.local_cache:
            self.local_cache.set(cache_key, metadata)

        # Redis cache (асинхронный)
        if self.redis_cache and await self.redis_cache.is_available():
            try:
                metadata_json = json.dumps(metadata, default=str)
                await self.redis_cache.set(cache_key, metadata_json)
            except (TypeError, ValueError) as e:
                logger.warning(f"Failed to serialize metadata: {e}")

    async def invalidate_file_metadata(self, file_id: str) -> None:
        """Асинхронная инвалидация метаданных файла."""
        cache_key = self._make_file_key(file_id)

        # Local cache (синхронный)
        if self.local_cache:
            self.local_cache.delete(cache_key)

        # Redis cache (асинхронный)
        if self.redis_cache:
            await self.redis_cache.delete(cache_key)

    async def close(self) -> None:
        """Асинхронное закрытие всех cache connections."""
        if self.redis_cache:
            await self.redis_cache.close()


# Global instance (инициализируется асинхронно при startup)
cache_service = CacheService()


async def get_cache_service() -> CacheService:
    """
    Dependency для получения cache service в FastAPI endpoints.

    Example:
        @app.get("/file/{file_id}")
        async def get_file(
            file_id: str,
            cache: CacheService = Depends(get_cache_service)
        ):
            metadata = await cache.get_file_metadata(file_id)
            return metadata
    """
    return cache_service
