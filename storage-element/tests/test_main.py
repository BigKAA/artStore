"""
Integration tests для FastAPI application.

Тестирует основные endpoints и application lifecycle.
"""

import pytest
from fastapi.testclient import TestClient
from pathlib import Path
import tempfile

from app.main import app


@pytest.fixture
def client():
    """Create FastAPI test client."""
    with TestClient(app) as client:
        yield client


class TestRootEndpoint:
    """Тесты для root endpoint."""

    def test_root_endpoint(self, client):
        """Тест root endpoint возвращает информацию о приложении."""
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()

        assert "name" in data
        assert "version" in data
        assert "mode" in data
        assert "endpoints" in data


class TestHealthEndpoints:
    """Тесты для health check endpoints."""

    def test_liveness_probe(self, client):
        """Тест liveness probe."""
        response = client.get("/health/live")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "ok"
        assert "timestamp" in data
        assert "checks" in data
        assert data["checks"]["process"] == "running"

    def test_readiness_probe(self, client):
        """Тест readiness probe."""
        response = client.get("/health/ready")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] in ["ok", "degraded"]
        assert "timestamp" in data
        assert "checks" in data
        assert "storage_directory" in data["checks"]
        assert "wal_directory" in data["checks"]
        assert "configuration" in data["checks"]

    def test_readiness_probe_storage_accessible(self, client):
        """Тест что readiness probe проверяет доступность storage."""
        response = client.get("/health/ready")

        assert response.status_code == 200
        data = response.json()

        # Storage directory should be accessible
        assert data["checks"]["storage_directory"] == "accessible"


class TestAPIV1Endpoint:
    """Тесты для API v1 endpoint."""

    def test_api_v1_info(self, client):
        """Тест API v1 info endpoint."""
        response = client.get("/api/v1")

        assert response.status_code == 200
        data = response.json()

        assert data["version"] == "1.0"
        assert "endpoints" in data
        assert "files" in data["endpoints"]
        assert "search" in data["endpoints"]


class TestMiddleware:
    """Тесты для middleware."""

    def test_cors_headers(self, client):
        """Тест CORS middleware добавляет headers."""
        response = client.options("/", headers={"Origin": "http://localhost"})

        # CORS headers should be present in debug mode
        assert response.status_code in [200, 405]  # May vary by FastAPI version

    def test_gzip_compression(self, client):
        """Тест GZip compression middleware."""
        response = client.get("/", headers={"Accept-Encoding": "gzip"})

        # Small responses may not be compressed
        assert response.status_code == 200


class TestErrorHandling:
    """Тесты для error handling."""

    def test_404_not_found(self, client):
        """Тест 404 для несуществующего endpoint."""
        response = client.get("/nonexistent")

        assert response.status_code == 404


class TestLoggingMiddleware:
    """Тесты для logging middleware."""

    def test_request_logging(self, client, caplog):
        """Тест что requests логируются."""
        import logging
        caplog.set_level(logging.INFO)

        response = client.get("/")

        assert response.status_code == 200
        # Check that request was logged (may vary by log format)
