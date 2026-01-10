"""
Integration tests для CacheRebuildService.

Тестирует полный workflow cache synchronization:
- Полная пересборка кеша из attr.json файлов
- Инкрементальная пересборка
- Проверка консистентности
- Lazy rebuild при expired entries
- Priority-based locking

Требует:
- Реальную БД (SQLite in-memory)
- Mock storage backend (LocalBackend)
- Mock Redis для locks
"""

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import AsyncGenerator
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file_metadata import FileMetadata
from app.services.cache_rebuild_service import (
    CacheRebuildService,
    ConsistencyReport,
    RebuildResult
)
from app.services.cache_lock_manager import CacheLockManager, LockType
from app.services.storage_backends.local_backend import LocalBackend


# ==========================================
# Fixtures
# ==========================================

@pytest.fixture
def temp_storage_with_attr_files() -> Path:
    """
    Создать временное хранилище с attr.json файлами.

    Returns:
        Path: Путь к временному хранилищу с тестовыми файлами
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="cache_rebuild_test_"))

    # Создать структуру директорий: 2025/01/10/12/
    storage_path = temp_dir / "2025" / "01" / "10" / "12"
    storage_path.mkdir(parents=True)

    # Создать 5 тестовых attr.json файлов
    for i in range(5):
        file_id = str(uuid4())
        filename = f"test_document_{i}.pdf"
        storage_filename = f"{filename}_{file_id}.pdf"

        attr_data = {
            "file_id": file_id,
            "original_filename": filename,
            "storage_filename": storage_filename,
            "file_size": 1024 * (i + 1),
            "mime_type": "application/pdf",
            "storage_path": f"2025/01/10/12/{storage_filename}",
            "sha256": f"checksum-{i}",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "uploaded_by": "testuser",
            "version": 1
        }

        attr_file_path = storage_path / f"{storage_filename}.attr.json"
        attr_file_path.write_text(json.dumps(attr_data, indent=2))

        # Создать data файл (пустой, для проверки существования)
        data_file_path = storage_path / storage_filename
        data_file_path.write_bytes(b"test content" * 100)

    yield temp_dir

    # Cleanup
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def mock_local_backend(temp_storage_with_attr_files: Path) -> LocalBackend:
    """
    Создать LocalBackend с тестовыми данными.

    Args:
        temp_storage_with_attr_files: Временное хранилище с файлами

    Returns:
        LocalBackend: Настроенный backend для тестов
    """
    backend = LocalBackend()
    backend.base_path = temp_storage_with_attr_files
    return backend


@pytest_asyncio.fixture
async def mock_lock_manager(mock_redis) -> CacheLockManager:
    """
    Создать CacheLockManager с mock Redis.

    Args:
        mock_redis: Mock Redis client

    Returns:
        CacheLockManager: Lock manager для тестов
    """
    from unittest.mock import AsyncMock

    # Mock Redis для lock manager
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.delete = AsyncMock(return_value=1)
    mock_redis.exists = AsyncMock(return_value=False)

    lock_manager = CacheLockManager(redis_client=mock_redis)
    return lock_manager


# ==========================================
# Test: Full Cache Rebuild
# ==========================================

@pytest.mark.asyncio
@pytest.mark.integration
async def test_rebuild_cache_full_from_storage(
    async_session: AsyncSession,
    mock_local_backend: LocalBackend,
    mock_lock_manager: CacheLockManager
):
    """
    Тест полной пересборки кеша из attr.json файлов.

    Workflow:
    1. Пустая БД cache
    2. 5 attr.json файлов в storage
    3. Full rebuild
    4. Cache содержит 5 entries

    Проверяет:
    - Все attr.json файлы обработаны
    - Cache entries созданы корректно
    - Метаданные совпадают с attr.json
    """
    # Arrange: Patch storage backend
    from unittest.mock import patch

    with patch("app.services.cache_rebuild_service.get_storage_backend", return_value=mock_local_backend):
        service = CacheRebuildService(db=async_session, lock_manager=mock_lock_manager)

        # Verify: Cache пуст
        count_result = await async_session.execute(select(func.count(FileMetadata.file_id)))
        assert count_result.scalar() == 0

        # Act: Full rebuild
        result = await service.rebuild_cache_full()

        # Assert: Result statistics
        assert result.operation_type == "full"
        assert result.attr_files_scanned == 5
        assert result.entries_created == 5
        assert result.cache_entries_after == 5
        assert len(result.errors) == 0

        # Verify: Cache содержит 5 entries
        count_result = await async_session.execute(select(func.count(FileMetadata.file_id)))
        assert count_result.scalar() == 5

        # Verify: Метаданные корректны
        metadata_result = await async_session.execute(select(FileMetadata))
        all_metadata = metadata_result.scalars().all()

        assert len(all_metadata) == 5

        # Check one metadata entry
        first_metadata = all_metadata[0]
        assert first_metadata.original_filename.startswith("test_document_")
        assert first_metadata.content_type == "application/pdf"
        assert first_metadata.file_size > 0
        assert first_metadata.cache_updated_at is not None
        assert first_metadata.cache_ttl_hours in [24, 168]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_rebuild_cache_full_truncates_existing(
    async_session: AsyncSession,
    mock_local_backend: LocalBackend,
    mock_lock_manager: CacheLockManager
):
    """
    Тест что full rebuild удаляет существующий cache.

    Workflow:
    1. Cache содержит 3 старых entries
    2. Storage содержит 5 attr.json файлов
    3. Full rebuild
    4. Cache содержит 5 новых entries (старые удалены)

    Проверяет:
    - TRUNCATE удаляет старые entries
    - Новые entries созданы из attr.json
    """
    # Arrange: Добавить 3 старых entries в cache
    for i in range(3):
        old_metadata = FileMetadata(
            file_id=uuid4(),
            original_filename=f"old_file_{i}.txt",
            storage_filename=f"old_file_{i}.txt",
            file_size=512,
            content_type="text/plain",
            storage_path=f"old/path/{i}",
            checksum="old-checksum",
            created_by_id="old-user",
            created_by_username="olduser",
            metadata={}
        )
        async_session.add(old_metadata)

    await async_session.commit()

    # Verify: Cache содержит 3 entries
    count_result = await async_session.execute(select(func.count(FileMetadata.file_id)))
    assert count_result.scalar() == 3

    # Act: Full rebuild
    from unittest.mock import patch

    with patch("app.services.cache_rebuild_service.get_storage_backend", return_value=mock_local_backend):
        service = CacheRebuildService(db=async_session, lock_manager=mock_lock_manager)
        result = await service.rebuild_cache_full()

    # Assert: Старые entries удалены, новые созданы
    assert result.cache_entries_before == 3
    assert result.cache_entries_after == 5
    assert result.entries_created == 5

    # Verify: Cache содержит только новые entries
    metadata_result = await async_session.execute(select(FileMetadata))
    all_metadata = metadata_result.scalars().all()

    assert len(all_metadata) == 5

    # Verify: Нет старых entries
    for metadata in all_metadata:
        assert not metadata.original_filename.startswith("old_file_")


# ==========================================
# Test: Incremental Cache Rebuild
# ==========================================

@pytest.mark.asyncio
@pytest.mark.integration
async def test_rebuild_cache_incremental_adds_new_entries(
    async_session: AsyncSession,
    mock_local_backend: LocalBackend,
    mock_lock_manager: CacheLockManager
):
    """
    Тест инкрементальной пересборки добавляет только новые entries.

    Workflow:
    1. Cache содержит 2 existing entries
    2. Storage содержит 5 attr.json файлов
    3. Incremental rebuild
    4. Cache содержит 5 entries (2 existing + 3 new)

    Проверяет:
    - Existing entries НЕ изменяются
    - Только новые entries добавляются
    """
    # Arrange: Получить file_id из первых 2 attr.json файлов
    from unittest.mock import patch

    with patch("app.services.cache_rebuild_service.get_storage_backend", return_value=mock_local_backend):
        # Read first 2 attr files to get their file_ids
        attr_files = []
        async for attr_info in mock_local_backend.list_attr_files(limit=2):
            attr_data = await mock_local_backend.read_attr_file(attr_info.relative_path)
            attr_files.append(attr_data)

        # Create cache entries for first 2 files
        for attr_data in attr_files:
            metadata = FileMetadata(
                file_id=uuid4(attr_data["file_id"]),
                original_filename=attr_data["original_filename"],
                storage_filename=attr_data["storage_filename"],
                file_size=attr_data["file_size"],
                content_type=attr_data["mime_type"],
                storage_path=attr_data["storage_path"],
                checksum=attr_data["sha256"],
                created_by_id=attr_data["uploaded_by"],
                created_by_username=attr_data["uploaded_by"],
                metadata=attr_data
            )
            async_session.add(metadata)

        await async_session.commit()

        # Verify: Cache contains 2 entries
        count_result = await async_session.execute(select(func.count(FileMetadata.file_id)))
        assert count_result.scalar() == 2

        # Act: Incremental rebuild
        service = CacheRebuildService(db=async_session, lock_manager=mock_lock_manager)
        result = await service.rebuild_cache_incremental()

        # Assert: Only 3 new entries added
        assert result.operation_type == "incremental"
        assert result.attr_files_scanned == 5
        assert result.entries_created == 3  # 5 total - 2 existing
        assert result.cache_entries_before == 2
        assert result.cache_entries_after == 5


# ==========================================
# Test: Consistency Check
# ==========================================

@pytest.mark.asyncio
@pytest.mark.integration
async def test_check_consistency_detects_orphans(
    async_session: AsyncSession,
    mock_local_backend: LocalBackend,
    mock_lock_manager: CacheLockManager
):
    """
    Тест проверки консистентности обнаруживает orphans.

    Workflow:
    1. Cache содержит 7 entries (2 orphans)
    2. Storage содержит 5 attr.json файлов
    3. Consistency check
    4. Обнаружены 2 orphan cache entries

    Проверяет:
    - Orphan cache entries detected
    - Корректный расчёт inconsistency percentage
    """
    from unittest.mock import patch

    with patch("app.services.cache_rebuild_service.get_storage_backend", return_value=mock_local_backend):
        # Arrange: Add 5 valid + 2 orphan entries
        # First, get valid file_ids from storage
        valid_file_ids = []
        async for attr_info in mock_local_backend.list_attr_files():
            attr_data = await mock_local_backend.read_attr_file(attr_info.relative_path)
            valid_file_ids.append(attr_data["file_id"])

            # Create valid cache entry
            metadata = FileMetadata(
                file_id=uuid4(attr_data["file_id"]),
                original_filename=attr_data["original_filename"],
                storage_filename=attr_data["storage_filename"],
                file_size=attr_data["file_size"],
                content_type=attr_data["mime_type"],
                storage_path=attr_data["storage_path"],
                checksum=attr_data["sha256"],
                created_by_id=attr_data["uploaded_by"],
                created_by_username=attr_data["uploaded_by"],
                metadata=attr_data
            )
            async_session.add(metadata)

        # Add 2 orphan cache entries (no corresponding attr.json)
        for i in range(2):
            orphan_metadata = FileMetadata(
                file_id=uuid4(),  # Random UUID, no attr.json
                original_filename=f"orphan_file_{i}.pdf",
                storage_filename=f"orphan_{i}.pdf",
                file_size=1024,
                content_type="application/pdf",
                storage_path=f"orphan/path/{i}",
                checksum=f"orphan-checksum-{i}",
                created_by_id="orphan-user",
                created_by_username="orphanuser",
                metadata={}
            )
            async_session.add(orphan_metadata)

        await async_session.commit()

        # Verify: Cache has 7 entries
        count_result = await async_session.execute(select(func.count(FileMetadata.file_id)))
        assert count_result.scalar() == 7

        # Act: Check consistency
        service = CacheRebuildService(db=async_session, lock_manager=mock_lock_manager)
        report = await service.check_consistency()

        # Assert: Orphans detected
        assert report.total_attr_files == 5
        assert report.total_cache_entries == 7
        assert len(report.orphan_cache_entries) == 2
        assert len(report.orphan_attr_files) == 0
        assert report.is_consistent is False
        assert report.inconsistency_percentage > 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_check_consistency_detects_expired_entries(
    async_session: AsyncSession,
    mock_local_backend: LocalBackend,
    mock_lock_manager: CacheLockManager
):
    """
    Тест обнаружения expired cache entries.

    Workflow:
    1. Cache содержит 3 entries (1 expired)
    2. Consistency check
    3. Expired entry detected

    Проверяет:
    - Expired entries обнаружены через cache_expired property
    """
    # Arrange: Create 2 fresh + 1 expired entry
    for i in range(2):
        fresh_metadata = FileMetadata(
            file_id=uuid4(),
            original_filename=f"fresh_file_{i}.pdf",
            storage_filename=f"fresh_{i}.pdf",
            file_size=1024,
            content_type="application/pdf",
            storage_path=f"fresh/path/{i}",
            checksum=f"fresh-checksum-{i}",
            created_by_id="fresh-user",
            created_by_username="freshuser",
            cache_updated_at=datetime.now(timezone.utc),  # Fresh
            cache_ttl_hours=24,
            metadata={}
        )
        async_session.add(fresh_metadata)

    # Expired entry
    expired_metadata = FileMetadata(
        file_id=uuid4(),
        original_filename="expired_file.pdf",
        storage_filename="expired.pdf",
        file_size=2048,
        content_type="application/pdf",
        storage_path="expired/path",
        checksum="expired-checksum",
        created_by_id="expired-user",
        created_by_username="expireduser",
        cache_updated_at=datetime.now(timezone.utc) - timedelta(days=2),  # 2 days ago
        cache_ttl_hours=24,  # TTL 24 hours
        metadata={}
    )
    async_session.add(expired_metadata)

    await async_session.commit()

    # Act: Check consistency
    from unittest.mock import patch

    with patch("app.services.cache_rebuild_service.get_storage_backend", return_value=mock_local_backend):
        service = CacheRebuildService(db=async_session, lock_manager=mock_lock_manager)
        report = await service.check_consistency()

    # Assert: 1 expired entry detected
    assert len(report.expired_cache_entries) == 1
    assert str(expired_metadata.file_id) in report.expired_cache_entries


# ==========================================
# Test: Cleanup Expired Entries
# ==========================================

@pytest.mark.asyncio
@pytest.mark.integration
async def test_cleanup_expired_entries_deletes_expired(
    async_session: AsyncSession,
    mock_lock_manager: CacheLockManager
):
    """
    Тест удаления expired cache entries.

    Workflow:
    1. Cache содержит 5 entries (3 expired)
    2. Cleanup expired
    3. Cache содержит 2 entries (expired удалены)

    Проверяет:
    - Только expired entries удалены
    - Fresh entries НЕ затронуты
    """
    # Arrange: Create 2 fresh + 3 expired entries
    fresh_ids = []
    expired_ids = []

    for i in range(2):
        fresh_metadata = FileMetadata(
            file_id=uuid4(),
            original_filename=f"fresh_file_{i}.pdf",
            storage_filename=f"fresh_{i}.pdf",
            file_size=1024,
            content_type="application/pdf",
            storage_path=f"fresh/path/{i}",
            checksum=f"fresh-checksum-{i}",
            created_by_id="fresh-user",
            created_by_username="freshuser",
            cache_updated_at=datetime.now(timezone.utc),
            cache_ttl_hours=24,
            metadata={}
        )
        async_session.add(fresh_metadata)
        fresh_ids.append(fresh_metadata.file_id)

    for i in range(3):
        expired_metadata = FileMetadata(
            file_id=uuid4(),
            original_filename=f"expired_file_{i}.pdf",
            storage_filename=f"expired_{i}.pdf",
            file_size=2048,
            content_type="application/pdf",
            storage_path=f"expired/path/{i}",
            checksum=f"expired-checksum-{i}",
            created_by_id="expired-user",
            created_by_username="expireduser",
            cache_updated_at=datetime.now(timezone.utc) - timedelta(days=2),
            cache_ttl_hours=24,
            metadata={}
        )
        async_session.add(expired_metadata)
        expired_ids.append(expired_metadata.file_id)

    await async_session.commit()

    # Verify: Cache has 5 entries
    count_result = await async_session.execute(select(func.count(FileMetadata.file_id)))
    assert count_result.scalar() == 5

    # Act: Cleanup expired
    service = CacheRebuildService(db=async_session, lock_manager=mock_lock_manager)
    result = await service.cleanup_expired_entries()

    # Assert: 3 expired entries deleted
    assert result.operation_type == "cleanup_expired"
    assert result.entries_deleted == 3

    # Verify: Cache has 2 fresh entries remaining
    count_result = await async_session.execute(select(func.count(FileMetadata.file_id)))
    assert count_result.scalar() == 2

    # Verify: Only fresh entries remain
    metadata_result = await async_session.execute(select(FileMetadata.file_id))
    remaining_ids = [row[0] for row in metadata_result.all()]

    for fresh_id in fresh_ids:
        assert fresh_id in remaining_ids

    for expired_id in expired_ids:
        assert expired_id not in remaining_ids


# ==========================================
# Test: Priority-Based Locking
# ==========================================

@pytest.mark.asyncio
@pytest.mark.integration
async def test_manual_rebuild_blocks_lazy_rebuild(
    async_session: AsyncSession,
    mock_local_backend: LocalBackend
):
    """
    Тест что MANUAL_REBUILD lock блокирует LAZY_REBUILD.

    Workflow:
    1. MANUAL_REBUILD lock захвачен
    2. LAZY_REBUILD пытается захватить lock
    3. LAZY_REBUILD НЕ может захватить lock (higher priority operation)

    Проверяет:
    - Priority-based locking работает корректно
    - MANUAL_REBUILD имеет приоритет над LAZY_REBUILD
    """
    from unittest.mock import patch, AsyncMock
    from redis.exceptions import LockError

    # Mock Redis для lock manager
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.delete = AsyncMock(return_value=1)
    mock_redis.exists = AsyncMock(side_effect=lambda key: "manual_rebuild" in key)

    lock_manager = CacheLockManager(redis_client=mock_redis)

    # Act: Try to acquire LAZY_REBUILD lock while MANUAL_REBUILD is held
    with pytest.raises(LockError) as exc_info:
        await lock_manager.acquire_lock(LockType.LAZY_REBUILD, timeout=5, blocking=False)

    # Assert: Lock acquisition failed due to priority conflict
    assert "higher priority operation" in str(exc_info.value).lower()
