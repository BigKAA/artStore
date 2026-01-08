"""
Unit tests для AdaptiveCapacityMonitor с Leader Election.

Тестирует:
- Leader Election logic (SET NX EX)
- Leader renewal и failover
- Capacity polling и caching
- Lazy update mechanism
- Metrics recording

Sprint 17: Geo-Distributed Capacity Management
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import pytest_asyncio

from redis.exceptions import RedisError

from app.services.capacity_monitor import (
    AdaptiveCapacityMonitor,
    CapacityMonitorConfig,
    StorageCapacityInfo,
    MonitorRole,
    HealthStatus,
    init_capacity_monitor,
    close_capacity_monitor,
    get_capacity_monitor,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_redis():
    """
    Mock async Redis client для unit tests.

    Имитирует поведение redis.asyncio.Redis.
    """
    redis = AsyncMock()

    # Default behavior
    redis.set = AsyncMock(return_value=True)  # Lock acquired
    redis.get = AsyncMock(return_value=None)
    redis.delete = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=True)
    redis.hset = AsyncMock(return_value=1)
    redis.hgetall = AsyncMock(return_value={})

    return redis


@pytest.fixture
def storage_endpoints():
    """
    Тестовые Storage Element endpoints.
    """
    return {
        "se-01": "http://storage-01:8010",
        "se-02": "http://storage-02:8010",
        "se-03": "http://storage-03:8010",
    }


@pytest.fixture
def monitor_config():
    """
    Конфигурация для тестов с короткими таймаутами.
    """
    return CapacityMonitorConfig(
        leader_ttl=5,  # 5 секунд для быстрых тестов
        leader_renewal_interval=2,
        base_interval=1,
        http_timeout=2,
        http_retries=1,
        cache_ttl=60,
        health_ttl=60,
    )


@pytest_asyncio.fixture
async def capacity_monitor(mock_redis, storage_endpoints, monitor_config):
    """
    Создание AdaptiveCapacityMonitor для тестов.

    Не запускает background tasks (start() не вызывается).
    """
    monitor = AdaptiveCapacityMonitor(
        redis_client=mock_redis,
        storage_endpoints=storage_endpoints,
        config=monitor_config,
    )
    yield monitor

    # Cleanup
    if monitor._running:
        await monitor.stop()


@pytest.fixture
def sample_capacity_response():
    """
    Пример ответа от Storage Element /api/v1/capacity.
    """
    return {
        "storage_id": "se-01",
        "mode": "edit",
        "capacity": {
            "total": 1099511627776,  # 1TB
            "used": 549755813888,  # 500GB
            "available": 549755813888,  # 500GB
            "percent_used": 50.0,
        },
        "health": "healthy",
        "backend": "local",
        "location": "dc1",
        "last_update": "2025-01-15T12:00:00+00:00",
    }


@pytest.fixture
def sample_capacity_info():
    """
    Пример StorageCapacityInfo для тестов.
    """
    return StorageCapacityInfo(
        storage_id="se-01",
        mode="edit",
        total=1099511627776,
        used=549755813888,
        available=549755813888,
        percent_used=50.0,
        health=HealthStatus.HEALTHY,
        backend="local",
        location="dc1",
        last_update="2025-01-15T12:00:00+00:00",
        last_poll="2025-01-15T12:01:00+00:00",
        endpoint="http://storage-01:8010",
    )


# ============================================================================
# STORAGE CAPACITY INFO TESTS
# ============================================================================

class TestStorageCapacityInfo:
    """Тесты для dataclass StorageCapacityInfo."""

    def test_to_dict_serialization(self, sample_capacity_info):
        """Тест сериализации в dict для Redis."""
        data = sample_capacity_info.to_dict()

        assert data["storage_id"] == "se-01"
        assert data["mode"] == "edit"
        assert data["total"] == "1099511627776"  # Строка для Redis
        assert data["used"] == "549755813888"
        assert data["available"] == "549755813888"
        assert data["percent_used"] == "50.0"
        assert data["health"] == "healthy"
        assert data["backend"] == "local"
        assert data["location"] == "dc1"

    def test_from_dict_deserialization(self):
        """Тест десериализации из Redis dict."""
        data = {
            "storage_id": "se-02",
            "mode": "rw",
            "total": "2199023255552",  # 2TB
            "used": "1099511627776",  # 1TB
            "available": "1099511627776",
            "percent_used": "50.0",
            "health": "healthy",
            "backend": "s3",
            "location": "dc2",
            "last_update": "2025-01-15T12:00:00+00:00",
            "last_poll": "2025-01-15T12:01:00+00:00",
            "endpoint": "http://storage-02:8010",
        }

        info = StorageCapacityInfo.from_dict(data)

        assert info.storage_id == "se-02"
        assert info.mode == "rw"
        assert info.total == 2199023255552
        assert info.used == 1099511627776
        assert info.available == 1099511627776
        assert info.percent_used == 50.0
        assert info.health == HealthStatus.HEALTHY
        assert info.backend == "s3"

    def test_is_writable_edit_mode_healthy(self, sample_capacity_info):
        """SE в режиме edit и healthy должен быть writable."""
        assert sample_capacity_info.is_writable is True

    def test_is_writable_rw_mode_healthy(self):
        """SE в режиме rw и healthy должен быть writable."""
        info = StorageCapacityInfo(
            storage_id="se-01",
            mode="rw",
            total=1000,
            used=500,
            available=500,
            percent_used=50.0,
            health=HealthStatus.HEALTHY,
            backend="local",
            location="dc1",
            last_update="",
            last_poll="",
            endpoint="",
        )
        assert info.is_writable is True

    def test_is_writable_ro_mode_not_writable(self):
        """SE в режиме ro не должен быть writable."""
        info = StorageCapacityInfo(
            storage_id="se-01",
            mode="ro",
            total=1000,
            used=500,
            available=500,
            percent_used=50.0,
            health=HealthStatus.HEALTHY,
            backend="local",
            location="dc1",
            last_update="",
            last_poll="",
            endpoint="",
        )
        assert info.is_writable is False

    def test_is_writable_unhealthy_not_writable(self):
        """SE с unhealthy status не должен быть writable."""
        info = StorageCapacityInfo(
            storage_id="se-01",
            mode="edit",
            total=1000,
            used=500,
            available=500,
            percent_used=50.0,
            health=HealthStatus.UNHEALTHY,
            backend="local",
            location="dc1",
            last_update="",
            last_poll="",
            endpoint="",
        )
        assert info.is_writable is False

    def test_can_accept_file_sufficient_space(self, sample_capacity_info):
        """SE с достаточным местом должен принять файл."""
        file_size = 100 * 1024 * 1024  # 100MB
        assert sample_capacity_info.can_accept_file(file_size) is True

    def test_can_accept_file_insufficient_space(self):
        """SE без достаточного места не должен принять файл."""
        info = StorageCapacityInfo(
            storage_id="se-01",
            mode="edit",
            total=1000,
            used=900,
            available=100,
            percent_used=90.0,
            health=HealthStatus.HEALTHY,
            backend="local",
            location="dc1",
            last_update="",
            last_poll="",
            endpoint="",
        )
        file_size = 200  # Больше чем available
        assert info.can_accept_file(file_size) is False


# ============================================================================
# LEADER ELECTION TESTS
# ============================================================================

class TestLeaderElection:
    """Тесты для Leader Election логики."""

    @pytest.mark.asyncio
    async def test_acquire_leadership_success(self, capacity_monitor, mock_redis):
        """Успешное получение Leader lock."""
        mock_redis.set.return_value = True  # Lock acquired

        result = await capacity_monitor._try_acquire_leadership()

        assert result is True
        assert capacity_monitor.role == MonitorRole.LEADER
        assert capacity_monitor.is_leader is True

        # Verify Redis call
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args.kwargs["nx"] is True  # SET NX
        assert call_args.kwargs["ex"] == capacity_monitor._config.leader_ttl

    @pytest.mark.asyncio
    async def test_acquire_leadership_failed_another_leader(
        self, capacity_monitor, mock_redis
    ):
        """Неудача получения lock - другой instance уже Leader."""
        mock_redis.set.return_value = False  # Lock NOT acquired
        mock_redis.get.return_value = "ingester-other-instance"

        result = await capacity_monitor._try_acquire_leadership()

        assert result is False
        assert capacity_monitor.role == MonitorRole.FOLLOWER
        assert capacity_monitor.is_leader is False

    @pytest.mark.asyncio
    async def test_acquire_leadership_redis_error(self, capacity_monitor, mock_redis):
        """Ошибка Redis при попытке получить lock."""
        mock_redis.set.side_effect = RedisError("Connection refused")

        result = await capacity_monitor._try_acquire_leadership()

        assert result is False
        assert capacity_monitor.role == MonitorRole.UNKNOWN

    @pytest.mark.asyncio
    async def test_renew_leadership_success(self, capacity_monitor, mock_redis):
        """Успешное продление Leader lock."""
        # Setup: monitor is leader
        capacity_monitor._role = MonitorRole.LEADER
        mock_redis.get.return_value = capacity_monitor._instance_id  # Our lock
        mock_redis.expire.return_value = True

        result = await capacity_monitor._renew_leadership()

        assert result is True
        mock_redis.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_renew_leadership_lost_to_another(self, capacity_monitor, mock_redis):
        """Leader lock захвачен другим instance."""
        # Setup: monitor thinks it's leader
        capacity_monitor._role = MonitorRole.LEADER
        mock_redis.get.return_value = "ingester-other-instance"  # Different leader

        result = await capacity_monitor._renew_leadership()

        assert result is False
        assert capacity_monitor.role == MonitorRole.FOLLOWER

    @pytest.mark.asyncio
    async def test_renew_leadership_redis_error(self, capacity_monitor, mock_redis):
        """Ошибка Redis при продлении lock."""
        capacity_monitor._role = MonitorRole.LEADER
        mock_redis.get.side_effect = RedisError("Timeout")

        result = await capacity_monitor._renew_leadership()

        assert result is False

    @pytest.mark.asyncio
    async def test_release_leadership_success(self, capacity_monitor, mock_redis):
        """Успешное освобождение Leader lock."""
        capacity_monitor._role = MonitorRole.LEADER
        mock_redis.get.return_value = capacity_monitor._instance_id  # Our lock
        mock_redis.delete.return_value = 1

        await capacity_monitor._release_leadership()

        mock_redis.delete.assert_called_once()
        assert capacity_monitor.role == MonitorRole.FOLLOWER

    @pytest.mark.asyncio
    async def test_release_leadership_not_our_lock(self, capacity_monitor, mock_redis):
        """Не удаляем чужой lock."""
        capacity_monitor._role = MonitorRole.LEADER
        mock_redis.get.return_value = "ingester-other-instance"  # Not our lock

        await capacity_monitor._release_leadership()

        # delete НЕ должен вызываться для чужого lock
        mock_redis.delete.assert_not_called()


# ============================================================================
# CAPACITY POLLING TESTS
# ============================================================================

class TestCapacityPolling:
    """Тесты для HTTP polling Storage Elements."""

    @pytest.mark.asyncio
    async def test_poll_storage_element_success(
        self, capacity_monitor, mock_redis, sample_capacity_response
    ):
        """Успешный polling одного SE."""
        # Mock HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_capacity_response
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.get.return_value = mock_response
        capacity_monitor._http_client = mock_http

        result = await capacity_monitor._poll_storage_element(
            "se-01", "http://storage-01:8010"
        )

        assert result is not None
        assert result.storage_id == "se-01"
        assert result.mode == "edit"
        assert result.health == HealthStatus.HEALTHY
        assert result.percent_used == 50.0

        # Verify cache was updated
        mock_redis.hset.assert_called()
        mock_redis.expire.assert_called()

    @pytest.mark.asyncio
    async def test_poll_storage_element_http_error(self, capacity_monitor, mock_redis):
        """HTTP ошибка при polling."""
        import httpx

        mock_http = AsyncMock()
        mock_http.get.side_effect = httpx.HTTPStatusError(
            "Not Found",
            request=MagicMock(),
            response=MagicMock(status_code=404),
        )
        capacity_monitor._http_client = mock_http

        result = await capacity_monitor._poll_storage_element(
            "se-01", "http://storage-01:8010"
        )

        assert result is None
        # SE should be marked unhealthy
        assert capacity_monitor._failure_counts.get("se-01", 0) >= 1

    @pytest.mark.asyncio
    async def test_poll_storage_element_timeout(self, capacity_monitor, mock_redis):
        """Timeout при polling."""
        import httpx

        mock_http = AsyncMock()
        mock_http.get.side_effect = httpx.TimeoutException("Timeout")
        capacity_monitor._http_client = mock_http

        result = await capacity_monitor._poll_storage_element(
            "se-01", "http://storage-01:8010"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_poll_storage_element_no_http_client(self, capacity_monitor):
        """Polling без HTTP клиента возвращает None."""
        capacity_monitor._http_client = None

        result = await capacity_monitor._poll_storage_element(
            "se-01", "http://storage-01:8010"
        )

        assert result is None


# ============================================================================
# CACHE OPERATIONS TESTS
# ============================================================================

class TestCacheOperations:
    """Тесты для операций с Redis cache."""

    @pytest.mark.asyncio
    async def test_save_capacity_to_cache(
        self, capacity_monitor, mock_redis, sample_capacity_info
    ):
        """Сохранение capacity в Redis cache."""
        await capacity_monitor._save_capacity_to_cache("se-01", sample_capacity_info)

        # Verify hset was called with correct data
        mock_redis.hset.assert_called_once()
        call_args = mock_redis.hset.call_args
        assert call_args.args[0] == "capacity:se-01"

        # Verify TTL was set
        mock_redis.expire.assert_called()

    @pytest.mark.asyncio
    async def test_save_capacity_to_cache_redis_error(
        self, capacity_monitor, mock_redis, sample_capacity_info
    ):
        """Redis ошибка при сохранении capacity."""
        mock_redis.hset.side_effect = RedisError("Connection lost")

        # Не должно выбрасывать исключение, а только логировать
        await capacity_monitor._save_capacity_to_cache("se-01", sample_capacity_info)

    @pytest.mark.asyncio
    async def test_get_capacity_success(self, capacity_monitor, mock_redis):
        """Успешное получение capacity из cache."""
        mock_redis.hgetall.return_value = {
            "storage_id": "se-01",
            "mode": "edit",
            "total": "1099511627776",
            "used": "549755813888",
            "available": "549755813888",
            "percent_used": "50.0",
            "health": "healthy",
            "backend": "local",
            "location": "dc1",
            "last_update": "2025-01-15T12:00:00+00:00",
            "last_poll": "2025-01-15T12:01:00+00:00",
            "endpoint": "http://storage-01:8010",
        }

        result = await capacity_monitor.get_capacity("se-01")

        assert result is not None
        assert result.storage_id == "se-01"
        assert result.mode == "edit"
        mock_redis.hgetall.assert_called_once_with("capacity:se-01")

    @pytest.mark.asyncio
    async def test_get_capacity_cache_miss(self, capacity_monitor, mock_redis):
        """Cache miss при получении capacity."""
        mock_redis.hgetall.return_value = {}  # Empty = cache miss

        result = await capacity_monitor.get_capacity("se-01")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_capacity_redis_error(self, capacity_monitor, mock_redis):
        """Redis ошибка при получении capacity."""
        mock_redis.hgetall.side_effect = RedisError("Connection refused")

        result = await capacity_monitor.get_capacity("se-01")

        assert result is None

    @pytest.mark.asyncio
    async def test_mark_se_unhealthy(self, capacity_monitor, mock_redis):
        """Пометка SE как unhealthy в cache."""
        await capacity_monitor._mark_se_unhealthy("se-01", "Connection timeout")

        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args.args[0] == "health:se-01"
        assert "unhealthy" in call_args.args[1]


# ============================================================================
# LAZY UPDATE TESTS
# ============================================================================

class TestLazyUpdate:
    """Тесты для lazy update mechanism."""

    @pytest.mark.asyncio
    async def test_trigger_lazy_update_success(
        self, capacity_monitor, mock_redis, sample_capacity_response
    ):
        """Успешный lazy update для конкретного SE."""
        # Mock HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_capacity_response
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.get.return_value = mock_response
        capacity_monitor._http_client = mock_http

        result = await capacity_monitor.trigger_lazy_update(
            "se-01", reason="insufficient_storage"
        )

        assert result is not None
        assert result.storage_id == "se-01"

    @pytest.mark.asyncio
    async def test_trigger_lazy_update_unknown_se(self, capacity_monitor):
        """Lazy update для неизвестного SE."""
        result = await capacity_monitor.trigger_lazy_update(
            "se-unknown", reason="test"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_trigger_lazy_update_works_as_follower(
        self, capacity_monitor, mock_redis, sample_capacity_response
    ):
        """Lazy update работает даже если instance - Follower."""
        # Setup: monitor is follower
        capacity_monitor._role = MonitorRole.FOLLOWER

        # Mock HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_capacity_response
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.get.return_value = mock_response
        capacity_monitor._http_client = mock_http

        result = await capacity_monitor.trigger_lazy_update("se-01", reason="507_error")

        # Should still work (lazy update is role-independent)
        assert result is not None


# ============================================================================
# AVAILABLE STORAGE ELEMENTS TESTS
# ============================================================================

class TestGetAvailableStorageElements:
    """Тесты для получения списка доступных SE."""

    @pytest.mark.asyncio
    async def test_get_available_storage_elements_filters_by_mode(
        self, capacity_monitor, mock_redis
    ):
        """Фильтрация по режиму SE."""
        # Mock: se-01 is edit, se-02 is ro
        async def mock_hgetall(key):
            if key == "capacity:se-01":
                return {
                    "storage_id": "se-01",
                    "mode": "edit",
                    "total": "1000",
                    "used": "500",
                    "available": "500",
                    "percent_used": "50.0",
                    "health": "healthy",
                    "backend": "local",
                    "location": "dc1",
                    "last_update": "",
                    "last_poll": "",
                    "endpoint": "",
                }
            elif key == "capacity:se-02":
                return {
                    "storage_id": "se-02",
                    "mode": "ro",  # Read-only
                    "total": "1000",
                    "used": "500",
                    "available": "500",
                    "percent_used": "50.0",
                    "health": "healthy",
                    "backend": "local",
                    "location": "dc1",
                    "last_update": "",
                    "last_poll": "",
                    "endpoint": "",
                }
            return {}

        mock_redis.hgetall = mock_hgetall

        result = await capacity_monitor.get_available_storage_elements(mode="edit")

        # Только se-01 с mode=edit
        assert len(result) == 1
        assert result[0].storage_id == "se-01"

    @pytest.mark.asyncio
    async def test_get_available_storage_elements_filters_unhealthy(
        self, capacity_monitor, mock_redis
    ):
        """Фильтрация unhealthy SE."""
        async def mock_hgetall(key):
            if key == "capacity:se-01":
                return {
                    "storage_id": "se-01",
                    "mode": "edit",
                    "total": "1000",
                    "used": "500",
                    "available": "500",
                    "percent_used": "50.0",
                    "health": "unhealthy",  # Unhealthy
                    "backend": "local",
                    "location": "dc1",
                    "last_update": "",
                    "last_poll": "",
                    "endpoint": "",
                }
            return {}

        mock_redis.hgetall = mock_hgetall

        result = await capacity_monitor.get_available_storage_elements()

        # Unhealthy SE не должны быть в результате
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_available_storage_elements_sorted_by_usage(
        self, capacity_monitor, mock_redis
    ):
        """SE отсортированы по percent_used (меньше заполненные первыми)."""
        async def mock_hgetall(key):
            if key == "capacity:se-01":
                return {
                    "storage_id": "se-01",
                    "mode": "edit",
                    "total": "1000",
                    "used": "800",
                    "available": "200",
                    "percent_used": "80.0",  # 80% used
                    "health": "healthy",
                    "backend": "local",
                    "location": "dc1",
                    "last_update": "",
                    "last_poll": "",
                    "endpoint": "",
                }
            elif key == "capacity:se-02":
                return {
                    "storage_id": "se-02",
                    "mode": "edit",
                    "total": "1000",
                    "used": "200",
                    "available": "800",
                    "percent_used": "20.0",  # 20% used
                    "health": "healthy",
                    "backend": "local",
                    "location": "dc1",
                    "last_update": "",
                    "last_poll": "",
                    "endpoint": "",
                }
            elif key == "capacity:se-03":
                return {
                    "storage_id": "se-03",
                    "mode": "edit",
                    "total": "1000",
                    "used": "500",
                    "available": "500",
                    "percent_used": "50.0",  # 50% used
                    "health": "healthy",
                    "backend": "local",
                    "location": "dc1",
                    "last_update": "",
                    "last_poll": "",
                    "endpoint": "",
                }
            return {}

        mock_redis.hgetall = mock_hgetall

        result = await capacity_monitor.get_available_storage_elements()

        # Должны быть отсортированы: se-02 (20%), se-03 (50%), se-01 (80%)
        assert len(result) == 3
        assert result[0].storage_id == "se-02"
        assert result[1].storage_id == "se-03"
        assert result[2].storage_id == "se-01"


# ============================================================================
# START/STOP LIFECYCLE TESTS
# ============================================================================

class TestMonitorLifecycle:
    """Тесты для start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_creates_http_client(self, capacity_monitor, mock_redis):
        """Start должен создать HTTP клиент."""
        assert capacity_monitor._http_client is None

        await capacity_monitor.start()

        assert capacity_monitor._http_client is not None
        assert capacity_monitor._running is True

        await capacity_monitor.stop()

    @pytest.mark.asyncio
    async def test_start_acquires_leadership(self, capacity_monitor, mock_redis):
        """Start должен попытаться получить leadership."""
        mock_redis.set.return_value = True

        await capacity_monitor.start()

        # Verify leadership was attempted
        mock_redis.set.assert_called()
        assert capacity_monitor.role in [MonitorRole.LEADER, MonitorRole.FOLLOWER]

        await capacity_monitor.stop()

    @pytest.mark.asyncio
    async def test_start_twice_no_effect(self, capacity_monitor, mock_redis):
        """Повторный start не должен иметь эффекта."""
        await capacity_monitor.start()
        await capacity_monitor.start()  # Second call

        # Should still be running, no errors
        assert capacity_monitor._running is True

        await capacity_monitor.stop()

    @pytest.mark.asyncio
    async def test_stop_releases_leadership(self, capacity_monitor, mock_redis):
        """Stop должен освободить leadership lock."""
        mock_redis.set.return_value = True
        mock_redis.get.return_value = capacity_monitor._instance_id

        await capacity_monitor.start()
        assert capacity_monitor.role == MonitorRole.LEADER

        await capacity_monitor.stop()

        # Leadership should be released
        assert capacity_monitor._running is False
        assert capacity_monitor._http_client is None

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self, capacity_monitor):
        """Stop когда monitor не запущен - no-op."""
        assert capacity_monitor._running is False

        await capacity_monitor.stop()  # Should not raise

        assert capacity_monitor._running is False


# ============================================================================
# STATUS AND METRICS TESTS
# ============================================================================

class TestStatusAndMetrics:
    """Тесты для get_status и метрик."""

    def test_get_status_initial(self, capacity_monitor):
        """Статус до запуска."""
        status = capacity_monitor.get_status()

        assert status["instance_id"] == capacity_monitor._instance_id
        assert status["role"] == "unknown"
        assert status["running"] is False
        assert status["storage_elements_count"] == 3
        assert status["leader_transitions_count"] == 0

    @pytest.mark.asyncio
    async def test_get_status_after_start(self, capacity_monitor, mock_redis):
        """Статус после запуска."""
        mock_redis.set.return_value = True

        await capacity_monitor.start()

        status = capacity_monitor.get_status()

        assert status["role"] == "leader"
        assert status["running"] is True
        assert status["leader_transitions_count"] >= 1

        await capacity_monitor.stop()

    def test_instance_id_unique(self, mock_redis, storage_endpoints, monitor_config):
        """Каждый instance должен иметь уникальный ID."""
        monitor1 = AdaptiveCapacityMonitor(
            mock_redis, storage_endpoints, monitor_config
        )
        monitor2 = AdaptiveCapacityMonitor(
            mock_redis, storage_endpoints, monitor_config
        )

        assert monitor1.instance_id != monitor2.instance_id


# ============================================================================
# GLOBAL SINGLETON TESTS
# ============================================================================

class TestGlobalSingleton:
    """Тесты для глобальных функций init/get/close."""

    @pytest.mark.asyncio
    async def test_init_and_get_capacity_monitor(self, mock_redis, storage_endpoints):
        """init_capacity_monitor создаёт и запускает monitor."""
        # Mock metrics to avoid errors
        with patch("app.services.capacity_monitor.record_leader_state"), \
             patch("app.services.capacity_monitor.record_leader_transition"), \
             patch("app.services.capacity_monitor.record_lock_acquisition"):

            mock_redis.set.return_value = True

            monitor = await init_capacity_monitor(mock_redis, storage_endpoints)

            assert monitor is not None
            assert monitor._running is True

            # get_capacity_monitor должен вернуть тот же instance
            retrieved = await get_capacity_monitor()
            assert retrieved is monitor

            await close_capacity_monitor()

    @pytest.mark.asyncio
    async def test_close_capacity_monitor(self, mock_redis, storage_endpoints):
        """close_capacity_monitor останавливает и удаляет monitor."""
        with patch("app.services.capacity_monitor.record_leader_state"), \
             patch("app.services.capacity_monitor.record_leader_transition"), \
             patch("app.services.capacity_monitor.record_lock_acquisition"):

            mock_redis.set.return_value = True
            mock_redis.get.return_value = None

            await init_capacity_monitor(mock_redis, storage_endpoints)
            await close_capacity_monitor()

            # После close get должен вернуть None
            retrieved = await get_capacity_monitor()
            assert retrieved is None


# ============================================================================
# ADAPTIVE POLLING STATE TESTS
# ============================================================================

class TestAdaptivePollingState:
    """Тесты для adaptive polling state tracking."""

    def test_record_poll_success_resets_failure_count(self, capacity_monitor):
        """Успешный poll сбрасывает failure count."""
        capacity_monitor._failure_counts["se-01"] = 3  # Had failures

        capacity_monitor._record_poll_success(
            "se-01",
            StorageCapacityInfo(
                storage_id="se-01",
                mode="edit",
                total=1000,
                used=500,
                available=500,
                percent_used=50.0,
                health=HealthStatus.HEALTHY,
                backend="local",
                location="dc1",
                last_update="",
                last_poll="",
                endpoint="",
            ),
        )

        assert capacity_monitor._failure_counts["se-01"] == 0

    def test_record_poll_failure_increments_count(self, capacity_monitor):
        """Неудачный poll увеличивает failure count."""
        capacity_monitor._failure_counts["se-01"] = 2

        capacity_monitor._record_poll_failure("se-01")

        assert capacity_monitor._failure_counts["se-01"] == 3


# ============================================================================
# SPRINT 21: SE CONFIG RELOAD TESTS
# ============================================================================

class TestReloadStorageEndpoints:
    """
    Sprint 21 Phase 1: Тесты для динамического обновления SE конфигурации.

    Проверяет:
    - reload_storage_endpoints(): обновление endpoints и priorities
    - _clear_se_cache(): очистка Redis cache для удалённых SE
    - Обработка added, removed, updated SE
    - Логирование изменений
    - Metrics recording
    """

    @pytest.mark.asyncio
    async def test_reload_storage_endpoints_added(self, capacity_monitor, mock_redis):
        """
        Тест добавления новых Storage Elements.

        Сценарий:
        - Исходные SE: se-01, se-02, se-03
        - Новые SE: se-01, se-02, se-03, se-04 (добавлен se-04)
        - Проверяем обновление _storage_endpoints и _storage_priorities
        """
        # Initial state
        initial_endpoints = {
            "se-01": "http://storage-01:8010",
            "se-02": "http://storage-02:8010",
            "se-03": "http://storage-03:8010",
        }
        initial_priorities = {"se-01": 1, "se-02": 2, "se-03": 3}

        capacity_monitor._storage_endpoints = initial_endpoints.copy()
        capacity_monitor._storage_priorities = initial_priorities.copy()

        # New configuration (added se-04)
        new_endpoints = {
            "se-01": "http://storage-01:8010",
            "se-02": "http://storage-02:8010",
            "se-03": "http://storage-03:8010",
            "se-04": "http://storage-04:8010",  # NEW
        }
        new_priorities = {"se-01": 1, "se-02": 2, "se-03": 3, "se-04": 4}

        # Reload configuration
        with patch("app.services.capacity_monitor.record_se_config_change") as mock_metric:
            await capacity_monitor.reload_storage_endpoints(new_endpoints, new_priorities)

            # Verify endpoints updated
            assert capacity_monitor._storage_endpoints == new_endpoints
            assert capacity_monitor._storage_priorities == new_priorities

            # Verify metrics recorded
            mock_metric.assert_any_call("added", count=1)

    @pytest.mark.asyncio
    async def test_reload_storage_endpoints_removed(self, capacity_monitor, mock_redis):
        """
        Тест удаления Storage Elements и очистки cache.

        Сценарий:
        - Исходные SE: se-01, se-02, se-03
        - Новые SE: se-01, se-02 (удалён se-03)
        - Проверяем удаление из _storage_endpoints и очистку Redis cache
        """
        # Initial state
        initial_endpoints = {
            "se-01": "http://storage-01:8010",
            "se-02": "http://storage-02:8010",
            "se-03": "http://storage-03:8010",
        }
        initial_priorities = {"se-01": 1, "se-02": 2, "se-03": 3}

        capacity_monitor._storage_endpoints = initial_endpoints.copy()
        capacity_monitor._storage_priorities = initial_priorities.copy()

        # New configuration (removed se-03)
        new_endpoints = {
            "se-01": "http://storage-01:8010",
            "se-02": "http://storage-02:8010",
        }
        new_priorities = {"se-01": 1, "se-02": 2}

        # Reload configuration
        with patch("app.services.capacity_monitor.record_se_config_change") as mock_metric:
            await capacity_monitor.reload_storage_endpoints(new_endpoints, new_priorities)

            # Verify endpoints updated
            assert capacity_monitor._storage_endpoints == new_endpoints
            assert capacity_monitor._storage_priorities == new_priorities
            assert "se-03" not in capacity_monitor._storage_endpoints

            # Verify Redis cache cleared for removed SE
            mock_redis.delete.assert_any_call("capacity:se-03")
            mock_redis.delete.assert_any_call("health:se-03")
            mock_redis.zrem.assert_any_call("capacity:edit:available", "se-03")
            mock_redis.zrem.assert_any_call("capacity:rw:available", "se-03")

            # Verify metrics recorded
            mock_metric.assert_any_call("removed", count=1)

    @pytest.mark.asyncio
    async def test_reload_storage_endpoints_updated(self, capacity_monitor, mock_redis):
        """
        Тест обновления endpoint URL и priority.

        Сценарий:
        - Исходные SE: se-01 (http://storage-01:8010, priority=1)
        - Новые SE: se-01 (http://storage-01-new:8010, priority=5)
        - Проверяем обновление endpoint и priority
        """
        # Initial state
        initial_endpoints = {
            "se-01": "http://storage-01:8010",
            "se-02": "http://storage-02:8010",
        }
        initial_priorities = {"se-01": 1, "se-02": 2}

        capacity_monitor._storage_endpoints = initial_endpoints.copy()
        capacity_monitor._storage_priorities = initial_priorities.copy()

        # New configuration (updated se-01 endpoint and priority)
        new_endpoints = {
            "se-01": "http://storage-01-new:8010",  # UPDATED URL
            "se-02": "http://storage-02:8010",
        }
        new_priorities = {"se-01": 5, "se-02": 2}  # UPDATED priority

        # Reload configuration
        with patch("app.services.capacity_monitor.record_se_config_change") as mock_metric:
            await capacity_monitor.reload_storage_endpoints(new_endpoints, new_priorities)

            # Verify endpoints updated
            assert capacity_monitor._storage_endpoints["se-01"] == "http://storage-01-new:8010"
            assert capacity_monitor._storage_priorities["se-01"] == 5

            # Verify metrics recorded (updated counts for endpoint or priority changes)
            mock_metric.assert_any_call("updated", count=1)

    @pytest.mark.asyncio
    async def test_reload_storage_endpoints_empty_data(self, capacity_monitor, mock_redis):
        """
        Тест обработки пустых данных (все SE удалены).

        Edge case:
        - Новые endpoints и priorities пусты
        - Все SE должны быть удалены и cache очищен
        """
        # Initial state
        initial_endpoints = {
            "se-01": "http://storage-01:8010",
            "se-02": "http://storage-02:8010",
        }
        initial_priorities = {"se-01": 1, "se-02": 2}

        capacity_monitor._storage_endpoints = initial_endpoints.copy()
        capacity_monitor._storage_priorities = initial_priorities.copy()

        # New configuration (empty - all SE removed)
        new_endpoints = {}
        new_priorities = {}

        # Reload configuration
        with patch("app.services.capacity_monitor.record_se_config_change") as mock_metric:
            await capacity_monitor.reload_storage_endpoints(new_endpoints, new_priorities)

            # Verify all endpoints removed
            assert capacity_monitor._storage_endpoints == {}
            assert capacity_monitor._storage_priorities == {}

            # Verify Redis cache cleared for all removed SE
            assert mock_redis.delete.call_count >= 4  # 2 SE × (capacity + health)
            assert mock_redis.zrem.call_count >= 4  # 2 SE × (edit + rw)

            # Verify metrics recorded
            mock_metric.assert_any_call("removed", count=2)

    @pytest.mark.asyncio
    async def test_clear_se_cache_success(self, capacity_monitor, mock_redis):
        """
        Тест успешной очистки Redis cache для удалённого SE.

        Проверяет:
        - Удаление capacity cache (capacity:se_id)
        - Удаление health cache (health:se_id)
        - Удаление из sorted sets (capacity:edit:available, capacity:rw:available)
        """
        # Mock successful Redis operations
        mock_redis.delete = AsyncMock(return_value=1)
        mock_redis.zrem = AsyncMock(return_value=1)

        # Clear cache for se-01
        await capacity_monitor._clear_se_cache("se-01")

        # Verify Redis operations called
        mock_redis.delete.assert_any_call("capacity:se-01")
        mock_redis.delete.assert_any_call("health:se-01")
        mock_redis.zrem.assert_any_call("capacity:edit:available", "se-01")
        mock_redis.zrem.assert_any_call("capacity:rw:available", "se-01")

    @pytest.mark.asyncio
    async def test_clear_se_cache_redis_error(self, capacity_monitor, mock_redis):
        """
        Тест обработки Redis ошибок при очистке cache.

        Сценарий:
        - Redis.delete() выбрасывает RedisError
        - Метод должен логировать warning и продолжить работу (graceful degradation)
        """
        # Mock Redis error
        mock_redis.delete = AsyncMock(side_effect=RedisError("Connection lost"))
        mock_redis.zrem = AsyncMock(return_value=1)

        # Clear cache should not raise exception
        try:
            await capacity_monitor._clear_se_cache("se-01")
        except RedisError:
            pytest.fail("_clear_se_cache() should handle RedisError gracefully")

        # Verify Redis delete was attempted
        mock_redis.delete.assert_called()

    @pytest.mark.asyncio
    async def test_reload_storage_endpoints_complex_scenario(self, capacity_monitor, mock_redis):
        """
        Тест комплексного сценария: одновременно added, removed, updated SE.

        Сценарий:
        - Исходные SE: se-01, se-02, se-03
        - Новые SE: se-01 (updated endpoint), se-02, se-04 (added), se-05 (added)
        - Удалён: se-03
        - Обновлён: se-01 (endpoint и priority)
        - Добавлены: se-04, se-05
        """
        # Initial state
        initial_endpoints = {
            "se-01": "http://storage-01:8010",
            "se-02": "http://storage-02:8010",
            "se-03": "http://storage-03:8010",
        }
        initial_priorities = {"se-01": 1, "se-02": 2, "se-03": 3}

        capacity_monitor._storage_endpoints = initial_endpoints.copy()
        capacity_monitor._storage_priorities = initial_priorities.copy()

        # New configuration (complex changes)
        new_endpoints = {
            "se-01": "http://storage-01-new:8010",  # UPDATED
            "se-02": "http://storage-02:8010",  # NO CHANGE
            "se-04": "http://storage-04:8010",  # ADDED
            "se-05": "http://storage-05:8010",  # ADDED
        }
        new_priorities = {
            "se-01": 10,  # UPDATED priority
            "se-02": 2,
            "se-04": 4,
            "se-05": 5,
        }

        # Reload configuration
        with patch("app.services.capacity_monitor.record_se_config_change") as mock_metric:
            await capacity_monitor.reload_storage_endpoints(new_endpoints, new_priorities)

            # Verify final state
            assert capacity_monitor._storage_endpoints == new_endpoints
            assert capacity_monitor._storage_priorities == new_priorities

            # Verify removed SE cache cleared
            mock_redis.delete.assert_any_call("capacity:se-03")
            mock_redis.delete.assert_any_call("health:se-03")

            # Verify metrics recorded
            # added=2 (se-04, se-05), removed=1 (se-03), updated=1 (se-01)
            mock_metric.assert_any_call("added", count=2)
            mock_metric.assert_any_call("removed", count=1)
            mock_metric.assert_any_call("updated", count=1)
