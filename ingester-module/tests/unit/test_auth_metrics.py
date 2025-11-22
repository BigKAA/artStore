"""
Unit tests для JWT Authentication Prometheus metrics.

Тестирует метрики модуля app/services/auth_metrics.py:
- Counter metrics: auth_token_requests_total, auth_token_source_total, auth_token_refresh_total
- Histogram metrics: auth_token_acquisition_duration, auth_token_refresh_duration
- Gauge metrics: auth_token_ttl, auth_token_cache_hit_rate
- Helper functions: calculate_cache_hit_rate(), classify_auth_error()

Sprint 23 Phase 1: JWT Authentication Metrics Implementation.
"""

import pytest
from unittest.mock import MagicMock
import httpx

from app.services.auth_metrics import (
    auth_token_requests_total,
    auth_token_acquisition_duration,
    auth_token_source_total,
    auth_token_refresh_total,
    auth_token_refresh_duration,
    auth_token_ttl,
    auth_token_validation_total,
    auth_token_cache_hit_rate,
    auth_errors_total,
    calculate_cache_hit_rate,
    classify_auth_error,
    get_all_metrics,
)


class TestAuthMetricsCounters:
    """Test Counter metrics для authentication tracking."""

    def test_auth_token_requests_total_metric_exists(self):
        """Verify auth_token_requests_total counter exists."""
        assert auth_token_requests_total is not None
        # Prometheus auto-removes _total suffix from Counter names
        assert auth_token_requests_total._name == "auth_token_requests"
        assert auth_token_requests_total._type == "counter"

    def test_auth_token_requests_total_labels(self):
        """Verify auth_token_requests_total has correct labels."""
        # Increment with valid labels
        auth_token_requests_total.labels(status="success", error_type="").inc()
        auth_token_requests_total.labels(status="failure", error_type="http_401").inc()

        # Verify metric has expected label names
        assert "status" in auth_token_requests_total._labelnames
        assert "error_type" in auth_token_requests_total._labelnames

    def test_auth_token_source_total_metric_exists(self):
        """Verify auth_token_source_total counter exists."""
        assert auth_token_source_total is not None
        # Prometheus auto-removes _total suffix from Counter names
        assert auth_token_source_total._name == "auth_token_source"
        assert "source" in auth_token_source_total._labelnames

    def test_auth_token_source_total_cache_hit(self):
        """Test tracking cache hits."""
        initial_value = auth_token_source_total.labels(source="cache")._value.get()
        auth_token_source_total.labels(source="cache").inc()
        assert auth_token_source_total.labels(source="cache")._value.get() == initial_value + 1

    def test_auth_token_source_total_fresh_request(self):
        """Test tracking fresh requests."""
        initial_value = auth_token_source_total.labels(source="fresh_request")._value.get()
        auth_token_source_total.labels(source="fresh_request").inc()
        assert auth_token_source_total.labels(source="fresh_request")._value.get() == initial_value + 1

    def test_auth_token_refresh_total_metric_exists(self):
        """Verify auth_token_refresh_total counter exists."""
        assert auth_token_refresh_total is not None
        # Prometheus auto-removes _total suffix from Counter names
        assert auth_token_refresh_total._name == "auth_token_refresh"
        assert "status" in auth_token_refresh_total._labelnames
        assert "trigger" in auth_token_refresh_total._labelnames

    def test_auth_token_refresh_total_triggers(self):
        """Test different refresh triggers."""
        # Test all trigger types
        for trigger in ["expired", "expiring_soon", "manual"]:
            auth_token_refresh_total.labels(status="success", trigger=trigger).inc()
            auth_token_refresh_total.labels(status="failure", trigger=trigger).inc()

    def test_auth_token_validation_total_metric_exists(self):
        """Verify auth_token_validation_total counter exists."""
        assert auth_token_validation_total is not None
        # Prometheus auto-removes _total suffix from Counter names
        assert auth_token_validation_total._name == "auth_token_validation"
        assert "result" in auth_token_validation_total._labelnames

    def test_auth_token_validation_total_results(self):
        """Test all validation result types."""
        for result in ["valid", "expired", "expiring_soon", "missing"]:
            auth_token_validation_total.labels(result=result).inc()

    def test_auth_errors_total_metric_exists(self):
        """Verify auth_errors_total counter exists."""
        assert auth_errors_total is not None
        # Prometheus auto-removes _total suffix from Counter names
        assert auth_errors_total._name == "auth_errors"
        assert "error_type" in auth_errors_total._labelnames
        assert "admin_module_url" in auth_errors_total._labelnames


class TestAuthMetricsHistograms:
    """Test Histogram metrics для latency tracking."""

    def test_auth_token_acquisition_duration_metric_exists(self):
        """Verify auth_token_acquisition_duration histogram exists."""
        assert auth_token_acquisition_duration is not None
        assert auth_token_acquisition_duration._name == "auth_token_acquisition_duration_seconds"
        assert auth_token_acquisition_duration._type == "histogram"

    def test_auth_token_acquisition_duration_buckets(self):
        """Verify histogram has correct buckets for OAuth 2.0 latency."""
        expected_buckets = [0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0]
        # Prometheus adds +Inf bucket automatically
        assert auth_token_acquisition_duration._upper_bounds[:-1] == expected_buckets

    def test_auth_token_acquisition_duration_observe(self):
        """Test observing acquisition duration."""
        # Observe some latencies
        auth_token_acquisition_duration.observe(0.15)  # Fast
        auth_token_acquisition_duration.observe(0.5)   # Normal
        auth_token_acquisition_duration.observe(2.0)   # Slow

    def test_auth_token_refresh_duration_metric_exists(self):
        """Verify auth_token_refresh_duration histogram exists."""
        assert auth_token_refresh_duration is not None
        assert auth_token_refresh_duration._name == "auth_token_refresh_duration_seconds"
        assert auth_token_refresh_duration._type == "histogram"

    def test_auth_token_refresh_duration_buckets(self):
        """Verify refresh duration histogram has correct buckets."""
        expected_buckets = [0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
        assert auth_token_refresh_duration._upper_bounds[:-1] == expected_buckets

    def test_auth_token_refresh_duration_observe(self):
        """Test observing refresh duration."""
        auth_token_refresh_duration.observe(0.25)  # Typical refresh time


class TestAuthMetricsGauges:
    """Test Gauge metrics для state tracking."""

    def test_auth_token_ttl_metric_exists(self):
        """Verify auth_token_ttl gauge exists."""
        assert auth_token_ttl is not None
        assert auth_token_ttl._name == "auth_token_ttl_seconds"
        assert auth_token_ttl._type == "gauge"

    def test_auth_token_ttl_set(self):
        """Test setting TTL gauge."""
        auth_token_ttl.set(1800)  # 30 minutes
        assert auth_token_ttl._value.get() == 1800

        auth_token_ttl.set(300)   # 5 minutes (expiring soon)
        assert auth_token_ttl._value.get() == 300

        auth_token_ttl.set(0)     # Expired
        assert auth_token_ttl._value.get() == 0

    def test_auth_token_cache_hit_rate_metric_exists(self):
        """Verify auth_token_cache_hit_rate gauge exists."""
        assert auth_token_cache_hit_rate is not None
        assert auth_token_cache_hit_rate._name == "auth_token_cache_hit_rate"

    def test_auth_token_cache_hit_rate_set(self):
        """Test setting cache hit rate percentage."""
        auth_token_cache_hit_rate.set(85.5)  # 85.5% hit rate
        assert auth_token_cache_hit_rate._value.get() == 85.5


class TestCalculateCacheHitRate:
    """Test calculate_cache_hit_rate() helper function."""

    def test_calculate_cache_hit_rate_normal(self):
        """Test normal cache hit rate calculation."""
        result = calculate_cache_hit_rate(850, 1000)
        assert result == 85.0

    def test_calculate_cache_hit_rate_perfect(self):
        """Test 100% cache hit rate."""
        result = calculate_cache_hit_rate(1000, 1000)
        assert result == 100.0

    def test_calculate_cache_hit_rate_zero(self):
        """Test 0% cache hit rate (all cache misses)."""
        result = calculate_cache_hit_rate(0, 1000)
        assert result == 0.0

    def test_calculate_cache_hit_rate_zero_requests(self):
        """Test edge case with zero total requests."""
        result = calculate_cache_hit_rate(0, 0)
        assert result == 0.0

    def test_calculate_cache_hit_rate_low(self):
        """Test low cache hit rate."""
        result = calculate_cache_hit_rate(25, 1000)
        assert result == 2.5

    def test_calculate_cache_hit_rate_high(self):
        """Test high cache hit rate."""
        result = calculate_cache_hit_rate(950, 1000)
        assert result == 95.0


class TestClassifyAuthError:
    """Test classify_auth_error() helper function."""

    def test_classify_http_401_error(self):
        """Test classification of 401 Unauthorized errors."""
        exception = Exception("401 Unauthorized")
        assert classify_auth_error(exception) == "http_401"

        exception = Exception("unauthorized access")
        assert classify_auth_error(exception) == "http_401"

    def test_classify_http_500_error(self):
        """Test classification of 500 Server errors."""
        exception = Exception("500 Internal Server Error")
        assert classify_auth_error(exception) == "http_500"

        exception = Exception("internal server error occurred")
        assert classify_auth_error(exception) == "http_500"

    def test_classify_timeout_error(self):
        """Test classification of timeout errors."""
        exception = Exception("Request timeout")
        assert classify_auth_error(exception) == "timeout"

        exception = Exception("connection timed out")
        assert classify_auth_error(exception) == "timeout"

    def test_classify_connection_error(self):
        """Test classification of connection errors."""
        exception = Exception("Connection refused")
        assert classify_auth_error(exception) == "connection_error"

        exception = Exception("network unreachable")
        assert classify_auth_error(exception) == "connection_error"

    def test_classify_ssl_error(self):
        """Test classification of SSL/TLS errors."""
        exception = Exception("SSL handshake failed")
        assert classify_auth_error(exception) == "ssl_error"

        exception = Exception("certificate verification failed")
        assert classify_auth_error(exception) == "ssl_error"

    def test_classify_invalid_json_error(self):
        """Test classification of JSON parsing errors."""
        exception = Exception("Invalid JSON response")
        assert classify_auth_error(exception) == "invalid_json"

        exception = Exception("Failed to decode JSON")
        assert classify_auth_error(exception) == "invalid_json"

    def test_classify_missing_token_error(self):
        """Test classification of missing access_token errors."""
        exception = Exception("access_token not found in response")
        assert classify_auth_error(exception) == "missing_token"

    def test_classify_unknown_error(self):
        """Test classification of unknown errors."""
        exception = Exception("Something weird happened")
        assert classify_auth_error(exception) == "unknown"

    def test_classify_httpx_status_error(self):
        """Test classification with httpx.HTTPStatusError."""
        # Mock httpx.HTTPStatusError
        mock_response = MagicMock()
        mock_response.status_code = 401
        exception = httpx.HTTPStatusError(
            "401 Unauthorized",
            request=MagicMock(),
            response=mock_response
        )
        assert classify_auth_error(exception) == "http_401"


class TestGetAllMetrics:
    """Test get_all_metrics() helper function."""

    def test_get_all_metrics_returns_dict(self):
        """Verify get_all_metrics() returns dictionary."""
        metrics = get_all_metrics()
        assert isinstance(metrics, dict)

    def test_get_all_metrics_contains_all_metrics(self):
        """Verify get_all_metrics() returns all 9 metrics."""
        metrics = get_all_metrics()
        assert len(metrics) == 9

        # Verify all metric keys exist
        expected_keys = [
            "auth_token_requests_total",
            "auth_token_acquisition_duration",
            "auth_token_source_total",
            "auth_token_refresh_total",
            "auth_token_refresh_duration",
            "auth_token_ttl",
            "auth_token_validation_total",
            "auth_token_cache_hit_rate",
            "auth_errors_total",
        ]
        for key in expected_keys:
            assert key in metrics

    def test_get_all_metrics_returns_metric_objects(self):
        """Verify get_all_metrics() returns actual metric objects."""
        metrics = get_all_metrics()

        # Verify metrics are Prometheus metric objects
        assert metrics["auth_token_requests_total"] == auth_token_requests_total
        assert metrics["auth_token_acquisition_duration"] == auth_token_acquisition_duration
        assert metrics["auth_token_ttl"] == auth_token_ttl


class TestMetricsIntegration:
    """Integration tests для complete metrics workflow."""

    def test_metrics_workflow_cache_hit(self):
        """Test complete metrics workflow for cache hit scenario."""
        # Simulate cache hit scenario
        auth_token_source_total.labels(source="cache").inc()
        auth_token_validation_total.labels(result="valid").inc()
        auth_token_ttl.set(1500)  # 25 minutes remaining

        # No refresh needed, so no acquisition duration recorded

    def test_metrics_workflow_token_refresh_success(self):
        """Test complete metrics workflow for successful token refresh."""
        # Simulate token refresh scenario
        auth_token_source_total.labels(source="fresh_request").inc()
        auth_token_validation_total.labels(result="expired").inc()
        auth_token_refresh_total.labels(status="success", trigger="expired").inc()
        auth_token_refresh_duration.observe(0.25)
        auth_token_acquisition_duration.observe(0.3)
        auth_token_requests_total.labels(status="success", error_type="").inc()
        auth_token_ttl.set(1800)  # Fresh token, 30 minutes

    def test_metrics_workflow_token_refresh_failure(self):
        """Test complete metrics workflow for failed token refresh."""
        # Simulate refresh failure scenario
        auth_token_source_total.labels(source="fresh_request").inc()
        auth_token_validation_total.labels(result="missing").inc()
        auth_token_refresh_total.labels(status="failure", trigger="manual").inc()
        auth_token_refresh_duration.observe(5.0)  # Slow failure
        auth_token_acquisition_duration.observe(5.0)
        auth_token_requests_total.labels(status="failure", error_type="http_500").inc()
        auth_errors_total.labels(
            error_type="http_500",
            admin_module_url="http://admin_module:8000"
        ).inc()
        auth_token_ttl.set(0)  # No token

    def test_metrics_workflow_proactive_refresh(self):
        """Test complete metrics workflow for proactive token refresh."""
        # Simulate proactive refresh (< 5 minutes until expiry)
        auth_token_source_total.labels(source="fresh_request").inc()
        auth_token_validation_total.labels(result="expiring_soon").inc()
        auth_token_refresh_total.labels(status="success", trigger="expiring_soon").inc()
        auth_token_refresh_duration.observe(0.2)
        auth_token_acquisition_duration.observe(0.25)
        auth_token_requests_total.labels(status="success", error_type="").inc()
        auth_token_ttl.set(1800)


class TestMetricsDocumentation:
    """Test that metrics have proper documentation."""

    def test_auth_token_requests_total_documentation(self):
        """Verify auth_token_requests_total has documentation."""
        assert auth_token_requests_total._documentation is not None
        assert "JWT token acquisition" in auth_token_requests_total._documentation

    def test_auth_token_acquisition_duration_documentation(self):
        """Verify auth_token_acquisition_duration has documentation."""
        assert auth_token_acquisition_duration._documentation is not None
        assert "latency" in auth_token_acquisition_duration._documentation.lower()

    def test_auth_token_source_total_documentation(self):
        """Verify auth_token_source_total has documentation."""
        assert auth_token_source_total._documentation is not None
        assert "cache" in auth_token_source_total._documentation.lower()

    def test_auth_token_ttl_documentation(self):
        """Verify auth_token_ttl has documentation."""
        assert auth_token_ttl._documentation is not None
        assert "expiration" in auth_token_ttl._documentation.lower()
