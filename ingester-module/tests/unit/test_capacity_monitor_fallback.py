"""
Unit тесты для fallback механизма в AdaptiveCapacityMonitor.

Sprint 17 Extension: Runtime Fallback для Capacity Метрик.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from redis.exceptions import RedisError

from app.services.capacity_monitor import (
    AdaptiveCapacityMonitor,
    StorageCapacityInfo,
    HealthStatus,
    CapacityMonitorConfig
)


@pytest.mark.asyncio
async def test_get_capacity_fallback_on_redis_error():
    """Тест fallback на Admin Module API при Redis failure."""
    # Setup
    redis_client = AsyncMock()
    redis_client.hgetall = AsyncMock(side_effect=RedisError("Connection refused"))

    admin_client = AsyncMock()
    admin_client.get_storage_element_capacity = AsyncMock(
        return_value=StorageCapacityInfo(
            storage_id="se-01",
            mode="rw",
            total=10737418240,
            used=5368709120,
            available=5368709120,
            percent_used=50.0,
            health=HealthStatus.HEALTHY,
            backend="local",
            location="dc1",
            last_update="2026-01-16T10:00:00Z",
            last_poll="2026-01-16T10:00:00Z",
            endpoint="http://localhost:8010"
        )
    )

    monitor = AdaptiveCapacityMonitor(
        redis_client=redis_client,
        storage_endpoints={"se-01": "http://localhost:8010"},
        config=CapacityMonitorConfig(),
        admin_client=admin_client
    )

    # Execute
    capacity = await monitor.get_capacity("se-01")

    # Assert
    assert capacity is not None
    assert capacity.storage_id == "se-01"
    assert capacity.total == 10737418240
    assert capacity.used == 5368709120
    assert capacity.percent_used == 50.0
    assert capacity.health == HealthStatus.HEALTHY

    # Verify fallback был использован
    admin_client.get_storage_element_capacity.assert_called_once_with("se-01")


@pytest.mark.asyncio
async def test_get_capacity_no_fallback_without_admin_client():
    """Тест что без admin_client fallback не работает."""
    # Setup
    redis_client = AsyncMock()
    redis_client.hgetall = AsyncMock(side_effect=RedisError("Connection refused"))

    monitor = AdaptiveCapacityMonitor(
        redis_client=redis_client,
        storage_endpoints={"se-01": "http://localhost:8010"},
        config=CapacityMonitorConfig(),
        admin_client=None  # Без admin_client
    )

    # Execute
    capacity = await monitor.get_capacity("se-01")

    # Assert
    assert capacity is None


@pytest.mark.asyncio
async def test_get_capacity_fallback_se_not_found():
    """Тест fallback когда SE не найден в Admin Module."""
    # Setup
    redis_client = AsyncMock()
    redis_client.hgetall = AsyncMock(side_effect=RedisError("Connection refused"))

    admin_client = AsyncMock()
    admin_client.get_storage_element_capacity = AsyncMock(return_value=None)  # SE not found

    monitor = AdaptiveCapacityMonitor(
        redis_client=redis_client,
        storage_endpoints={"se-01": "http://localhost:8010"},
        config=CapacityMonitorConfig(),
        admin_client=admin_client
    )

    # Execute
    capacity = await monitor.get_capacity("se-01")

    # Assert
    assert capacity is None
    admin_client.get_storage_element_capacity.assert_called_once_with("se-01")


@pytest.mark.asyncio
async def test_get_capacity_fallback_admin_client_error():
    """Тест fallback когда Admin Module API возвращает ошибку."""
    # Setup
    redis_client = AsyncMock()
    redis_client.hgetall = AsyncMock(side_effect=RedisError("Connection refused"))

    admin_client = AsyncMock()
    from app.services.admin_client import AdminClientError
    admin_client.get_storage_element_capacity = AsyncMock(
        side_effect=AdminClientError("Admin Module unavailable")
    )

    monitor = AdaptiveCapacityMonitor(
        redis_client=redis_client,
        storage_endpoints={"se-01": "http://localhost:8010"},
        config=CapacityMonitorConfig(),
        admin_client=admin_client
    )

    # Execute
    capacity = await monitor.get_capacity("se-01")

    # Assert
    assert capacity is None
    admin_client.get_storage_element_capacity.assert_called_once_with("se-01")


@pytest.mark.asyncio
async def test_get_capacity_redis_success_no_fallback():
    """Тест что fallback НЕ используется когда Redis работает."""
    # Setup
    redis_client = AsyncMock()
    redis_client.hgetall = AsyncMock(return_value={
        "storage_id": "se-01",
        "mode": "rw",
        "total": "10737418240",
        "used": "5368709120",
        "available": "5368709120",
        "percent_used": "50.0",
        "health": "healthy",
        "backend": "local",
        "location": "dc1",
        "last_update": "2026-01-16T10:00:00Z",
        "last_poll": "2026-01-16T10:00:00Z",
        "endpoint": "http://localhost:8010",
    })

    admin_client = AsyncMock()

    monitor = AdaptiveCapacityMonitor(
        redis_client=redis_client,
        storage_endpoints={"se-01": "http://localhost:8010"},
        config=CapacityMonitorConfig(),
        admin_client=admin_client
    )

    # Execute
    capacity = await monitor.get_capacity("se-01")

    # Assert
    assert capacity is not None
    assert capacity.storage_id == "se-01"

    # Verify fallback НЕ был использован
    admin_client.get_storage_element_capacity.assert_not_called()


@pytest.mark.asyncio
async def test_get_all_capacities_with_fallback():
    """Тест get_all_capacities с fallback для каждого SE."""
    # Setup
    redis_client = AsyncMock()
    redis_client.hgetall = AsyncMock(side_effect=RedisError("Connection refused"))

    admin_client = AsyncMock()

    def get_capacity_side_effect(se_id):
        """Mock для возврата разных capacity для разных SE."""
        if se_id == "se-01":
            return StorageCapacityInfo(
                storage_id="se-01",
                mode="rw",
                total=10737418240,
                used=5368709120,
                available=5368709120,
                percent_used=50.0,
                health=HealthStatus.HEALTHY,
                backend="local",
                location="dc1",
                last_update="2026-01-16T10:00:00Z",
                last_poll="2026-01-16T10:00:00Z",
                endpoint="http://localhost:8010"
            )
        elif se_id == "se-02":
            return StorageCapacityInfo(
                storage_id="se-02",
                mode="rw",
                total=21474836480,
                used=10737418240,
                available=10737418240,
                percent_used=50.0,
                health=HealthStatus.HEALTHY,
                backend="s3",
                location="dc2",
                last_update="2026-01-16T10:00:00Z",
                last_poll="2026-01-16T10:00:00Z",
                endpoint="http://localhost:8011"
            )
        return None

    admin_client.get_storage_element_capacity = AsyncMock(side_effect=get_capacity_side_effect)

    monitor = AdaptiveCapacityMonitor(
        redis_client=redis_client,
        storage_endpoints={
            "se-01": "http://localhost:8010",
            "se-02": "http://localhost:8011"
        },
        config=CapacityMonitorConfig(),
        admin_client=admin_client
    )

    # Execute
    capacities = await monitor.get_all_capacities()

    # Assert
    assert len(capacities) == 2
    assert "se-01" in capacities
    assert "se-02" in capacities
    assert capacities["se-01"].total == 10737418240
    assert capacities["se-02"].total == 21474836480

    # Verify fallback был вызван для обоих SE
    assert admin_client.get_storage_element_capacity.call_count == 2


@pytest.mark.asyncio
async def test_get_capacity_cache_miss_no_fallback():
    """Тест cache miss (данных нет) без fallback (Redis работает, но данных нет)."""
    # Setup
    redis_client = AsyncMock()
    redis_client.hgetall = AsyncMock(return_value={})  # Empty dict = cache miss

    admin_client = AsyncMock()

    monitor = AdaptiveCapacityMonitor(
        redis_client=redis_client,
        storage_endpoints={"se-01": "http://localhost:8010"},
        config=CapacityMonitorConfig(),
        admin_client=admin_client
    )

    # Execute
    capacity = await monitor.get_capacity("se-01")

    # Assert
    assert capacity is None

    # Verify fallback НЕ был использован (Redis работает, просто данных нет)
    admin_client.get_storage_element_capacity.assert_not_called()
