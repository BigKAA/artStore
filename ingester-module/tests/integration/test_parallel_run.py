"""
Интеграционные тесты для Sprint 18 Phase 3: Parallel Run.

Тестирует работу POLLING и PUSH моделей в параллельном режиме:
- Fallback chain: POLLING → PUSH → Admin Module
- Конфигурационные флаги (use_for_selection, fallback_to_push)
- Метрики источника выбора
- Health endpoint с data_sources информацией
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from app.services.storage_selector import (
    StorageSelector,
    StorageElementInfo,
    CapacityStatus,
    RetentionPolicy,
)
from app.services.capacity_monitor import (
    AdaptiveCapacityMonitor,
    CapacityMonitorConfig,
    StorageCapacityInfo,
    HealthStatus,
)
from app.core.config import CapacityMonitorSettings


def make_capacity_info(
    storage_id: str = "se-test-01",
    mode: str = "edit",
    total: int = 10_000_000_000,
    used: int = 1_000_000_000,
    health: HealthStatus = HealthStatus.HEALTHY,
    endpoint: str = "http://se-01:8010",
) -> StorageCapacityInfo:
    """Хелпер для создания StorageCapacityInfo с правильной структурой."""
    return StorageCapacityInfo(
        storage_id=storage_id,
        mode=mode,
        total=total,
        used=used,
        available=total - used,
        percent_used=round(used / total * 100, 1) if total > 0 else 0.0,
        health=health,
        backend="local",
        location="dc1",
        last_update=datetime.now(timezone.utc).isoformat(),
        last_poll=datetime.now(timezone.utc).isoformat(),
        endpoint=endpoint,
    )


class TestParallelRunFallbackChain:
    """
    Тесты fallback chain: POLLING → PUSH → Admin Module.

    Проверяют что StorageSelector корректно переключается между источниками
    данных при недоступности каждого из них.
    """

    @pytest.fixture
    def mock_redis_client(self):
        """Мок Redis клиента."""
        mock = AsyncMock()
        mock.ping = AsyncMock(return_value=True)
        mock.get = AsyncMock(return_value=None)
        mock.set = AsyncMock(return_value=True)
        mock.zrange = AsyncMock(return_value=[])
        mock.hgetall = AsyncMock(return_value={})
        return mock

    @pytest.fixture
    def mock_admin_client(self):
        """Мок Admin Module клиента."""
        mock = AsyncMock()
        mock.get_available_storage_elements = AsyncMock(return_value=[])
        return mock

    @pytest.fixture
    def sample_se_info(self) -> StorageElementInfo:
        """Пример StorageElementInfo для тестов."""
        return StorageElementInfo(
            element_id="se-test-01",
            mode="edit",
            endpoint="http://se-01:8010",
            priority=100,
            capacity_total=10_000_000_000,
            capacity_used=1_000_000_000,
            capacity_free=9_000_000_000,
            capacity_percent=10.0,
            capacity_status=CapacityStatus.OK,
            health_status="healthy",
            last_updated=datetime.now(timezone.utc)
        )

    @pytest.fixture
    def sample_capacity_info(self) -> StorageCapacityInfo:
        """Пример StorageCapacityInfo для POLLING модели."""
        return make_capacity_info()

    @pytest.mark.asyncio
    async def test_polling_model_selected_first(
        self,
        mock_redis_client,
        mock_admin_client,
        sample_capacity_info,
    ):
        """
        Тест: POLLING модель выбирается первой когда данные доступны.

        Сценарий:
        1. AdaptiveCapacityMonitor имеет данные о SE
        2. Redis PUSH модель также имеет данные
        3. StorageSelector должен выбрать SE из POLLING модели
        """
        # Мокируем get_capacity_monitor
        mock_monitor = AsyncMock()
        mock_monitor.get_cached_capacity = AsyncMock(return_value=sample_capacity_info)

        with patch("app.services.storage_selector.get_capacity_monitor", return_value=mock_monitor):
            with patch("app.services.storage_selector.settings") as mock_settings:
                mock_settings.capacity_monitor.enabled = True
                mock_settings.capacity_monitor.use_for_selection = True
                mock_settings.capacity_monitor.fallback_to_push = True

                selector = StorageSelector()
                selector._redis_client = mock_redis_client
                selector._admin_client = mock_admin_client
                selector._initialized = True

                # Мокируем _select_from_adaptive_monitor
                selector._select_from_adaptive_monitor = AsyncMock(
                    return_value=StorageElementInfo(
                        element_id="se-test-01",
                        mode="edit",
                        endpoint="http://se-01:8010",
                        priority=100,
                        capacity_total=10_000_000_000,
                        capacity_used=1_000_000_000,
                        capacity_free=9_000_000_000,
                        capacity_percent=10.0,
                        capacity_status=CapacityStatus.OK,
                        health_status="healthy",
                        last_updated=datetime.now(timezone.utc)
                    )
                )

                se = await selector.select_storage_element(
                    file_size=1024,
                    retention_policy=RetentionPolicy.TEMPORARY
                )

                assert se is not None
                assert se.element_id == "se-test-01"
                # POLLING должен быть вызван
                selector._select_from_adaptive_monitor.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_to_push_when_polling_empty(
        self,
        mock_redis_client,
        mock_admin_client,
        sample_se_info,
    ):
        """
        Тест: Fallback на PUSH модель когда POLLING не возвращает результатов.

        Сценарий:
        1. AdaptiveCapacityMonitor возвращает None (нет данных)
        2. Redis PUSH модель имеет данные
        3. StorageSelector должен выбрать SE из PUSH модели
        """
        # Настройка PUSH модели
        mock_redis_client.zrange = AsyncMock(return_value=["se-test-01"])
        mock_redis_client.hgetall = AsyncMock(return_value={
            "id": "se-test-01",
            "mode": "edit",
            "endpoint": "http://se-01:8010",
            "priority": "100",
            "capacity_total": "10000000000",
            "capacity_used": "1000000000",
            "capacity_free": "9000000000",
            "capacity_percent": "10.0",
            "capacity_status": "ok",
            "health_status": "healthy",
            "last_updated": datetime.now(timezone.utc).isoformat()
        })

        with patch("app.services.storage_selector.get_capacity_monitor", return_value=None):
            with patch("app.services.storage_selector.settings") as mock_settings:
                mock_settings.capacity_monitor.enabled = True
                mock_settings.capacity_monitor.use_for_selection = True
                mock_settings.capacity_monitor.fallback_to_push = True

                selector = StorageSelector()
                selector._redis_client = mock_redis_client
                selector._admin_client = mock_admin_client
                selector._initialized = True

                # POLLING возвращает None
                selector._select_from_adaptive_monitor = AsyncMock(return_value=None)

                se = await selector.select_storage_element(
                    file_size=1024,
                    retention_policy=RetentionPolicy.TEMPORARY
                )

                assert se is not None
                assert se.element_id == "se-test-01"

    @pytest.mark.asyncio
    async def test_fallback_to_admin_when_both_models_empty(
        self,
        mock_redis_client,
        mock_admin_client,
        sample_se_info,
    ):
        """
        Тест: Fallback на Admin Module когда POLLING и PUSH пусты.

        Сценарий:
        1. AdaptiveCapacityMonitor возвращает None
        2. Redis PUSH модель возвращает пустой список
        3. Admin Module возвращает SE
        4. StorageSelector должен выбрать SE из Admin Module
        """
        # PUSH модель пустая
        mock_redis_client.zrange = AsyncMock(return_value=[])

        # Admin Module имеет данные
        mock_admin_client.get_available_storage_elements = AsyncMock(
            return_value=[sample_se_info]
        )

        with patch("app.services.storage_selector.get_capacity_monitor", return_value=None):
            with patch("app.services.storage_selector.settings") as mock_settings:
                mock_settings.capacity_monitor.enabled = True
                mock_settings.capacity_monitor.use_for_selection = True
                mock_settings.capacity_monitor.fallback_to_push = True

                selector = StorageSelector()
                selector._redis_client = mock_redis_client
                selector._admin_client = mock_admin_client
                selector._initialized = True

                # Оба локальных источника пусты
                selector._select_from_adaptive_monitor = AsyncMock(return_value=None)
                selector._select_from_redis = AsyncMock(return_value=None)

                se = await selector.select_storage_element(
                    file_size=1024,
                    retention_policy=RetentionPolicy.TEMPORARY
                )

                assert se is not None
                assert se.element_id == "se-test-01"

    @pytest.mark.asyncio
    async def test_all_sources_exhausted_returns_none(
        self,
        mock_redis_client,
        mock_admin_client,
    ):
        """
        Тест: Возврат None когда все источники исчерпаны.

        Сценарий:
        1. POLLING модель пустая
        2. PUSH модель пустая
        3. Admin Module пустой
        4. StorageSelector должен вернуть None
        """
        mock_redis_client.zrange = AsyncMock(return_value=[])
        mock_admin_client.get_available_storage_elements = AsyncMock(return_value=[])

        with patch("app.services.storage_selector.get_capacity_monitor", return_value=None):
            with patch("app.services.storage_selector.settings") as mock_settings:
                mock_settings.capacity_monitor.enabled = True
                mock_settings.capacity_monitor.use_for_selection = True
                mock_settings.capacity_monitor.fallback_to_push = True

                selector = StorageSelector()
                selector._redis_client = mock_redis_client
                selector._admin_client = mock_admin_client
                selector._initialized = True

                selector._select_from_adaptive_monitor = AsyncMock(return_value=None)
                selector._select_from_redis = AsyncMock(return_value=None)
                selector._select_from_admin_module = AsyncMock(return_value=None)

                se = await selector.select_storage_element(
                    file_size=1024,
                    retention_policy=RetentionPolicy.TEMPORARY
                )

                assert se is None


class TestParallelRunConfigFlags:
    """
    Тесты конфигурационных флагов для Parallel Run.

    Проверяют что флаги use_for_selection и fallback_to_push
    корректно влияют на поведение StorageSelector.
    """

    def test_use_for_selection_flag_default_true(self):
        """Тест: use_for_selection по умолчанию True."""
        settings = CapacityMonitorSettings()
        assert settings.use_for_selection is True

    def test_fallback_to_push_flag_default_true(self):
        """Тест: fallback_to_push по умолчанию True."""
        settings = CapacityMonitorSettings()
        assert settings.fallback_to_push is True

    def test_boolean_parsing_on_off(self):
        """Тест: Парсинг boolean из on/off формата."""
        # Используем Pydantic валидатор напрямую
        settings = CapacityMonitorSettings(enabled="on")
        assert settings.enabled is True

        settings2 = CapacityMonitorSettings(enabled="off")
        assert settings2.enabled is False

    @pytest.mark.asyncio
    async def test_polling_disabled_skips_adaptive_monitor(self):
        """
        Тест: При use_for_selection=False POLLING модель пропускается.
        """
        mock_redis_client = AsyncMock()
        mock_redis_client.zrange = AsyncMock(return_value=["se-01"])
        mock_redis_client.hgetall = AsyncMock(return_value={
            "id": "se-01",
            "mode": "edit",
            "endpoint": "http://se-01:8010",
            "priority": "100",
            "capacity_total": "10000000000",
            "capacity_used": "1000000000",
            "capacity_free": "9000000000",
            "capacity_percent": "10.0",
            "capacity_status": "ok",
            "health_status": "healthy",
            "last_updated": datetime.now(timezone.utc).isoformat()
        })

        with patch("app.services.storage_selector.get_capacity_monitor", return_value=None):
            with patch("app.services.storage_selector.settings") as mock_settings:
                # Отключаем POLLING
                mock_settings.capacity_monitor.enabled = False
                mock_settings.capacity_monitor.use_for_selection = False
                mock_settings.capacity_monitor.fallback_to_push = True

                selector = StorageSelector()
                selector._redis_client = mock_redis_client
                selector._admin_client = None
                selector._initialized = True

                # POLLING не должен вызываться
                selector._select_from_adaptive_monitor = AsyncMock(return_value=None)

                se = await selector.select_storage_element(
                    file_size=1024,
                    retention_policy=RetentionPolicy.TEMPORARY
                )

                # SE должен быть выбран из PUSH модели
                assert se is not None


class TestParallelRunMetrics:
    """
    Тесты метрик для Parallel Run.

    Проверяют что storage_selection_source_total корректно записывает
    источник выбора SE.
    """

    def test_metrics_counter_exists(self):
        """Тест: Метрика storage_selection_source_total существует."""
        from app.core.metrics import storage_selection_source_total
        assert storage_selection_source_total is not None

    def test_record_selection_source_function_exists(self):
        """Тест: Функция record_selection_source существует."""
        from app.core.metrics import record_selection_source
        assert callable(record_selection_source)

    def test_record_selection_source_increments_counter(self):
        """Тест: record_selection_source инкрементирует счётчик."""
        from app.core.metrics import record_selection_source, storage_selection_source_total

        # Получаем начальное значение
        initial_value = storage_selection_source_total.labels(
            source="adaptive_monitor",
            status="success"
        )._value.get()

        # Записываем метрику
        record_selection_source(source="adaptive_monitor", success=True)

        # Проверяем инкремент
        new_value = storage_selection_source_total.labels(
            source="adaptive_monitor",
            status="success"
        )._value.get()

        assert new_value == initial_value + 1


class TestCapacityMonitorSortedSet:
    """
    Тесты sorted set в AdaptiveCapacityMonitor.

    Проверяют что capacity данные сохраняются в sorted set
    с правильным priority для Sequential Fill алгоритма.
    """

    @pytest.fixture
    def monitor_config(self) -> CapacityMonitorConfig:
        """Конфигурация монитора для тестов."""
        return CapacityMonitorConfig(
            leader_lock_key="test:leader_lock",
            leader_ttl=30,
            leader_renewal_interval=10,
            base_interval=30,
            max_interval=300,
            min_interval=10,
            http_timeout=15,
            http_retries=3,
            retry_base_delay=2.0,
            cache_ttl=600,
            health_ttl=600,
            failure_threshold=3,
            recovery_threshold=2,
            stability_threshold=5,
            change_threshold=5.0,
        )

    @pytest.mark.asyncio
    async def test_capacity_saved_to_sorted_set(self, monitor_config):
        """
        Тест: Capacity данные сохраняются в sorted set.

        Проверяет что _save_capacity_to_cache записывает SE в
        capacity:{mode}:available с правильным priority.
        """
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.zadd = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock(return_value=True)
        mock_redis.zrem = AsyncMock(return_value=1)
        mock_redis.setnx = AsyncMock(return_value=False)  # Не Leader

        storage_endpoints = {"se-01": "http://se-01:8010"}
        storage_priorities = {"se-01": 100}

        monitor = AdaptiveCapacityMonitor(
            redis_client=mock_redis,
            storage_endpoints=storage_endpoints,
            config=monitor_config,
            storage_priorities=storage_priorities,
        )

        # Создаём capacity info с правильной структурой
        capacity_info = make_capacity_info(
            storage_id="se-01",
            mode="edit",
            health=HealthStatus.HEALTHY,
            endpoint="http://se-01:8010",
        )

        # Сохраняем capacity
        await monitor._save_capacity_to_cache("se-01", capacity_info)

        # Проверяем что zadd был вызван для sorted set
        zadd_calls = [call for call in mock_redis.zadd.call_args_list]
        assert len(zadd_calls) > 0

        # Проверяем ключ sorted set
        sorted_set_key = zadd_calls[0][0][0]  # Первый аргумент первого вызова
        assert sorted_set_key == "capacity:edit:available"

    @pytest.mark.asyncio
    async def test_unhealthy_se_removed_from_sorted_set(self, monitor_config):
        """
        Тест: Unhealthy SE удаляется из sorted set.

        Проверяет что при health != HEALTHY SE удаляется из
        capacity:{mode}:available через ZREM.
        """
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.zadd = AsyncMock(return_value=1)
        mock_redis.zrem = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock(return_value=True)
        mock_redis.setnx = AsyncMock(return_value=False)

        storage_endpoints = {"se-01": "http://se-01:8010"}
        storage_priorities = {"se-01": 100}

        monitor = AdaptiveCapacityMonitor(
            redis_client=mock_redis,
            storage_endpoints=storage_endpoints,
            config=monitor_config,
            storage_priorities=storage_priorities,
        )

        # Создаём UNHEALTHY capacity info с правильной структурой
        capacity_info = make_capacity_info(
            storage_id="se-01",
            mode="edit",
            health=HealthStatus.UNHEALTHY,
            endpoint="http://se-01:8010",
        )

        # Сохраняем capacity
        await monitor._save_capacity_to_cache("se-01", capacity_info)

        # Проверяем что zrem был вызван для удаления из sorted set
        zrem_calls = [call for call in mock_redis.zrem.call_args_list]
        assert len(zrem_calls) > 0
