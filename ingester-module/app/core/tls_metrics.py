"""
TLS/mTLS Prometheus metrics для мониторинга encryption performance.

Provides instrumentation для TLS handshake performance, certificate health,
и connection management в OAuth 2.0 authentication flow.

Sprint 23 Phase 2: mTLS Performance Metrics Implementation.
"""

from prometheus_client import Counter, Histogram, Gauge

# ================================================================================
# TLS Handshake Performance Metrics
# ================================================================================

tls_handshake_duration = Histogram(
    'tls_handshake_duration_seconds',
    'TLS handshake duration in seconds',
    ['protocol', 'cipher_suite'],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0]
)
"""
TLS handshake latency histogram.

Labels:
    protocol: "TLSv1.3" | "TLSv1.2" | "unknown"
    cipher_suite: Negotiated cipher suite name (e.g., "TLS_AES_256_GCM_SHA384")

Buckets optimized для modern TLS handshake:
- 0.01s (10ms): Excellent TLS 1.3 performance
- 0.025s (25ms): Good TLS 1.3 or excellent TLS 1.2
- 0.05s (50ms): Acceptable TLS 1.2 performance
- 0.1s (100ms): Degraded performance (network latency)
- 0.25s (250ms): Poor performance
- 0.5s (500ms): Critical latency
- 1.0s: Unacceptable (investigate)
- 2.0s: Timeout scenarios

PromQL queries:
    # p95 handshake latency by protocol
    histogram_quantile(0.95,
      sum(rate(tls_handshake_duration_seconds_bucket[5m])) by (protocol, le)
    )

    # Compare TLS 1.3 vs 1.2 performance
    histogram_quantile(0.95,
      rate(tls_handshake_duration_seconds_bucket{protocol="TLSv1.3"}[5m])
    )
    vs
    histogram_quantile(0.95,
      rate(tls_handshake_duration_seconds_bucket{protocol="TLSv1.2"}[5m])
    )
"""

tls_handshake_total = Counter(
    'tls_handshake_total',
    'TLS handshake attempts and results',
    ['status', 'error_type']
)
"""
TLS handshake results counter.

Labels:
    status: "success" | "failure"
    error_type: "" (на success) | "cert_expired" | "cert_invalid" |
                "cert_untrusted" | "protocol_error" | "timeout" |
                "cipher_mismatch"

PromQL queries:
    # Handshake success rate
    (
      rate(tls_handshake_total{status="success"}[5m])
      /
      rate(tls_handshake_total[5m])
    ) * 100

    # Handshake errors by type
    sum(rate(tls_handshake_total{status="failure"}[5m])) by (error_type)
"""

# ================================================================================
# TLS Connection Management Metrics
# ================================================================================

tls_connections_active = Gauge(
    'tls_connections_active',
    'Currently active TLS connections',
    ['protocol']
)
"""
Active TLS connections gauge.

Labels:
    protocol: "TLSv1.3" | "TLSv1.2"

Value: Number of active encrypted connections

PromQL queries:
    # Total active connections
    sum(tls_connections_active)

    # Active connections by protocol
    tls_connections_active{protocol="TLSv1.3"}
"""

tls_connection_reuse_total = Counter(
    'tls_connection_reuse_total',
    'TLS connection reuse from pool',
    ['reused']
)
"""
Connection reuse counter для tracking pool efficiency.

Labels:
    reused: "true" | "false"

PromQL queries:
    # Connection reuse rate
    (
      rate(tls_connection_reuse_total{reused="true"}[5m])
      /
      rate(tls_connection_reuse_total[5m])
    ) * 100
"""

# ================================================================================
# Certificate Health Metrics
# ================================================================================

tls_certificate_expiry_days = Gauge(
    'tls_certificate_expiry_days',
    'Days until certificate expiration',
    ['cert_type', 'subject']
)
"""
Certificate expiration gauge.

Labels:
    cert_type: "ca" | "client"
    subject: Certificate subject DN (RFC 4514 format)

Value: Days until expiration (negative if expired)

Alert thresholds:
    - <30 days: Warning (plan renewal)
    - <7 days: Critical (immediate action required)
    - <0 days: Certificate expired (service degradation)

PromQL queries:
    # Certificates expiring within 30 days
    tls_certificate_expiry_days < 30

    # Expired certificates
    tls_certificate_expiry_days < 0

    # Group by certificate type
    tls_certificate_expiry_days{cert_type="client"}
"""

tls_certificate_validation_total = Counter(
    'tls_certificate_validation_total',
    'Certificate validation results',
    ['result']
)
"""
Certificate validation results counter.

Labels:
    result: "valid" | "expired" | "invalid" | "untrusted" | "revoked"

PromQL queries:
    # Validation success rate
    (
      rate(tls_certificate_validation_total{result="valid"}[5m])
      /
      rate(tls_certificate_validation_total[5m])
    ) * 100

    # Validation failures by reason
    sum(rate(tls_certificate_validation_total{result!="valid"}[5m])) by (result)
"""

# ================================================================================
# TLS Protocol Distribution Metrics
# ================================================================================

tls_protocol_usage_total = Counter(
    'tls_protocol_usage_total',
    'TLS protocol version usage',
    ['protocol']
)
"""
TLS protocol version usage counter.

Labels:
    protocol: "TLSv1.3" | "TLSv1.2" | "TLSv1.1" | "TLSv1.0" (legacy)

Security note: TLSv1.0 и TLSv1.1 deprecated и insecure

PromQL queries:
    # Protocol distribution
    sum(rate(tls_protocol_usage_total[5m])) by (protocol)

    # Percentage using modern protocols (TLS 1.2+)
    (
      sum(rate(tls_protocol_usage_total{protocol=~"TLSv1\\.[23]"}[5m]))
      /
      sum(rate(tls_protocol_usage_total[5m]))
    ) * 100
"""

tls_cipher_suite_usage_total = Counter(
    'tls_cipher_suite_usage_total',
    'Cipher suite negotiation results',
    ['cipher_suite', 'protocol']
)
"""
Cipher suite usage counter.

Labels:
    cipher_suite: Negotiated cipher suite (e.g., "TLS_AES_256_GCM_SHA384")
    protocol: TLS protocol version

Security monitoring:
    - Track usage of weak ciphers (CBC mode, RC4, MD5)
    - Prefer AEAD ciphers (GCM, ChaCha20-Poly1305)

PromQL queries:
    # Most used cipher suites
    topk(5, sum(rate(tls_cipher_suite_usage_total[5m])) by (cipher_suite))

    # AEAD cipher usage percentage
    (
      sum(rate(tls_cipher_suite_usage_total{cipher_suite=~".*GCM.*|.*CHACHA20.*"}[5m]))
      /
      sum(rate(tls_cipher_suite_usage_total[5m]))
    ) * 100
"""

# ================================================================================
# Helper Functions
# ================================================================================

def extract_tls_protocol(ssl_object) -> str:
    """
    Extract TLS protocol version from SSL object.

    Args:
        ssl_object: SSL socket or context object

    Returns:
        Protocol version string: "TLSv1.3", "TLSv1.2", or "unknown"

    Example:
        >>> extract_tls_protocol(ssl_sock)
        'TLSv1.3'
    """
    try:
        if hasattr(ssl_object, 'version'):
            version = ssl_object.version()
            if version:
                return version
        return "unknown"
    except Exception:
        return "unknown"


def extract_cipher_suite(ssl_object) -> str:
    """
    Extract negotiated cipher suite from SSL object.

    Args:
        ssl_object: SSL socket or context object

    Returns:
        Cipher suite name or "unknown"

    Example:
        >>> extract_cipher_suite(ssl_sock)
        'TLS_AES_256_GCM_SHA384'
    """
    try:
        if hasattr(ssl_object, 'cipher'):
            cipher_info = ssl_object.cipher()
            if cipher_info and len(cipher_info) > 0:
                return cipher_info[0]  # Cipher name
        return "unknown"
    except Exception:
        return "unknown"


def classify_tls_error(exception: Exception) -> str:
    """
    Classify TLS exception для error_type label.

    Args:
        exception: Exception raised during TLS handshake

    Returns:
        Error type string для Prometheus label

    Error Types:
        - "cert_expired": Certificate has expired
        - "cert_invalid": Invalid certificate format or signature
        - "cert_untrusted": Certificate not trusted (CA issue)
        - "protocol_error": TLS protocol negotiation failed
        - "cipher_mismatch": No common cipher suites
        - "timeout": Handshake timeout
        - "unknown": Unclassified TLS error

    Example:
        >>> from ssl import SSLError
        >>> classify_tls_error(SSLError("certificate verify failed"))
        'cert_invalid'
    """
    error_str = str(exception).lower()

    # Certificate errors
    if "expired" in error_str or "certificate expired" in error_str:
        return "cert_expired"
    if "verify failed" in error_str or "verification failed" in error_str:
        return "cert_invalid"
    if "untrusted" in error_str or "unknown ca" in error_str:
        return "cert_untrusted"

    # Protocol errors
    if "protocol" in error_str or "version" in error_str:
        return "protocol_error"
    if "cipher" in error_str or "no shared cipher" in error_str:
        return "cipher_mismatch"

    # Timeout errors
    if "timeout" in error_str or "timed out" in error_str:
        return "timeout"

    return "unknown"


# ================================================================================
# Metrics Export Helper
# ================================================================================

def get_all_tls_metrics() -> dict:
    """
    Get all TLS metrics для testing и debugging.

    Returns:
        Dictionary с current metric values

    Example:
        >>> metrics = get_all_tls_metrics()
        >>> print(metrics['tls_handshake_total'])
        Counter for TLS handshake results
    """
    return {
        "tls_handshake_duration": tls_handshake_duration,
        "tls_handshake_total": tls_handshake_total,
        "tls_connections_active": tls_connections_active,
        "tls_connection_reuse_total": tls_connection_reuse_total,
        "tls_certificate_expiry_days": tls_certificate_expiry_days,
        "tls_certificate_validation_total": tls_certificate_validation_total,
        "tls_protocol_usage_total": tls_protocol_usage_total,
        "tls_cipher_suite_usage_total": tls_cipher_suite_usage_total,
    }
