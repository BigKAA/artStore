"""
Unit tests для Cache Service (ASYNC).

Тестирует:
- LocalCache operations (get, set, delete, TTL)
- RedisCacheService operations (async)
- Multi-level caching strategy
- Cache invalidation
"""

import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

from app.services.cache_service import LocalCache, RedisCacheService, CacheService


# ========================================
# LocalCache Tests (синхронные - работа с памятью)
# ========================================

@pytest.mark.unit
class TestLocalCache:
    """Tests для LocalCache (in-memory)."""

    def test_set_and_get(self):
        """Тест сохранения и получения значений."""
        cache = LocalCache(ttl_seconds=300)

        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_nonexistent_key(self):
        """Тест получения несуществующего ключа."""
        cache = LocalCache()

        assert cache.get("nonexistent") is None

    def test_ttl_expiration(self):
        """Тест истечения TTL."""
        cache = LocalCache(ttl_seconds=0)  # Немедленное истечение

        cache.set("key1", "value1")

        # Сразу после установки ключ еще доступен (проверка timestamp)
        # Но при следующем обращении TTL истечет
        import time
        time.sleep(0.1)

        assert cache.get("key1") is None

    def test_max_size_eviction(self):
        """Тест вытеснения при превышении max_size."""
        cache = LocalCache(ttl_seconds=300, max_size=2)

        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")  # Должен вытеснить key1 (самый старый)

        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"
        assert cache.get("key3") == "value3"

    def test_delete(self):
        """Тест удаления ключа."""
        cache = LocalCache()

        cache.set("key1", "value1")
        cache.delete("key1")

        assert cache.get("key1") is None

    def test_clear(self):
        """Тест очистки всего кеша."""
        cache = LocalCache()

        cache.set("key1", "value1")
        cache.set("key2", "value2")

        cache.clear()

        assert cache.get("key1") is None
        assert cache.get("key2") is None


# ========================================
# RedisCacheService Tests (async)
# ========================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestRedisCacheService:
    """Tests для RedisCacheService (async)."""

    async def test_initialization_success(self):
        """Тест успешной инициализации Redis (async)."""
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        with patch("app.services.cache_service.aioredis.from_url", return_value=mock_redis):
            service = RedisCacheService()
            await service.initialize()

            assert service._is_available is True
            mock_redis.ping.assert_awaited_once()

    async def test_initialization_failure(self):
        """Тест неудачной инициализации Redis (async)."""
        from redis.exceptions import RedisError

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=RedisError("Connection failed"))

        with patch("app.services.cache_service.aioredis.from_url", return_value=mock_redis):
            service = RedisCacheService()
            await service.initialize()

            assert service._is_available is False

    async def test_get_success(self):
        """Тест успешного получения значения (async)."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="test_value")
        mock_redis.ping = AsyncMock(return_value=True)

        with patch("app.services.cache_service.aioredis.from_url", return_value=mock_redis):
            service = RedisCacheService()
            await service.initialize()

            value = await service.get("test_key")

            assert value == "test_value"
            mock_redis.get.assert_awaited_with("test_key")

    async def test_get_unavailable(self):
        """Тест получения при недоступном Redis (async)."""
        service = RedisCacheService()
        service._is_available = False

        value = await service.get("test_key")

        assert value is None

    async def test_set_success(self):
        """Тест успешного сохранения значения (async)."""
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        with patch("app.services.cache_service.aioredis.from_url", return_value=mock_redis):
            service = RedisCacheService()
            await service.initialize()

            result = await service.set("test_key", "test_value", ttl_seconds=300)

            assert result is True
            mock_redis.setex.assert_awaited_with(
                name="test_key",
                time=300,
                value="test_value"
            )

    async def test_delete_success(self):
        """Тест успешного удаления ключа (async)."""
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(return_value=1)
        mock_redis.ping = AsyncMock(return_value=True)

        with patch("app.services.cache_service.aioredis.from_url", return_value=mock_redis):
            service = RedisCacheService()
            await service.initialize()

            result = await service.delete("test_key")

            assert result is True
            mock_redis.delete.assert_awaited_with("test_key")

    async def test_close(self):
        """Тест закрытия Redis connection (async)."""
        mock_redis = AsyncMock()
        mock_redis.close = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        with patch("app.services.cache_service.aioredis.from_url", return_value=mock_redis):
            service = RedisCacheService()
            await service.initialize()

            await service.close()

            mock_redis.close.assert_awaited_once()
            assert service._redis_client is None
            assert service._is_available is False


# ========================================
# CacheService Tests (async multi-level)
# ========================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestCacheService:
    """Tests для Multi-Level CacheService (async)."""

    def test_file_key_generation(self):
        """Тест генерации ключа для файла."""
        service = CacheService()

        key = service._make_file_key("test-file-id")

        assert key == "file:test-file-id"

    async def test_get_from_local_cache(self):
        """Тест получения из local cache (быстрый путь, sync)."""
        mock_settings = MagicMock()
        mock_settings.cache.local_enabled = True
        mock_settings.cache.redis_enabled = False

        with patch("app.services.cache_service.settings", mock_settings):
            service = CacheService()
            test_metadata = {"id": "test-id", "filename": "test.pdf"}

            # Заполнение local cache
            if service.local_cache:
                service.local_cache.set("file:test-id", test_metadata)

            result = await service.get_file_metadata("test-id")

            assert result == test_metadata

    async def test_get_from_redis_cache(self):
        """Тест получения из Redis cache с сохранением в local (async)."""
        mock_redis = AsyncMock()
        test_metadata = {"id": "test-id", "filename": "test.pdf"}
        metadata_json = json.dumps(test_metadata, default=str)
        mock_redis.get = AsyncMock(return_value=metadata_json)
        mock_redis.ping = AsyncMock(return_value=True)

        mock_settings = MagicMock()
        mock_settings.cache.local_enabled = True
        mock_settings.cache.redis_enabled = True
        mock_settings.redis.url = "redis://localhost:6379"
        mock_settings.redis.max_connections = 10
        mock_settings.redis.socket_timeout = 5.0
        mock_settings.redis.socket_connect_timeout = 5.0

        with patch("app.services.cache_service.settings", mock_settings), \
             patch("app.services.cache_service.aioredis.from_url", return_value=mock_redis):
            service = CacheService()
            await service.initialize()

            result = await service.get_file_metadata("test-id")

            assert result == test_metadata

            # Проверка сохранения в local cache
            if service.local_cache:
                local_result = service.local_cache.get("file:test-id")
                assert local_result == test_metadata

    async def test_cache_miss(self):
        """Тест cache miss на всех уровнях (async)."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.ping = AsyncMock(return_value=True)

        mock_settings = MagicMock()
        mock_settings.cache.local_enabled = True
        mock_settings.cache.redis_enabled = True
        mock_settings.redis.url = "redis://localhost:6379"
        mock_settings.redis.max_connections = 10
        mock_settings.redis.socket_timeout = 5.0
        mock_settings.redis.socket_connect_timeout = 5.0

        with patch("app.services.cache_service.settings", mock_settings), \
             patch("app.services.cache_service.aioredis.from_url", return_value=mock_redis):
            service = CacheService()
            await service.initialize()

            result = await service.get_file_metadata("nonexistent-id")

            assert result is None

    async def test_set_file_metadata(self):
        """Тест сохранения метаданных на всех уровнях (async)."""
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        mock_settings = MagicMock()
        mock_settings.cache.local_enabled = True
        mock_settings.cache.redis_enabled = True
        mock_settings.cache.redis_ttl = 1800
        mock_settings.redis.url = "redis://localhost:6379"
        mock_settings.redis.max_connections = 10
        mock_settings.redis.socket_timeout = 5.0
        mock_settings.redis.socket_connect_timeout = 5.0

        with patch("app.services.cache_service.settings", mock_settings), \
             patch("app.services.cache_service.aioredis.from_url", return_value=mock_redis):
            service = CacheService()
            await service.initialize()

            test_metadata = {"id": "test-id", "filename": "test.pdf"}
            await service.set_file_metadata("test-id", test_metadata)

            # Проверка local cache
            if service.local_cache:
                local_result = service.local_cache.get("file:test-id")
                assert local_result == test_metadata

            # Проверка вызова Redis
            mock_redis.setex.assert_awaited()

    async def test_invalidate_file_metadata(self):
        """Тест инвалидации метаданных на всех уровнях (async)."""
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(return_value=1)
        mock_redis.ping = AsyncMock(return_value=True)
        mock_redis.setex = AsyncMock()

        mock_settings = MagicMock()
        mock_settings.cache.local_enabled = True
        mock_settings.cache.redis_enabled = True
        mock_settings.cache.redis_ttl = 1800
        mock_settings.redis.url = "redis://localhost:6379"
        mock_settings.redis.max_connections = 10
        mock_settings.redis.socket_timeout = 5.0
        mock_settings.redis.socket_connect_timeout = 5.0

        with patch("app.services.cache_service.settings", mock_settings), \
             patch("app.services.cache_service.aioredis.from_url", return_value=mock_redis):
            service = CacheService()
            await service.initialize()

            test_metadata = {"id": "test-id", "filename": "test.pdf"}

            # Установка в кеш
            await service.set_file_metadata("test-id", test_metadata)

            # Сбрасываем mock для get чтобы вернуть None после invalidation
            mock_redis.get = AsyncMock(return_value=None)

            # Инвалидация
            await service.invalidate_file_metadata("test-id")

            # Проверка удаления из local cache
            if service.local_cache:
                assert service.local_cache.get("file:test-id") is None

    async def test_corrupted_redis_data(self):
        """Тест обработки поврежденных данных в Redis (async)."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="invalid json")
        mock_redis.delete = AsyncMock(return_value=1)
        mock_redis.ping = AsyncMock(return_value=True)

        mock_settings = MagicMock()
        mock_settings.cache.local_enabled = True
        mock_settings.cache.redis_enabled = True
        mock_settings.redis.url = "redis://localhost:6379"
        mock_settings.redis.max_connections = 10
        mock_settings.redis.socket_timeout = 5.0
        mock_settings.redis.socket_connect_timeout = 5.0

        with patch("app.services.cache_service.settings", mock_settings), \
             patch("app.services.cache_service.aioredis.from_url", return_value=mock_redis):
            service = CacheService()
            await service.initialize()

            result = await service.get_file_metadata("test-id")

            # Должен вернуть None и удалить поврежденные данные
            assert result is None
            mock_redis.delete.assert_awaited()

    async def test_close(self):
        """Тест закрытия всех connections (async)."""
        mock_redis = AsyncMock()
        mock_redis.close = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        mock_settings = MagicMock()
        mock_settings.cache.local_enabled = True
        mock_settings.cache.redis_enabled = True
        mock_settings.redis.url = "redis://localhost:6379"
        mock_settings.redis.max_connections = 10
        mock_settings.redis.socket_timeout = 5.0
        mock_settings.redis.socket_connect_timeout = 5.0

        with patch("app.services.cache_service.settings", mock_settings), \
             patch("app.services.cache_service.aioredis.from_url", return_value=mock_redis):
            service = CacheService()
            await service.initialize()

            await service.close()

            mock_redis.close.assert_awaited_once()
