"""
Unit tests для Cache Service.

Тестирует:
- LocalCache operations (get, set, delete, TTL)
- RedisCacheService operations  
- Multi-level caching strategy
- Cache invalidation
"""

import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from app.services.cache_service import LocalCache, RedisCacheService, CacheService


# ========================================
# LocalCache Tests
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
# RedisCacheService Tests
# ========================================

@pytest.mark.unit
class TestRedisCacheService:
    """Tests для RedisCacheService."""

    def test_initialization_success(self, mock_redis):
        """Тест успешной инициализации Redis."""
        with patch("app.services.cache_service.redis.Redis", return_value=mock_redis):
            service = RedisCacheService()
            
            assert service._is_available is True
            mock_redis.ping.assert_called_once()

    def test_initialization_failure(self):
        """Тест неудачной инициализации Redis."""
        from redis.exceptions import RedisError

        mock_redis = MagicMock()
        mock_redis.ping.side_effect = RedisError("Connection failed")

        with patch("app.services.cache_service.redis.Redis", return_value=mock_redis):
            service = RedisCacheService()

            assert service._is_available is False

    def test_get_success(self, mock_redis):
        """Тест успешного получения значения."""
        mock_redis.get.return_value = "test_value"
        
        with patch("app.services.cache_service.redis.Redis", return_value=mock_redis):
            service = RedisCacheService()
            service._is_available = True
            
            value = service.get("test_key")
            
            assert value == "test_value"
            mock_redis.get.assert_called_with("test_key")

    def test_get_unavailable(self):
        """Тест получения при недоступном Redis."""
        service = RedisCacheService()
        service._is_available = False
        
        value = service.get("test_key")
        
        assert value is None

    def test_set_success(self, mock_redis):
        """Тест успешного сохранения значения."""
        with patch("app.services.cache_service.redis.Redis", return_value=mock_redis):
            service = RedisCacheService()
            service._is_available = True
            
            result = service.set("test_key", "test_value", ttl_seconds=300)
            
            assert result is True
            mock_redis.setex.assert_called_with(
                name="test_key",
                time=300,
                value="test_value"
            )

    def test_delete_success(self, mock_redis):
        """Тест успешного удаления ключа."""
        mock_redis.delete.return_value = 1
        
        with patch("app.services.cache_service.redis.Redis", return_value=mock_redis):
            service = RedisCacheService()
            service._is_available = True
            
            result = service.delete("test_key")
            
            assert result is True
            mock_redis.delete.assert_called_with("test_key")


# ========================================
# CacheService Tests
# ========================================

@pytest.mark.unit  
class TestCacheService:
    """Tests для Multi-Level CacheService."""

    def test_file_key_generation(self):
        """Тест генерации ключа для файла."""
        service = CacheService()
        
        key = service._make_file_key("test-file-id")
        
        assert key == "file:test-file-id"

    def test_get_from_local_cache(self, mock_cache_service):
        """Тест получения из local cache (быстрый путь)."""
        test_metadata = {"id": "test-id", "filename": "test.pdf"}
        
        # Заполнение local cache
        if mock_cache_service.local_cache:
            mock_cache_service.local_cache.set(
                "file:test-id",
                test_metadata
            )
        
        result = mock_cache_service.get_file_metadata("test-id")
        
        assert result == test_metadata

    def test_get_from_redis_cache(self, mock_cache_service, mock_redis):
        """Тест получения из Redis cache с сохранением в local."""
        test_metadata = {"id": "test-id", "filename": "test.pdf"}
        metadata_json = json.dumps(test_metadata, default=str)
        
        # Mock Redis возвращает данные
        if mock_cache_service.redis_cache:
            mock_cache_service.redis_cache._redis_client.get.return_value = metadata_json
        
        result = mock_cache_service.get_file_metadata("test-id")
        
        assert result == test_metadata
        
        # Проверка сохранения в local cache
        if mock_cache_service.local_cache:
            local_result = mock_cache_service.local_cache.get("file:test-id")
            assert local_result == test_metadata

    def test_cache_miss(self, mock_cache_service):
        """Тест cache miss на всех уровнях."""
        result = mock_cache_service.get_file_metadata("nonexistent-id")
        
        assert result is None

    def test_set_file_metadata(self, mock_cache_service):
        """Тест сохранения метаданных на всех уровнях."""
        test_metadata = {"id": "test-id", "filename": "test.pdf"}
        
        mock_cache_service.set_file_metadata("test-id", test_metadata)
        
        # Проверка local cache
        if mock_cache_service.local_cache:
            local_result = mock_cache_service.local_cache.get("file:test-id")
            assert local_result == test_metadata

    def test_invalidate_file_metadata(self, mock_cache_service):
        """Тест инвалидации метаданных на всех уровнях."""
        test_metadata = {"id": "test-id", "filename": "test.pdf"}
        
        # Установка в кеш
        mock_cache_service.set_file_metadata("test-id", test_metadata)
        
        # Инвалидация
        mock_cache_service.invalidate_file_metadata("test-id")
        
        # Проверка удаления
        result = mock_cache_service.get_file_metadata("test-id")
        assert result is None

    def test_corrupted_redis_data(self, mock_cache_service):
        """Тест обработки поврежденных данных в Redis."""
        # Mock Redis возвращает некорректный JSON
        if mock_cache_service.redis_cache:
            mock_cache_service.redis_cache._redis_client.get.return_value = "invalid json"
        
        result = mock_cache_service.get_file_metadata("test-id")
        
        # Должен вернуть None и удалить поврежденные данные
        assert result is None
