"""
Unit тесты для metrics модуля Ingester Module.

Sprint 17, Task 4.1: Тестирование Prometheus метрик.
"""

import pytest
from prometheus_client import REGISTRY

from app.core.metrics import (
    storage_selection_duration,
    storage_selection_total,
    storage_unavailable_total,
    storage_element_selected,
    file_finalize_duration,
    file_finalize_total,
    file_finalize_phase_duration,
    finalize_transactions_in_progress,
    finalize_checksum_mismatch_total,
    upload_total,
    upload_bytes_total,
    upload_duration,
    record_storage_selection,
    record_file_finalization,
    record_finalize_phase,
    update_finalize_in_progress,
    record_upload,
    get_all_ingester_metrics,
)


class TestStorageSelectionMetrics:
    """Тесты метрик выбора Storage Element."""

    def test_storage_selection_metrics_exist(self):
        """Проверка что все метрики выбора SE определены."""
        metrics = get_all_ingester_metrics()

        assert "storage_selection_duration" in metrics
        assert "storage_selection_total" in metrics
        assert "storage_unavailable_total" in metrics
        assert "storage_element_selected" in metrics

    def test_record_storage_selection_success(self):
        """Тест записи успешного выбора SE."""
        # Записываем успешный выбор
        record_storage_selection(
            retention_policy="temporary",
            status="success",
            source="redis",
            duration_seconds=0.025,
            storage_element_id="se-01",
            mode="edit"
        )

        # Проверяем что метрики записаны (без ошибок)
        # Prometheus сам управляет значениями, мы просто проверяем что запись прошла

    def test_record_storage_selection_failed(self):
        """Тест записи неудачного выбора SE."""
        record_storage_selection(
            retention_policy="permanent",
            status="failed",
            source="none",
            duration_seconds=0.5
        )

        # При status="failed" должен инкрементироваться storage_unavailable_total

    def test_record_storage_selection_fallback(self):
        """Тест записи fallback выбора SE."""
        record_storage_selection(
            retention_policy="temporary",
            status="fallback",
            source="local_config",
            duration_seconds=0.1,
            storage_element_id="local-fallback",
            mode="edit"
        )


class TestFileFinalizationMetrics:
    """Тесты метрик финализации файлов."""

    def test_finalize_metrics_exist(self):
        """Проверка что все метрики финализации определены."""
        metrics = get_all_ingester_metrics()

        assert "file_finalize_duration" in metrics
        assert "file_finalize_total" in metrics
        assert "file_finalize_phase_duration" in metrics
        assert "finalize_transactions_in_progress" in metrics
        assert "finalize_checksum_mismatch_total" in metrics

    def test_record_file_finalization_success(self):
        """Тест записи успешной финализации."""
        record_file_finalization(
            status="success",
            duration_seconds=5.5,
            checksum_mismatch=False
        )

    def test_record_file_finalization_failed(self):
        """Тест записи неудачной финализации."""
        record_file_finalization(
            status="failed",
            duration_seconds=2.0,
            checksum_mismatch=False
        )

    def test_record_file_finalization_with_checksum_mismatch(self):
        """Тест записи финализации с несовпадением checksum."""
        record_file_finalization(
            status="failed",
            duration_seconds=3.0,
            checksum_mismatch=True
        )

    def test_record_finalize_phase(self):
        """Тест записи метрик отдельных фаз финализации."""
        record_finalize_phase("select_target", 0.05)
        record_finalize_phase("copy", 2.5)
        record_finalize_phase("verify", 0.1)

    def test_update_finalize_in_progress(self):
        """Тест обновления счётчика активных транзакций."""
        # Начальное значение
        initial_value = finalize_transactions_in_progress._value._value

        # Увеличиваем
        update_finalize_in_progress(1)
        assert finalize_transactions_in_progress._value._value == initial_value + 1

        # Уменьшаем
        update_finalize_in_progress(-1)
        assert finalize_transactions_in_progress._value._value == initial_value


class TestUploadMetrics:
    """Тесты метрик загрузки файлов."""

    def test_upload_metrics_exist(self):
        """Проверка что все метрики загрузки определены."""
        metrics = get_all_ingester_metrics()

        assert "upload_total" in metrics
        assert "upload_bytes_total" in metrics
        assert "upload_duration" in metrics

    def test_record_upload_success(self):
        """Тест записи успешной загрузки."""
        record_upload(
            retention_policy="temporary",
            status="success",
            bytes_count=1048576,  # 1MB
            duration_seconds=0.5
        )

    def test_record_upload_failed(self):
        """Тест записи неудачной загрузки."""
        record_upload(
            retention_policy="permanent",
            status="failed",
            bytes_count=0,
            duration_seconds=0.1
        )

    def test_record_upload_rejected(self):
        """Тест записи отклонённой загрузки."""
        record_upload(
            retention_policy="temporary",
            status="rejected",
            bytes_count=0
        )


class TestMetricsIntegration:
    """Интеграционные тесты метрик."""

    def test_all_metrics_registered_with_prometheus(self):
        """Проверка что все метрики зарегистрированы в Prometheus."""
        # Получаем все имена метрик из registry
        metric_names = [m.name for m in REGISTRY.collect()]

        # Проверяем наличие наших метрик
        # Prometheus добавляет суффиксы _total, _bucket и т.д.
        expected_prefixes = [
            "storage_selection",
            "storage_unavailable",
            "storage_element_selected",
            "file_finalize",
            "finalize_transactions",
            "finalize_checksum",
            "ingester_upload",
        ]

        for prefix in expected_prefixes:
            found = any(prefix in name for name in metric_names)
            assert found, f"Metrics with prefix '{prefix}' not found in registry"

    def test_get_all_ingester_metrics(self):
        """Тест функции получения всех метрик."""
        metrics = get_all_ingester_metrics()

        assert isinstance(metrics, dict)
        assert len(metrics) == 12  # Ожидаем 12 метрик

        # Проверяем типы метрик
        from prometheus_client import Counter, Gauge, Histogram

        assert isinstance(metrics["storage_selection_duration"], Histogram)
        assert isinstance(metrics["storage_selection_total"], Counter)
        assert isinstance(metrics["storage_unavailable_total"], Counter)
        assert isinstance(metrics["finalize_transactions_in_progress"], Gauge)
