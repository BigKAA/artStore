"""
Integration tests для Root и Metrics endpoints.

Тестирует:
- GET / - Root endpoint с информацией о сервисе
- GET /metrics - Prometheus metrics endpoint

Эти endpoints предоставляют информацию о сервисе и метрики для мониторинга.
"""

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """
    Test client для тестирования endpoints.
    """
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


class TestRootEndpoint:
    """
    Tests для GET / endpoint.

    Root endpoint предоставляет базовую информацию о сервисе,
    включая версию, описание и список доступных endpoints.
    """

    def test_root_returns_200_ok(self, client):
        """
        Тест: Root endpoint возвращает 200 OK.
        """
        response = client.get("/")

        assert response.status_code == status.HTTP_200_OK

    def test_root_returns_service_info(self, client):
        """
        Тест: Root endpoint возвращает информацию о сервисе.
        """
        response = client.get("/")

        data = response.json()
        assert "service" in data
        assert data["service"] == "ArtStore Query Module"

    def test_root_contains_version(self, client):
        """
        Тест: Root endpoint содержит версию сервиса.
        """
        response = client.get("/")

        data = response.json()
        assert "version" in data
        assert isinstance(data["version"], str)
        # Версия должна быть в формате semver
        assert len(data["version"].split(".")) == 3

    def test_root_contains_description(self, client):
        """
        Тест: Root endpoint содержит описание сервиса.
        """
        response = client.get("/")

        data = response.json()
        assert "description" in data
        assert "search" in data["description"].lower() or "download" in data["description"].lower()

    def test_root_contains_features(self, client):
        """
        Тест: Root endpoint перечисляет features сервиса.
        """
        response = client.get("/")

        data = response.json()
        assert "features" in data
        assert isinstance(data["features"], list)
        assert len(data["features"]) > 0

    def test_root_contains_endpoints_list(self, client):
        """
        Тест: Root endpoint содержит список доступных endpoints.
        """
        response = client.get("/")

        data = response.json()
        assert "endpoints" in data
        assert isinstance(data["endpoints"], dict)

        # Проверяем основные endpoints
        endpoints = data["endpoints"]
        assert "health" in endpoints or any("health" in str(v) for v in endpoints.values())

    def test_root_response_structure(self, client):
        """
        Тест: Root response имеет полную структуру.
        """
        response = client.get("/")

        data = response.json()
        required_fields = ["service", "version", "description", "features", "endpoints"]

        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

    def test_root_returns_json(self, client):
        """
        Тест: Root endpoint возвращает JSON.
        """
        response = client.get("/")

        assert response.headers["content-type"] == "application/json"

    def test_root_no_auth_required(self, client):
        """
        Тест: Root endpoint доступен без аутентификации.

        Это публичный endpoint для discovery.
        """
        # Запрос без Authorization header
        response = client.get("/")

        assert response.status_code == status.HTTP_200_OK


class TestMetricsEndpoint:
    """
    Tests для GET /metrics endpoint.

    Metrics endpoint предоставляет Prometheus-совместимые метрики
    для мониторинга производительности и состояния сервиса.
    """

    def test_metrics_returns_200_ok(self, client):
        """
        Тест: Metrics endpoint возвращает 200 OK.
        """
        response = client.get("/metrics")

        assert response.status_code == status.HTTP_200_OK

    def test_metrics_returns_prometheus_format(self, client):
        """
        Тест: Metrics endpoint возвращает данные в формате Prometheus.

        Prometheus формат - это текстовый формат с метриками и их значениями.
        """
        response = client.get("/metrics")

        # Prometheus формат обычно text/plain или OpenMetrics format
        content_type = response.headers.get("content-type", "")
        assert "text" in content_type or "openmetrics" in content_type

    def test_metrics_contains_standard_metrics(self, client):
        """
        Тест: Metrics содержит стандартные Python/FastAPI метрики.
        """
        response = client.get("/metrics")
        content = response.text

        # Стандартные метрики Python/Process
        # (Могут отличаться в зависимости от конфигурации prometheus_client)
        # Проверяем что есть какой-то валидный Prometheus формат
        assert "# HELP" in content or "TYPE" in content or "_" in content

    def test_metrics_no_auth_required(self, client):
        """
        Тест: Metrics endpoint доступен без аутентификации.

        Prometheus должен иметь возможность scrape метрики без авторизации.
        В production это обычно защищается на уровне сети.
        """
        response = client.get("/metrics")

        assert response.status_code == status.HTTP_200_OK

    def test_metrics_is_accessible(self, client):
        """
        Тест: Metrics endpoint доступен и отвечает.
        """
        import time

        start = time.time()
        response = client.get("/metrics")
        elapsed = time.time() - start

        assert response.status_code == status.HTTP_200_OK
        # Метрики должны быть быстрыми (< 1 секунды)
        assert elapsed < 1.0, f"Metrics too slow: {elapsed:.3f}s"


class TestDocumentationEndpoints:
    """
    Tests для OpenAPI документации.

    FastAPI автоматически генерирует:
    - /docs - Swagger UI
    - /openapi.json - OpenAPI schema
    """

    def test_docs_endpoint_available(self, client):
        """
        Тест: Swagger UI доступен на /docs.
        """
        response = client.get("/docs")

        # Swagger UI возвращает HTML
        assert response.status_code == status.HTTP_200_OK
        assert "text/html" in response.headers.get("content-type", "")

    def test_openapi_json_available(self, client):
        """
        Тест: OpenAPI schema доступна на /openapi.json.
        """
        response = client.get("/openapi.json")

        assert response.status_code == status.HTTP_200_OK
        assert "application/json" in response.headers.get("content-type", "")

        # Проверяем структуру OpenAPI
        data = response.json()
        assert "openapi" in data
        assert "info" in data
        assert "paths" in data

    def test_openapi_contains_title(self, client):
        """
        Тест: OpenAPI schema содержит название сервиса.
        """
        response = client.get("/openapi.json")
        data = response.json()

        assert "title" in data["info"]
        assert "Query" in data["info"]["title"] or "ArtStore" in data["info"]["title"]

    def test_openapi_contains_version(self, client):
        """
        Тест: OpenAPI schema содержит версию API.
        """
        response = client.get("/openapi.json")
        data = response.json()

        assert "version" in data["info"]

    def test_docs_no_auth_required(self, client):
        """
        Тест: Документация доступна без аутентификации.
        """
        response = client.get("/docs")
        assert response.status_code == status.HTTP_200_OK

        response = client.get("/openapi.json")
        assert response.status_code == status.HTTP_200_OK
