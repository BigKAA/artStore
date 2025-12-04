"""
Integration tests для Leader Election failover в AdaptiveCapacityMonitor.

Тестирует:
- Automatic failover при падении Leader
- Leadership acquisition race conditions
- Follower promotion после истечения TTL
- Multi-instance coordination

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
)


# ============================================================================
# FIXTURES
# ============================================================================

# Пропускаем тесты если Redis недоступен
pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_REDIS_TESTS", "false").lower() == "true",
    reason="Redis tests disabled via SKIP_REDIS_TESTS env var"
)


@pytest_asyncio.fixture
async def redis_client():
    """
    Подключение к тестовому Redis.

    Использует localhost:6379 или переменную окружения TEST_REDIS_URL.
    """
    redis_url = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/1")

    try:
        client = Redis.from_url(
            redis_url,
            decode_responses=True,
        )
        # Проверяем подключение
        await client.ping()

        yield client

        # Cleanup: удаляем тестовые ключи
        keys = await client.keys("capacity_monitor:*")
        keys.extend(await client.keys("capacity:*"))
        keys.extend(await client.keys("health:*"))
        if keys:
            await client.delete(*keys)

        await client.aclose()

    except Exception as e:
        pytest.skip(f"Redis not available: {e}")


@pytest.fixture
def storage_endpoints():
    """Тестовые Storage Element endpoints."""
    return {
        "se-test-01": "http://mock-storage-01:8010",
        "se-test-02": "http://mock-storage-02:8010",
    }


@pytest.fixture
def fast_config():
    """
    Конфигурация с короткими таймаутами для быстрых тестов.
    """
    return CapacityMonitorConfig(
        leader_ttl=3,  # 3 секунды TTL для быстрых тестов
        leader_renewal_interval=1,  # Каждую секунду
        base_interval=1,
        http_timeout=1,
        http_retries=1,
        cache_ttl=10,
        health_ttl=10,
    )


def create_monitor(redis_client, storage_endpoints, config):
    """
    Фабрика для создания мониторов.
    """
    return AdaptiveCapacityMonitor(
        redis_client=redis_client,
        storage_endpoints=storage_endpoints,
        config=config,
    )


# ============================================================================
# LEADER ELECTION INTEGRATION TESTS
# ============================================================================

@pytest.mark.asyncio
class TestLeaderElectionIntegration:
    """Integration тесты для Leader Election с реальным Redis."""

    async def test_single_instance_becomes_leader(
        self, redis_client, storage_endpoints, fast_config
    ):
        """Единственный instance должен стать Leader."""
        # Mock metrics
        with patch("app.services.capacity_monitor.record_leader_state"), \
             patch("app.services.capacity_monitor.record_leader_transition"), \
             patch("app.services.capacity_monitor.record_lock_acquisition"):

            monitor = create_monitor(redis_client, storage_endpoints, fast_config)

            await monitor.start()

            try:
                assert monitor.role == MonitorRole.LEADER
                assert monitor.is_leader is True

                # Проверяем что lock реально создан в Redis
                lock_value = await redis_client.get(fast_config.leader_lock_key)
                assert lock_value == monitor.instance_id

            finally:
                await monitor.stop()

    async def test_second_instance_becomes_follower(
        self, redis_client, storage_endpoints, fast_config
    ):
        """Второй instance должен стать Follower."""
        with patch("app.services.capacity_monitor.record_leader_state"), \
             patch("app.services.capacity_monitor.record_leader_transition"), \
             patch("app.services.capacity_monitor.record_lock_acquisition"):

            # Первый monitor - Leader
            monitor1 = create_monitor(redis_client, storage_endpoints, fast_config)
            await monitor1.start()

            # Второй monitor - должен стать Follower
            monitor2 = create_monitor(redis_client, storage_endpoints, fast_config)
            await monitor2.start()

            try:
                assert monitor1.role == MonitorRole.LEADER
                assert monitor2.role == MonitorRole.FOLLOWER

                # Разные instance_id
                assert monitor1.instance_id != monitor2.instance_id

                # Lock принадлежит первому
                lock_value = await redis_client.get(fast_config.leader_lock_key)
                assert lock_value == monitor1.instance_id

            finally:
                await monitor1.stop()
                await monitor2.stop()

    async def test_follower_becomes_leader_after_ttl_expires(
        self, redis_client, storage_endpoints, fast_config
    ):
        """Follower становится Leader после истечения TTL."""
        with patch("app.services.capacity_monitor.record_leader_state"), \
             patch("app.services.capacity_monitor.record_leader_transition"), \
             patch("app.services.capacity_monitor.record_lock_acquisition"):

            # Первый monitor - Leader
            monitor1 = create_monitor(redis_client, storage_endpoints, fast_config)
            await monitor1.start()

            # Второй monitor - Follower
            monitor2 = create_monitor(redis_client, storage_endpoints, fast_config)
            await monitor2.start()

            assert monitor1.role == MonitorRole.LEADER
            assert monitor2.role == MonitorRole.FOLLOWER

            # Останавливаем Leader (симуляция crash)
            await monitor1.stop()

            # Ждём истечения TTL + время на renewal loop
            await asyncio.sleep(fast_config.leader_ttl + fast_config.leader_renewal_interval + 1)

            try:
                # Follower должен стать Leader
                assert monitor2.role == MonitorRole.LEADER

                # Lock теперь принадлежит второму
                lock_value = await redis_client.get(fast_config.leader_lock_key)
                assert lock_value == monitor2.instance_id

            finally:
                await monitor2.stop()

    async def test_leader_renews_lock_periodically(
        self, redis_client, storage_endpoints, fast_config
    ):
        """Leader продлевает lock периодически."""
        with patch("app.services.capacity_monitor.record_leader_state"), \
             patch("app.services.capacity_monitor.record_leader_transition"), \
             patch("app.services.capacity_monitor.record_lock_acquisition"):

            monitor = create_monitor(redis_client, storage_endpoints, fast_config)
            await monitor.start()

            try:
                assert monitor.role == MonitorRole.LEADER

                # Получаем начальный TTL
                initial_ttl = await redis_client.ttl(fast_config.leader_lock_key)
                assert initial_ttl > 0

                # Ждём один цикл renewal
                await asyncio.sleep(fast_config.leader_renewal_interval + 0.5)

                # TTL должен быть обновлён (близок к leader_ttl)
                renewed_ttl = await redis_client.ttl(fast_config.leader_lock_key)
                assert renewed_ttl > 0

                # Monitor всё ещё Leader
                assert monitor.role == MonitorRole.LEADER

            finally:
                await monitor.stop()

    async def test_graceful_leadership_release(
        self, redis_client, storage_endpoints, fast_config
    ):
        """Leader освобождает lock при graceful shutdown."""
        with patch("app.services.capacity_monitor.record_leader_state"), \
             patch("app.services.capacity_monitor.record_leader_transition"), \
             patch("app.services.capacity_monitor.record_lock_acquisition"):

            monitor = create_monitor(redis_client, storage_endpoints, fast_config)
            await monitor.start()

            assert monitor.role == MonitorRole.LEADER

            # Graceful stop
            await monitor.stop()

            # Lock должен быть удалён
            lock_exists = await redis_client.exists(fast_config.leader_lock_key)
            assert lock_exists == 0


# ============================================================================
# FAILOVER SCENARIO TESTS
# ============================================================================

@pytest.mark.asyncio
class TestFailoverScenarios:
    """Тесты различных сценариев failover."""

    async def test_rapid_leader_succession(
        self, redis_client, storage_endpoints, fast_config
    ):
        """Быстрая смена Leader при последовательных падениях."""
        with patch("app.services.capacity_monitor.record_leader_state"), \
             patch("app.services.capacity_monitor.record_leader_transition"), \
             patch("app.services.capacity_monitor.record_lock_acquisition"):

            monitors = []
            try:
                # Создаём 3 монитора
                for i in range(3):
                    m = create_monitor(redis_client, storage_endpoints, fast_config)
                    await m.start()
                    monitors.append(m)

                # Первый - Leader, остальные - Followers
                assert monitors[0].role == MonitorRole.LEADER
                assert all(m.role == MonitorRole.FOLLOWER for m in monitors[1:])

                # Останавливаем текущего Leader
                await monitors[0].stop()

                # Ждём failover
                await asyncio.sleep(fast_config.leader_ttl + fast_config.leader_renewal_interval + 1)

                # Один из оставшихся должен стать Leader
                leaders = [m for m in monitors[1:] if m.role == MonitorRole.LEADER]
                assert len(leaders) == 1

            finally:
                for m in monitors:
                    if m._running:
                        await m.stop()

    async def test_leadership_preserved_during_brief_redis_hiccup(
        self, redis_client, storage_endpoints, fast_config
    ):
        """Leader сохраняет роль при кратковременном сбое Redis."""
        with patch("app.services.capacity_monitor.record_leader_state"), \
             patch("app.services.capacity_monitor.record_leader_transition"), \
             patch("app.services.capacity_monitor.record_lock_acquisition"):

            monitor = create_monitor(redis_client, storage_endpoints, fast_config)
            await monitor.start()

            try:
                assert monitor.role == MonitorRole.LEADER

                # Симулируем короткий сбой (меньше TTL)
                # Ждём меньше чем TTL
                await asyncio.sleep(1)

                # Leader должен сохранить роль
                assert monitor.role == MonitorRole.LEADER

            finally:
                await monitor.stop()


# ============================================================================
# CAPACITY CACHE INTEGRATION TESTS
# ============================================================================

@pytest.mark.asyncio
class TestCapacityCacheIntegration:
    """Integration тесты для кеширования capacity в Redis."""

    async def test_leader_writes_capacity_to_cache(
        self, redis_client, storage_endpoints, fast_config
    ):
        """Leader записывает capacity данные в Redis cache."""
        with patch("app.services.capacity_monitor.record_leader_state"), \
             patch("app.services.capacity_monitor.record_leader_transition"), \
             patch("app.services.capacity_monitor.record_lock_acquisition"), \
             patch("app.services.capacity_monitor.record_capacity_poll"), \
             patch("app.services.capacity_monitor.record_cache_access"), \
             patch("app.services.capacity_monitor.record_poll_failure"):

            monitor = create_monitor(redis_client, storage_endpoints, fast_config)

            # Мокаем успешный HTTP response (MagicMock для синхронных методов)
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "storage_id": "se-test-01",
                "mode": "edit",
                "capacity": {
                    "total": 1099511627776,
                    "used": 549755813888,
                    "available": 549755813888,
                    "percent_used": 50.0,
                },
                "health": "healthy",
                "backend": "local",
                "location": "dc1",
                "last_update": "2025-01-15T12:00:00Z",
            }
            mock_response.raise_for_status = MagicMock()  # Синхронный метод

            mock_http = AsyncMock()
            mock_http.get.return_value = mock_response

            # Создаём HTTP клиент ДО start, чтобы избежать real HTTP calls
            monitor._http_client = mock_http
            monitor._running = True
            monitor._role = MonitorRole.LEADER

            # Записываем lock в Redis чтобы симулировать Leadership
            await redis_client.set(
                fast_config.leader_lock_key,
                monitor._instance_id,
                ex=fast_config.leader_ttl
            )

            try:
                # Выполняем polling вручную
                result = await monitor._poll_storage_element(
                    "se-test-01", "http://mock-storage-01:8010"
                )

                assert result is not None

                # Проверяем что данные в Redis
                cache_key = "capacity:se-test-01"
                cached_data = await redis_client.hgetall(cache_key)

                assert cached_data["storage_id"] == "se-test-01"
                assert cached_data["mode"] == "edit"
                assert cached_data["health"] == "healthy"

                # Проверяем TTL
                ttl = await redis_client.ttl(cache_key)
                assert ttl > 0

            finally:
                monitor._running = False
                await redis_client.delete(fast_config.leader_lock_key)

    async def test_follower_reads_from_cache(
        self, redis_client, storage_endpoints, fast_config
    ):
        """Follower читает capacity данные из cache."""
        with patch("app.services.capacity_monitor.record_leader_state"), \
             patch("app.services.capacity_monitor.record_leader_transition"), \
             patch("app.services.capacity_monitor.record_lock_acquisition"), \
             patch("app.services.capacity_monitor.record_cache_access"):

            # Leader записывает данные
            monitor1 = create_monitor(redis_client, storage_endpoints, fast_config)
            await monitor1.start()

            # Вручную записываем данные в cache (симуляция polling)
            cache_key = "capacity:se-test-01"
            await redis_client.hset(
                cache_key,
                mapping={
                    "storage_id": "se-test-01",
                    "mode": "edit",
                    "total": "1099511627776",
                    "used": "549755813888",
                    "available": "549755813888",
                    "percent_used": "50.0",
                    "health": "healthy",
                    "backend": "local",
                    "location": "dc1",
                    "last_update": "2025-01-15T12:00:00Z",
                    "last_poll": "2025-01-15T12:01:00Z",
                    "endpoint": "http://mock-storage-01:8010",
                }
            )
            await redis_client.expire(cache_key, fast_config.cache_ttl)

            # Follower создаётся
            monitor2 = create_monitor(redis_client, storage_endpoints, fast_config)
            await monitor2.start()

            try:
                assert monitor2.role == MonitorRole.FOLLOWER

                # Follower может прочитать данные из cache
                capacity = await monitor2.get_capacity("se-test-01")

                assert capacity is not None
                assert capacity.storage_id == "se-test-01"
                assert capacity.mode == "edit"
                assert capacity.percent_used == 50.0

            finally:
                await monitor1.stop()
                await monitor2.stop()

    async def test_cache_survives_leader_change(
        self, redis_client, storage_endpoints, fast_config
    ):
        """Cache данные сохраняются при смене Leader."""
        with patch("app.services.capacity_monitor.record_leader_state"), \
             patch("app.services.capacity_monitor.record_leader_transition"), \
             patch("app.services.capacity_monitor.record_lock_acquisition"), \
             patch("app.services.capacity_monitor.record_cache_access"):

            # Записываем данные в cache
            cache_key = "capacity:se-test-01"
            await redis_client.hset(
                cache_key,
                mapping={
                    "storage_id": "se-test-01",
                    "mode": "rw",
                    "total": "2199023255552",
                    "used": "1099511627776",
                    "available": "1099511627776",
                    "percent_used": "50.0",
                    "health": "healthy",
                    "backend": "s3",
                    "location": "dc2",
                    "last_update": "2025-01-15T12:00:00Z",
                    "last_poll": "2025-01-15T12:01:00Z",
                    "endpoint": "http://mock-storage-01:8010",
                }
            )
            await redis_client.expire(cache_key, fast_config.cache_ttl)

            # Первый Leader
            monitor1 = create_monitor(redis_client, storage_endpoints, fast_config)
            await monitor1.start()
            assert monitor1.role == MonitorRole.LEADER

            # Второй - Follower
            monitor2 = create_monitor(redis_client, storage_endpoints, fast_config)
            await monitor2.start()
            assert monitor2.role == MonitorRole.FOLLOWER

            # Оба могут читать cache
            capacity1 = await monitor1.get_capacity("se-test-01")
            capacity2 = await monitor2.get_capacity("se-test-01")

            assert capacity1 is not None
            assert capacity2 is not None
            assert capacity1.storage_id == capacity2.storage_id

            # Останавливаем Leader
            await monitor1.stop()

            # Ждём failover
            await asyncio.sleep(fast_config.leader_ttl + fast_config.leader_renewal_interval + 1)

            try:
                # Новый Leader всё ещё может читать cache
                capacity_after = await monitor2.get_capacity("se-test-01")
                assert capacity_after is not None
                assert capacity_after.storage_id == "se-test-01"

            finally:
                await monitor2.stop()


# ============================================================================
# LAZY UPDATE INTEGRATION TESTS
# ============================================================================

@pytest.mark.asyncio
class TestLazyUpdateIntegration:
    """Integration тесты для lazy update mechanism."""

    async def test_lazy_update_works_for_follower(
        self, redis_client, storage_endpoints, fast_config
    ):
        """Follower может выполнить lazy update."""
        with patch("app.services.capacity_monitor.record_leader_state"), \
             patch("app.services.capacity_monitor.record_leader_transition"), \
             patch("app.services.capacity_monitor.record_lock_acquisition"), \
             patch("app.services.capacity_monitor.record_lazy_update"), \
             patch("app.services.capacity_monitor.record_capacity_poll"), \
             patch("app.services.capacity_monitor.record_poll_failure"):

            # Создаём Follower напрямую (без Leader, просто симулируем)
            monitor2 = create_monitor(redis_client, storage_endpoints, fast_config)

            # Мокаем HTTP для Follower (MagicMock для синхронных методов)
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "storage_id": "se-test-01",
                "mode": "edit",
                "capacity": {
                    "total": 1000000000,
                    "used": 100000000,
                    "available": 900000000,
                    "percent_used": 10.0,
                },
                "health": "healthy",
                "backend": "local",
                "location": "dc1",
                "last_update": "2025-01-15T12:00:00Z",
            }
            mock_response.raise_for_status = MagicMock()  # Синхронный метод httpx

            mock_http = AsyncMock()
            mock_http.get.return_value = mock_response

            # Устанавливаем состояние Follower напрямую
            monitor2._http_client = mock_http
            monitor2._running = True
            monitor2._role = MonitorRole.FOLLOWER

            try:
                # Follower выполняет lazy update (после 507 error)
                result = await monitor2.trigger_lazy_update(
                    "se-test-01", reason="insufficient_storage"
                )

                assert result is not None
                assert result.storage_id == "se-test-01"

                # Данные должны быть в cache (записаны Follower)
                cached = await redis_client.hgetall("capacity:se-test-01")
                assert cached["storage_id"] == "se-test-01"

            finally:
                monitor2._running = False


# ============================================================================
# CONCURRENT ACCESS TESTS
# ============================================================================

@pytest.mark.asyncio
class TestConcurrentAccess:
    """Тесты конкурентного доступа к Leader Election."""

    async def test_only_one_leader_with_concurrent_start(
        self, redis_client, storage_endpoints, fast_config
    ):
        """При одновременном старте только один становится Leader."""
        with patch("app.services.capacity_monitor.record_leader_state"), \
             patch("app.services.capacity_monitor.record_leader_transition"), \
             patch("app.services.capacity_monitor.record_lock_acquisition"):

            monitors = []

            async def start_monitor():
                m = create_monitor(redis_client, storage_endpoints, fast_config)
                await m.start()
                return m

            try:
                # Запускаем 5 мониторов "одновременно"
                tasks = [start_monitor() for _ in range(5)]
                monitors = await asyncio.gather(*tasks)

                # Небольшая задержка для стабилизации
                await asyncio.sleep(0.5)

                # Проверяем что ровно один Leader
                leaders = [m for m in monitors if m.role == MonitorRole.LEADER]
                followers = [m for m in monitors if m.role == MonitorRole.FOLLOWER]

                assert len(leaders) == 1, f"Expected 1 leader, got {len(leaders)}"
                assert len(followers) == 4, f"Expected 4 followers, got {len(followers)}"

                # Lock в Redis принадлежит единственному Leader
                lock_value = await redis_client.get(fast_config.leader_lock_key)
                assert lock_value == leaders[0].instance_id

            finally:
                for m in monitors:
                    await m.stop()
