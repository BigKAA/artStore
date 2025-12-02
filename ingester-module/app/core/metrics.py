"""
Prometheus Metrics для Ingester Module.

Sprint 17, Task 4.1: Custom business metrics для мониторинга:
- Storage selection operations
- File finalization (Two-Phase Commit)
- Upload operations
- Storage availability

Эти метрики дополняют стандартные HTTP metrics от OpenTelemetry.
"""

from prometheus_client import Counter, Gauge, Histogram
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# STORAGE SELECTION METRICS
# ============================================================================

storage_selection_duration = Histogram(
    "storage_selection_duration_seconds",
    "Duration of storage element selection operation",
    ["retention_policy"],  # temporary | permanent
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)
"""
Время выбора Storage Element.

Labels:
    retention_policy: "temporary" или "permanent"

Buckets оптимизированы для Redis/HTTP latency:
- 0.01-0.05s: Отличный результат (Redis cached)
- 0.1-0.5s: Нормальная сетевая latency
- 1.0-5.0s: Проблемы или fallback

PromQL:
    # p95 selection latency
    histogram_quantile(0.95, rate(storage_selection_duration_seconds_bucket[5m]))

    # Средняя latency по retention_policy
    rate(storage_selection_duration_seconds_sum[5m])
    /
    rate(storage_selection_duration_seconds_count[5m])
"""

storage_selection_total = Counter(
    "storage_selection_total",
    "Total storage element selection operations",
    ["retention_policy", "status", "source"]
    # status: success | fallback | failed
    # source: redis | admin_module | local_config
)
"""
Общее количество операций выбора SE.

Labels:
    retention_policy: "temporary" или "permanent"
    status: "success", "fallback", "failed"
    source: "redis", "admin_module", "local_config"

PromQL:
    # Selection success rate
    sum(rate(storage_selection_total{status="success"}[5m]))
    /
    sum(rate(storage_selection_total[5m]))

    # Fallback rate (Redis unavailable)
    sum(rate(storage_selection_total{source!="redis"}[5m]))
    /
    sum(rate(storage_selection_total[5m]))
"""

storage_unavailable_total = Counter(
    "storage_unavailable_total",
    "Total times no storage element was available for upload",
    ["retention_policy"]
)
"""
Количество случаев когда не найден подходящий SE.

Labels:
    retention_policy: "temporary" или "permanent"

PromQL:
    # Unavailability rate
    rate(storage_unavailable_total[5m])

    # Alert rule example
    # increase(storage_unavailable_total[5m]) > 0
"""

storage_element_selected = Counter(
    "storage_element_selected_total",
    "Total selections per storage element",
    ["storage_element_id", "mode"]
)
"""
Распределение выбора по Storage Elements.

Labels:
    storage_element_id: ID выбранного SE
    mode: "edit" или "rw"

PromQL:
    # Distribution of uploads across SEs
    sum(rate(storage_element_selected_total[5m])) by (storage_element_id)
"""


# ============================================================================
# FILE FINALIZATION METRICS (Two-Phase Commit)
# ============================================================================

file_finalize_duration = Histogram(
    "file_finalize_duration_seconds",
    "Duration of file finalization (Two-Phase Commit)",
    ["status"],  # success | failed | rollback
    buckets=[1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0]
)
"""
Время финализации файла (Two-Phase Commit).

Labels:
    status: "success", "failed", "rollback"

Buckets оптимизированы для file copy operations:
- 1-5s: Маленькие файлы
- 10-60s: Средние файлы
- 120-300s: Большие файлы

PromQL:
    # p95 finalization time
    histogram_quantile(0.95, rate(file_finalize_duration_seconds_bucket[5m]))
"""

file_finalize_total = Counter(
    "file_finalize_total",
    "Total file finalization operations",
    ["status"]  # success | failed | rollback
)
"""
Общее количество операций финализации.

Labels:
    status: "success", "failed", "rollback"

PromQL:
    # Finalization success rate
    rate(file_finalize_total{status="success"}[5m])
    /
    rate(file_finalize_total[5m])
"""

file_finalize_phase_duration = Histogram(
    "file_finalize_phase_duration_seconds",
    "Duration of individual finalization phases",
    ["phase"],  # copy | verify | update | cleanup_schedule
    buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0]
)
"""
Время отдельных фаз финализации.

Labels:
    phase: "copy", "verify", "update", "cleanup_schedule"

PromQL:
    # Breakdown по фазам
    sum(rate(file_finalize_phase_duration_seconds_sum[5m])) by (phase)
    /
    sum(rate(file_finalize_phase_duration_seconds_count[5m])) by (phase)
"""

finalize_transactions_in_progress = Gauge(
    "finalize_transactions_in_progress",
    "Number of finalization transactions currently in progress"
)
"""
Количество активных транзакций финализации.

PromQL:
    # Current in-progress transactions
    finalize_transactions_in_progress

    # Alert: слишком много параллельных операций
    finalize_transactions_in_progress > 10
"""

finalize_checksum_mismatch_total = Counter(
    "finalize_checksum_mismatch_total",
    "Total checksum mismatches during finalization"
)
"""
Количество несовпадений checksum при финализации.

Критическая метрика для data integrity!

PromQL:
    # Any checksum mismatch is critical
    increase(finalize_checksum_mismatch_total[1h]) > 0
"""


# ============================================================================
# UPLOAD METRICS
# ============================================================================

upload_total = Counter(
    "ingester_upload_total",
    "Total upload operations",
    ["retention_policy", "status"]  # status: success | failed | rejected
)
"""
Общее количество операций загрузки.

Labels:
    retention_policy: "temporary" или "permanent"
    status: "success", "failed", "rejected"

PromQL:
    # Upload success rate
    sum(rate(ingester_upload_total{status="success"}[5m]))
    /
    sum(rate(ingester_upload_total[5m]))
"""

upload_bytes_total = Counter(
    "ingester_upload_bytes_total",
    "Total bytes uploaded",
    ["retention_policy"]
)
"""
Общий объём загруженных данных.

Labels:
    retention_policy: "temporary" или "permanent"

PromQL:
    # Upload throughput bytes/sec
    rate(ingester_upload_bytes_total[5m])
"""

upload_duration = Histogram(
    "ingester_upload_duration_seconds",
    "Upload operation duration",
    ["retention_policy"],
    buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0]
)
"""
Время загрузки файла.

Labels:
    retention_policy: "temporary" или "permanent"

PromQL:
    # p95 upload time
    histogram_quantile(0.95, rate(ingester_upload_duration_seconds_bucket[5m]))
"""


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def record_storage_selection(
    retention_policy: str,
    status: str,
    source: str,
    duration_seconds: float,
    storage_element_id: str = None,
    mode: str = None
) -> None:
    """
    Запись метрик выбора Storage Element.

    Args:
        retention_policy: "temporary" или "permanent"
        status: "success", "fallback", "failed"
        source: "redis", "admin_module", "local_config"
        duration_seconds: Время выбора в секундах
        storage_element_id: ID выбранного SE (опционально)
        mode: Режим SE - "edit" или "rw" (опционально)
    """
    storage_selection_total.labels(
        retention_policy=retention_policy,
        status=status,
        source=source
    ).inc()

    storage_selection_duration.labels(
        retention_policy=retention_policy
    ).observe(duration_seconds)

    if status == "failed":
        storage_unavailable_total.labels(
            retention_policy=retention_policy
        ).inc()
    elif storage_element_id and mode:
        storage_element_selected.labels(
            storage_element_id=storage_element_id,
            mode=mode
        ).inc()

    logger.debug(
        f"Recorded storage selection: policy={retention_policy}, "
        f"status={status}, source={source}, duration={duration_seconds:.3f}s"
    )


def record_file_finalization(
    status: str,
    duration_seconds: float,
    checksum_mismatch: bool = False
) -> None:
    """
    Запись метрик финализации файла.

    Args:
        status: "success", "failed", "rollback"
        duration_seconds: Время финализации в секундах
        checksum_mismatch: Было ли несовпадение checksum
    """
    file_finalize_total.labels(status=status).inc()
    file_finalize_duration.labels(status=status).observe(duration_seconds)

    if checksum_mismatch:
        finalize_checksum_mismatch_total.inc()

    logger.debug(
        f"Recorded file finalization: status={status}, "
        f"duration={duration_seconds:.2f}s, checksum_mismatch={checksum_mismatch}"
    )


def record_finalize_phase(phase: str, duration_seconds: float) -> None:
    """
    Запись метрики отдельной фазы финализации.

    Args:
        phase: "copy", "verify", "update", "cleanup_schedule"
        duration_seconds: Время фазы в секундах
    """
    file_finalize_phase_duration.labels(phase=phase).observe(duration_seconds)
    logger.debug(f"Recorded finalize phase: {phase}, duration={duration_seconds:.3f}s")


def update_finalize_in_progress(delta: int) -> None:
    """
    Обновление счётчика активных транзакций финализации.

    Args:
        delta: +1 при старте, -1 при завершении
    """
    if delta > 0:
        finalize_transactions_in_progress.inc(delta)
    else:
        finalize_transactions_in_progress.dec(abs(delta))


def record_upload(
    retention_policy: str,
    status: str,
    bytes_count: int = 0,
    duration_seconds: float = None
) -> None:
    """
    Запись метрик загрузки файла.

    Args:
        retention_policy: "temporary" или "permanent"
        status: "success", "failed", "rejected"
        bytes_count: Размер файла в байтах
        duration_seconds: Время загрузки (опционально)
    """
    upload_total.labels(
        retention_policy=retention_policy,
        status=status
    ).inc()

    if status == "success" and bytes_count > 0:
        upload_bytes_total.labels(
            retention_policy=retention_policy
        ).inc(bytes_count)

    if duration_seconds is not None:
        upload_duration.labels(
            retention_policy=retention_policy
        ).observe(duration_seconds)

    logger.debug(
        f"Recorded upload: policy={retention_policy}, status={status}, "
        f"bytes={bytes_count}, duration={duration_seconds}"
    )


# ============================================================================
# METRICS EXPORT
# ============================================================================

def get_all_ingester_metrics() -> dict:
    """
    Получение всех метрик Ingester Module для тестирования.

    Returns:
        dict: Словарь с references на все метрики
    """
    return {
        # Storage Selection
        "storage_selection_duration": storage_selection_duration,
        "storage_selection_total": storage_selection_total,
        "storage_unavailable_total": storage_unavailable_total,
        "storage_element_selected": storage_element_selected,
        # File Finalization
        "file_finalize_duration": file_finalize_duration,
        "file_finalize_total": file_finalize_total,
        "file_finalize_phase_duration": file_finalize_phase_duration,
        "finalize_transactions_in_progress": finalize_transactions_in_progress,
        "finalize_checksum_mismatch_total": finalize_checksum_mismatch_total,
        # Upload
        "upload_total": upload_total,
        "upload_bytes_total": upload_bytes_total,
        "upload_duration": upload_duration,
    }
