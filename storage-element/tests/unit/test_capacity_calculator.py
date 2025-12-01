"""
Unit тесты для модуля capacity_calculator.

Тестируют:
- Расчёт адаптивных порогов для разных размеров SE
- Определение статуса ёмкости
- Pre-flight проверку для файлов
- Граничные случаи (нулевая ёмкость, очень маленькие SE)
"""

import pytest

from app.core.capacity_calculator import (
    CapacityStatus,
    calculate_adaptive_threshold,
    get_capacity_status,
    can_accept_file,
    format_capacity_info,
    THRESHOLDS_CONFIG,
)


# Константы для тестов
GB = 1024 ** 3  # 1 гигабайт в байтах
TB = 1024 ** 4  # 1 терабайт в байтах


class TestCalculateAdaptiveThreshold:
    """Тесты расчёта адаптивных порогов."""

    def test_rw_mode_large_storage_10tb(self):
        """Большое RW хранилище (10TB) - используются процентные пороги."""
        total_bytes = 10 * TB  # 10TB = 10240 GB
        thresholds = calculate_adaptive_threshold(total_bytes, "rw")

        assert thresholds is not None

        # Для 10TB SE (10240 GB):
        # warning_free = max(10240GB * 0.15, 150GB) = max(1536GB, 150GB) = 1536GB
        # warning_threshold = (1 - 1536/10240) * 100 = 85%
        total_gb = 10 * 1024  # 10240 GB
        expected_warning_free = total_gb * 0.15  # 1536 GB
        assert thresholds["warning_free_gb"] == pytest.approx(expected_warning_free, abs=0.1)
        assert thresholds["warning_threshold"] == pytest.approx(85.0, abs=0.1)

        # critical_free = max(10240GB * 0.08, 80GB) = 819.2GB
        expected_critical_free = total_gb * 0.08  # 819.2 GB
        assert thresholds["critical_free_gb"] == pytest.approx(expected_critical_free, abs=0.1)
        assert thresholds["critical_threshold"] == pytest.approx(92.0, abs=0.1)

        # full_free = max(10240GB * 0.02, 20GB) = 204.8GB
        expected_full_free = total_gb * 0.02  # 204.8 GB
        assert thresholds["full_free_gb"] == pytest.approx(expected_full_free, abs=0.1)
        assert thresholds["full_threshold"] == pytest.approx(98.0, abs=0.1)

    def test_rw_mode_small_storage_500gb(self):
        """Маленькое RW хранилище (500GB) - используются минимальные GB."""
        total_bytes = 500 * GB  # 500GB
        thresholds = calculate_adaptive_threshold(total_bytes, "rw")

        assert thresholds is not None

        # Для 500GB SE:
        # warning_free = max(500GB * 0.15, 150GB) = max(75GB, 150GB) = 150GB (минимум!)
        # warning_threshold = (1 - 150/500) * 100 = 70%
        assert thresholds["warning_free_gb"] == 150.0  # минимум для RW
        assert thresholds["warning_threshold"] == pytest.approx(70.0, abs=0.1)

        # critical_free = max(500GB * 0.08, 80GB) = max(40GB, 80GB) = 80GB
        assert thresholds["critical_free_gb"] == 80.0
        assert thresholds["critical_threshold"] == pytest.approx(84.0, abs=0.1)

        # full_free = max(500GB * 0.02, 20GB) = max(10GB, 20GB) = 20GB
        assert thresholds["full_free_gb"] == 20.0
        assert thresholds["full_threshold"] == pytest.approx(96.0, abs=0.1)

    def test_edit_mode_large_storage_5tb(self):
        """Большое Edit хранилище (5TB) - используются процентные пороги."""
        total_bytes = 5 * TB  # 5TB = 5120GB
        thresholds = calculate_adaptive_threshold(total_bytes, "edit")

        assert thresholds is not None

        # Для Edit 5TB (5120 GB):
        # warning_free = max(5120GB * 0.10, 100GB) = max(512GB, 100GB) = 512GB
        total_gb = 5 * 1024  # 5120 GB
        expected_warning_free = total_gb * 0.10  # 512 GB
        assert thresholds["warning_free_gb"] == pytest.approx(expected_warning_free, abs=0.1)
        assert thresholds["warning_threshold"] == pytest.approx(90.0, abs=0.1)

        # critical_free = max(5120GB * 0.05, 50GB) = 256GB
        expected_critical_free = total_gb * 0.05  # 256 GB
        assert thresholds["critical_free_gb"] == pytest.approx(expected_critical_free, abs=0.1)
        assert thresholds["critical_threshold"] == pytest.approx(95.0, abs=0.1)

    def test_edit_mode_small_storage_200gb(self):
        """Маленькое Edit хранилище (200GB) - используются минимальные GB."""
        total_bytes = 200 * GB
        thresholds = calculate_adaptive_threshold(total_bytes, "edit")

        assert thresholds is not None

        # warning_free = max(200GB * 0.10, 100GB) = max(20GB, 100GB) = 100GB
        assert thresholds["warning_free_gb"] == 100.0  # минимум для Edit
        assert thresholds["warning_threshold"] == pytest.approx(50.0, abs=0.1)

    def test_readonly_modes_return_none(self):
        """Режимы только чтения (ro, ar) не нуждаются в порогах."""
        for mode in ["ro", "ar"]:
            thresholds = calculate_adaptive_threshold(1 * TB, mode)
            assert thresholds is None

    def test_unknown_mode_returns_none(self):
        """Неизвестный режим возвращает None."""
        thresholds = calculate_adaptive_threshold(1 * TB, "unknown")
        assert thresholds is None

    def test_zero_capacity_handles_gracefully(self):
        """Нулевая ёмкость обрабатывается корректно."""
        thresholds = calculate_adaptive_threshold(0, "rw")

        assert thresholds is not None
        # При нулевой ёмкости пороги должны быть 100% (всё заполнено)
        assert thresholds["full_threshold"] == 100.0

    def test_very_small_storage_100gb(self):
        """Очень маленькое хранилище (100GB) - минимальные GB превышают ёмкость."""
        total_bytes = 100 * GB
        thresholds = calculate_adaptive_threshold(total_bytes, "rw")

        assert thresholds is not None

        # warning_free = max(100GB * 0.15, 150GB) = 150GB
        # Но 150GB > 100GB общей ёмкости!
        # threshold = (1 - 150/100) * 100 = -50% → clamp to 0%
        assert thresholds["warning_free_gb"] == 150.0
        # Порог ограничен диапазоном 0-100%
        assert thresholds["warning_threshold"] == 0.0  # всегда в warning


class TestGetCapacityStatus:
    """Тесты определения статуса ёмкости."""

    @pytest.fixture
    def rw_thresholds(self):
        """Пороги для 1TB RW хранилища."""
        return calculate_adaptive_threshold(1 * TB, "rw")

    def test_status_ok(self, rw_thresholds):
        """Статус OK при низком заполнении."""
        total = 1 * TB
        used = int(total * 0.50)  # 50% заполнено

        status = get_capacity_status(used, total, rw_thresholds)
        assert status == CapacityStatus.OK

    def test_status_warning(self, rw_thresholds):
        """Статус WARNING при достижении порога."""
        total = 1 * TB
        # Для 1TB: warning_threshold ≈ 85%
        used = int(total * 0.86)  # 86% заполнено

        status = get_capacity_status(used, total, rw_thresholds)
        assert status == CapacityStatus.WARNING

    def test_status_critical(self, rw_thresholds):
        """Статус CRITICAL при критическом заполнении."""
        total = 1 * TB
        # Для 1TB: critical_threshold ≈ 92%
        used = int(total * 0.93)  # 93% заполнено

        status = get_capacity_status(used, total, rw_thresholds)
        assert status == CapacityStatus.CRITICAL

    def test_status_full(self, rw_thresholds):
        """Статус FULL при полном заполнении."""
        total = 1 * TB
        # Для 1TB: full_threshold ≈ 98%
        used = int(total * 0.99)  # 99% заполнено

        status = get_capacity_status(used, total, rw_thresholds)
        assert status == CapacityStatus.FULL

    def test_status_ok_for_none_thresholds(self):
        """Для режимов без порогов всегда OK."""
        status = get_capacity_status(900 * GB, 1 * TB, None)
        assert status == CapacityStatus.OK

    def test_zero_total_returns_full(self, rw_thresholds):
        """Нулевая общая ёмкость = FULL."""
        status = get_capacity_status(0, 0, rw_thresholds)
        assert status == CapacityStatus.FULL

    def test_boundary_exactly_at_warning(self):
        """Граничный случай - ровно на пороге warning."""
        total = 10 * TB
        thresholds = calculate_adaptive_threshold(total, "rw")

        # Ровно на пороге warning (85%)
        used = int(total * thresholds["warning_threshold"] / 100)
        status = get_capacity_status(used, total, thresholds)

        # На границе >= порог = WARNING
        assert status == CapacityStatus.WARNING


class TestCanAcceptFile:
    """Тесты pre-flight проверки файлов."""

    @pytest.fixture
    def edit_thresholds(self):
        """Пороги для 500GB Edit хранилища."""
        return calculate_adaptive_threshold(500 * GB, "edit")

    def test_accept_file_ok(self, edit_thresholds):
        """Файл принимается при достаточном месте."""
        total = 500 * GB
        used = 200 * GB  # 40% заполнено
        file_size = 10 * GB

        can_accept, reason = can_accept_file(file_size, used, total, edit_thresholds)

        assert can_accept is True
        assert reason == "ok"

    def test_reject_when_storage_full(self, edit_thresholds):
        """Файл отклоняется при полном хранилище."""
        total = 500 * GB
        used = 495 * GB  # 99% заполнено (FULL)
        file_size = 1 * GB

        can_accept, reason = can_accept_file(file_size, used, total, edit_thresholds)

        assert can_accept is False
        assert reason == "storage_full"

    def test_reject_when_would_become_full(self, edit_thresholds):
        """Файл отклоняется, если после загрузки станет FULL."""
        total = 500 * GB
        used = 480 * GB  # 96% - ещё не FULL
        file_size = 15 * GB  # После загрузки будет 99% = FULL

        can_accept, reason = can_accept_file(file_size, used, total, edit_thresholds)

        assert can_accept is False
        assert reason == "insufficient_space_after_upload"

    def test_reject_large_file_in_critical(self, edit_thresholds):
        """Большой файл (>100MB) отклоняется в CRITICAL статусе."""
        total = 500 * GB
        # Для 500GB Edit: critical ≈ 90%
        used = int(total * 0.92)  # 92% = CRITICAL
        file_size = 200 * 1024 * 1024  # 200MB > 100MB лимит

        can_accept, reason = can_accept_file(file_size, used, total, edit_thresholds)

        assert can_accept is False
        assert reason == "file_too_large_for_critical_capacity"

    def test_accept_small_file_in_critical(self, edit_thresholds):
        """Маленький файл (<100MB) принимается в CRITICAL статусе."""
        total = 500 * GB
        used = int(total * 0.92)  # 92% = CRITICAL
        file_size = 50 * 1024 * 1024  # 50MB < 100MB лимит

        can_accept, reason = can_accept_file(file_size, used, total, edit_thresholds)

        assert can_accept is True
        assert reason == "ok"

    def test_reject_readonly_mode(self):
        """Файлы не принимаются в режиме только чтения."""
        thresholds = calculate_adaptive_threshold(1 * TB, "ro")  # None

        can_accept, reason = can_accept_file(1 * GB, 500 * GB, 1 * TB, thresholds)

        assert can_accept is False
        assert reason == "storage_mode_readonly"


class TestFormatCapacityInfo:
    """Тесты форматирования информации о ёмкости."""

    def test_format_with_thresholds(self):
        """Форматирование с порогами."""
        total = 1 * TB  # 1024 GB
        used = 500 * GB  # 500 GB
        thresholds = calculate_adaptive_threshold(total, "rw")

        info = format_capacity_info(used, total, thresholds)

        assert info["total_bytes"] == total
        assert info["used_bytes"] == used
        assert info["free_bytes"] == total - used
        assert info["total_gb"] == pytest.approx(1024.0, abs=1)
        assert info["used_gb"] == pytest.approx(500.0, abs=1)
        assert info["free_gb"] == pytest.approx(524.0, abs=1)
        # 500 / 1024 * 100 = ~48.8%
        assert info["used_percent"] == pytest.approx(48.8, abs=1)
        assert info["status"] == "ok"
        assert "thresholds" in info

    def test_format_without_thresholds(self):
        """Форматирование без порогов (ro/ar режим)."""
        info = format_capacity_info(500 * GB, 1 * TB, None)

        assert info["status"] == "ok"
        assert "thresholds" not in info

    def test_format_zero_total(self):
        """Форматирование при нулевой ёмкости."""
        info = format_capacity_info(0, 0, None)

        assert info["total_gb"] == 0.0
        assert info["used_percent"] == 0.0


class TestThresholdsConfig:
    """Тесты конфигурации порогов."""

    def test_rw_config_exists(self):
        """Конфигурация RW существует и корректна."""
        assert "rw" in THRESHOLDS_CONFIG
        config = THRESHOLDS_CONFIG["rw"]

        assert "warning" in config
        assert "critical" in config
        assert "full" in config

        # Пороги должны быть в порядке убывания свободного места
        assert config["warning"][0] > config["critical"][0] > config["full"][0]
        assert config["warning"][1] > config["critical"][1] > config["full"][1]

    def test_edit_config_exists(self):
        """Конфигурация Edit существует и корректна."""
        assert "edit" in THRESHOLDS_CONFIG
        config = THRESHOLDS_CONFIG["edit"]

        assert config["warning"][0] > config["critical"][0] > config["full"][0]

    def test_edit_thresholds_lower_than_rw(self):
        """Edit пороги ниже чем RW (меньше буфер)."""
        rw = THRESHOLDS_CONFIG["rw"]
        edit = THRESHOLDS_CONFIG["edit"]

        # Edit требует меньше свободного места
        assert edit["warning"][0] < rw["warning"][0]
        assert edit["warning"][1] < rw["warning"][1]
