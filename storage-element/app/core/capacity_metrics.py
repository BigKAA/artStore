"""
Storage Capacity Prometheus metrics для Storage Element.

Sprint 14: Adaptive Capacity Metrics Implementation.

Provides comprehensive instrumentation для мониторинга:
- Capacity utilization (total, used, free bytes)
- Capacity thresholds и alerts
- Storage health status
- File operations throughput
"""

from prometheus_client import Gauge, Counter, Histogram, Info

# ================================================================================
# Storage Capacity Metrics
# ================================================================================

storage_capacity_total_bytes = Gauge(
    'storage_capacity_total_bytes',
    'Total storage capacity in bytes',
    ['storage_element_id', 'mode']
)
"""
Total storage capacity gauge.

Labels:
    storage_element_id: Unique SE identifier (e.g., "se-01")
    mode: Storage mode ("edit", "rw", "ro", "ar")

PromQL queries:
    # Total capacity across all SEs
    sum(storage_capacity_total_bytes)

    # Total capacity by mode
    sum(storage_capacity_total_bytes) by (mode)
"""

storage_capacity_used_bytes = Gauge(
    'storage_capacity_used_bytes',
    'Used storage capacity in bytes',
    ['storage_element_id', 'mode']
)
"""
Used storage capacity gauge.

Labels:
    storage_element_id: Unique SE identifier
    mode: Storage mode

PromQL queries:
    # Used capacity across all SEs
    sum(storage_capacity_used_bytes)

    # Used capacity by SE
    storage_capacity_used_bytes{storage_element_id="se-01"}
"""

storage_capacity_free_bytes = Gauge(
    'storage_capacity_free_bytes',
    'Free storage capacity in bytes',
    ['storage_element_id', 'mode']
)
"""
Free storage capacity gauge.

Labels:
    storage_element_id: Unique SE identifier
    mode: Storage mode

PromQL queries:
    # Free capacity across all SEs
    sum(storage_capacity_free_bytes)

    # Low free capacity alerts (< 10GB)
    storage_capacity_free_bytes < 10737418240
"""

storage_capacity_percent_used = Gauge(
    'storage_capacity_percent_used',
    'Storage capacity utilization percentage (0-100)',
    ['storage_element_id', 'mode']
)
"""
Storage capacity utilization percentage gauge.

Value: 0-100 percentage

Labels:
    storage_element_id: Unique SE identifier
    mode: Storage mode

PromQL queries:
    # Average utilization across all SEs
    avg(storage_capacity_percent_used)

    # SEs with utilization > 90%
    storage_capacity_percent_used > 90

    # Utilization by mode
    avg(storage_capacity_percent_used) by (mode)
"""

# ================================================================================
# Capacity Status Metrics
# ================================================================================

storage_capacity_status = Gauge(
    'storage_capacity_status',
    'Storage capacity status (1=ok, 2=warning, 3=critical, 4=full)',
    ['storage_element_id', 'mode']
)
"""
Capacity status gauge для alerting.

Values:
    1: OK - Normal operation
    2: WARNING - Approaching capacity threshold
    3: CRITICAL - Critical capacity threshold exceeded
    4: FULL - Storage full, no new files accepted

Labels:
    storage_element_id: Unique SE identifier
    mode: Storage mode

PromQL queries:
    # SEs in critical or full status
    storage_capacity_status >= 3

    # Count by status
    count(storage_capacity_status == 2)  # Warning count
    count(storage_capacity_status >= 3)   # Critical + Full count
"""

storage_health_status = Gauge(
    'storage_health_status',
    'Storage Element health status (1=healthy, 0=unhealthy)',
    ['storage_element_id', 'mode']
)
"""
Health status gauge.

Values:
    1: Healthy - SE is operational
    0: Unhealthy - SE has issues

Labels:
    storage_element_id: Unique SE identifier
    mode: Storage mode

PromQL queries:
    # Count healthy SEs
    count(storage_health_status == 1)

    # Unhealthy SEs
    storage_health_status == 0
"""

# ================================================================================
# Adaptive Capacity Thresholds Metrics
# ================================================================================

storage_threshold_warning_percent = Gauge(
    'storage_threshold_warning_percent',
    'Warning threshold percentage for this SE',
    ['storage_element_id', 'mode']
)
"""
Dynamic warning threshold gauge.

Sprint 14: Adaptive thresholds based on SE size.
Larger SEs have higher thresholds (more absolute space left at same %).

Labels:
    storage_element_id: Unique SE identifier
    mode: Storage mode

PromQL queries:
    # Current warning thresholds
    storage_threshold_warning_percent
"""

storage_threshold_critical_percent = Gauge(
    'storage_threshold_critical_percent',
    'Critical threshold percentage for this SE',
    ['storage_element_id', 'mode']
)
"""
Dynamic critical threshold gauge.

Sprint 14: Adaptive thresholds based on SE size.

Labels:
    storage_element_id: Unique SE identifier
    mode: Storage mode
"""

storage_threshold_full_percent = Gauge(
    'storage_threshold_full_percent',
    'Full threshold percentage for this SE',
    ['storage_element_id', 'mode']
)
"""
Dynamic full threshold gauge.

Sprint 14: Adaptive thresholds based on SE size.

Labels:
    storage_element_id: Unique SE identifier
    mode: Storage mode
"""

# ================================================================================
# File Operations Metrics
# ================================================================================

storage_files_total = Gauge(
    'storage_files_total',
    'Total number of files stored',
    ['storage_element_id', 'mode']
)
"""
Total files count gauge.

Labels:
    storage_element_id: Unique SE identifier
    mode: Storage mode

PromQL queries:
    # Total files across all SEs
    sum(storage_files_total)

    # Files by mode
    sum(storage_files_total) by (mode)
"""

storage_file_uploads_total = Counter(
    'storage_file_uploads_total',
    'Total file upload operations',
    ['storage_element_id', 'mode', 'status']
)
"""
File uploads counter.

Labels:
    storage_element_id: Unique SE identifier
    mode: Storage mode
    status: "success" | "failure"

PromQL queries:
    # Upload rate per second
    rate(storage_file_uploads_total[5m])

    # Upload success rate
    (
      rate(storage_file_uploads_total{status="success"}[5m])
      /
      rate(storage_file_uploads_total[5m])
    ) * 100
"""

storage_file_downloads_total = Counter(
    'storage_file_downloads_total',
    'Total file download operations',
    ['storage_element_id', 'mode', 'status']
)
"""
File downloads counter.

Labels:
    storage_element_id: Unique SE identifier
    mode: Storage mode
    status: "success" | "failure"
"""

storage_file_deletes_total = Counter(
    'storage_file_deletes_total',
    'Total file delete operations',
    ['storage_element_id', 'mode', 'status']
)
"""
File deletes counter.

Labels:
    storage_element_id: Unique SE identifier
    mode: Storage mode
    status: "success" | "failure"
"""

storage_file_upload_bytes_total = Counter(
    'storage_file_upload_bytes_total',
    'Total bytes uploaded',
    ['storage_element_id', 'mode']
)
"""
Total uploaded bytes counter.

Labels:
    storage_element_id: Unique SE identifier
    mode: Storage mode

PromQL queries:
    # Upload throughput bytes/sec
    rate(storage_file_upload_bytes_total[5m])

    # Total uploaded in last hour
    increase(storage_file_upload_bytes_total[1h])
"""

storage_file_download_bytes_total = Counter(
    'storage_file_download_bytes_total',
    'Total bytes downloaded',
    ['storage_element_id', 'mode']
)
"""
Total downloaded bytes counter.

Labels:
    storage_element_id: Unique SE identifier
    mode: Storage mode
"""

# ================================================================================
# Latency Metrics
# ================================================================================

storage_file_upload_duration_seconds = Histogram(
    'storage_file_upload_duration_seconds',
    'File upload latency in seconds',
    ['storage_element_id', 'mode'],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0]
)
"""
File upload latency histogram.

Buckets optimized для file operations:
- 0.1s-0.5s: Small files
- 1.0s-5.0s: Medium files
- 10.0s-60.0s: Large files
- 120.0s: Very large files

Labels:
    storage_element_id: Unique SE identifier
    mode: Storage mode

PromQL queries:
    # p95 upload latency
    histogram_quantile(0.95, rate(storage_file_upload_duration_seconds_bucket[5m]))
"""

storage_file_download_duration_seconds = Histogram(
    'storage_file_download_duration_seconds',
    'File download latency in seconds',
    ['storage_element_id', 'mode'],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0]
)
"""
File download latency histogram.

Labels:
    storage_element_id: Unique SE identifier
    mode: Storage mode
"""

# ================================================================================
# Redis Registry Metrics
# ================================================================================

storage_redis_publish_total = Counter(
    'storage_redis_publish_total',
    'Total Redis health reports published',
    ['storage_element_id', 'status']
)
"""
Redis publish counter для HealthReporter.

Sprint 14: Tracking health report publishing.

Labels:
    storage_element_id: Unique SE identifier
    status: "success" | "failure"

PromQL queries:
    # Publish success rate
    rate(storage_redis_publish_total{status="success"}[5m])
    /
    rate(storage_redis_publish_total[5m])
"""

storage_redis_publish_duration_seconds = Histogram(
    'storage_redis_publish_duration_seconds',
    'Redis health report publish latency in seconds',
    ['storage_element_id'],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
)
"""
Redis publish latency histogram.

Sprint 14: Monitoring HealthReporter performance.

Labels:
    storage_element_id: Unique SE identifier

Buckets optimized для Redis operations:
- 0.01s-0.05s: Excellent (local Redis)
- 0.1s-0.25s: Good (network latency)
- 0.5s-1.0s: Degraded (Redis overloaded)
"""

# ================================================================================
# Storage Element Info
# ================================================================================

storage_element_info = Info(
    'storage_element',
    'Storage Element information'
)
"""
Storage Element info metric.

Labels exported:
    storage_element_id: Unique SE identifier
    mode: Current mode ("edit", "rw", "ro", "ar")
    priority: Sequential Fill priority
    version: SE software version

Usage:
    storage_element_info.info({
        'storage_element_id': 'se-01',
        'mode': 'edit',
        'priority': '10',
        'version': '1.0.0'
    })
"""

# ================================================================================
# Helper Functions
# ================================================================================

def capacity_status_to_value(status: str) -> int:
    """
    Convert capacity status string to numeric value для Prometheus gauge.

    Args:
        status: Capacity status string ("ok", "warning", "critical", "full")

    Returns:
        Numeric value (1-4) для gauge metric

    Example:
        >>> capacity_status_to_value("warning")
        2
    """
    status_map = {
        "ok": 1,
        "warning": 2,
        "critical": 3,
        "full": 4
    }
    return status_map.get(status.lower(), 0)


def update_capacity_metrics(
    element_id: str,
    mode: str,
    total_bytes: int,
    used_bytes: int,
    free_bytes: int,
    percent_used: float,
    status: str,
    health: str = "healthy",
    warning_threshold: float = None,
    critical_threshold: float = None,
    full_threshold: float = None
) -> None:
    """
    Update all capacity-related metrics atomically.

    Sprint 14: Helper для HealthReporter и capacity calculator.

    Args:
        element_id: Storage Element ID
        mode: Storage mode ("edit", "rw", etc.)
        total_bytes: Total capacity in bytes
        used_bytes: Used capacity in bytes
        free_bytes: Free capacity in bytes
        percent_used: Utilization percentage (0-100)
        status: Capacity status ("ok", "warning", "critical", "full")
        health: Health status ("healthy", "unhealthy")
        warning_threshold: Warning threshold percentage (optional)
        critical_threshold: Critical threshold percentage (optional)
        full_threshold: Full threshold percentage (optional)

    Example:
        >>> update_capacity_metrics(
        ...     element_id="se-01",
        ...     mode="edit",
        ...     total_bytes=1099511627776,  # 1TB
        ...     used_bytes=549755813888,    # 512GB
        ...     free_bytes=549755813888,    # 512GB
        ...     percent_used=50.0,
        ...     status="ok",
        ...     health="healthy",
        ...     warning_threshold=85.0,
        ...     critical_threshold=92.0,
        ...     full_threshold=98.0
        ... )
    """
    # Capacity gauges
    storage_capacity_total_bytes.labels(
        storage_element_id=element_id, mode=mode
    ).set(total_bytes)

    storage_capacity_used_bytes.labels(
        storage_element_id=element_id, mode=mode
    ).set(used_bytes)

    storage_capacity_free_bytes.labels(
        storage_element_id=element_id, mode=mode
    ).set(free_bytes)

    storage_capacity_percent_used.labels(
        storage_element_id=element_id, mode=mode
    ).set(percent_used)

    # Status gauges
    storage_capacity_status.labels(
        storage_element_id=element_id, mode=mode
    ).set(capacity_status_to_value(status))

    storage_health_status.labels(
        storage_element_id=element_id, mode=mode
    ).set(1 if health == "healthy" else 0)

    # Threshold gauges (optional)
    if warning_threshold is not None:
        storage_threshold_warning_percent.labels(
            storage_element_id=element_id, mode=mode
        ).set(warning_threshold)

    if critical_threshold is not None:
        storage_threshold_critical_percent.labels(
            storage_element_id=element_id, mode=mode
        ).set(critical_threshold)

    if full_threshold is not None:
        storage_threshold_full_percent.labels(
            storage_element_id=element_id, mode=mode
        ).set(full_threshold)


def record_file_operation(
    element_id: str,
    mode: str,
    operation: str,
    status: str,
    bytes_count: int = 0,
    duration_seconds: float = None
) -> None:
    """
    Record file operation metrics.

    Args:
        element_id: Storage Element ID
        mode: Storage mode
        operation: Operation type ("upload", "download", "delete")
        status: Operation status ("success", "failure")
        bytes_count: Bytes transferred (for upload/download)
        duration_seconds: Operation duration (optional)

    Example:
        >>> record_file_operation(
        ...     element_id="se-01",
        ...     mode="edit",
        ...     operation="upload",
        ...     status="success",
        ...     bytes_count=1048576,
        ...     duration_seconds=0.5
        ... )
    """
    if operation == "upload":
        storage_file_uploads_total.labels(
            storage_element_id=element_id, mode=mode, status=status
        ).inc()

        if status == "success" and bytes_count > 0:
            storage_file_upload_bytes_total.labels(
                storage_element_id=element_id, mode=mode
            ).inc(bytes_count)

        if duration_seconds is not None:
            storage_file_upload_duration_seconds.labels(
                storage_element_id=element_id, mode=mode
            ).observe(duration_seconds)

    elif operation == "download":
        storage_file_downloads_total.labels(
            storage_element_id=element_id, mode=mode, status=status
        ).inc()

        if status == "success" and bytes_count > 0:
            storage_file_download_bytes_total.labels(
                storage_element_id=element_id, mode=mode
            ).inc(bytes_count)

        if duration_seconds is not None:
            storage_file_download_duration_seconds.labels(
                storage_element_id=element_id, mode=mode
            ).observe(duration_seconds)

    elif operation == "delete":
        storage_file_deletes_total.labels(
            storage_element_id=element_id, mode=mode, status=status
        ).inc()


def record_redis_publish(
    element_id: str,
    status: str,
    duration_seconds: float = None
) -> None:
    """
    Record Redis health report publish metrics.

    Sprint 14: Used by HealthReporter.

    Args:
        element_id: Storage Element ID
        status: Publish status ("success", "failure")
        duration_seconds: Publish duration (optional)

    Example:
        >>> record_redis_publish("se-01", "success", 0.025)
    """
    storage_redis_publish_total.labels(
        storage_element_id=element_id, status=status
    ).inc()

    if duration_seconds is not None:
        storage_redis_publish_duration_seconds.labels(
            storage_element_id=element_id
        ).observe(duration_seconds)


# ================================================================================
# Metrics Export Helper
# ================================================================================

def get_all_capacity_metrics() -> dict:
    """
    Get all capacity metrics для testing и debugging.

    Returns:
        Dictionary с all metric references

    Example:
        >>> metrics = get_all_capacity_metrics()
        >>> print(metrics['storage_capacity_total_bytes'])
    """
    return {
        "storage_capacity_total_bytes": storage_capacity_total_bytes,
        "storage_capacity_used_bytes": storage_capacity_used_bytes,
        "storage_capacity_free_bytes": storage_capacity_free_bytes,
        "storage_capacity_percent_used": storage_capacity_percent_used,
        "storage_capacity_status": storage_capacity_status,
        "storage_health_status": storage_health_status,
        "storage_threshold_warning_percent": storage_threshold_warning_percent,
        "storage_threshold_critical_percent": storage_threshold_critical_percent,
        "storage_threshold_full_percent": storage_threshold_full_percent,
        "storage_files_total": storage_files_total,
        "storage_file_uploads_total": storage_file_uploads_total,
        "storage_file_downloads_total": storage_file_downloads_total,
        "storage_file_deletes_total": storage_file_deletes_total,
        "storage_file_upload_bytes_total": storage_file_upload_bytes_total,
        "storage_file_download_bytes_total": storage_file_download_bytes_total,
        "storage_file_upload_duration_seconds": storage_file_upload_duration_seconds,
        "storage_file_download_duration_seconds": storage_file_download_duration_seconds,
        "storage_redis_publish_total": storage_redis_publish_total,
        "storage_redis_publish_duration_seconds": storage_redis_publish_duration_seconds,
        "storage_element_info": storage_element_info,
    }
