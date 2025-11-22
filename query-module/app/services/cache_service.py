"""
Query Module - Cache Service.

Реализует Multi-Level Caching стратегию:
- Local Cache (in-memory): Fastest, TTL 300s
- Redis Cache (distributed): Fast, TTL 1800s
- PostgreSQL: Source of truth, fallback при cache miss

ВАЖНО: Redis работает в СИНХРОННОМ режиме (redis-py, НЕ redis.asyncio)
согласно архитектурным требованиям ArtStore проекта.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from functools import lru_cache

import redis
from redis.exceptions import RedisError, ConnectionError as RedisConnectionError

from app.core.config import settings
from app.core.exceptions import CacheUnavailableException, CacheCorruptedException

logger = logging.getLogger(__name__)


class LocalCache:
    """
    In-memory LRU кеш для ultra-fast доступа к метаданным.

    Использует functools.lru_cache для автоматического управления размером.
    TTL реализован через timestamp проверку.
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
    """Distributed cache service через Redis (SYNC режим)."""

    def __init__(self):
        """Инициализация Redis connection pool."""
        self._redis_client: Optional[redis.Redis] = None
        self._is_available = False

        try:
            self._redis_client = redis.Redis(
                host=settings.redis.host,
                port=settings.redis.port,
                db=settings.redis.db,
                password=settings.redis.password if settings.redis.password else None,
                decode_responses=True,
                socket_timeout=settings.redis.socket_timeout,
                socket_connect_timeout=settings.redis.socket_connect_timeout,
                socket_keepalive=True,
                health_check_interval=30,
                max_connections=settings.redis.max_connections,
            )

            self._redis_client.ping()
            self._is_available = True
            logger.info("Redis cache initialized")

        except (RedisError, RedisConnectionError) as e:
            logger.warning(f"Redis unavailable: {e}")
            self._is_available = False

    def is_available(self) -> bool:
        """Проверка доступности Redis."""
        if not self._is_available:
            return False
        try:
            self._redis_client.ping()
            return True
        except:
            self._is_available = False
            return False

    def get(self, key: str) -> Optional[str]:
        """Получение значения из Redis."""
        if not self.is_available():
            return None
        try:
            return self._redis_client.get(key)
        except (RedisError, RedisConnectionError):
            self._is_available = False
            return None

    def set(self, key: str, value: str, ttl_seconds: Optional[int] = None) -> bool:
        """Сохранение значения в Redis."""
        if not self.is_available():
            return False
        try:
            ttl = ttl_seconds or settings.cache.redis_ttl
            self._redis_client.setex(name=key, time=ttl, value=value)
            return True
        except (RedisError, RedisConnectionError):
            self._is_available = False
            return False

    def delete(self, key: str) -> bool:
        """Удаление записи из Redis."""
        if not self.is_available():
            return False
        try:
            return self._redis_client.delete(key) > 0
        except (RedisError, RedisConnectionError):
            self._is_available = False
            return False

    def close(self) -> None:
        """Закрытие Redis connection pool."""
        if self._redis_client:
            self._redis_client.close()


class CacheService:
    """Multi-Level Cache Service."""

    def __init__(self):
        """Инициализация multi-level cache."""
        self.local_cache = LocalCache() if settings.cache.local_enabled else None
        self.redis_cache = RedisCacheService() if settings.cache.redis_enabled else None

    def _make_file_key(self, file_id: str) -> str:
        """Создание ключа кеша для файла."""
        return f"file:{file_id}"

    def get_file_metadata(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Получение метаданных файла из multi-level cache."""
        cache_key = self._make_file_key(file_id)

        # 1. Local Cache
        if self.local_cache:
            local_value = self.local_cache.get(cache_key)
            if local_value is not None:
                return local_value

        # 2. Redis Cache
        if self.redis_cache and self.redis_cache.is_available():
            redis_value = self.redis_cache.get(cache_key)
            if redis_value:
                try:
                    metadata = json.loads(redis_value)
                    if self.local_cache:
                        self.local_cache.set(cache_key, metadata)
                    return metadata
                except json.JSONDecodeError:
                    self.redis_cache.delete(cache_key)

        return None

    def set_file_metadata(self, file_id: str, metadata: Dict[str, Any]) -> None:
        """Сохранение метаданных файла в multi-level cache."""
        cache_key = self._make_file_key(file_id)

        if self.local_cache:
            self.local_cache.set(cache_key, metadata)

        if self.redis_cache and self.redis_cache.is_available():
            try:
                metadata_json = json.dumps(metadata, default=str)
                self.redis_cache.set(cache_key, metadata_json)
            except (TypeError, ValueError) as e:
                logger.warning(f"Failed to serialize metadata: {e}")

    def invalidate_file_metadata(self, file_id: str) -> None:
        """Инвалидация метаданных файла."""
        cache_key = self._make_file_key(file_id)
        if self.local_cache:
            self.local_cache.delete(cache_key)
        if self.redis_cache:
            self.redis_cache.delete(cache_key)

    def close(self) -> None:
        """Закрытие всех cache connections."""
        if self.redis_cache:
            self.redis_cache.close()


# Singleton instance
cache_service = CacheService()
