"""
Unit тесты для AdminModuleClient.get_storage_element_capacity().

Sprint 17 Extension: Runtime Fallback для Capacity Метрик.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from app.services.admin_client import AdminModuleClient, AdminClientError, AdminClientAuthError
from app.services.capacity_monitor import StorageCapacityInfo, HealthStatus


@pytest.mark.asyncio
async def test_get_storage_element_capacity_success():
    """Тест успешного получения capacity через Admin Module API."""
    # Setup
    client = AdminModuleClient()
    client._initialized = True
    client._access_token = "test_token"

    # Mock HTTP response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "element_id": "se-01",
        "mode": "rw",
        "capacity_bytes": 10737418240,  # 10GB
        "used_bytes": 5368709120,       # 5GB
        "health_status": "healthy",
        "capacity_status": "ok",
        "api_url": "http://localhost:8010"
    }

    client._http_client = AsyncMock()
    client._http_client.get = AsyncMock(return_value=mock_response)

    # Execute
    capacity = await client.get_storage_element_capacity("se-01")

    # Assert
    assert capacity is not None
    assert capacity.storage_id == "se-01"
    assert capacity.mode == "rw"
    assert capacity.total == 10737418240
    assert capacity.used == 5368709120
    assert capacity.available == 5368709120
    assert capacity.percent_used == 50.0
    assert capacity.health == HealthStatus.HEALTHY
    assert capacity.endpoint == "http://localhost:8010"

    # Verify API call
    client._http_client.get.assert_called_once_with(
        "/api/v1/internal/storage-elements/se-01",
        headers={"Authorization": "Bearer test_token"}
    )


@pytest.mark.asyncio
async def test_get_storage_element_capacity_not_found():
    """Тест 404 Not Found для несуществующего SE."""
    # Setup
    client = AdminModuleClient()
    client._initialized = True
    client._access_token = "test_token"

    # Mock HTTP response 404
    mock_response = MagicMock()
    mock_response.status_code = 404

    client._http_client = AsyncMock()
    client._http_client.get = AsyncMock(return_value=mock_response)

    # Execute
    capacity = await client.get_storage_element_capacity("non-existent")

    # Assert
    assert capacity is None


@pytest.mark.asyncio
async def test_get_storage_element_capacity_auth_retry():
    """Тест retry при 401 Unauthorized."""
    # Setup
    client = AdminModuleClient()
    client._initialized = True
    client._access_token = "expired_token"

    # Mock first response: 401
    mock_response_401 = MagicMock()
    mock_response_401.status_code = 401

    # Mock second response after auth refresh: 200
    mock_response_200 = MagicMock()
    mock_response_200.status_code = 200
    mock_response_200.json.return_value = {
        "element_id": "se-01",
        "mode": "rw",
        "capacity_bytes": 10737418240,
        "used_bytes": 5368709120,
        "health_status": "healthy",
        "api_url": "http://localhost:8010"
    }

    client._http_client = AsyncMock()
    client._http_client.get = AsyncMock(side_effect=[mock_response_401, mock_response_200])

    # Mock _ensure_authenticated
    client._ensure_authenticated = AsyncMock(return_value="new_token")

    # Execute
    capacity = await client.get_storage_element_capacity("se-01")

    # Assert
    assert capacity is not None
    assert capacity.storage_id == "se-01"
    assert client._ensure_authenticated.call_count == 1
    assert client._http_client.get.call_count == 2


@pytest.mark.asyncio
async def test_get_storage_element_capacity_not_initialized():
    """Тест ошибки при вызове без инициализации."""
    # Setup
    client = AdminModuleClient()
    # НЕ инициализирован (_initialized = False)

    # Execute & Assert
    with pytest.raises(AdminClientError, match="not initialized"):
        await client.get_storage_element_capacity("se-01")


@pytest.mark.asyncio
async def test_parse_capacity_info_all_health_statuses():
    """Тест парсинга всех возможных health_status значений."""
    # Setup
    client = AdminModuleClient()

    test_cases = [
        ("healthy", HealthStatus.HEALTHY),
        ("degraded", HealthStatus.DEGRADED),
        ("unhealthy", HealthStatus.UNHEALTHY),
        ("unknown", HealthStatus.UNHEALTHY),  # fallback для неизвестного статуса
    ]

    for health_str, expected_health in test_cases:
        data = {
            "element_id": "se-01",
            "mode": "rw",
            "capacity_bytes": 10737418240,
            "used_bytes": 5368709120,
            "health_status": health_str,
            "api_url": "http://localhost:8010"
        }

        # Execute
        capacity = client._parse_capacity_info("se-01", data)

        # Assert
        assert capacity.health == expected_health, f"Failed for health_status={health_str}"


@pytest.mark.asyncio
async def test_parse_capacity_info_percent_calculation():
    """Тест корректности расчёта процента использования."""
    # Setup
    client = AdminModuleClient()

    test_cases = [
        (10737418240, 5368709120, 50.0),    # 50%
        (10737418240, 10737418240, 100.0),  # 100%
        (10737418240, 0, 0.0),              # 0%
        (10737418240, 1073741824, 10.0),    # 10%
        (0, 0, 0.0),                        # Edge case: total=0
    ]

    for total, used, expected_percent in test_cases:
        data = {
            "element_id": "se-01",
            "mode": "rw",
            "capacity_bytes": total,
            "used_bytes": used,
            "health_status": "healthy",
            "api_url": "http://localhost:8010"
        }

        # Execute
        capacity = client._parse_capacity_info("se-01", data)

        # Assert
        assert capacity.percent_used == expected_percent, \
            f"Failed for total={total}, used={used}: expected {expected_percent}%, got {capacity.percent_used}%"
        assert capacity.available == (total - used)


@pytest.mark.asyncio
async def test_get_storage_element_capacity_connection_error():
    """Тест обработки ошибки соединения."""
    # Setup
    client = AdminModuleClient()
    client._initialized = True
    client._access_token = "test_token"

    # Mock connection error
    import httpx
    client._http_client = AsyncMock()
    client._http_client.get = AsyncMock(side_effect=httpx.RequestError("Connection failed"))

    # Execute & Assert
    from app.services.admin_client import AdminClientConnectionError
    with pytest.raises(AdminClientConnectionError, match="Failed to connect"):
        await client.get_storage_element_capacity("se-01")
