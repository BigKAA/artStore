"""
Unit тесты для GarbageCollectorService.

Тестирование стратегий очистки файлов:
1. TTL-based cleanup
2. Finalized files cleanup
3. Cleanup queue processing
4. Orphaned files detection
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.models.cleanup_queue import (
    CleanupPriority,
    CleanupReason,
    FileCleanupQueue,
)
from app.models.file import File, RetentionPolicy
from app.models.finalize_transaction import (
    FileFinalizeTransaction,
    FinalizeTransactionStatus,
)
from app.models.storage_element import StorageElement, StorageMode, StorageStatus
from app.services.garbage_collector_service import (
    GarbageCollectorService,
    GCRunResult,
    GCFileResult,
)


class TestGarbageCollectorService:
    """Тесты для GarbageCollectorService."""

    @pytest.fixture
    def gc_service(self):
        """Создание GC service с default настройками."""
        return GarbageCollectorService(
            batch_size=10,
            http_timeout=5,
            safety_margin_hours=24,
            orphan_grace_days=7,
            max_retry_count=3,
        )

    @pytest.fixture
    def mock_session(self):
        """Mock AsyncSession для тестов."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.flush = AsyncMock()
        return session

    def _create_mock_scalars_result(self, items):
        """Helper для создания mock результата с scalars().all() pattern."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = items
        mock_result.scalars.return_value = mock_scalars
        return mock_result

    def _create_mock_scalar_one_or_none_result(self, item):
        """Helper для создания mock результата с scalar_one_or_none() pattern."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = item
        return mock_result

    def _create_mock_fetchall_result(self, rows):
        """Helper для создания mock результата с fetchall() pattern."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = rows
        return mock_result

    # ========================================================================
    # Tests for TTL-based cleanup
    # ========================================================================

    @pytest.mark.asyncio
    async def test_cleanup_expired_ttl_finds_expired_files(
        self, gc_service, mock_session
    ):
        """
        Тест: _cleanup_expired_ttl находит файлы с истекшим TTL
        и добавляет их в cleanup queue.
        """
        # Создаём mock expired files
        now = datetime.now(timezone.utc)
        expired_file = MagicMock(spec=File)
        expired_file.file_id = uuid4()
        expired_file.storage_element_id = "se-01"
        expired_file.storage_path = "/data/test.pdf"
        expired_file.retention_policy = RetentionPolicy.TEMPORARY
        expired_file.ttl_expires_at = now - timedelta(hours=1)  # Истёк час назад
        expired_file.deleted_at = None

        # Mock для select File query
        mock_result = self._create_mock_scalars_result([expired_file])

        # Mock для existing queue check (нет существующей записи)
        mock_existing_result = self._create_mock_scalar_one_or_none_result(None)

        mock_session.execute.side_effect = [mock_result, mock_existing_result]

        # Вызываем метод
        added, failed, errors = await gc_service._cleanup_expired_ttl(mock_session)

        # Проверяем результат
        assert added == 1
        assert failed == 0
        assert len(errors) == 0
        assert mock_session.add.called

    @pytest.mark.asyncio
    async def test_cleanup_expired_ttl_skips_already_queued(
        self, gc_service, mock_session
    ):
        """
        Тест: _cleanup_expired_ttl пропускает файлы, уже находящиеся в очереди.
        """
        now = datetime.now(timezone.utc)
        expired_file = MagicMock(spec=File)
        expired_file.file_id = uuid4()
        expired_file.storage_element_id = "se-01"
        expired_file.retention_policy = RetentionPolicy.TEMPORARY
        expired_file.ttl_expires_at = now - timedelta(hours=1)
        expired_file.deleted_at = None

        # Mock для select File query
        mock_result = self._create_mock_scalars_result([expired_file])

        # Mock для existing queue check (УЖЕ есть запись в очереди)
        existing_queue_item = MagicMock(spec=FileCleanupQueue)
        mock_existing_result = self._create_mock_scalar_one_or_none_result(existing_queue_item)

        mock_session.execute.side_effect = [mock_result, mock_existing_result]

        # Вызываем метод
        added, failed, errors = await gc_service._cleanup_expired_ttl(mock_session)

        # Проверяем что файл пропущен
        assert added == 0
        assert failed == 0
        assert not mock_session.add.called

    @pytest.mark.asyncio
    async def test_cleanup_expired_ttl_no_expired_files(
        self, gc_service, mock_session
    ):
        """
        Тест: _cleanup_expired_ttl корректно обрабатывает случай без expired файлов.
        """
        # Mock для select File query - пустой результат
        mock_result = self._create_mock_scalars_result([])

        mock_session.execute.return_value = mock_result

        # Вызываем метод
        added, failed, errors = await gc_service._cleanup_expired_ttl(mock_session)

        # Проверяем результат
        assert added == 0
        assert failed == 0
        assert len(errors) == 0

    # ========================================================================
    # Tests for Finalized files cleanup
    # ========================================================================

    @pytest.mark.asyncio
    async def test_cleanup_finalized_files_with_safety_margin(
        self, gc_service, mock_session
    ):
        """
        Тест: _cleanup_finalized_files добавляет файлы только после safety margin.
        """
        now = datetime.now(timezone.utc)

        # Транзакция завершена 25 часов назад (больше safety margin)
        completed_txn = MagicMock(spec=FileFinalizeTransaction)
        completed_txn.file_id = uuid4()
        completed_txn.source_se = "se-edit-01"
        completed_txn.target_se = "se-rw-01"
        completed_txn.status = FinalizeTransactionStatus.COMPLETED
        completed_txn.completed_at = now - timedelta(hours=25)

        # Mock для select transactions query
        mock_result = self._create_mock_scalars_result([completed_txn])

        # Mock для existing queue check
        mock_existing_result = self._create_mock_scalar_one_or_none_result(None)

        # Mock для file query
        mock_file = MagicMock(spec=File)
        mock_file.storage_path = "/data/test.pdf"
        mock_file_result = self._create_mock_scalar_one_or_none_result(mock_file)

        mock_session.execute.side_effect = [mock_result, mock_existing_result, mock_file_result]

        # Вызываем метод
        added, failed, errors = await gc_service._cleanup_finalized_files(mock_session)

        # Проверяем результат
        assert added == 1
        assert failed == 0
        assert mock_session.add.called

    @pytest.mark.asyncio
    async def test_cleanup_finalized_files_within_safety_margin(
        self, gc_service, mock_session
    ):
        """
        Тест: _cleanup_finalized_files НЕ добавляет файлы в пределах safety margin.
        """
        now = datetime.now(timezone.utc)

        # Транзакция завершена 10 часов назад (в пределах safety margin)
        completed_txn = MagicMock(spec=FileFinalizeTransaction)
        completed_txn.file_id = uuid4()
        completed_txn.source_se = "se-edit-01"
        completed_txn.status = FinalizeTransactionStatus.COMPLETED
        completed_txn.completed_at = now - timedelta(hours=10)  # < 24h safety margin

        # Mock для select transactions query - пустой т.к. не прошёл safety margin
        mock_result = self._create_mock_scalars_result([])  # Query фильтрует по completed_at

        mock_session.execute.return_value = mock_result

        # Вызываем метод
        added, failed, errors = await gc_service._cleanup_finalized_files(mock_session)

        # Проверяем что файлы не добавлены
        assert added == 0
        assert not mock_session.add.called

    # ========================================================================
    # Tests for Cleanup Queue Processing
    # ========================================================================

    @pytest.mark.asyncio
    async def test_process_cleanup_queue_successful_delete(
        self, gc_service, mock_session
    ):
        """
        Тест: _process_cleanup_queue успешно удаляет файлы.
        """
        now = datetime.now(timezone.utc)

        # Очередь с одной записью
        queue_item = MagicMock(spec=FileCleanupQueue)
        queue_item.id = 1
        queue_item.file_id = uuid4()
        queue_item.storage_element_id = "se-01"
        queue_item.storage_path = "/data/test.pdf"
        queue_item.scheduled_at = now - timedelta(hours=1)
        queue_item.cleanup_reason = CleanupReason.TTL_EXPIRED
        queue_item.processed_at = None
        queue_item.retry_count = 0

        # Mock storage element
        storage_element = MagicMock(spec=StorageElement)
        storage_element.name = "se-01"
        storage_element.api_url = "http://storage-01:8010"
        storage_element.status = StorageStatus.ONLINE

        # Mock для queue query
        mock_queue_result = self._create_mock_scalars_result([queue_item])

        # Mock для storage elements query
        mock_se_result = self._create_mock_scalars_result([storage_element])

        mock_session.execute.side_effect = [mock_queue_result, mock_se_result]

        # Mock HTTP delete
        with patch.object(
            gc_service,
            '_delete_file_from_storage',
            return_value=(True, None)
        ) as mock_delete:
            with patch.object(
                gc_service,
                '_mark_file_as_deleted',
                return_value=None
            ):
                cleaned, failed, errors = await gc_service._process_cleanup_queue(mock_session)

        assert cleaned == 1
        assert failed == 0
        mock_delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_cleanup_queue_storage_offline(
        self, gc_service, mock_session
    ):
        """
        Тест: _process_cleanup_queue retry при offline storage element.
        """
        now = datetime.now(timezone.utc)

        queue_item = MagicMock(spec=FileCleanupQueue)
        queue_item.id = 1
        queue_item.file_id = uuid4()
        queue_item.storage_element_id = "se-offline"
        queue_item.cleanup_reason = CleanupReason.TTL_EXPIRED
        queue_item.processed_at = None
        queue_item.retry_count = 0

        # Storage element offline
        storage_element = MagicMock(spec=StorageElement)
        storage_element.name = "se-offline"
        storage_element.status = StorageStatus.OFFLINE

        mock_queue_result = self._create_mock_scalars_result([queue_item])

        mock_se_result = self._create_mock_scalars_result([storage_element])

        mock_session.execute.side_effect = [mock_queue_result, mock_se_result]

        cleaned, failed, errors = await gc_service._process_cleanup_queue(mock_session)

        assert cleaned == 0
        assert failed == 1
        # retry_count должен быть увеличен
        assert queue_item.retry_count == 1

    @pytest.mark.asyncio
    async def test_process_cleanup_queue_empty(self, gc_service, mock_session):
        """
        Тест: _process_cleanup_queue корректно обрабатывает пустую очередь.
        """
        mock_result = self._create_mock_scalars_result([])

        mock_session.execute.return_value = mock_result

        cleaned, failed, errors = await gc_service._process_cleanup_queue(mock_session)

        assert cleaned == 0
        assert failed == 0
        assert len(errors) == 0

    # ========================================================================
    # Tests for HTTP delete operations
    # ========================================================================

    @pytest.mark.asyncio
    async def test_delete_file_from_storage_success(self, gc_service):
        """
        Тест: _delete_file_from_storage успешно удаляет файл.
        """
        file_id = uuid4()

        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 204  # No Content

            mock_client_instance = AsyncMock()
            mock_client_instance.delete = AsyncMock(return_value=mock_response)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock()
            mock_client.return_value = mock_client_instance

            success, error = await gc_service._delete_file_from_storage(
                api_url="http://storage-01:8010",
                file_id=file_id,
            )

        assert success is True
        assert error is None

    @pytest.mark.asyncio
    async def test_delete_file_from_storage_404_is_success(self, gc_service):
        """
        Тест: _delete_file_from_storage считает 404 успехом (файл уже удалён).
        """
        file_id = uuid4()

        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 404  # Not Found

            mock_client_instance = AsyncMock()
            mock_client_instance.delete = AsyncMock(return_value=mock_response)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock()
            mock_client.return_value = mock_client_instance

            success, error = await gc_service._delete_file_from_storage(
                api_url="http://storage-01:8010",
                file_id=file_id,
            )

        assert success is True
        assert error is None

    @pytest.mark.asyncio
    async def test_delete_file_from_storage_server_error(self, gc_service):
        """
        Тест: _delete_file_from_storage обрабатывает server error.
        """
        file_id = uuid4()

        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"

            mock_client_instance = AsyncMock()
            mock_client_instance.delete = AsyncMock(return_value=mock_response)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock()
            mock_client.return_value = mock_client_instance

            success, error = await gc_service._delete_file_from_storage(
                api_url="http://storage-01:8010",
                file_id=file_id,
            )

        assert success is False
        assert "500" in error

    # ========================================================================
    # Tests for Orphaned files cleanup
    # ========================================================================

    @pytest.mark.asyncio
    async def test_cleanup_orphaned_files_detects_orphans(
        self, gc_service, mock_session
    ):
        """
        Тест: cleanup_orphaned_files обнаруживает orphaned файлы.
        """
        # Файлы на storage element
        file_ids_on_storage = [uuid4(), uuid4(), uuid4()]

        # Только один файл известен в БД
        known_file_id = file_ids_on_storage[0]

        mock_result = self._create_mock_fetchall_result([(known_file_id,)])

        # Mock для existing queue check - нет существующих записей
        mock_existing_result = self._create_mock_scalar_one_or_none_result(None)

        mock_session.execute.side_effect = [
            mock_result,
            mock_existing_result,
            mock_existing_result,
        ]

        added, failed, errors = await gc_service.cleanup_orphaned_files(
            session=mock_session,
            storage_element_id="se-01",
            file_ids_on_storage=file_ids_on_storage,
        )

        # 2 orphaned файла должны быть добавлены
        assert added == 2
        assert failed == 0

    @pytest.mark.asyncio
    async def test_cleanup_orphaned_files_empty_storage(
        self, gc_service, mock_session
    ):
        """
        Тест: cleanup_orphaned_files корректно обрабатывает пустой storage.
        """
        added, failed, errors = await gc_service.cleanup_orphaned_files(
            session=mock_session,
            storage_element_id="se-01",
            file_ids_on_storage=[],
        )

        assert added == 0
        assert failed == 0
        assert not mock_session.execute.called

    # ========================================================================
    # Tests for full GC run
    # ========================================================================

    @pytest.mark.asyncio
    async def test_run_garbage_collection_success(self, gc_service, mock_session):
        """
        Тест: run_garbage_collection успешно выполняет все этапы.
        """
        with patch.object(
            gc_service,
            '_process_cleanup_queue',
            return_value=(5, 0, [])
        ):
            with patch.object(
                gc_service,
                '_cleanup_expired_ttl',
                return_value=(3, 0, [])
            ):
                with patch.object(
                    gc_service,
                    '_cleanup_finalized_files',
                    return_value=(2, 0, [])
                ):
                    with patch.object(
                        gc_service,
                        '_update_queue_size_metric',
                        return_value=None
                    ):
                        result = await gc_service.run_garbage_collection(mock_session)

        assert isinstance(result, GCRunResult)
        assert result.queue_processed == 5
        assert result.ttl_cleaned == 3
        assert result.finalized_cleaned == 2
        assert result.total_cleaned == 10  # 5 + 3 + 2
        assert result.total_failed == 0
        assert len(result.errors) == 0
        assert result.duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_run_garbage_collection_with_errors(self, gc_service, mock_session):
        """
        Тест: run_garbage_collection собирает ошибки из всех этапов.
        """
        with patch.object(
            gc_service,
            '_process_cleanup_queue',
            return_value=(3, 2, ["Queue error 1"])
        ):
            with patch.object(
                gc_service,
                '_cleanup_expired_ttl',
                return_value=(1, 1, ["TTL error 1"])
            ):
                with patch.object(
                    gc_service,
                    '_cleanup_finalized_files',
                    return_value=(0, 1, ["Finalized error 1"])
                ):
                    with patch.object(
                        gc_service,
                        '_update_queue_size_metric',
                        return_value=None
                    ):
                        result = await gc_service.run_garbage_collection(mock_session)

        assert result.total_cleaned == 4  # 3 + 1 + 0
        assert result.total_failed == 4  # 2 + 1 + 1
        assert len(result.errors) == 3

    # ========================================================================
    # Tests for manual operations
    # ========================================================================

    @pytest.mark.asyncio
    async def test_add_to_cleanup_queue_manual(self, gc_service, mock_session):
        """
        Тест: add_to_cleanup_queue создаёт запись с правильными параметрами.
        """
        file_id = uuid4()

        result = await gc_service.add_to_cleanup_queue(
            session=mock_session,
            file_id=file_id,
            storage_element_id="se-01",
            reason=CleanupReason.MANUAL,
            priority=CleanupPriority.HIGH,
            storage_path="/data/manual.pdf",
        )

        assert mock_session.add.called
        assert mock_session.flush.called


class TestGCRunResult:
    """Тесты для GCRunResult dataclass."""

    def test_total_cleaned_calculation(self):
        """Тест: total_cleaned суммирует все cleaned counts."""
        result = GCRunResult(
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            ttl_cleaned=10,
            finalized_cleaned=5,
            orphaned_cleaned=3,
            queue_processed=7,
        )

        assert result.total_cleaned == 25  # 10 + 5 + 3 + 7

    def test_total_failed_calculation(self):
        """Тест: total_failed суммирует все failed counts."""
        result = GCRunResult(
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            ttl_failed=2,
            finalized_failed=1,
            orphaned_failed=3,
            queue_failed=4,
        )

        assert result.total_failed == 10  # 2 + 1 + 3 + 4

    def test_duration_seconds_calculation(self):
        """Тест: duration_seconds корректно вычисляет разницу."""
        start = datetime.now(timezone.utc)
        end = start + timedelta(seconds=30)

        result = GCRunResult(started_at=start, completed_at=end)

        assert result.duration_seconds == 30.0
