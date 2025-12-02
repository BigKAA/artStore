"""
Garbage Collector Service для автоматической очистки файлов.

Сервис для фонового удаления файлов по различным стратегиям:
1. TTL-based cleanup: удаление temporary файлов с истекшим TTL
2. Finalized files cleanup: удаление из Edit SE после успешной финализации (+24h safety)
3. Orphaned files cleanup: удаление файлов без записей в DB (age > 7 days)

Интервал запуска: каждые 6 часов (настраивается через SCHEDULER_GC_INTERVAL_HOURS).

Safety Features:
- 24-hour safety margin после финализации
- 7-day grace period для orphaned файлов
- Retry logic для transient failures (max 3 attempts)
- Batch processing для ограничения нагрузки

Prometheus Metrics:
- gc_files_cleaned_total: Количество очищенных файлов (по причине)
- gc_files_failed_total: Количество ошибок очистки (по причине)
- gc_run_duration_seconds: Длительность выполнения GC job
- gc_last_run_timestamp: Timestamp последнего запуска
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple
from uuid import UUID

import httpx
from prometheus_client import Counter, Gauge, Histogram
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
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
from app.models.storage_element import StorageElement, StorageStatus

logger = logging.getLogger(__name__)

# ============================================================================
# Prometheus Metrics для мониторинга GC операций
# ============================================================================

GC_FILES_CLEANED = Counter(
    "gc_files_cleaned_total",
    "Количество успешно очищенных файлов",
    ["reason"],  # ttl_expired, finalized, orphaned, manual
)

GC_FILES_FAILED = Counter(
    "gc_files_failed_total",
    "Количество ошибок при очистке файлов",
    ["reason", "error_type"],  # reason + timeout/connection/api_error
)

GC_RUN_DURATION = Histogram(
    "gc_run_duration_seconds",
    "Длительность выполнения GC job",
    ["cleanup_type"],  # full, ttl_only, finalized_only, orphaned_only
    buckets=[1, 5, 10, 30, 60, 120, 300, 600],
)

GC_LAST_RUN = Gauge(
    "gc_last_run_timestamp",
    "Unix timestamp последнего запуска GC job",
)

GC_QUEUE_SIZE = Gauge(
    "gc_queue_pending_size",
    "Количество файлов в очереди на удаление (pending)",
)


# ============================================================================
# Data Classes для результатов GC операций
# ============================================================================


@dataclass
class GCFileResult:
    """Результат очистки одного файла."""

    file_id: UUID
    storage_element_id: str
    reason: str
    success: bool
    error: Optional[str] = None


@dataclass
class GCRunResult:
    """Результат запуска GC job."""

    started_at: datetime
    completed_at: datetime
    ttl_cleaned: int = 0
    ttl_failed: int = 0
    finalized_cleaned: int = 0
    finalized_failed: int = 0
    orphaned_cleaned: int = 0
    orphaned_failed: int = 0
    queue_processed: int = 0
    queue_failed: int = 0
    errors: List[str] = field(default_factory=list)

    @property
    def total_cleaned(self) -> int:
        """Общее количество успешно очищенных файлов."""
        return self.ttl_cleaned + self.finalized_cleaned + self.orphaned_cleaned + self.queue_processed

    @property
    def total_failed(self) -> int:
        """Общее количество ошибок."""
        return self.ttl_failed + self.finalized_failed + self.orphaned_failed + self.queue_failed

    @property
    def duration_seconds(self) -> float:
        """Длительность выполнения в секундах."""
        return (self.completed_at - self.started_at).total_seconds()


# ============================================================================
# GarbageCollectorService
# ============================================================================


class GarbageCollectorService:
    """
    Сервис для Garbage Collection файлов.

    Выполняет три типа очистки:
    1. TTL-based: временные файлы с истекшим TTL
    2. Finalized: файлы из Edit SE после финализации (+24h safety margin)
    3. Orphaned: файлы без записей в БД (>7 дней)

    Также обрабатывает cleanup queue для асинхронного удаления.

    Attributes:
        batch_size: Максимальное количество файлов за одну итерацию
        http_timeout: Timeout для HTTP запросов к Storage Elements
        safety_margin_hours: Safety margin после финализации (default: 24h)
        orphan_grace_days: Grace period для orphaned файлов (default: 7 days)
        max_retry_count: Максимальное количество retry для failed операций
    """

    # Настройки по умолчанию
    DEFAULT_BATCH_SIZE = 100
    DEFAULT_HTTP_TIMEOUT = 30
    DEFAULT_SAFETY_MARGIN_HOURS = 24
    DEFAULT_ORPHAN_GRACE_DAYS = 7
    DEFAULT_MAX_RETRY_COUNT = 3

    # API endpoints на Storage Element
    DELETE_FILE_ENDPOINT = "/api/v1/files/{file_id}"

    def __init__(
        self,
        batch_size: Optional[int] = None,
        http_timeout: Optional[int] = None,
        safety_margin_hours: Optional[int] = None,
        orphan_grace_days: Optional[int] = None,
        max_retry_count: Optional[int] = None,
    ):
        """
        Инициализация GC сервиса.

        Args:
            batch_size: Максимальный batch size для обработки
            http_timeout: Timeout для HTTP запросов
            safety_margin_hours: Safety margin после финализации
            orphan_grace_days: Grace period для orphaned файлов
            max_retry_count: Max retry для failed операций
        """
        self.batch_size = batch_size or self.DEFAULT_BATCH_SIZE
        self.http_timeout = http_timeout or self.DEFAULT_HTTP_TIMEOUT
        self.safety_margin_hours = safety_margin_hours or self.DEFAULT_SAFETY_MARGIN_HOURS
        self.orphan_grace_days = orphan_grace_days or self.DEFAULT_ORPHAN_GRACE_DAYS
        self.max_retry_count = max_retry_count or self.DEFAULT_MAX_RETRY_COUNT

    # ========================================================================
    # Main GC Entry Point
    # ========================================================================

    async def run_garbage_collection(self, session: AsyncSession) -> GCRunResult:
        """
        Запуск полного цикла Garbage Collection.

        Выполняет последовательно:
        1. Обработка cleanup queue (файлы с scheduled_at <= now)
        2. TTL-based cleanup (temporary файлы с истекшим TTL)
        3. Finalized files cleanup (Edit SE после финализации +24h)

        Note: Orphaned cleanup выполняется отдельным методом по запросу,
        так как требует сканирования Storage Elements.

        Args:
            session: AsyncSession для работы с БД

        Returns:
            GCRunResult: Результаты выполнения GC
        """
        started_at = datetime.now(timezone.utc)
        result = GCRunResult(
            started_at=started_at,
            completed_at=started_at,  # Будет обновлено в конце
        )

        logger.info("Starting Garbage Collection job")
        GC_LAST_RUN.set(started_at.timestamp())

        try:
            # 1. Обработка cleanup queue
            queue_cleaned, queue_failed, queue_errors = await self._process_cleanup_queue(session)
            result.queue_processed = queue_cleaned
            result.queue_failed = queue_failed
            result.errors.extend(queue_errors)

            # 2. TTL-based cleanup
            ttl_cleaned, ttl_failed, ttl_errors = await self._cleanup_expired_ttl(session)
            result.ttl_cleaned = ttl_cleaned
            result.ttl_failed = ttl_failed
            result.errors.extend(ttl_errors)

            # 3. Finalized files cleanup (добавление в queue)
            finalized_cleaned, finalized_failed, finalized_errors = await self._cleanup_finalized_files(session)
            result.finalized_cleaned = finalized_cleaned
            result.finalized_failed = finalized_failed
            result.errors.extend(finalized_errors)

            # Commit всех изменений
            await session.commit()

        except Exception as e:
            logger.error(f"GC job failed with exception: {e}", exc_info=True)
            result.errors.append(f"GC job exception: {str(e)}")
            await session.rollback()

        finally:
            result.completed_at = datetime.now(timezone.utc)

            # Обновляем метрики
            GC_RUN_DURATION.labels(cleanup_type="full").observe(result.duration_seconds)

            # Обновляем размер очереди
            await self._update_queue_size_metric(session)

            logger.info(
                f"GC job completed: "
                f"cleaned={result.total_cleaned}, failed={result.total_failed}, "
                f"duration={result.duration_seconds:.2f}s"
            )

        return result

    # ========================================================================
    # Cleanup Queue Processing
    # ========================================================================

    async def _process_cleanup_queue(
        self, session: AsyncSession
    ) -> Tuple[int, int, List[str]]:
        """
        Обработка cleanup queue - удаление файлов, готовых к очистке.

        Выбирает записи из file_cleanup_queue где:
        - processed_at IS NULL (не обработаны)
        - scheduled_at <= now (время наступило)
        - retry_count < max_retry_count (не превышен лимит retry)

        Сортировка: по priority DESC, затем по scheduled_at ASC.

        Args:
            session: AsyncSession для работы с БД

        Returns:
            Tuple[int, int, List[str]]: (cleaned_count, failed_count, errors)
        """
        cleaned_count = 0
        failed_count = 0
        errors: List[str] = []
        now = datetime.now(timezone.utc)

        logger.debug("Processing cleanup queue")

        # Получаем записи для обработки
        query = (
            select(FileCleanupQueue)
            .where(
                and_(
                    FileCleanupQueue.processed_at.is_(None),
                    FileCleanupQueue.scheduled_at <= now,
                    FileCleanupQueue.retry_count < self.max_retry_count,
                )
            )
            .order_by(
                FileCleanupQueue.priority.desc(),
                FileCleanupQueue.scheduled_at.asc(),
            )
            .limit(self.batch_size)
        )

        result = await session.execute(query)
        queue_items = result.scalars().all()

        if not queue_items:
            logger.debug("Cleanup queue is empty")
            return 0, 0, []

        logger.info(f"Processing {len(queue_items)} items from cleanup queue")

        # Получаем storage elements для определения URL
        storage_elements = await self._get_storage_elements_map(session)

        for item in queue_items:
            try:
                # Получаем URL storage element
                se = storage_elements.get(item.storage_element_id)
                if not se:
                    # SE не найден - пропускаем или помечаем как failed
                    item.processed_at = now
                    item.success = False
                    item.error_message = f"Storage element {item.storage_element_id} not found in DB"
                    item.retry_count += 1
                    failed_count += 1
                    GC_FILES_FAILED.labels(reason=item.cleanup_reason, error_type="se_not_found").inc()
                    continue

                if se.status != StorageStatus.ONLINE:
                    # SE offline - retry позже
                    item.retry_count += 1
                    item.error_message = f"Storage element {item.storage_element_id} is {se.status.value}"
                    failed_count += 1
                    GC_FILES_FAILED.labels(reason=item.cleanup_reason, error_type="se_offline").inc()
                    continue

                # Вызываем DELETE endpoint на Storage Element
                success, error = await self._delete_file_from_storage(
                    api_url=se.api_url,
                    file_id=item.file_id,
                )

                item.processed_at = now
                item.success = success

                if success:
                    cleaned_count += 1
                    GC_FILES_CLEANED.labels(reason=item.cleanup_reason).inc()

                    # Помечаем файл как удалённый в files таблице
                    await self._mark_file_as_deleted(
                        session=session,
                        file_id=item.file_id,
                        reason=item.cleanup_reason,
                    )

                    logger.debug(
                        f"File {item.file_id} cleaned from {item.storage_element_id}, "
                        f"reason={item.cleanup_reason}"
                    )
                else:
                    item.error_message = error
                    item.retry_count += 1
                    failed_count += 1
                    GC_FILES_FAILED.labels(reason=item.cleanup_reason, error_type="delete_failed").inc()
                    errors.append(f"Failed to delete {item.file_id}: {error}")

            except Exception as e:
                item.processed_at = now
                item.success = False
                item.error_message = str(e)
                item.retry_count += 1
                failed_count += 1
                GC_FILES_FAILED.labels(reason=item.cleanup_reason, error_type="exception").inc()
                errors.append(f"Exception processing {item.file_id}: {str(e)}")
                logger.error(f"Exception processing queue item {item.id}: {e}", exc_info=True)

        return cleaned_count, failed_count, errors

    # ========================================================================
    # TTL-Based Cleanup
    # ========================================================================

    async def _cleanup_expired_ttl(
        self, session: AsyncSession
    ) -> Tuple[int, int, List[str]]:
        """
        Очистка файлов с истекшим TTL.

        Находит temporary файлы где:
        - retention_policy = TEMPORARY
        - ttl_expires_at <= now
        - deleted_at IS NULL (не удалены)
        - Нет pending записи в cleanup queue

        Добавляет их в cleanup queue с reason=ttl_expired.

        Args:
            session: AsyncSession для работы с БД

        Returns:
            Tuple[int, int, List[str]]: (added_to_queue, failed, errors)
        """
        added_count = 0
        failed_count = 0
        errors: List[str] = []
        now = datetime.now(timezone.utc)

        logger.debug("Checking for TTL-expired files")

        # Находим файлы с истекшим TTL
        query = (
            select(File)
            .where(
                and_(
                    File.retention_policy == RetentionPolicy.TEMPORARY,
                    File.ttl_expires_at <= now,
                    File.deleted_at.is_(None),
                )
            )
            .limit(self.batch_size)
        )

        result = await session.execute(query)
        expired_files = result.scalars().all()

        if not expired_files:
            logger.debug("No TTL-expired files found")
            return 0, 0, []

        logger.info(f"Found {len(expired_files)} TTL-expired files")

        for file in expired_files:
            try:
                # Проверяем, нет ли уже pending записи в очереди
                existing_query = (
                    select(FileCleanupQueue)
                    .where(
                        and_(
                            FileCleanupQueue.file_id == file.file_id,
                            FileCleanupQueue.processed_at.is_(None),
                        )
                    )
                )
                existing_result = await session.execute(existing_query)
                if existing_result.scalar_one_or_none():
                    logger.debug(f"File {file.file_id} already in cleanup queue, skipping")
                    continue

                # Добавляем в очередь
                queue_item = FileCleanupQueue(
                    file_id=file.file_id,
                    storage_element_id=file.storage_element_id,
                    storage_path=file.storage_path,
                    scheduled_at=now,  # Сразу готов к удалению
                    priority=CleanupPriority.NORMAL,
                    cleanup_reason=CleanupReason.TTL_EXPIRED,
                )
                session.add(queue_item)
                added_count += 1

                logger.debug(f"Added TTL-expired file {file.file_id} to cleanup queue")

            except Exception as e:
                failed_count += 1
                errors.append(f"Failed to queue TTL file {file.file_id}: {str(e)}")
                logger.error(f"Exception queueing TTL file {file.file_id}: {e}", exc_info=True)

        logger.info(f"TTL cleanup: added {added_count} files to queue, {failed_count} failed")
        return added_count, failed_count, errors

    # ========================================================================
    # Finalized Files Cleanup
    # ========================================================================

    async def _cleanup_finalized_files(
        self, session: AsyncSession
    ) -> Tuple[int, int, List[str]]:
        """
        Очистка файлов после успешной финализации.

        Находит файлы где:
        - finalized_at IS NOT NULL (финализированы)
        - finalized_at + safety_margin <= now (прошёл safety margin)
        - Есть COMPLETED транзакция финализации
        - Нет pending записи в cleanup queue для source SE

        Добавляет в cleanup queue для удаления с source (Edit) SE.

        Args:
            session: AsyncSession для работы с БД

        Returns:
            Tuple[int, int, List[str]]: (added_to_queue, failed, errors)
        """
        added_count = 0
        failed_count = 0
        errors: List[str] = []
        now = datetime.now(timezone.utc)
        safety_cutoff = now - timedelta(hours=self.safety_margin_hours)

        logger.debug("Checking for finalized files ready for cleanup")

        # Находим завершённые транзакции финализации с прошедшим safety margin
        query = (
            select(FileFinalizeTransaction)
            .where(
                and_(
                    FileFinalizeTransaction.status == FinalizeTransactionStatus.COMPLETED,
                    FileFinalizeTransaction.completed_at <= safety_cutoff,
                )
            )
            .limit(self.batch_size)
        )

        result = await session.execute(query)
        completed_transactions = result.scalars().all()

        if not completed_transactions:
            logger.debug("No finalized files ready for cleanup")
            return 0, 0, []

        logger.info(f"Found {len(completed_transactions)} finalized transactions ready for cleanup")

        for txn in completed_transactions:
            try:
                # Проверяем, нет ли уже pending записи в очереди для source SE
                existing_query = (
                    select(FileCleanupQueue)
                    .where(
                        and_(
                            FileCleanupQueue.file_id == txn.file_id,
                            FileCleanupQueue.storage_element_id == txn.source_se,
                            FileCleanupQueue.processed_at.is_(None),
                        )
                    )
                )
                existing_result = await session.execute(existing_query)
                if existing_result.scalar_one_or_none():
                    logger.debug(f"File {txn.file_id} from {txn.source_se} already in cleanup queue")
                    continue

                # Получаем информацию о файле для storage_path
                file_query = select(File).where(File.file_id == txn.file_id)
                file_result = await session.execute(file_query)
                file_record = file_result.scalar_one_or_none()

                # Добавляем в очередь для удаления с source (Edit) SE
                queue_item = FileCleanupQueue(
                    file_id=txn.file_id,
                    storage_element_id=txn.source_se,
                    storage_path=file_record.storage_path if file_record else None,
                    scheduled_at=now,  # Сразу готов к удалению (safety margin уже прошёл)
                    priority=CleanupPriority.NORMAL,
                    cleanup_reason=CleanupReason.FINALIZED,
                )
                session.add(queue_item)
                added_count += 1

                logger.debug(
                    f"Added finalized file {txn.file_id} from source SE {txn.source_se} "
                    f"to cleanup queue"
                )

            except Exception as e:
                failed_count += 1
                errors.append(f"Failed to queue finalized file {txn.file_id}: {str(e)}")
                logger.error(f"Exception queueing finalized file {txn.file_id}: {e}", exc_info=True)

        logger.info(f"Finalized cleanup: added {added_count} files to queue, {failed_count} failed")
        return added_count, failed_count, errors

    # ========================================================================
    # Orphaned Files Cleanup (On-Demand)
    # ========================================================================

    async def cleanup_orphaned_files(
        self,
        session: AsyncSession,
        storage_element_id: str,
        file_ids_on_storage: List[UUID],
    ) -> Tuple[int, int, List[str]]:
        """
        Очистка orphaned файлов на Storage Element.

        Сравнивает список файлов на Storage Element с записями в БД.
        Файлы, которых нет в БД и которые старше orphan_grace_days,
        добавляются в cleanup queue.

        Note: Этот метод вызывается по запросу, не автоматически.
        Список файлов на SE получается через внешний механизм (например, API).

        Args:
            session: AsyncSession для работы с БД
            storage_element_id: ID storage element
            file_ids_on_storage: Список file_id на storage element

        Returns:
            Tuple[int, int, List[str]]: (added_to_queue, failed, errors)
        """
        added_count = 0
        failed_count = 0
        errors: List[str] = []
        now = datetime.now(timezone.utc)

        if not file_ids_on_storage:
            return 0, 0, []

        logger.info(
            f"Checking {len(file_ids_on_storage)} files on {storage_element_id} for orphans"
        )

        # Получаем все известные file_id из БД
        db_query = select(File.file_id).where(File.file_id.in_(file_ids_on_storage))
        db_result = await session.execute(db_query)
        known_file_ids = {row[0] for row in db_result.fetchall()}

        # Находим orphaned файлы
        orphaned_ids = set(file_ids_on_storage) - known_file_ids

        if not orphaned_ids:
            logger.debug(f"No orphaned files found on {storage_element_id}")
            return 0, 0, []

        logger.warning(
            f"Found {len(orphaned_ids)} orphaned files on {storage_element_id}"
        )

        # Добавляем в очередь с отложенным временем (grace period)
        scheduled_at = now + timedelta(days=self.orphan_grace_days)

        for file_id in orphaned_ids:
            try:
                # Проверяем, нет ли уже pending записи
                existing_query = (
                    select(FileCleanupQueue)
                    .where(
                        and_(
                            FileCleanupQueue.file_id == file_id,
                            FileCleanupQueue.storage_element_id == storage_element_id,
                            FileCleanupQueue.processed_at.is_(None),
                        )
                    )
                )
                existing_result = await session.execute(existing_query)
                if existing_result.scalar_one_or_none():
                    continue

                queue_item = FileCleanupQueue(
                    file_id=file_id,
                    storage_element_id=storage_element_id,
                    storage_path=None,  # Неизвестен для orphaned
                    scheduled_at=scheduled_at,  # После grace period
                    priority=CleanupPriority.LOW,
                    cleanup_reason=CleanupReason.ORPHANED,
                )
                session.add(queue_item)
                added_count += 1

            except Exception as e:
                failed_count += 1
                errors.append(f"Failed to queue orphaned file {file_id}: {str(e)}")

        logger.info(
            f"Orphaned cleanup on {storage_element_id}: "
            f"added {added_count} files to queue (scheduled in {self.orphan_grace_days} days), "
            f"{failed_count} failed"
        )

        return added_count, failed_count, errors

    # ========================================================================
    # Helper Methods
    # ========================================================================

    async def _get_storage_elements_map(
        self, session: AsyncSession
    ) -> dict:
        """
        Получить map storage_element_id -> StorageElement.

        Args:
            session: AsyncSession для работы с БД

        Returns:
            dict: Map ID → StorageElement
        """
        query = select(StorageElement)
        result = await session.execute(query)
        storage_elements = result.scalars().all()
        return {se.name: se for se in storage_elements}

    async def _delete_file_from_storage(
        self,
        api_url: str,
        file_id: UUID,
    ) -> Tuple[bool, Optional[str]]:
        """
        Удаление файла с Storage Element через HTTP DELETE.

        Args:
            api_url: Base URL storage element
            file_id: UUID файла для удаления

        Returns:
            Tuple[bool, Optional[str]]: (success, error_message)
        """
        url = f"{api_url.rstrip('/')}{self.DELETE_FILE_ENDPOINT.format(file_id=file_id)}"

        try:
            async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                response = await client.delete(url)

                if response.status_code in (200, 204, 404):
                    # 200/204 = успешно удалено
                    # 404 = файл уже не существует (считаем успехом)
                    return True, None

                return False, f"HTTP {response.status_code}: {response.text[:200]}"

        except httpx.TimeoutException:
            return False, f"Timeout after {self.http_timeout}s"

        except httpx.ConnectError as e:
            return False, f"Connection error: {str(e)}"

        except Exception as e:
            return False, f"Unexpected error: {str(e)}"

    async def _mark_file_as_deleted(
        self,
        session: AsyncSession,
        file_id: UUID,
        reason: str,
    ) -> None:
        """
        Пометить файл как удалённый в таблице files.

        Args:
            session: AsyncSession для работы с БД
            file_id: UUID файла
            reason: Причина удаления
        """
        now = datetime.now(timezone.utc)

        stmt = (
            update(File)
            .where(File.file_id == file_id)
            .values(
                deleted_at=now,
                deletion_reason=reason,
            )
        )
        await session.execute(stmt)

    async def _update_queue_size_metric(self, session: AsyncSession) -> None:
        """
        Обновить метрику размера очереди.

        Args:
            session: AsyncSession для работы с БД
        """
        try:
            from sqlalchemy import func

            query = select(func.count()).select_from(FileCleanupQueue).where(
                FileCleanupQueue.processed_at.is_(None)
            )
            result = await session.execute(query)
            count = result.scalar() or 0
            GC_QUEUE_SIZE.set(count)
        except Exception as e:
            logger.warning(f"Failed to update queue size metric: {e}")

    # ========================================================================
    # Manual Operations
    # ========================================================================

    async def add_to_cleanup_queue(
        self,
        session: AsyncSession,
        file_id: UUID,
        storage_element_id: str,
        reason: str,
        priority: int = CleanupPriority.NORMAL,
        scheduled_at: Optional[datetime] = None,
        storage_path: Optional[str] = None,
    ) -> FileCleanupQueue:
        """
        Добавить файл в очередь на удаление вручную.

        Args:
            session: AsyncSession для работы с БД
            file_id: UUID файла
            storage_element_id: ID storage element
            reason: Причина удаления
            priority: Приоритет (default: NORMAL)
            scheduled_at: Время удаления (default: сейчас)
            storage_path: Путь к файлу (опционально)

        Returns:
            FileCleanupQueue: Созданная запись
        """
        if scheduled_at is None:
            scheduled_at = datetime.now(timezone.utc)

        queue_item = FileCleanupQueue(
            file_id=file_id,
            storage_element_id=storage_element_id,
            storage_path=storage_path,
            scheduled_at=scheduled_at,
            priority=priority,
            cleanup_reason=reason,
        )
        session.add(queue_item)
        await session.flush()

        logger.info(
            f"Manually added file {file_id} to cleanup queue: "
            f"reason={reason}, priority={priority}, scheduled={scheduled_at}"
        )

        return queue_item


# ============================================================================
# Global Instance
# ============================================================================

garbage_collector_service = GarbageCollectorService()
