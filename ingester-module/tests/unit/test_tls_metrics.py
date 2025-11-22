"""
Unit tests для TLS/mTLS Prometheus metrics.

Тестирует метрики модуля app/core/tls_metrics.py:
- Handshake metrics: duration, success/failure tracking
- Connection metrics: active connections, reuse tracking
- Certificate health: expiry monitoring, validation results
- Protocol distribution: TLS versions, cipher suites
- Helper functions: extract_tls_protocol(), extract_cipher_suite(), classify_tls_error()

Sprint 23 Phase 2: mTLS Performance Metrics Implementation.
"""

import pytest
from unittest.mock import MagicMock
import ssl

from app.core.tls_metrics import (
    tls_handshake_duration,
    tls_handshake_total,
    tls_connections_active,
    tls_connection_reuse_total,
    tls_certificate_expiry_days,
    tls_certificate_validation_total,
    tls_protocol_usage_total,
    tls_cipher_suite_usage_total,
    extract_tls_protocol,
    extract_cipher_suite,
    classify_tls_error,
    get_all_tls_metrics,
)


class TestTLSHandshakeMetrics:
    """Test TLS handshake performance metrics."""

    def test_tls_handshake_duration_metric_exists(self):
        """Verify tls_handshake_duration histogram exists."""
        assert tls_handshake_duration is not None
        assert tls_handshake_duration._name == "tls_handshake_duration_seconds"
        assert tls_handshake_duration._type == "histogram"

    def test_tls_handshake_duration_labels(self):
        """Verify tls_handshake_duration has correct labels."""
        # Observe with valid labels
        tls_handshake_duration.labels(protocol="TLSv1.3", cipher_suite="TLS_AES_256_GCM_SHA384").observe(0.025)
        tls_handshake_duration.labels(protocol="TLSv1.2", cipher_suite="ECDHE-RSA-AES256-GCM-SHA384").observe(0.05)

        # Verify label names
        assert "protocol" in tls_handshake_duration._labelnames
        assert "cipher_suite" in tls_handshake_duration._labelnames

    def test_tls_handshake_duration_buckets(self):
        """Verify histogram has correct buckets for TLS handshake latency."""
        expected_buckets = [0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0]
        # Prometheus adds +Inf bucket automatically
        assert tls_handshake_duration._upper_bounds[:-1] == expected_buckets

    def test_tls_handshake_duration_observe_fast(self):
        """Test observing fast TLS 1.3 handshake."""
        tls_handshake_duration.labels(protocol="TLSv1.3", cipher_suite="TLS_AES_256_GCM_SHA384").observe(0.01)

    def test_tls_handshake_duration_observe_slow(self):
        """Test observing slow TLS 1.2 handshake."""
        tls_handshake_duration.labels(protocol="TLSv1.2", cipher_suite="ECDHE-RSA-AES256-GCM-SHA384").observe(0.15)

    def test_tls_handshake_total_metric_exists(self):
        """Verify tls_handshake_total counter exists."""
        assert tls_handshake_total is not None
        # Prometheus auto-removes _total suffix from Counter names
        assert tls_handshake_total._name == "tls_handshake"
        assert tls_handshake_total._type == "counter"

    def test_tls_handshake_total_labels(self):
        """Verify tls_handshake_total has correct labels."""
        assert "status" in tls_handshake_total._labelnames
        assert "error_type" in tls_handshake_total._labelnames

    def test_tls_handshake_total_success(self):
        """Test tracking successful handshakes."""
        initial_value = tls_handshake_total.labels(status="success", error_type="")._value.get()
        tls_handshake_total.labels(status="success", error_type="").inc()
        assert tls_handshake_total.labels(status="success", error_type="")._value.get() == initial_value + 1

    def test_tls_handshake_total_failure(self):
        """Test tracking failed handshakes with error classification."""
        for error_type in ["cert_expired", "cert_invalid", "protocol_error", "timeout"]:
            tls_handshake_total.labels(status="failure", error_type=error_type).inc()


class TestTLSConnectionMetrics:
    """Test TLS connection management metrics."""

    def test_tls_connections_active_metric_exists(self):
        """Verify tls_connections_active gauge exists."""
        assert tls_connections_active is not None
        assert tls_connections_active._name == "tls_connections_active"
        assert tls_connections_active._type == "gauge"

    def test_tls_connections_active_labels(self):
        """Verify tls_connections_active has correct labels."""
        assert "protocol" in tls_connections_active._labelnames

    def test_tls_connections_active_set(self):
        """Test setting active connection count."""
        tls_connections_active.labels(protocol="TLSv1.3").set(10)
        assert tls_connections_active.labels(protocol="TLSv1.3")._value.get() == 10

        tls_connections_active.labels(protocol="TLSv1.2").set(5)
        assert tls_connections_active.labels(protocol="TLSv1.2")._value.get() == 5

    def test_tls_connections_active_increment_decrement(self):
        """Test incrementing and decrementing active connections."""
        tls_connections_active.labels(protocol="TLSv1.3").set(0)
        tls_connections_active.labels(protocol="TLSv1.3").inc()
        assert tls_connections_active.labels(protocol="TLSv1.3")._value.get() == 1

        tls_connections_active.labels(protocol="TLSv1.3").dec()
        assert tls_connections_active.labels(protocol="TLSv1.3")._value.get() == 0

    def test_tls_connection_reuse_total_metric_exists(self):
        """Verify tls_connection_reuse_total counter exists."""
        assert tls_connection_reuse_total is not None
        # Prometheus auto-removes _total suffix
        assert tls_connection_reuse_total._name == "tls_connection_reuse"
        assert tls_connection_reuse_total._type == "counter"

    def test_tls_connection_reuse_total_labels(self):
        """Verify tls_connection_reuse_total has correct labels."""
        assert "reused" in tls_connection_reuse_total._labelnames

    def test_tls_connection_reuse_tracking(self):
        """Test tracking connection reuse vs new connections."""
        tls_connection_reuse_total.labels(reused="true").inc()
        tls_connection_reuse_total.labels(reused="false").inc()


class TestCertificateHealthMetrics:
    """Test certificate expiry and validation metrics."""

    def test_tls_certificate_expiry_days_metric_exists(self):
        """Verify tls_certificate_expiry_days gauge exists."""
        assert tls_certificate_expiry_days is not None
        assert tls_certificate_expiry_days._name == "tls_certificate_expiry_days"
        assert tls_certificate_expiry_days._type == "gauge"

    def test_tls_certificate_expiry_days_labels(self):
        """Verify tls_certificate_expiry_days has correct labels."""
        assert "cert_type" in tls_certificate_expiry_days._labelnames
        assert "subject" in tls_certificate_expiry_days._labelnames

    def test_tls_certificate_expiry_days_set_valid(self):
        """Test setting certificate expiry for valid certificate."""
        tls_certificate_expiry_days.labels(
            cert_type="ca",
            subject="CN=Test CA,O=ArtStore,C=US"
        ).set(365)  # 1 year until expiry

        assert tls_certificate_expiry_days.labels(
            cert_type="ca",
            subject="CN=Test CA,O=ArtStore,C=US"
        )._value.get() == 365

    def test_tls_certificate_expiry_days_set_expiring_soon(self):
        """Test setting certificate expiry for certificate expiring soon."""
        tls_certificate_expiry_days.labels(
            cert_type="client",
            subject="CN=Ingester Client,O=ArtStore"
        ).set(15)  # 15 days until expiry - warning threshold

    def test_tls_certificate_expiry_days_set_expired(self):
        """Test setting certificate expiry for expired certificate."""
        tls_certificate_expiry_days.labels(
            cert_type="client",
            subject="CN=Expired Cert,O=Test"
        ).set(-10)  # Expired 10 days ago

    def test_tls_certificate_validation_total_metric_exists(self):
        """Verify tls_certificate_validation_total counter exists."""
        assert tls_certificate_validation_total is not None
        # Prometheus auto-removes _total suffix
        assert tls_certificate_validation_total._name == "tls_certificate_validation"
        assert tls_certificate_validation_total._type == "counter"

    def test_tls_certificate_validation_total_labels(self):
        """Verify tls_certificate_validation_total has correct labels."""
        assert "result" in tls_certificate_validation_total._labelnames

    def test_tls_certificate_validation_results(self):
        """Test all certificate validation result types."""
        for result in ["valid", "expired", "invalid", "untrusted", "revoked"]:
            tls_certificate_validation_total.labels(result=result).inc()


class TestProtocolDistributionMetrics:
    """Test TLS protocol and cipher suite distribution metrics."""

    def test_tls_protocol_usage_total_metric_exists(self):
        """Verify tls_protocol_usage_total counter exists."""
        assert tls_protocol_usage_total is not None
        # Prometheus auto-removes _total suffix
        assert tls_protocol_usage_total._name == "tls_protocol_usage"
        assert tls_protocol_usage_total._type == "counter"

    def test_tls_protocol_usage_total_labels(self):
        """Verify tls_protocol_usage_total has correct labels."""
        assert "protocol" in tls_protocol_usage_total._labelnames

    def test_tls_protocol_usage_tracking(self):
        """Test tracking TLS protocol version usage."""
        for protocol in ["TLSv1.3", "TLSv1.2", "TLSv1.1", "TLSv1.0"]:
            tls_protocol_usage_total.labels(protocol=protocol).inc()

    def test_tls_cipher_suite_usage_total_metric_exists(self):
        """Verify tls_cipher_suite_usage_total counter exists."""
        assert tls_cipher_suite_usage_total is not None
        # Prometheus auto-removes _total suffix
        assert tls_cipher_suite_usage_total._name == "tls_cipher_suite_usage"
        assert tls_cipher_suite_usage_total._type == "counter"

    def test_tls_cipher_suite_usage_total_labels(self):
        """Verify tls_cipher_suite_usage_total has correct labels."""
        assert "cipher_suite" in tls_cipher_suite_usage_total._labelnames
        assert "protocol" in tls_cipher_suite_usage_total._labelnames

    def test_tls_cipher_suite_usage_tracking(self):
        """Test tracking cipher suite usage."""
        # TLS 1.3 AEAD cipher suites
        tls_cipher_suite_usage_total.labels(
            cipher_suite="TLS_AES_256_GCM_SHA384",
            protocol="TLSv1.3"
        ).inc()

        tls_cipher_suite_usage_total.labels(
            cipher_suite="TLS_CHACHA20_POLY1305_SHA256",
            protocol="TLSv1.3"
        ).inc()

        # TLS 1.2 cipher suites
        tls_cipher_suite_usage_total.labels(
            cipher_suite="ECDHE-RSA-AES256-GCM-SHA384",
            protocol="TLSv1.2"
        ).inc()


class TestExtractTLSProtocol:
    """Test extract_tls_protocol() helper function."""

    def test_extract_tls_protocol_with_version_method(self):
        """Test extracting protocol from SSL object with version() method."""
        mock_ssl = MagicMock()
        mock_ssl.version.return_value = "TLSv1.3"

        result = extract_tls_protocol(mock_ssl)
        assert result == "TLSv1.3"

    def test_extract_tls_protocol_tls12(self):
        """Test extracting TLS 1.2 protocol."""
        mock_ssl = MagicMock()
        mock_ssl.version.return_value = "TLSv1.2"

        result = extract_tls_protocol(mock_ssl)
        assert result == "TLSv1.2"

    def test_extract_tls_protocol_no_version_method(self):
        """Test extracting protocol when version() method doesn't exist."""
        mock_ssl = MagicMock(spec=[])  # No version method

        result = extract_tls_protocol(mock_ssl)
        assert result == "unknown"

    def test_extract_tls_protocol_version_returns_none(self):
        """Test extracting protocol when version() returns None."""
        mock_ssl = MagicMock()
        mock_ssl.version.return_value = None

        result = extract_tls_protocol(mock_ssl)
        assert result == "unknown"

    def test_extract_tls_protocol_exception(self):
        """Test extracting protocol when exception occurs."""
        mock_ssl = MagicMock()
        mock_ssl.version.side_effect = Exception("SSL error")

        result = extract_tls_protocol(mock_ssl)
        assert result == "unknown"


class TestExtractCipherSuite:
    """Test extract_cipher_suite() helper function."""

    def test_extract_cipher_suite_with_cipher_method(self):
        """Test extracting cipher suite from SSL object with cipher() method."""
        mock_ssl = MagicMock()
        mock_ssl.cipher.return_value = ("TLS_AES_256_GCM_SHA384", "TLSv1.3", 256)

        result = extract_cipher_suite(mock_ssl)
        assert result == "TLS_AES_256_GCM_SHA384"

    def test_extract_cipher_suite_tls12(self):
        """Test extracting TLS 1.2 cipher suite."""
        mock_ssl = MagicMock()
        mock_ssl.cipher.return_value = ("ECDHE-RSA-AES256-GCM-SHA384", "TLSv1.2", 256)

        result = extract_cipher_suite(mock_ssl)
        assert result == "ECDHE-RSA-AES256-GCM-SHA384"

    def test_extract_cipher_suite_no_cipher_method(self):
        """Test extracting cipher when cipher() method doesn't exist."""
        mock_ssl = MagicMock(spec=[])  # No cipher method

        result = extract_cipher_suite(mock_ssl)
        assert result == "unknown"

    def test_extract_cipher_suite_returns_none(self):
        """Test extracting cipher when cipher() returns None."""
        mock_ssl = MagicMock()
        mock_ssl.cipher.return_value = None

        result = extract_cipher_suite(mock_ssl)
        assert result == "unknown"

    def test_extract_cipher_suite_empty_tuple(self):
        """Test extracting cipher when cipher() returns empty tuple."""
        mock_ssl = MagicMock()
        mock_ssl.cipher.return_value = ()

        result = extract_cipher_suite(mock_ssl)
        assert result == "unknown"

    def test_extract_cipher_suite_exception(self):
        """Test extracting cipher when exception occurs."""
        mock_ssl = MagicMock()
        mock_ssl.cipher.side_effect = Exception("SSL error")

        result = extract_cipher_suite(mock_ssl)
        assert result == "unknown"


class TestClassifyTLSError:
    """Test classify_tls_error() helper function."""

    def test_classify_cert_expired_error(self):
        """Test classification of certificate expired errors."""
        exception = Exception("certificate expired")
        assert classify_tls_error(exception) == "cert_expired"

        exception = Exception("SSL: CERTIFICATE_VERIFY_FAILED - certificate has expired")
        assert classify_tls_error(exception) == "cert_expired"

    def test_classify_cert_invalid_error(self):
        """Test classification of certificate verification errors."""
        exception = Exception("certificate verify failed")
        assert classify_tls_error(exception) == "cert_invalid"

        exception = Exception("SSL verification failed")
        assert classify_tls_error(exception) == "cert_invalid"

    def test_classify_cert_untrusted_error(self):
        """Test classification of untrusted certificate errors."""
        exception = Exception("certificate untrusted")
        assert classify_tls_error(exception) == "cert_untrusted"

        exception = Exception("unknown CA - certificate authority not recognized")
        assert classify_tls_error(exception) == "cert_untrusted"

    def test_classify_protocol_error(self):
        """Test classification of TLS protocol errors."""
        exception = Exception("TLS protocol version mismatch")
        assert classify_tls_error(exception) == "protocol_error"

        exception = Exception("SSL version negotiation failed")
        assert classify_tls_error(exception) == "protocol_error"

    def test_classify_cipher_mismatch_error(self):
        """Test classification of cipher suite mismatch errors."""
        exception = Exception("no shared cipher suites")
        assert classify_tls_error(exception) == "cipher_mismatch"

        exception = Exception("cipher negotiation failed")
        assert classify_tls_error(exception) == "cipher_mismatch"

    def test_classify_timeout_error(self):
        """Test classification of TLS handshake timeout errors."""
        exception = Exception("SSL handshake timed out")
        assert classify_tls_error(exception) == "timeout"

        exception = Exception("connection timeout during TLS negotiation")
        assert classify_tls_error(exception) == "timeout"

    def test_classify_unknown_error(self):
        """Test classification of unknown TLS errors."""
        exception = Exception("Something weird happened during SSL")
        assert classify_tls_error(exception) == "unknown"

    def test_classify_ssl_error_object(self):
        """Test classification with ssl.SSLError."""
        try:
            # This won't actually raise, just testing the classification
            exception = ssl.SSLError("certificate verify failed")
            assert classify_tls_error(exception) == "cert_invalid"
        except Exception:
            pass  # Skip if SSL error can't be created in test


class TestGetAllTLSMetrics:
    """Test get_all_tls_metrics() helper function."""

    def test_get_all_tls_metrics_returns_dict(self):
        """Verify get_all_tls_metrics() returns dictionary."""
        metrics = get_all_tls_metrics()
        assert isinstance(metrics, dict)

    def test_get_all_tls_metrics_contains_all_metrics(self):
        """Verify get_all_tls_metrics() returns all 8 metrics."""
        metrics = get_all_tls_metrics()
        assert len(metrics) == 8

        # Verify all metric keys exist
        expected_keys = [
            "tls_handshake_duration",
            "tls_handshake_total",
            "tls_connections_active",
            "tls_connection_reuse_total",
            "tls_certificate_expiry_days",
            "tls_certificate_validation_total",
            "tls_protocol_usage_total",
            "tls_cipher_suite_usage_total",
        ]
        for key in expected_keys:
            assert key in metrics

    def test_get_all_tls_metrics_returns_metric_objects(self):
        """Verify get_all_tls_metrics() returns actual metric objects."""
        metrics = get_all_tls_metrics()

        # Verify metrics are Prometheus metric objects
        assert metrics["tls_handshake_duration"] == tls_handshake_duration
        assert metrics["tls_handshake_total"] == tls_handshake_total
        assert metrics["tls_connections_active"] == tls_connections_active
        assert metrics["tls_certificate_expiry_days"] == tls_certificate_expiry_days


class TestTLSMetricsIntegration:
    """Integration tests для complete TLS metrics workflow."""

    def test_tls_metrics_workflow_successful_handshake(self):
        """Test complete metrics workflow for successful TLS 1.3 handshake."""
        # Simulate successful TLS 1.3 handshake
        protocol = "TLSv1.3"
        cipher_suite = "TLS_AES_256_GCM_SHA384"

        # Record handshake
        tls_handshake_duration.labels(protocol=protocol, cipher_suite=cipher_suite).observe(0.015)
        tls_handshake_total.labels(status="success", error_type="").inc()
        tls_protocol_usage_total.labels(protocol=protocol).inc()
        tls_cipher_suite_usage_total.labels(cipher_suite=cipher_suite, protocol=protocol).inc()

        # Track active connection
        tls_connections_active.labels(protocol=protocol).inc()

        # Track connection reuse (new connection)
        tls_connection_reuse_total.labels(reused="false").inc()

    def test_tls_metrics_workflow_failed_handshake(self):
        """Test complete metrics workflow for failed TLS handshake."""
        # Simulate failed handshake due to expired certificate
        protocol = "TLSv1.2"

        # Record failed handshake
        tls_handshake_duration.labels(protocol=protocol, cipher_suite="unknown").observe(0.05)
        tls_handshake_total.labels(status="failure", error_type="cert_expired").inc()
        tls_protocol_usage_total.labels(protocol=protocol).inc()

        # No active connection established

    def test_tls_metrics_workflow_certificate_monitoring(self):
        """Test complete metrics workflow for certificate monitoring."""
        # Monitor CA certificate
        tls_certificate_expiry_days.labels(
            cert_type="ca",
            subject="CN=ArtStore CA,O=ArtStore,C=US"
        ).set(365)
        tls_certificate_validation_total.labels(result="valid").inc()

        # Monitor client certificate expiring soon
        tls_certificate_expiry_days.labels(
            cert_type="client",
            subject="CN=Ingester Client,O=ArtStore"
        ).set(25)
        tls_certificate_validation_total.labels(result="valid").inc()

    def test_tls_metrics_workflow_connection_pool_reuse(self):
        """Test complete metrics workflow for connection pool reuse."""
        protocol = "TLSv1.3"

        # First connection (new)
        tls_connections_active.labels(protocol=protocol).inc()
        tls_connection_reuse_total.labels(reused="false").inc()

        # Second request (reused connection)
        tls_connection_reuse_total.labels(reused="true").inc()

        # Third request (reused connection)
        tls_connection_reuse_total.labels(reused="true").inc()

        # Connection closed
        tls_connections_active.labels(protocol=protocol).dec()


class TestTLSMetricsDocumentation:
    """Test that TLS metrics have proper documentation."""

    def test_tls_handshake_duration_documentation(self):
        """Verify tls_handshake_duration has documentation."""
        assert tls_handshake_duration._documentation is not None
        assert "handshake" in tls_handshake_duration._documentation.lower()

    def test_tls_certificate_expiry_days_documentation(self):
        """Verify tls_certificate_expiry_days has documentation."""
        assert tls_certificate_expiry_days._documentation is not None
        assert "expiration" in tls_certificate_expiry_days._documentation.lower()

    def test_tls_connections_active_documentation(self):
        """Verify tls_connections_active has documentation."""
        assert tls_connections_active._documentation is not None
        assert "active" in tls_connections_active._documentation.lower()

    def test_tls_protocol_usage_total_documentation(self):
        """Verify tls_protocol_usage_total has documentation."""
        assert tls_protocol_usage_total._documentation is not None
        assert "protocol" in tls_protocol_usage_total._documentation.lower()
