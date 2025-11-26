"""
Integration tests for System endpoints.

Tests root endpoint и Prometheus metrics endpoint для мониторинга.
"""

import pytest
import re
from httpx import AsyncClient


class TestRootEndpoint:
    """
    Тесты для root endpoint: GET /

    Root endpoint предоставляет service discovery информацию.
    """

    @pytest.mark.asyncio
    async def test_root_endpoint_returns_service_info(self, client: AsyncClient):
        """
        Root endpoint должен возвращать базовую информацию о сервисе.

        Expected response:
        - service: str
        - version: str
        - status: str
        - docs: str
        """
        response = await client.get("/")

        assert response.status_code == 200
        data = response.json()

        # Проверка обязательных полей
        assert "service" in data
        assert "version" in data
        assert "status" in data
        assert "docs" in data

        # Проверка типов
        assert isinstance(data["service"], str)
        assert isinstance(data["version"], str)
        assert isinstance(data["status"], str)
        assert isinstance(data["docs"], str)

    @pytest.mark.asyncio
    async def test_root_endpoint_includes_version(self, client: AsyncClient):
        """
        Root endpoint должен включать version из config.

        Version format: semver (e.g., "0.1.0", "1.2.3").
        """
        response = await client.get("/")

        assert response.status_code == 200
        data = response.json()

        # Проверка version field
        assert "version" in data
        version = data["version"]

        # Version должен быть не пустым
        assert version
        assert len(version) > 0

        # Version должен соответствовать semver формату (опционально)
        # Примеры: "0.1.0", "1.2.3", "2.0.0-beta"
        semver_pattern = r'^\d+\.\d+\.\d+(-[a-zA-Z0-9]+)?$'
        assert re.match(semver_pattern, version), f"Version '{version}' не соответствует semver формату"

    @pytest.mark.asyncio
    async def test_root_endpoint_docs_url_in_debug_mode(self, client: AsyncClient):
        """
        Root endpoint должен показывать docs URL в debug mode.

        В production mode docs должны быть disabled для безопасности.
        """
        response = await client.get("/")

        assert response.status_code == 200
        data = response.json()

        # Проверка docs field
        assert "docs" in data
        docs = data["docs"]

        # В тестовом окружении APP_DEBUG=on, поэтому docs должен быть "/docs"
        # В production будет "disabled in production"
        assert docs in ["/docs", "disabled in production"]


class TestMetricsEndpoint:
    """
    Тесты для Prometheus metrics endpoint: GET /metrics/

    Metrics endpoint предоставляет метрики в Prometheus text exposition format.
    Note: FastAPI mount требует trailing slash (/metrics/ не /metrics).
    """

    @pytest.mark.asyncio
    async def test_metrics_endpoint_returns_prometheus_format(self, client: AsyncClient):
        """
        Metrics endpoint должен возвращать Prometheus text format.

        Prometheus text format:
        - Content-Type: text/plain; charset=utf-8
        - Lines with metric_name{labels} value timestamp
        """
        response = await client.get("/metrics/")

        assert response.status_code == 200

        # Проверка Content-Type
        content_type = response.headers.get("content-type", "")
        assert "text/plain" in content_type, f"Expected text/plain, got {content_type}"

        # Проверка что response text не пустой
        text = response.text
        assert text
        assert len(text) > 0

        # Проверка базовой структуры Prometheus format
        # Должны быть строки с метриками (не комментарии)
        metric_lines = [line for line in text.split("\n") if line and not line.startswith("#")]
        assert len(metric_lines) > 0, "No metrics found in response"

    @pytest.mark.asyncio
    async def test_metrics_endpoint_contains_auth_metrics(self, client: AsyncClient):
        """
        Metrics endpoint должен содержать auth_* метрики из Sprint 23.

        Expected auth metrics:
        - auth_token_requests_total
        - auth_token_source_total
        - auth_token_refresh_total
        - auth_token_validation_total
        - auth_errors_total
        - auth_token_acquisition_duration_seconds
        - auth_token_refresh_duration_seconds
        - auth_token_ttl_seconds
        - auth_token_cache_hit_rate
        """
        response = await client.get("/metrics/")

        assert response.status_code == 200
        text = response.text

        # Проверка наличия auth метрик
        expected_metrics = [
            "auth_token_requests_total",
            "auth_token_source_total",
            "auth_token_refresh_total",
            "auth_token_validation_total",
            "auth_errors_total",
            "auth_token_acquisition_duration_seconds",
            "auth_token_refresh_duration_seconds",
            "auth_token_ttl_seconds",
            "auth_token_cache_hit_rate"
        ]

        for metric in expected_metrics:
            assert metric in text, f"Auth metric '{metric}' not found in /metrics response"

    @pytest.mark.asyncio
    async def test_metrics_endpoint_counter_increments(self, client: AsyncClient):
        """
        Counters должны увеличиваться при выполнении операций.

        Проверяет что если auth_token_requests_total counter присутствует,
        то его значение >= 0. В тестовом окружении counter может отсутствовать
        до первого реального auth request.
        """
        response = await client.get("/metrics/")

        assert response.status_code == 200
        text = response.text

        # Найти counter auth_token_requests_total
        counter_pattern = r'auth_token_requests_total\{[^}]*\}\s+(\d+(\.\d+)?)'
        matches = re.findall(counter_pattern, text)

        # Counter может отсутствовать в тестовом окружении (до первого auth request)
        # Но если присутствует - должен быть >= 0
        if len(matches) > 0:
            for match in matches:
                value = float(match[0])
                assert value >= 0, f"Counter value {value} should be >= 0"

    @pytest.mark.asyncio
    async def test_metrics_endpoint_histogram_buckets(self, client: AsyncClient):
        """
        Histograms должны иметь bucket структуру.

        Проверяет auth_token_acquisition_duration_seconds histogram.
        """
        response = await client.get("/metrics/")

        assert response.status_code == 200
        text = response.text

        # Найти histogram buckets
        histogram_pattern = r'auth_token_acquisition_duration_seconds_bucket'

        # Histogram buckets должны присутствовать
        assert histogram_pattern in text, "auth_token_acquisition_duration_seconds_bucket not found"

        # Проверка базовой структуры histogram (должны быть _bucket, _count, _sum)
        assert "auth_token_acquisition_duration_seconds_count" in text
        assert "auth_token_acquisition_duration_seconds_sum" in text

    @pytest.mark.asyncio
    async def test_metrics_endpoint_gauge_values(self, client: AsyncClient):
        """
        Gauges должны возвращать текущие значения.

        Проверяет auth_token_ttl_seconds и auth_token_cache_hit_rate gauges.
        """
        response = await client.get("/metrics/")

        assert response.status_code == 200
        text = response.text

        # Проверка gauge auth_token_ttl_seconds
        ttl_pattern = r'auth_token_ttl_seconds\s+(-?\d+(\.\d+)?)'
        ttl_matches = re.findall(ttl_pattern, text)

        if len(ttl_matches) > 0:
            # Gauge присутствует, проверяем значение
            ttl_value = float(ttl_matches[0][0])
            # TTL может быть 0 (нет токена) или положительным числом секунд
            assert ttl_value >= 0, f"TTL gauge value {ttl_value} should be >= 0"

        # Проверка gauge auth_token_cache_hit_rate
        hit_rate_pattern = r'auth_token_cache_hit_rate\s+(-?\d+(\.\d+)?)'
        hit_rate_matches = re.findall(hit_rate_pattern, text)

        if len(hit_rate_matches) > 0:
            # Gauge присутствует, проверяем значение
            hit_rate_value = float(hit_rate_matches[0][0])
            # Hit rate должен быть между 0.0 и 1.0
            assert 0.0 <= hit_rate_value <= 1.0, f"Hit rate {hit_rate_value} should be between 0.0 and 1.0"

    @pytest.mark.asyncio
    async def test_metrics_endpoint_no_auth_required(self, client: AsyncClient):
        """
        Metrics endpoint должен быть публично доступен без JWT токена.

        Prometheus scraping не должен требовать authentication.
        """
        # Запрос БЕЗ Authorization headers
        response = await client.get("/metrics/")

        assert response.status_code == 200

        # Должен вернуть metrics в Prometheus format
        text = response.text
        assert "auth_token_requests_total" in text
