"""
Integration tests for Health Check endpoints.

Tests liveness and readiness probes для Kubernetes/Docker monitoring.
"""

import pytest
from httpx import AsyncClient
from datetime import datetime
from unittest.mock import AsyncMock, patch


class TestLivenessProbe:
    """
    Тесты для liveness probe endpoint: GET /api/v1/health/live

    Liveness probe должен всегда возвращать 200 OK если приложение запущено.
    """

    @pytest.mark.asyncio
    async def test_liveness_probe_returns_200_ok(self, client: AsyncClient):
        """
        Базовая проверка доступности liveness endpoint.

        Liveness probe должен всегда отвечать 200 OK если application running.
        """
        response = await client.get("/api/v1/health/live")

        assert response.status_code == 200
        data = response.json()
        assert data is not None

    @pytest.mark.asyncio
    async def test_liveness_probe_response_format(self, client: AsyncClient):
        """
        Валидация структуры HealthResponse согласно Pydantic schema.

        Expected fields:
        - status: str
        - timestamp: datetime (ISO format)
        - version: str
        - service: str
        """
        response = await client.get("/api/v1/health/live")

        assert response.status_code == 200
        data = response.json()

        # Проверка обязательных полей
        assert "status" in data
        assert "timestamp" in data
        assert "version" in data
        assert "service" in data

        # Проверка типов
        assert isinstance(data["status"], str)
        assert isinstance(data["version"], str)
        assert isinstance(data["service"], str)

        # Проверка значений
        assert data["status"] == "ok"

        # Проверка формата timestamp (ISO 8601)
        timestamp = data["timestamp"]
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))  # Should not raise

    @pytest.mark.asyncio
    async def test_liveness_probe_no_auth_required(self, client: AsyncClient):
        """
        Liveness probe должен быть публично доступен без JWT токена.

        Health checks не должны требовать authentication для monitoring систем.
        """
        # Запрос БЕЗ Authorization headers
        response = await client.get("/api/v1/health/live")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_liveness_probe_includes_service_metadata(self, client: AsyncClient):
        """
        Liveness probe должен возвращать service metadata.

        Проверяет что version и service name присутствуют в response.
        """
        response = await client.get("/api/v1/health/live")

        assert response.status_code == 200
        data = response.json()

        # Service name должен быть "artstore-ingester" (из config)
        assert data["service"] == "artstore-ingester"

        # Version должен быть не пустым
        assert data["version"]
        assert len(data["version"]) > 0


class TestReadinessProbe:
    """
    Тесты для readiness probe endpoint: GET /api/v1/health/ready

    Readiness probe проверяет доступность dependencies (Storage Element, Redis).
    """

    @pytest.mark.asyncio
    async def test_readiness_probe_all_dependencies_healthy(self, client: AsyncClient):
        """
        Readiness probe возвращает status="ok" когда все dependencies доступны.

        Мокирует успешный health check от Storage Element.
        """
        # Mock httpx.AsyncClient для storage health check
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            response = await client.get("/api/v1/health/ready")

        assert response.status_code == 200
        data = response.json()

        # Overall status должен быть "ok"
        assert data["status"] == "ok"

        # Storage Element check должен быть "ok"
        assert "checks" in data
        assert "storage_element" in data["checks"]
        assert data["checks"]["storage_element"] == "ok"

    @pytest.mark.asyncio
    async def test_readiness_probe_storage_element_unavailable(self, client: AsyncClient):
        """
        Readiness probe возвращает status="degraded" когда Storage Element недоступен.

        Мокирует failed health check от Storage Element (connection error).
        """
        # Mock httpx.AsyncClient для симуляции connection error
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            response = await client.get("/api/v1/health/ready")

        assert response.status_code == 200  # Still returns 200, but status is degraded
        data = response.json()

        # Overall status должен быть "degraded"
        assert data["status"] == "degraded"

        # Storage Element check должен быть "fail"
        assert data["checks"]["storage_element"] == "fail"

    @pytest.mark.asyncio
    async def test_readiness_probe_response_format(self, client: AsyncClient):
        """
        Валидация структуры ReadinessResponse согласно Pydantic schema.

        Expected fields:
        - status: str ("ok" or "degraded")
        - timestamp: datetime (ISO format)
        - checks: dict
        """
        # Mock successful health check
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            response = await client.get("/api/v1/health/ready")

        assert response.status_code == 200
        data = response.json()

        # Проверка обязательных полей
        assert "status" in data
        assert "timestamp" in data
        assert "checks" in data

        # Проверка типов
        assert isinstance(data["status"], str)
        assert isinstance(data["checks"], dict)

        # Проверка допустимых значений status
        assert data["status"] in ["ok", "degraded"]

        # Проверка формата timestamp (ISO 8601)
        timestamp = data["timestamp"]
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))  # Should not raise

    @pytest.mark.asyncio
    async def test_readiness_probe_timeout_handling(self, client: AsyncClient):
        """
        Readiness probe должен обрабатывать timeout при проверке dependencies.

        Timeout для Storage Element health check: 5 секунд.
        """
        import asyncio

        # Mock httpx.AsyncClient с timeout exception
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=asyncio.TimeoutError("Request timeout"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            response = await client.get("/api/v1/health/ready")

        assert response.status_code == 200
        data = response.json()

        # При timeout overall status должен быть "degraded"
        assert data["status"] == "degraded"

        # Storage Element check должен быть "fail"
        assert data["checks"]["storage_element"] == "fail"

    @pytest.mark.asyncio
    async def test_readiness_probe_no_auth_required(self, client: AsyncClient):
        """
        Readiness probe должен быть публично доступен без JWT токена.

        Health checks не должны требовать authentication для load balancers.
        """
        # Mock successful health check
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            # Запрос БЕЗ Authorization headers
            response = await client.get("/api/v1/health/ready")

        assert response.status_code == 200
        data = response.json()

        # Должен работать без authentication
        assert "status" in data
        assert data["status"] in ["ok", "degraded"]
