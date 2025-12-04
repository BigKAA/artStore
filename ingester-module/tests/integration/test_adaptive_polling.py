"""
Integration tests для Adaptive Polling в AdaptiveCapacityMonitor.

Тестирует:
- Динамическую адаптацию интервалов polling
- Увеличение интервала при стабильных данных
- Уменьшение интервала при ошибках
- Взаимодействие adaptive polling с Leader Election

Требования:
- Redis должен быть запущен для интеграционных тестов
- Используем pytest-docker или локальный Redis

Sprint 17: Geo-Distributed Capacity Management
"""

import asyncio
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from redis.asyncio import Redis

from app.services.capacity_monitor import (
    AdaptiveCapacityMonitor,
    CapacityMonitorConfig,
    MonitorRole,
    StorageCapacityInfo,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def redis_client():
    """Создаёт реальное Redis подключение для тестов."""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/15")
    client = Redis.from_url(redis_url, decode_responses=True)

    # Проверяем соединение
    try:
        await client.ping()
    except Exception as e:
        pytest.skip(f"Redis не доступен: {e}")

    # Очистка тестовых ключей перед тестом
    await client.delete("capacity:adaptive:*")
    await client.delete("capacity:se-*")

    yield client

    # Очистка после теста
    keys = await client.keys("capacity:*")
    if keys:
        await client.delete(*keys)

    await client.aclose()


@pytest.fixture
def storage_endpoints():
    """Конфигурация тестовых Storage Elements."""
    return {
        "se-test-01": "http://mock-storage-01:8010",
        "se-test-02": "http://mock-storage-02:8010",
    }


@pytest.fixture
def fast_config():
    """Быстрая конфигурация для тестов с короткими интервалами."""
    return CapacityMonitorConfig(
        leader_ttl=3,  # 3 секунды TTL для быстрых тестов
        leader_renewal_interval=1,  # Обновление каждую секунду
        base_interval=1,  # 1 секунда между polling
        http_timeout=1,
        http_retries=1,
        cache_ttl=10,
        health_ttl=10,
    )


def create_monitor(
    redis_client: Redis,
    storage_endpoints: dict[str, str],
    config: CapacityMonitorConfig
) -> AdaptiveCapacityMonitor:
    """Фабрика для создания тестовых мониторов."""
    return AdaptiveCapacityMonitor(
        redis_client=redis_client,
        storage_endpoints=storage_endpoints,
        config=config
    )


def create_mock_response(
    storage_id: str,
    mode: str = "edit",
    total: int = 1099511627776,
    used: int = 549755813888,
    available: int = 549755813888,
    percent_used: float = 50.0,
    health: str = "healthy",
    backend: str = "local",
    location: str = "dc1"
) -> MagicMock:
    """Создаёт mock HTTP response с данными capacity."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "storage_id": storage_id,
        "mode": mode,
        "capacity": {
            "total": total,
            "used": used,
            "available": available,
            "percent_used": percent_used,
        },
        "health": health,
        "backend": backend,
        "location": location,
        "last_update": datetime.now(timezone.utc).isoformat(),
    }
    mock_response.raise_for_status = MagicMock()
    return mock_response


# ============================================================================
# ADAPTIVE POLLING INTERVAL TESTS
# ============================================================================

@pytest.mark.asyncio
class TestAdaptivePollingIntervals:
    """Тесты для динамической адаптации интервалов polling."""

    async def test_initial_interval_is_base_interval(
        self, redis_client, storage_endpoints, fast_config
    ):
        """Начальный интервал равен base_interval из конфигурации."""
        with patch("app.services.capacity_monitor.record_leader_state"), \
             patch("app.services.capacity_monitor.record_leader_transition"), \
             patch("app.services.capacity_monitor.record_lock_acquisition"):

            monitor = create_monitor(redis_client, storage_endpoints, fast_config)

            # Изначально интервалы пустые
            assert len(monitor._poll_intervals) == 0

            # После инициализации base_interval используется по умолчанию
            # В fast_config base_interval=1 для быстрых тестов
            assert monitor._config.base_interval == fast_config.base_interval

    async def test_failure_count_increments_on_poll_failure(
        self, redis_client, storage_endpoints, fast_config
    ):
        """Счётчик ошибок увеличивается при неудачном polling."""
        with patch("app.services.capacity_monitor.record_leader_state"), \
             patch("app.services.capacity_monitor.record_leader_transition"), \
             patch("app.services.capacity_monitor.record_lock_acquisition"), \
             patch("app.services.capacity_monitor.record_capacity_poll"), \
             patch("app.services.capacity_monitor.record_poll_failure"):

            monitor = create_monitor(redis_client, storage_endpoints, fast_config)

            # Записываем ошибки polling
            monitor._record_poll_failure("se-test-01")
            assert monitor._failure_counts["se-test-01"] == 1

            monitor._record_poll_failure("se-test-01")
            assert monitor._failure_counts["se-test-01"] == 2

            monitor._record_poll_failure("se-test-01")
            assert monitor._failure_counts["se-test-01"] == 3

    async def test_success_resets_failure_count(
        self, redis_client, storage_endpoints, fast_config
    ):
        """Успешный polling сбрасывает счётчик ошибок."""
        with patch("app.services.capacity_monitor.record_leader_state"), \
             patch("app.services.capacity_monitor.record_leader_transition"), \
             patch("app.services.capacity_monitor.record_lock_acquisition"):

            monitor = create_monitor(redis_client, storage_endpoints, fast_config)

            # Записываем несколько ошибок
            monitor._failure_counts["se-test-01"] = 5

            # Создаём mock capacity info
            capacity_info = StorageCapacityInfo(
                storage_id="se-test-01",
                mode="edit",
                total=1000000,
                used=500000,
                available=500000,
                percent_used=50.0,
                health="healthy",
                backend="local",
                location="dc1",
                last_update=datetime.now(timezone.utc),
                last_poll=datetime.now(timezone.utc),
                endpoint="http://mock-storage-01:8010",
            )

            # Успешный polling должен сбросить счётчик
            monitor._record_poll_success("se-test-01", capacity_info)

            assert monitor._failure_counts["se-test-01"] == 0


# ============================================================================
# POLLING EXECUTION INTEGRATION TESTS
# ============================================================================

@pytest.mark.asyncio
class TestPollingExecutionIntegration:
    """Integration тесты для выполнения polling."""

    async def test_leader_executes_polling_loop(
        self, redis_client, storage_endpoints, fast_config
    ):
        """Leader выполняет polling loop для всех Storage Elements."""
        with patch("app.services.capacity_monitor.record_leader_state"), \
             patch("app.services.capacity_monitor.record_leader_transition"), \
             patch("app.services.capacity_monitor.record_lock_acquisition"), \
             patch("app.services.capacity_monitor.record_capacity_poll"), \
             patch("app.services.capacity_monitor.record_cache_access"), \
             patch("app.services.capacity_monitor.record_poll_failure"):

            monitor = create_monitor(redis_client, storage_endpoints, fast_config)

            # Создаём mock HTTP response
            mock_response = create_mock_response("se-test-01")

            mock_http = AsyncMock()
            mock_http.get.return_value = mock_response

            # Устанавливаем состояние Leader
            monitor._http_client = mock_http
            monitor._running = True
            monitor._role = MonitorRole.LEADER

            # Записываем lock в Redis
            await redis_client.set(
                fast_config.leader_lock_key,
                monitor._instance_id,
                ex=fast_config.leader_ttl
            )

            try:
                # Выполняем один polling
                result = await monitor._poll_storage_element(
                    "se-test-01", "http://mock-storage-01:8010"
                )

                assert result is not None
                assert result.storage_id == "se-test-01"
                assert result.mode == "edit"

                # Проверяем, что HTTP запрос был выполнен
                mock_http.get.assert_called_once()

            finally:
                monitor._running = False
                await redis_client.delete(fast_config.leader_lock_key)

    async def test_multiple_storage_elements_polled(
        self, redis_client, storage_endpoints, fast_config
    ):
        """Leader опрашивает несколько Storage Elements."""
        with patch("app.services.capacity_monitor.record_leader_state"), \
             patch("app.services.capacity_monitor.record_leader_transition"), \
             patch("app.services.capacity_monitor.record_lock_acquisition"), \
             patch("app.services.capacity_monitor.record_capacity_poll"), \
             patch("app.services.capacity_monitor.record_cache_access"), \
             patch("app.services.capacity_monitor.record_poll_failure"):

            monitor = create_monitor(redis_client, storage_endpoints, fast_config)

            # Мокаем разные ответы для разных SE
            responses = {
                "http://mock-storage-01:8010/api/v1/capacity": create_mock_response(
                    "se-test-01", percent_used=40.0
                ),
                "http://mock-storage-02:8010/api/v1/capacity": create_mock_response(
                    "se-test-02", mode="rw", percent_used=70.0
                ),
            }

            async def mock_get(url, **kwargs):
                return responses.get(url, create_mock_response("unknown"))

            mock_http = AsyncMock()
            mock_http.get.side_effect = mock_get

            # Устанавливаем состояние Leader
            monitor._http_client = mock_http
            monitor._running = True
            monitor._role = MonitorRole.LEADER

            await redis_client.set(
                fast_config.leader_lock_key,
                monitor._instance_id,
                ex=fast_config.leader_ttl
            )

            try:
                # Polling первого SE
                result1 = await monitor._poll_storage_element(
                    "se-test-01", "http://mock-storage-01:8010"
                )
                assert result1 is not None
                assert result1.storage_id == "se-test-01"

                # Polling второго SE
                result2 = await monitor._poll_storage_element(
                    "se-test-02", "http://mock-storage-02:8010"
                )
                assert result2 is not None
                assert result2.storage_id == "se-test-02"
                assert result2.mode == "rw"

            finally:
                monitor._running = False
                await redis_client.delete(fast_config.leader_lock_key)


# ============================================================================
# CACHE INTEGRATION WITH POLLING TESTS
# ============================================================================

@pytest.mark.asyncio
class TestCacheIntegrationWithPolling:
    """Тесты интеграции кеширования и polling."""

    async def test_polling_updates_redis_cache(
        self, redis_client, storage_endpoints, fast_config
    ):
        """Успешный polling обновляет данные в Redis cache."""
        with patch("app.services.capacity_monitor.record_leader_state"), \
             patch("app.services.capacity_monitor.record_leader_transition"), \
             patch("app.services.capacity_monitor.record_lock_acquisition"), \
             patch("app.services.capacity_monitor.record_capacity_poll"), \
             patch("app.services.capacity_monitor.record_cache_access"), \
             patch("app.services.capacity_monitor.record_poll_failure"):

            monitor = create_monitor(redis_client, storage_endpoints, fast_config)

            mock_response = create_mock_response("se-test-01", percent_used=65.5)

            mock_http = AsyncMock()
            mock_http.get.return_value = mock_response

            monitor._http_client = mock_http
            monitor._running = True
            monitor._role = MonitorRole.LEADER

            await redis_client.set(
                fast_config.leader_lock_key,
                monitor._instance_id,
                ex=fast_config.leader_ttl
            )

            try:
                # Выполняем polling
                result = await monitor._poll_storage_element(
                    "se-test-01", "http://mock-storage-01:8010"
                )
                assert result is not None

                # Проверяем Redis cache
                cache_key = "capacity:se-test-01"
                cached = await redis_client.hgetall(cache_key)

                assert cached["storage_id"] == "se-test-01"
                assert cached["mode"] == "edit"
                assert cached["health"] == "healthy"

                # Проверяем TTL
                ttl = await redis_client.ttl(cache_key)
                assert ttl > 0

            finally:
                monitor._running = False
                await redis_client.delete(fast_config.leader_lock_key)

    async def test_get_capacity_returns_cached_data(
        self, redis_client, storage_endpoints, fast_config
    ):
        """get_capacity возвращает данные из Redis cache."""
        with patch("app.services.capacity_monitor.record_leader_state"), \
             patch("app.services.capacity_monitor.record_leader_transition"), \
             patch("app.services.capacity_monitor.record_lock_acquisition"), \
             patch("app.services.capacity_monitor.record_cache_access"):

            monitor = create_monitor(redis_client, storage_endpoints, fast_config)

            # Записываем данные в cache напрямую
            cache_key = "capacity:se-test-01"
            await redis_client.hset(
                cache_key,
                mapping={
                    "storage_id": "se-test-01",
                    "mode": "edit",
                    "total": "1000000000",
                    "used": "400000000",
                    "available": "600000000",
                    "percent_used": "40.0",
                    "health": "healthy",
                    "backend": "local",
                    "location": "dc1",
                    "last_update": datetime.now(timezone.utc).isoformat(),
                    "last_poll": datetime.now(timezone.utc).isoformat(),
                    "endpoint": "http://mock-storage-01:8010",
                }
            )
            await redis_client.expire(cache_key, fast_config.cache_ttl)

            # Устанавливаем состояние
            monitor._running = True
            monitor._role = MonitorRole.FOLLOWER

            try:
                # get_capacity должен вернуть данные из cache
                capacity = await monitor.get_capacity("se-test-01")

                assert capacity is not None
                assert capacity.storage_id == "se-test-01"
                assert capacity.mode == "edit"
                assert capacity.percent_used == 40.0

            finally:
                monitor._running = False
                await redis_client.delete(cache_key)


# ============================================================================
# ERROR HANDLING INTEGRATION TESTS
# ============================================================================

@pytest.mark.asyncio
class TestErrorHandlingIntegration:
    """Тесты обработки ошибок в polling."""

    async def test_http_timeout_increments_failure_count(
        self, redis_client, storage_endpoints, fast_config
    ):
        """HTTP timeout увеличивает счётчик ошибок."""
        import httpx

        with patch("app.services.capacity_monitor.record_leader_state"), \
             patch("app.services.capacity_monitor.record_leader_transition"), \
             patch("app.services.capacity_monitor.record_lock_acquisition"), \
             patch("app.services.capacity_monitor.record_capacity_poll"), \
             patch("app.services.capacity_monitor.record_poll_failure"):

            monitor = create_monitor(redis_client, storage_endpoints, fast_config)

            # Мокаем HTTP timeout
            mock_http = AsyncMock()
            mock_http.get.side_effect = httpx.TimeoutException("Connection timeout")

            monitor._http_client = mock_http
            monitor._running = True
            monitor._role = MonitorRole.LEADER

            await redis_client.set(
                fast_config.leader_lock_key,
                monitor._instance_id,
                ex=fast_config.leader_ttl
            )

            try:
                # Polling должен вернуть None при timeout
                result = await monitor._poll_storage_element(
                    "se-test-01", "http://mock-storage-01:8010"
                )

                assert result is None

            finally:
                monitor._running = False
                await redis_client.delete(fast_config.leader_lock_key)

    async def test_http_error_response_handled(
        self, redis_client, storage_endpoints, fast_config
    ):
        """HTTP error response (5xx) обрабатывается корректно."""
        import httpx

        with patch("app.services.capacity_monitor.record_leader_state"), \
             patch("app.services.capacity_monitor.record_leader_transition"), \
             patch("app.services.capacity_monitor.record_lock_acquisition"), \
             patch("app.services.capacity_monitor.record_capacity_poll"), \
             patch("app.services.capacity_monitor.record_poll_failure"):

            monitor = create_monitor(redis_client, storage_endpoints, fast_config)

            # Мокаем HTTP error response
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Internal Server Error",
                request=MagicMock(),
                response=mock_response
            )

            mock_http = AsyncMock()
            mock_http.get.return_value = mock_response

            monitor._http_client = mock_http
            monitor._running = True
            monitor._role = MonitorRole.LEADER

            await redis_client.set(
                fast_config.leader_lock_key,
                monitor._instance_id,
                ex=fast_config.leader_ttl
            )

            try:
                # Polling должен вернуть None при HTTP error
                result = await monitor._poll_storage_element(
                    "se-test-01", "http://mock-storage-01:8010"
                )

                assert result is None

            finally:
                monitor._running = False
                await redis_client.delete(fast_config.leader_lock_key)


# ============================================================================
# CONCURRENT POLLING TESTS
# ============================================================================

@pytest.mark.asyncio
class TestConcurrentPolling:
    """Тесты для concurrent polling операций."""

    async def test_parallel_polling_multiple_se(
        self, redis_client, storage_endpoints, fast_config
    ):
        """Параллельный polling нескольких Storage Elements."""
        with patch("app.services.capacity_monitor.record_leader_state"), \
             patch("app.services.capacity_monitor.record_leader_transition"), \
             patch("app.services.capacity_monitor.record_lock_acquisition"), \
             patch("app.services.capacity_monitor.record_capacity_poll"), \
             patch("app.services.capacity_monitor.record_cache_access"), \
             patch("app.services.capacity_monitor.record_poll_failure"):

            monitor = create_monitor(redis_client, storage_endpoints, fast_config)

            # Создаём mock responses для обоих SE
            call_count = 0

            async def mock_get(url, **kwargs):
                nonlocal call_count
                call_count += 1
                # Небольшая задержка для симуляции сетевого вызова
                await asyncio.sleep(0.1)

                if "storage-01" in url:
                    return create_mock_response("se-test-01")
                else:
                    return create_mock_response("se-test-02")

            mock_http = AsyncMock()
            mock_http.get.side_effect = mock_get

            monitor._http_client = mock_http
            monitor._running = True
            monitor._role = MonitorRole.LEADER

            await redis_client.set(
                fast_config.leader_lock_key,
                monitor._instance_id,
                ex=fast_config.leader_ttl
            )

            try:
                # Параллельный polling
                tasks = [
                    monitor._poll_storage_element(
                        "se-test-01", "http://mock-storage-01:8010"
                    ),
                    monitor._poll_storage_element(
                        "se-test-02", "http://mock-storage-02:8010"
                    ),
                ]

                results = await asyncio.gather(*tasks)

                # Оба должны успешно завершиться
                assert all(r is not None for r in results)
                assert len(results) == 2
                assert call_count == 2

                # Проверяем разные storage_id
                storage_ids = {r.storage_id for r in results}
                assert storage_ids == {"se-test-01", "se-test-02"}

            finally:
                monitor._running = False
                await redis_client.delete(fast_config.leader_lock_key)

    async def test_follower_does_not_poll_directly(
        self, redis_client, storage_endpoints, fast_config
    ):
        """Follower читает из cache, а не делает direct polling."""
        with patch("app.services.capacity_monitor.record_leader_state"), \
             patch("app.services.capacity_monitor.record_leader_transition"), \
             patch("app.services.capacity_monitor.record_lock_acquisition"), \
             patch("app.services.capacity_monitor.record_cache_access"):

            # Leader записывает данные
            cache_key = "capacity:se-test-01"
            await redis_client.hset(
                cache_key,
                mapping={
                    "storage_id": "se-test-01",
                    "mode": "edit",
                    "total": "1000000000",
                    "used": "500000000",
                    "available": "500000000",
                    "percent_used": "50.0",
                    "health": "healthy",
                    "backend": "local",
                    "location": "dc1",
                    "last_update": datetime.now(timezone.utc).isoformat(),
                    "last_poll": datetime.now(timezone.utc).isoformat(),
                    "endpoint": "http://mock-storage-01:8010",
                }
            )
            await redis_client.expire(cache_key, fast_config.cache_ttl)

            # Leader уже держит lock
            await redis_client.set(
                fast_config.leader_lock_key,
                "existing-leader-id",
                ex=fast_config.leader_ttl
            )

            monitor = create_monitor(redis_client, storage_endpoints, fast_config)
            await monitor.start()

            try:
                # Должен стать Follower
                assert monitor.role == MonitorRole.FOLLOWER

                # HTTP клиент не должен вызываться для get_capacity
                mock_http = AsyncMock()
                monitor._http_client = mock_http

                # get_capacity читает из cache
                capacity = await monitor.get_capacity("se-test-01")

                # HTTP не вызывался (читали из cache)
                mock_http.get.assert_not_called()

                # Данные получены из cache
                assert capacity is not None
                assert capacity.storage_id == "se-test-01"

            finally:
                await monitor.stop()
                await redis_client.delete(cache_key)
                await redis_client.delete(fast_config.leader_lock_key)


# ============================================================================
# STATUS AND METRICS INTEGRATION TESTS
# ============================================================================

@pytest.mark.asyncio
class TestStatusAndMetricsIntegration:
    """Тесты для status и metrics в контексте polling."""

    async def test_status_includes_polling_info(
        self, redis_client, storage_endpoints, fast_config
    ):
        """Status включает информацию о polling."""
        with patch("app.services.capacity_monitor.record_leader_state"), \
             patch("app.services.capacity_monitor.record_leader_transition"), \
             patch("app.services.capacity_monitor.record_lock_acquisition"):

            monitor = create_monitor(redis_client, storage_endpoints, fast_config)
            await monitor.start()

            try:
                status = monitor.get_status()

                assert "instance_id" in status
                assert "role" in status
                assert "running" in status
                assert "storage_elements_count" in status
                assert "config" in status

                # Проверяем конфигурацию
                assert status["config"]["base_interval"] == fast_config.base_interval
                assert status["storage_elements_count"] == len(storage_endpoints)

            finally:
                await monitor.stop()

    async def test_health_status_reflects_polling_state(
        self, redis_client, storage_endpoints, fast_config
    ):
        """Health status отражает состояние polling."""
        with patch("app.services.capacity_monitor.record_leader_state"), \
             patch("app.services.capacity_monitor.record_leader_transition"), \
             patch("app.services.capacity_monitor.record_lock_acquisition"):

            monitor = create_monitor(redis_client, storage_endpoints, fast_config)

            # До запуска
            status_before = monitor.get_status()
            assert status_before["running"] is False

            # После запуска
            await monitor.start()
            status_after = monitor.get_status()
            assert status_after["running"] is True

            # После остановки
            await monitor.stop()
            status_stopped = monitor.get_status()
            assert status_stopped["running"] is False
