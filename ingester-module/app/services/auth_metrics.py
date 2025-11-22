"""
JWT Authentication Prometheus metrics для AuthService.

Provides comprehensive instrumentation для OAuth 2.0 Client Credentials
authentication flow, включая token acquisition, refresh, validation и errors.

Sprint 23 Phase 1: JWT Authentication Metrics Implementation.
"""

from prometheus_client import Counter, Histogram, Gauge

# ================================================================================
# Token Acquisition Metrics
# ================================================================================

auth_token_requests_total = Counter(
    'auth_token_requests_total',
    'Total JWT token acquisition requests',
    ['status', 'error_type']
)
"""
Total JWT token requests counter.

Labels:
    status: "success" | "failure"
    error_type: "" (на success) | "http_401" | "http_500" | "timeout" |
                "connection_error" | "invalid_json" | "missing_token"

Usage:
    auth_token_requests_total.labels(status="success", error_type="").inc()
    auth_token_requests_total.labels(status="failure", error_type="http_401").inc()
"""

auth_token_acquisition_duration = Histogram(
    'auth_token_acquisition_duration_seconds',
    'JWT token acquisition latency in seconds',
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0]
)
"""
Token acquisition duration histogram.

Buckets optimized для OAuth 2.0 flow latency:
- 0.1s: Excellent (cached or very fast network)
- 0.25s: Good (typical fast response)
- 0.5s: Acceptable (normal network latency)
- 1.0s: Degraded (slow Admin Module response)
- 2.5s: Poor (high latency or load)
- 5.0s: Critical (timeout threshold approaching)
- 10.0s: Timeout (default timeout limit)
- 30.0s: Extended timeout scenarios

PromQL queries:
    # p95 latency
    histogram_quantile(0.95, rate(auth_token_acquisition_duration_seconds_bucket[5m]))

    # p99 latency
    histogram_quantile(0.99, rate(auth_token_acquisition_duration_seconds_bucket[5m]))
"""

auth_token_source_total = Counter(
    'auth_token_source_total',
    'Token source: cache vs fresh request',
    ['source']
)
"""
Token source counter для tracking cache efficiency.

Labels:
    source: "cache" | "fresh_request"

PromQL queries:
    # Cache hit rate percentage
    (
      rate(auth_token_source_total{source="cache"}[5m])
      /
      rate(auth_token_source_total[5m])
    ) * 100
"""

# ================================================================================
# Token Refresh Metrics
# ================================================================================

auth_token_refresh_total = Counter(
    'auth_token_refresh_total',
    'Token refresh operations',
    ['status', 'trigger']
)
"""
Token refresh counter с детализацией по trigger reason.

Labels:
    status: "success" | "failure"
    trigger: "expiring_soon" (proactive refresh <5min) |
             "expired" (reactive refresh) |
             "manual" (forced refresh)

Usage:
    auth_token_refresh_total.labels(status="success", trigger="expiring_soon").inc()
"""

auth_token_refresh_duration = Histogram(
    'auth_token_refresh_duration_seconds',
    'Token refresh latency in seconds',
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)
"""
Token refresh duration histogram.

Similar buckets to acquisition, but typically faster due to
Admin Module caching и connection pool reuse.

PromQL queries:
    # Average refresh latency
    rate(auth_token_refresh_duration_seconds_sum[5m])
    /
    rate(auth_token_refresh_duration_seconds_count[5m])
"""

# ================================================================================
# Token Lifecycle Metrics
# ================================================================================

auth_token_ttl = Gauge(
    'auth_token_ttl_seconds',
    'Time until current token expiration in seconds'
)
"""
Token TTL (Time To Live) gauge.

Value: Seconds until token expires (0 if no token or expired)

PromQL queries:
    # Tokens expiring within 5 minutes
    auth_token_ttl_seconds < 300

    # Average TTL
    avg(auth_token_ttl_seconds)
"""

# ================================================================================
# Token Validation Metrics
# ================================================================================

auth_token_validation_total = Counter(
    'auth_token_validation_total',
    'Token validation check results',
    ['result']
)
"""
Token validation results counter.

Labels:
    result: "valid" | "expired" | "expiring_soon" | "missing"

Usage:
    auth_token_validation_total.labels(result="valid").inc()
    auth_token_validation_total.labels(result="expiring_soon").inc()
"""

auth_token_cache_hit_rate = Gauge(
    'auth_token_cache_hit_rate',
    'Token cache hit rate percentage (0-100)'
)
"""
Token cache hit rate gauge.

Value: Percentage (0-100) of requests served from cache

Calculation:
    (cache_hits / total_requests) * 100

Target: >80% для efficient token reuse
Warning: <60% indicates excessive token refreshes
"""

# ================================================================================
# Error Tracking Metrics
# ================================================================================

auth_errors_total = Counter(
    'auth_errors_total',
    'Authentication errors by type and Admin Module',
    ['error_type', 'admin_module_url']
)
"""
Authentication errors counter с детализацией по error type и Admin Module URL.

Labels:
    error_type: "http_401" | "http_500" | "timeout" | "connection_error" |
                "invalid_json" | "missing_token" | "ssl_error"
    admin_module_url: Admin Module base URL для tracking multi-instance errors

PromQL queries:
    # Total error rate
    rate(auth_errors_total[5m])

    # Errors by type
    sum(rate(auth_errors_total[5m])) by (error_type)

    # Errors by Admin Module instance
    sum(rate(auth_errors_total[5m])) by (admin_module_url)
"""

# ================================================================================
# Helper Functions
# ================================================================================

def calculate_cache_hit_rate(cache_hits: int, total_requests: int) -> float:
    """
    Calculate cache hit rate percentage.

    Args:
        cache_hits: Number of requests served from cache
        total_requests: Total number of token requests

    Returns:
        Cache hit rate as percentage (0-100)

    Example:
        >>> calculate_cache_hit_rate(850, 1000)
        85.0
    """
    if total_requests == 0:
        return 0.0
    return (cache_hits / total_requests) * 100


def classify_auth_error(exception: Exception) -> str:
    """
    Classify authentication exception для error_type label.

    Args:
        exception: Exception raised during authentication

    Returns:
        Error type string для Prometheus label

    Error Types:
        - "http_401": Unauthorized (invalid credentials)
        - "http_500": Server error from Admin Module
        - "timeout": Request timeout
        - "connection_error": Network connectivity issue
        - "invalid_json": Invalid JSON response from Admin Module
        - "missing_token": Response missing access_token field
        - "ssl_error": TLS/SSL handshake failure
        - "unknown": Unclassified error

    Example:
        >>> from httpx import HTTPStatusError
        >>> classify_auth_error(HTTPStatusError(..., status_code=401))
        'http_401'
    """
    error_str = str(exception).lower()

    # HTTP status errors
    if "401" in error_str or "unauthorized" in error_str:
        return "http_401"
    if "500" in error_str or "internal server error" in error_str:
        return "http_500"

    # Network errors
    if "timeout" in error_str or "timed out" in error_str:
        return "timeout"
    if "connection" in error_str or "network" in error_str:
        return "connection_error"

    # SSL/TLS errors
    if "ssl" in error_str or "certificate" in error_str or "handshake" in error_str:
        return "ssl_error"

    # Response parsing errors
    if "json" in error_str or "decode" in error_str:
        return "invalid_json"
    if "access_token" in error_str or "missing token" in error_str:
        return "missing_token"

    return "unknown"


# ================================================================================
# Metrics Export Helper
# ================================================================================

def get_all_metrics() -> dict:
    """
    Get all authentication metrics для testing и debugging.

    Returns:
        Dictionary с current metric values

    Example:
        >>> metrics = get_all_metrics()
        >>> print(metrics['auth_token_requests_total'])
        {'success': 1500, 'failure': 25}
    """
    return {
        "auth_token_requests_total": auth_token_requests_total,
        "auth_token_acquisition_duration": auth_token_acquisition_duration,
        "auth_token_source_total": auth_token_source_total,
        "auth_token_refresh_total": auth_token_refresh_total,
        "auth_token_refresh_duration": auth_token_refresh_duration,
        "auth_token_ttl": auth_token_ttl,
        "auth_token_validation_total": auth_token_validation_total,
        "auth_token_cache_hit_rate": auth_token_cache_hit_rate,
        "auth_errors_total": auth_errors_total,
    }
