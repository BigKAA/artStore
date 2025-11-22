"""
Unit тесты для health endpoints.
"""

import pytest


class TestHealthEndpoints:
    """Тесты для health check endpoints."""

    def test_liveness(self, client):
        """Тест liveness endpoint."""
        response = client.get("/health/live")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"
        assert "timestamp" in data
        assert "service" in data
        assert "version" in data

    def test_root_endpoint(self, client):
        """Тест root endpoint."""
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert "application" in data
        assert "version" in data
        assert "timestamp" in data
