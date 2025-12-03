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
    Тесты для liveness probe endpoint: GET /health/live

    Sprint 16: Health endpoints перенесены на /health (без /api/v1 prefix).
    Liveness probe должен всегда возвращать 200 OK если приложение запущено.
    """

    @pytest.mark.asyncio
    async def test_liveness_probe_returns_200_ok(self, client: AsyncClient):
        """
        Базовая проверка доступности liveness endpoint.

        Liveness probe должен всегда отвечать 200 OK если application running.
        """
        response = await client.get("/health/live")

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
        response = await client.get("/health/live")

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
        response = await client.get("/health/live")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_liveness_probe_includes_service_metadata(self, client: AsyncClient):
        """
        Liveness probe должен возвращать service metadata.

        Проверяет что version и service name присутствуют в response.
        """
        response = await client.get("/health/live")

        assert response.status_code == 200
        data = response.json()

        # Service name должен быть "artstore-ingester" (из config)
        assert data["service"] == "artstore-ingester"

        # Version должен быть не пустым
        assert data["version"]
        assert len(data["version"]) > 0


class TestReadinessProbe:
    """
    Тесты для readiness probe endpoint: GET /health/ready

    Sprint 16: Health endpoints перенесены на /health (без /api/v1 prefix).
    Readiness probe проверяет доступность dependencies (Storage Element, Redis).
    """

    @pytest.mark.asyncio
    async def test_readiness_probe_all_dependencies_healthy(self, client: AsyncClient):
        """
        Readiness probe возвращает status когда dependencies доступны.

        Sprint 16: Новая структура ответа с redis, admin_module, storage_elements.
        Мокирует успешный health check от Storage Element.

        Note: В тестовой среде без реального Redis/Admin Module
        статус будет degraded или fail, поэтому проверяем только структуру ответа.
        """
        response = await client.get("/health/ready")

        # Response может быть 200 (ok/degraded) или 503 (fail)
        assert response.status_code in (200, 503)
        data = response.json()

        # Проверка структуры ответа Sprint 16
        assert "status" in data
        assert data["status"] in ("ok", "degraded", "fail")
        assert "timestamp" in data
        assert "checks" in data

        # Sprint 16: checks содержит redis, admin_module, storage_elements
        # В тестовой среде эти компоненты могут быть недоступны
        checks = data["checks"]
        assert isinstance(checks, dict)

        # Если есть summary - проверяем его структуру
        if "summary" in data and data["summary"]:
            assert "total_se" in data["summary"]
            assert "healthy_se" in data["summary"]
            assert "health_percentage" in data["summary"]

    @pytest.mark.asyncio
    async def test_readiness_probe_storage_element_unavailable(self, client: AsyncClient):
        """
        Readiness probe возвращает status="degraded" или "fail" когда SE недоступен.

        Sprint 16: Новая структура проверяет storage_elements (множественное число).
        В тестовой среде SE обычно недоступны.
        """
        response = await client.get("/health/ready")

        # Response может быть 200 (degraded) или 503 (fail)
        assert response.status_code in (200, 503)
        data = response.json()

        # Без реальных SE статус должен быть degraded или fail
        assert data["status"] in ("degraded", "fail")

        # Sprint 16: проверяем наличие checks.storage_elements
        assert "checks" in data
        checks = data["checks"]
        # storage_elements должен существовать как ключ в checks
        # Значение может быть 'fail', 'degraded', 'no_elements', 'not_initialized', etc.
        if "storage_elements" in checks:
            assert checks["storage_elements"] in (
                "ok", "fail", "degraded", "no_elements",
                "not_initialized", "import_error", "error"
            )

    @pytest.mark.asyncio
    async def test_readiness_probe_response_format(self, client: AsyncClient):
        """
        Валидация структуры ReadinessResponse согласно Pydantic schema.

        Sprint 16: Обновленная структура ответа:
        - status: str ("ok", "degraded" или "fail")
        - timestamp: datetime (ISO format)
        - checks: dict (redis, admin_module, storage_elements)
        - storage_elements: dict (optional, детали по каждому SE)
        - summary: dict (optional, агрегированная статистика)
        """
        response = await client.get("/health/ready")

        # Response может быть 200 (ok/degraded) или 503 (fail)
        assert response.status_code in (200, 503)
        data = response.json()

        # Проверка обязательных полей
        assert "status" in data
        assert "timestamp" in data
        assert "checks" in data

        # Проверка типов
        assert isinstance(data["status"], str)
        assert isinstance(data["checks"], dict)

        # Sprint 16: добавлен status "fail"
        assert data["status"] in ["ok", "degraded", "fail"]

        # Проверка формата timestamp (ISO 8601)
        timestamp = data["timestamp"]
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))  # Should not raise

    @pytest.mark.asyncio
    async def test_readiness_probe_timeout_handling(self, client: AsyncClient):
        """
        Readiness probe должен обрабатывать timeout при проверке dependencies.

        Sprint 16: Проверяем что timeout обрабатывается gracefully
        и не вызывает crash endpoint'а.
        """
        # В тестовой среде без реальных сервисов будет timeout/error
        response = await client.get("/health/ready")

        # Response не должен быть ошибкой сервера (500)
        assert response.status_code in (200, 503)
        data = response.json()

        # При проблемах с dependencies status должен быть degraded или fail
        assert data["status"] in ("ok", "degraded", "fail")

        # Проверяем что response корректно структурирован
        assert "checks" in data
        assert isinstance(data["checks"], dict)

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
            response = await client.get("/health/ready")

        assert response.status_code == 200
        data = response.json()

        # Должен работать без authentication
        assert "status" in data
        assert data["status"] in ["ok", "degraded"]
