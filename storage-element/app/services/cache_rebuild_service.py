"""
Cache Rebuild Service для синхронизации PostgreSQL кеша с attr.json файлами.

Поддерживает:
- Полную пересборку кеша (truncate + rebuild)
- Инкрементальную пересборку (только новые файлы)
- Dry-run проверку консистентности
- Priority-based locking через CacheLockManager
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set
from uuid import UUID
from dataclasses import dataclass, field

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.file_metadata import FileMetadata
from app.services.storage_backends import get_storage_backend, AttrFileInfo
from app.services.cache_lock_manager import (
    CacheLockManager,
    LockType,
    get_cache_lock_manager
)

logger = logging.getLogger(__name__)


@dataclass
class ConsistencyReport:
    """Отчёт о консистентности кеша."""

    # Статистика
    total_attr_files: int = 0            # Всего attr.json в storage
    total_cache_entries: int = 0         # Всего записей в cache

    # Orphans
    orphan_cache_entries: List[str] = field(default_factory=list)  # file_id в cache, но нет attr.json
    orphan_attr_files: List[str] = field(default_factory=list)     # attr.json есть, но нет в cache

    # Expired
    expired_cache_entries: List[str] = field(default_factory=list)  # cache entries с истёкшим TTL

    # Summary
    is_consistent: bool = False
    inconsistency_percentage: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dict для JSON response."""
        return {
            "total_attr_files": self.total_attr_files,
            "total_cache_entries": self.total_cache_entries,
            "orphan_cache_count": len(self.orphan_cache_entries),
            "orphan_attr_count": len(self.orphan_attr_files),
            "expired_cache_count": len(self.expired_cache_entries),
            "is_consistent": self.is_consistent,
            "inconsistency_percentage": round(self.inconsistency_percentage, 2),
            "details": {
                "orphan_cache_entries": self.orphan_cache_entries[:10],  # First 10 для краткости
                "orphan_attr_files": self.orphan_attr_files[:10],
                "expired_cache_entries": self.expired_cache_entries[:10]
            }
        }


@dataclass
class RebuildResult:
    """Результат rebuild операции."""

    operation_type: str  # "full" | "incremental" | "cleanup_expired"
    started_at: datetime
    completed_at: datetime
    duration_seconds: float

    # Статистика
    attr_files_scanned: int = 0
    cache_entries_before: int = 0
    cache_entries_after: int = 0

    # Операции
    entries_created: int = 0
    entries_updated: int = 0
    entries_deleted: int = 0

    # Ошибки
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dict для JSON response."""
        return {
            "operation_type": self.operation_type,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "duration_seconds": round(self.duration_seconds, 2),
            "statistics": {
                "attr_files_scanned": self.attr_files_scanned,
                "cache_entries_before": self.cache_entries_before,
                "cache_entries_after": self.cache_entries_after,
                "entries_created": self.entries_created,
                "entries_updated": self.entries_updated,
                "entries_deleted": self.entries_deleted
            },
            "errors": self.errors[:10]  # First 10 errors
        }


class CacheRebuildService:
    """
    Сервис для синхронизации PostgreSQL кеша с attr.json файлами.

    Примеры:
        >>> rebuild_svc = CacheRebuildService(db_session)
        >>>
        >>> # Проверка консистентности (dry-run)
        >>> report = await rebuild_svc.check_consistency()
        >>>
        >>> # Полная пересборка
        >>> result = await rebuild_svc.rebuild_cache_full()
        >>>
        >>> # Инкрементальная пересборка
        >>> result = await rebuild_svc.rebuild_cache_incremental()
    """

    def __init__(
        self,
        db: AsyncSession,
        lock_manager: Optional[CacheLockManager] = None
    ):
        """
        Инициализация Cache Rebuild Service.

        Args:
            db: Database session
            lock_manager: Lock manager (опционально, по умолчанию singleton)
        """
        self.db = db
        self.lock_manager = lock_manager
        self.storage_backend = get_storage_backend()

    async def _get_lock_manager(self) -> CacheLockManager:
        """Получить lock manager (lazy init)."""
        if not self.lock_manager:
            self.lock_manager = await get_cache_lock_manager()
        return self.lock_manager

    async def check_consistency(self, dry_run: bool = True) -> ConsistencyReport:
        """
        Проверка консистентности кеша с attr.json файлами.

        Dry-run операция - НЕ изменяет данные, только анализирует.

        Args:
            dry_run: Если True, только анализ без изменений

        Returns:
            ConsistencyReport: Отчёт о консистентности
        """
        lock_mgr = await self._get_lock_manager()

        # Acquire lock (MANUAL_CHECK priority)
        acquired = await lock_mgr.acquire_lock(
            LockType.MANUAL_CHECK,
            timeout=600,  # 10 минут
            blocking=False
        )

        if not acquired:
            logger.warning("Cannot acquire lock for consistency check - higher priority operation in progress")
            raise RuntimeError("Cannot acquire lock: higher priority operation in progress")

        try:
            logger.info("Starting consistency check", extra={"element_id": settings.storage.element_id})

            report = ConsistencyReport()

            # 1. Получить все attr.json файлы из storage
            attr_file_ids = set()
            async for attr_info in self.storage_backend.list_attr_files():
                attr_file_ids.add(attr_info.file_id)
                report.total_attr_files += 1

            logger.info(f"Found {len(attr_file_ids)} attr.json files in storage")

            # 2. Получить все file_id из cache
            result = await self.db.execute(select(FileMetadata.file_id))
            cache_file_ids = {str(row[0]) for row in result.all()}
            report.total_cache_entries = len(cache_file_ids)

            logger.info(f"Found {len(cache_file_ids)} entries in cache")

            # 3. Найти orphans
            # Orphan cache: в cache есть, но нет attr.json
            report.orphan_cache_entries = list(cache_file_ids - attr_file_ids)

            # Orphan attr: attr.json есть, но нет в cache
            report.orphan_attr_files = list(attr_file_ids - cache_file_ids)

            # 4. Найти expired entries
            result = await self.db.execute(
                select(FileMetadata).where(
                    func.now() > (
                        FileMetadata.cache_updated_at +
                        func.make_interval(0, 0, 0, 0, FileMetadata.cache_ttl_hours)
                    )
                )
            )
            expired_entries = result.scalars().all()
            report.expired_cache_entries = [str(entry.file_id) for entry in expired_entries]

            logger.info(f"Found {len(report.expired_cache_entries)} expired cache entries")

            # 5. Вычислить consistency
            total_inconsistencies = (
                len(report.orphan_cache_entries) +
                len(report.orphan_attr_files)
            )

            if report.total_attr_files > 0:
                report.inconsistency_percentage = (
                    total_inconsistencies / report.total_attr_files
                ) * 100

            report.is_consistent = (
                len(report.orphan_cache_entries) == 0 and
                len(report.orphan_attr_files) == 0
            )

            logger.info(
                "Consistency check completed",
                extra={
                    "is_consistent": report.is_consistent,
                    "inconsistency_percentage": report.inconsistency_percentage,
                    "orphan_cache": len(report.orphan_cache_entries),
                    "orphan_attr": len(report.orphan_attr_files),
                    "expired": len(report.expired_cache_entries)
                }
            )

            return report

        finally:
            await lock_mgr.release_lock(LockType.MANUAL_CHECK)

    async def rebuild_cache_full(self) -> RebuildResult:
        """
        Полная пересборка кеша из attr.json файлов.

        Процесс:
        1. Acquire MANUAL_REBUILD lock (блокирует все остальные операции)
        2. TRUNCATE таблицу cache
        3. Scan всех attr.json файлов
        4. INSERT метаданных в cache
        5. Release lock

        Returns:
            RebuildResult: Результат пересборки
        """
        lock_mgr = await self._get_lock_manager()

        # Acquire lock (MANUAL_REBUILD priority - highest)
        acquired = await lock_mgr.acquire_lock(
            LockType.MANUAL_REBUILD,
            timeout=1800,  # 30 минут
            blocking=False
        )

        if not acquired:
            logger.warning("Cannot acquire lock for full rebuild - operation already in progress")
            raise RuntimeError("Cannot acquire lock: rebuild already in progress")

        started_at = datetime.now(timezone.utc)

        try:
            logger.info(
                "Starting full cache rebuild",
                extra={"element_id": settings.storage.element_id}
            )

            result = RebuildResult(
                operation_type="full",
                started_at=started_at,
                completed_at=started_at,  # Will update at end
                duration_seconds=0
            )

            # 1. Подсчёт cache entries до очистки
            count_result = await self.db.execute(select(func.count(FileMetadata.file_id)))
            result.cache_entries_before = count_result.scalar()

            logger.info(f"Cache entries before rebuild: {result.cache_entries_before}")

            # 2. TRUNCATE cache table
            # ВАЖНО: Используем raw SQL для TRUNCATE (быстрее DELETE)
            table_name = f"{settings.database.table_prefix}_files"
            await self.db.execute(text(f"TRUNCATE TABLE {table_name}"))
            await self.db.commit()

            logger.info(f"Truncated cache table: {table_name}")

            # 3. Scan всех attr.json и rebuild
            async for attr_info in self.storage_backend.list_attr_files():
                result.attr_files_scanned += 1

                try:
                    # Прочитать attr.json
                    attributes = await self.storage_backend.read_attr_file(
                        attr_info.relative_path
                    )

                    # Создать FileMetadata entry
                    metadata = self._create_metadata_from_attr(attributes)

                    # Insert в cache
                    self.db.add(metadata)
                    result.entries_created += 1

                    # Commit каждые 100 записей для performance
                    if result.entries_created % 100 == 0:
                        await self.db.commit()
                        logger.info(f"Processed {result.entries_created} entries...")

                except Exception as e:
                    error_msg = f"Failed to process attr file {attr_info.relative_path}: {e}"
                    logger.error(error_msg)
                    result.errors.append(error_msg)
                    continue

            # Final commit
            await self.db.commit()

            # 4. Подсчёт cache entries после rebuild
            count_result = await self.db.execute(select(func.count(FileMetadata.file_id)))
            result.cache_entries_after = count_result.scalar()

            # 5. Finalize result
            completed_at = datetime.now(timezone.utc)
            result.completed_at = completed_at
            result.duration_seconds = (completed_at - started_at).total_seconds()

            logger.info(
                "Full cache rebuild completed",
                extra={
                    "attr_files_scanned": result.attr_files_scanned,
                    "entries_created": result.entries_created,
                    "cache_entries_after": result.cache_entries_after,
                    "duration_seconds": result.duration_seconds,
                    "errors": len(result.errors)
                }
            )

            return result

        finally:
            await lock_mgr.release_lock(LockType.MANUAL_REBUILD)

    async def rebuild_cache_incremental(self) -> RebuildResult:
        """
        Инкрементальная пересборка кеша.

        Добавляет только отсутствующие в cache записи из attr.json.
        НЕ удаляет orphan cache entries.

        Returns:
            RebuildResult: Результат пересборки
        """
        lock_mgr = await self._get_lock_manager()

        acquired = await lock_mgr.acquire_lock(
            LockType.MANUAL_REBUILD,
            timeout=1800,
            blocking=False
        )

        if not acquired:
            raise RuntimeError("Cannot acquire lock: rebuild already in progress")

        started_at = datetime.now(timezone.utc)

        try:
            logger.info("Starting incremental cache rebuild")

            result = RebuildResult(
                operation_type="incremental",
                started_at=started_at,
                completed_at=started_at,
                duration_seconds=0
            )

            # 1. Подсчёт cache entries
            count_result = await self.db.execute(select(func.count(FileMetadata.file_id)))
            result.cache_entries_before = count_result.scalar()

            # 2. Получить все file_id из cache
            cache_result = await self.db.execute(select(FileMetadata.file_id))
            cache_file_ids = {str(row[0]) for row in cache_result.all()}

            logger.info(f"Cache contains {len(cache_file_ids)} entries")

            # 3. Scan attr.json и добавить отсутствующие
            async for attr_info in self.storage_backend.list_attr_files():
                result.attr_files_scanned += 1

                # Проверить есть ли уже в cache
                if attr_info.file_id in cache_file_ids:
                    continue  # Skip, уже есть

                try:
                    # Прочитать attr.json
                    attributes = await self.storage_backend.read_attr_file(
                        attr_info.relative_path
                    )

                    # Создать FileMetadata
                    metadata = self._create_metadata_from_attr(attributes)

                    # Insert в cache
                    self.db.add(metadata)
                    result.entries_created += 1

                    # Commit каждые 100
                    if result.entries_created % 100 == 0:
                        await self.db.commit()
                        logger.info(f"Added {result.entries_created} new entries...")

                except Exception as e:
                    error_msg = f"Failed to process {attr_info.relative_path}: {e}"
                    logger.error(error_msg)
                    result.errors.append(error_msg)
                    continue

            # Final commit
            await self.db.commit()

            # 4. Final statistics
            count_result = await self.db.execute(select(func.count(FileMetadata.file_id)))
            result.cache_entries_after = count_result.scalar()

            completed_at = datetime.now(timezone.utc)
            result.completed_at = completed_at
            result.duration_seconds = (completed_at - started_at).total_seconds()

            logger.info(
                "Incremental cache rebuild completed",
                extra={
                    "attr_files_scanned": result.attr_files_scanned,
                    "entries_created": result.entries_created,
                    "cache_entries_after": result.cache_entries_after,
                    "duration_seconds": result.duration_seconds
                }
            )

            return result

        finally:
            await lock_mgr.release_lock(LockType.MANUAL_REBUILD)

    async def cleanup_expired_entries(self) -> RebuildResult:
        """
        Удалить expired cache entries.

        Опциональная операция для очистки старых записей.

        Returns:
            RebuildResult: Результат cleanup
        """
        lock_mgr = await self._get_lock_manager()

        acquired = await lock_mgr.acquire_lock(
            LockType.BACKGROUND_CLEANUP,
            timeout=300,
            blocking=False
        )

        if not acquired:
            logger.info("Skipping cleanup: higher priority operation in progress")
            raise RuntimeError("Cannot acquire lock for cleanup")

        started_at = datetime.now(timezone.utc)

        try:
            logger.info("Starting expired cache cleanup")

            result = RebuildResult(
                operation_type="cleanup_expired",
                started_at=started_at,
                completed_at=started_at,
                duration_seconds=0
            )

            # Find expired entries
            expired_result = await self.db.execute(
                select(FileMetadata).where(
                    func.now() > (
                        FileMetadata.cache_updated_at +
                        func.make_interval(0, 0, 0, 0, FileMetadata.cache_ttl_hours)
                    )
                )
            )
            expired_entries = expired_result.scalars().all()

            logger.info(f"Found {len(expired_entries)} expired entries")

            # Delete expired entries
            for entry in expired_entries:
                await self.db.delete(entry)
                result.entries_deleted += 1

            await self.db.commit()

            completed_at = datetime.now(timezone.utc)
            result.completed_at = completed_at
            result.duration_seconds = (completed_at - started_at).total_seconds()

            logger.info(
                "Expired cache cleanup completed",
                extra={
                    "entries_deleted": result.entries_deleted,
                    "duration_seconds": result.duration_seconds
                }
            )

            return result

        finally:
            await lock_mgr.release_lock(LockType.BACKGROUND_CLEANUP)

    def _create_metadata_from_attr(self, attributes: dict) -> FileMetadata:
        """
        Создать FileMetadata из attr.json attributes.

        Args:
            attributes: Dict из attr.json файла

        Returns:
            FileMetadata: Объект метаданных
        """
        from datetime import datetime, timedelta

        # Parse timestamps
        created_at = datetime.fromisoformat(attributes['created_at'].replace('Z', '+00:00'))
        updated_at = datetime.fromisoformat(attributes['updated_at'].replace('Z', '+00:00'))

        # Определить TTL в зависимости от режима
        # edit/rw: 24 часа, ro/ar: 168 часов (7 дней)
        mode = settings.app.mode.value
        cache_ttl_hours = 168 if mode in ['ro', 'ar'] else 24

        metadata = FileMetadata(
            file_id=UUID(attributes['file_id']),
            original_filename=attributes['original_filename'],
            storage_filename=attributes['storage_filename'],
            file_size=attributes['file_size'],
            content_type=attributes.get('mime_type', 'application/octet-stream'),
            created_at=created_at,
            updated_at=updated_at,
            created_by_id=attributes.get('uploaded_by', 'unknown'),
            created_by_username=attributes.get('uploaded_by', 'unknown'),
            created_by_fullname=attributes.get('uploader_full_name'),
            description=attributes.get('description'),
            version=str(attributes.get('version', 1)),
            storage_path=attributes['storage_path'],
            checksum=attributes.get('sha256', ''),
            metadata_json=attributes,
            cache_updated_at=datetime.now(timezone.utc),
            cache_ttl_hours=cache_ttl_hours
        )

        return metadata
