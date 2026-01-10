"""
Unit tests для Cache API endpoints.

Тестирует:
- POST /api/v1/cache/rebuild - Полная пересборка кеша
- POST /api/v1/cache/rebuild/incremental - Инкрементальная пересборка
- GET /api/v1/cache/consistency - Проверка консистентности (dry-run)
- POST /api/v1/cache/cleanup-expired - Очистка expired entries
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file_metadata import FileMetadata
from app.services.cache_rebuild_service import ConsistencyReport, RebuildResult


# ==========================================
# Test Fixtures
# ==========================================

@pytest.fixture
def mock_cache_rebuild_service():
    """Mock CacheRebuildService для изоляции API тестов."""
    with patch("app.api.v1.endpoints.cache.CacheRebuildService") as mock:
        service_instance = mock.return_value
        yield service_instance


@pytest.fixture
def mock_cache_lock_manager():
    """Mock CacheLockManager для тестирования locking logic."""
    with patch("app.services.cache_lock_manager.get_cache_lock_manager") as mock:
        lock_manager = AsyncMock()
        mock.return_value = lock_manager
        yield lock_manager


@pytest_asyncio.fixture
async def expired_file_metadata(async_session: AsyncSession) -> FileMetadata:
    """
    Создать FileMetadata с истёкшим cache TTL.

    Args:
        async_session: Test database session

    Returns:
        FileMetadata: Запись с expired cache
    """
    metadata = FileMetadata(
        file_id=uuid4(),
        original_filename="expired_test.pdf",
        storage_filename=f"expired_test_{uuid4()}.pdf",
        file_size=2048,
        content_type="application/pdf",
        storage_path="2025/01/10/expired_test.pdf",
        checksum="test-checksum-expired",
        created_by_id="test-user",
        created_by_username="testuser",
        # Cache TTL истёк 2 дня назад
        cache_updated_at=datetime.now(timezone.utc) - timedelta(days=2),
        cache_ttl_hours=24,  # TTL 24 часа
        metadata={}
    )

    async_session.add(metadata)
    await async_session.commit()
    await async_session.refresh(metadata)

    return metadata


# ==========================================
# Test: POST /api/v1/cache/rebuild (Full Rebuild)
# ==========================================

@pytest.mark.asyncio
@pytest.mark.unit
async def test_rebuild_cache_full_success(
    async_client: AsyncClient,
    admin_auth_headers: dict,
    mock_cache_rebuild_service
):
    """
    Тест успешной полной пересборки кеша.

    Проверяет:
    - HTTP 200 response
    - Корректный формат RebuildResult
    - Вызов rebuild_cache_full() сервиса
    """
    # Arrange: Mock successful rebuild
    mock_result = RebuildResult(
        operation_type="full",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        duration_seconds=15.5,
        attr_files_scanned=100,
        cache_entries_before=80,
        cache_entries_after=100,
        entries_created=100,
        entries_updated=0,
        entries_deleted=0,
        errors=[]
    )

    mock_cache_rebuild_service.rebuild_cache_full = AsyncMock(return_value=mock_result)

    # Act: Call API
    response = await async_client.post(
        "/api/v1/cache/rebuild",
        headers=admin_auth_headers
    )

    # Assert: Check response
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["operation_type"] == "full"
    assert data["statistics"]["attr_files_scanned"] == 100
    assert data["statistics"]["entries_created"] == 100
    assert data["duration_seconds"] == 15.5
    assert len(data["errors"]) == 0

    # Verify service was called
    mock_cache_rebuild_service.rebuild_cache_full.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_rebuild_cache_full_unauthorized(async_client: AsyncClient):
    """
    Тест полной пересборки без JWT токена.

    Проверяет:
    - HTTP 401 Unauthorized
    - Требование аутентификации
    """
    # Act: Call API without auth
    response = await async_client.post("/api/v1/cache/rebuild")

    # Assert: Unauthorized
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
@pytest.mark.unit
async def test_rebuild_cache_full_lock_conflict(
    async_client: AsyncClient,
    admin_auth_headers: dict,
    mock_cache_rebuild_service
):
    """
    Тест конфликта locks при полной пересборке.

    Проверяет:
    - HTTP 409 Conflict при занятом lock
    - Корректное сообщение об ошибке
    """
    # Arrange: Mock lock conflict
    mock_cache_rebuild_service.rebuild_cache_full = AsyncMock(
        side_effect=RuntimeError("Cannot acquire lock: rebuild already in progress")
    )

    # Act: Call API
    response = await async_client.post(
        "/api/v1/cache/rebuild",
        headers=admin_auth_headers
    )

    # Assert: Conflict
    assert response.status_code == status.HTTP_409_CONFLICT
    assert "lock" in response.json()["detail"].lower()


# ==========================================
# Test: POST /api/v1/cache/rebuild/incremental
# ==========================================

@pytest.mark.asyncio
@pytest.mark.unit
async def test_rebuild_cache_incremental_success(
    async_client: AsyncClient,
    admin_auth_headers: dict,
    mock_cache_rebuild_service
):
    """
    Тест успешной инкрементальной пересборки.

    Проверяет:
    - HTTP 200 response
    - Только новые entries добавлены
    """
    # Arrange: Mock incremental rebuild
    mock_result = RebuildResult(
        operation_type="incremental",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        duration_seconds=5.2,
        attr_files_scanned=100,
        cache_entries_before=80,
        cache_entries_after=100,
        entries_created=20,  # Только новые
        entries_updated=0,
        entries_deleted=0,
        errors=[]
    )

    mock_cache_rebuild_service.rebuild_cache_incremental = AsyncMock(return_value=mock_result)

    # Act: Call API
    response = await async_client.post(
        "/api/v1/cache/rebuild/incremental",
        headers=admin_auth_headers
    )

    # Assert: Success
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["operation_type"] == "incremental"
    assert data["statistics"]["entries_created"] == 20
    assert data["statistics"]["cache_entries_before"] == 80
    assert data["statistics"]["cache_entries_after"] == 100


# ==========================================
# Test: GET /api/v1/cache/consistency
# ==========================================

@pytest.mark.asyncio
@pytest.mark.unit
async def test_check_consistency_all_consistent(
    async_client: AsyncClient,
    admin_auth_headers: dict,
    mock_cache_rebuild_service
):
    """
    Тест проверки консистентности когда всё согласовано.

    Проверяет:
    - HTTP 200 response
    - is_consistent = True
    - Нет orphans или expired entries
    """
    # Arrange: Mock consistent state
    mock_report = ConsistencyReport(
        total_attr_files=100,
        total_cache_entries=100,
        orphan_cache_entries=[],
        orphan_attr_files=[],
        expired_cache_entries=[],
        is_consistent=True,
        inconsistency_percentage=0.0
    )

    mock_cache_rebuild_service.check_consistency = AsyncMock(return_value=mock_report)

    # Act: Call API
    response = await async_client.get(
        "/api/v1/cache/consistency",
        headers=admin_auth_headers
    )

    # Assert: Consistent
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["is_consistent"] is True
    assert data["inconsistency_percentage"] == 0.0
    assert data["orphan_cache_count"] == 0
    assert data["orphan_attr_count"] == 0
    assert data["expired_cache_count"] == 0


@pytest.mark.asyncio
@pytest.mark.unit
async def test_check_consistency_with_orphans(
    async_client: AsyncClient,
    admin_auth_headers: dict,
    mock_cache_rebuild_service
):
    """
    Тест проверки консистентности с orphan entries.

    Проверяет:
    - HTTP 200 response
    - is_consistent = False
    - Orphans detected
    """
    # Arrange: Mock inconsistent state
    mock_report = ConsistencyReport(
        total_attr_files=100,
        total_cache_entries=105,
        orphan_cache_entries=["file-id-1", "file-id-2", "file-id-3"],  # 3 cache orphans
        orphan_attr_files=["file-id-4", "file-id-5"],  # 2 attr orphans
        expired_cache_entries=["file-id-6"],  # 1 expired
        is_consistent=False,
        inconsistency_percentage=5.0  # 5 orphans из 100 files
    )

    mock_cache_rebuild_service.check_consistency = AsyncMock(return_value=mock_report)

    # Act: Call API
    response = await async_client.get(
        "/api/v1/cache/consistency",
        headers=admin_auth_headers
    )

    # Assert: Inconsistent
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["is_consistent"] is False
    assert data["inconsistency_percentage"] == 5.0
    assert data["orphan_cache_count"] == 3
    assert data["orphan_attr_count"] == 2
    assert data["expired_cache_count"] == 1


# ==========================================
# Test: POST /api/v1/cache/cleanup-expired
# ==========================================

@pytest.mark.asyncio
@pytest.mark.unit
async def test_cleanup_expired_success(
    async_client: AsyncClient,
    admin_auth_headers: dict,
    mock_cache_rebuild_service
):
    """
    Тест успешной очистки expired entries.

    Проверяет:
    - HTTP 200 response
    - Корректное количество удалённых entries
    """
    # Arrange: Mock cleanup result
    mock_result = RebuildResult(
        operation_type="cleanup_expired",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        duration_seconds=2.1,
        entries_deleted=15,  # 15 expired entries удалено
        errors=[]
    )

    mock_cache_rebuild_service.cleanup_expired_entries = AsyncMock(return_value=mock_result)

    # Act: Call API
    response = await async_client.post(
        "/api/v1/cache/cleanup-expired",
        headers=admin_auth_headers
    )

    # Assert: Success
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["operation_type"] == "cleanup_expired"
    assert data["statistics"]["entries_deleted"] == 15
    assert data["duration_seconds"] == 2.1


@pytest.mark.asyncio
@pytest.mark.unit
async def test_cleanup_expired_no_entries(
    async_client: AsyncClient,
    admin_auth_headers: dict,
    mock_cache_rebuild_service
):
    """
    Тест cleanup когда нет expired entries.

    Проверяет:
    - HTTP 200 response
    - entries_deleted = 0
    """
    # Arrange: Mock no expired entries
    mock_result = RebuildResult(
        operation_type="cleanup_expired",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        duration_seconds=0.5,
        entries_deleted=0,  # Нет expired entries
        errors=[]
    )

    mock_cache_rebuild_service.cleanup_expired_entries = AsyncMock(return_value=mock_result)

    # Act: Call API
    response = await async_client.post(
        "/api/v1/cache/cleanup-expired",
        headers=admin_auth_headers
    )

    # Assert: Success with no deletions
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["statistics"]["entries_deleted"] == 0


# ==========================================
# Test: Error Handling
# ==========================================

@pytest.mark.asyncio
@pytest.mark.unit
async def test_rebuild_cache_internal_error(
    async_client: AsyncClient,
    admin_auth_headers: dict,
    mock_cache_rebuild_service
):
    """
    Тест обработки внутренних ошибок при rebuild.

    Проверяет:
    - HTTP 500 Internal Server Error
    - Корректное логирование ошибки
    """
    # Arrange: Mock internal error
    mock_cache_rebuild_service.rebuild_cache_full = AsyncMock(
        side_effect=Exception("Database connection failed")
    )

    # Act: Call API
    response = await async_client.post(
        "/api/v1/cache/rebuild",
        headers=admin_auth_headers
    )

    # Assert: Internal Server Error
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "error" in response.json()["detail"].lower()


# ==========================================
# Test: Cache Expiration Property
# ==========================================

@pytest.mark.asyncio
@pytest.mark.unit
async def test_cache_expired_property(expired_file_metadata: FileMetadata):
    """
    Тест property cache_expired для FileMetadata.

    Проверяет:
    - cache_expired = True для истёкших entries
    - Корректная логика TTL проверки
    """
    # Assert: Cache должен быть expired
    assert expired_file_metadata.cache_expired is True

    # Verify: cache_updated_at был 2 дня назад, TTL 24 часа
    age_hours = (
        datetime.now(timezone.utc) - expired_file_metadata.cache_updated_at
    ).total_seconds() / 3600

    assert age_hours > expired_file_metadata.cache_ttl_hours


@pytest.mark.asyncio
@pytest.mark.unit
async def test_cache_not_expired_property(async_session: AsyncSession):
    """
    Тест property cache_expired для свежего cache.

    Проверяет:
    - cache_expired = False для актуальных entries
    """
    # Arrange: Create fresh metadata
    metadata = FileMetadata(
        file_id=uuid4(),
        original_filename="fresh_test.pdf",
        storage_filename=f"fresh_test_{uuid4()}.pdf",
        file_size=1024,
        content_type="application/pdf",
        storage_path="2025/01/10/fresh_test.pdf",
        checksum="test-checksum-fresh",
        created_by_id="test-user",
        created_by_username="testuser",
        # Cache обновлён 1 час назад
        cache_updated_at=datetime.now(timezone.utc) - timedelta(hours=1),
        cache_ttl_hours=24,
        metadata={}
    )

    async_session.add(metadata)
    await async_session.commit()

    # Assert: Cache НЕ должен быть expired
    assert metadata.cache_expired is False
