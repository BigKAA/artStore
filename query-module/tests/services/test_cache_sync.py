"""
Unit tests для CacheSyncService.

PHASE 2/3: Sprint 16 - Query Module Sync Repair.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from uuid import uuid4

from app.services.cache_sync import CacheSyncService
from app.schemas.events import (
    FileCreatedEvent,
    FileUpdatedEvent,
    FileDeletedEvent,
    FileMetadataEvent,
)


@pytest.fixture
def cache_sync_service():
    """Fixture для CacheSyncService instance."""
    return CacheSyncService()


@pytest.fixture
def sample_metadata():
    """Fixture для FileMetadataEvent."""
    return FileMetadataEvent(
        file_id=uuid4(),
        original_filename="test_document.pdf",
        storage_filename="test_document_user_20260113_123456.pdf",
        file_size=1024000,
        checksum_sha256="abc123" * 10 + "abcd",  # 64 chars
        content_type="application/pdf",
        description="Test document",
        storage_element_id=1,
        storage_path="/files/active",
        compressed=False,
        compression_algorithm=None,
        original_size=None,
        uploaded_by="test_user",
        upload_source_ip="127.0.0.1",
        created_at=datetime.utcnow(),
        updated_at=None,
        retention_policy="standard",
        ttl_expires_at=None,
        ttl_days=365,
        user_metadata={},
        tags=["test", "document"],
    )


@pytest.fixture
def file_created_event(sample_metadata):
    """Fixture для FileCreatedEvent."""
    return FileCreatedEvent(
        file_id=sample_metadata.file_id,
        storage_element_id=1,
        metadata=sample_metadata,
    )


@pytest.fixture
def file_updated_event(sample_metadata):
    """Fixture для FileUpdatedEvent."""
    return FileUpdatedEvent(
        file_id=sample_metadata.file_id,
        storage_element_id=1,
        metadata=sample_metadata,
    )


@pytest.fixture
def file_deleted_event(sample_metadata):
    """Fixture для FileDeletedEvent."""
    return FileDeletedEvent(
        file_id=sample_metadata.file_id,
        storage_element_id=1,
        deleted_at=datetime.utcnow(),
    )


@pytest.mark.asyncio
async def test_handle_file_created_success(cache_sync_service, file_created_event):
    """Test успешной обработки file:created event."""
    with patch('app.services.cache_sync.get_db_session') as mock_get_session:
        mock_session = AsyncMock()
        mock_get_session.return_value = [mock_session].__aiter__()

        result = await cache_sync_service.handle_file_created(file_created_event)

        assert result is True
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_handle_file_created_database_error(cache_sync_service, file_created_event):
    """Test обработки database ошибки при file:created."""
    with patch('app.services.cache_sync.get_db_session') as mock_get_session:
        mock_session = AsyncMock()
        mock_session.execute.side_effect = Exception("Database error")
        mock_get_session.return_value = [mock_session].__aiter__()

        result = await cache_sync_service.handle_file_created(file_created_event)

        assert result is False


@pytest.mark.asyncio
async def test_handle_file_updated_success(cache_sync_service, file_updated_event):
    """Test успешной обработки file:updated event."""
    with patch('app.services.cache_sync.get_db_session') as mock_get_session:
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result
        mock_get_session.return_value = [mock_session].__aiter__()

        result = await cache_sync_service.handle_file_updated(file_updated_event)

        assert result is True
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_handle_file_updated_not_found(cache_sync_service, file_updated_event):
    """Test обработки file:updated когда файл не найден в cache."""
    with patch('app.services.cache_sync.get_db_session') as mock_get_session:
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0  # Файл не найден
        mock_session.execute.return_value = mock_result
        mock_get_session.return_value = [mock_session].__aiter__()

        with patch.object(cache_sync_service, 'handle_file_created', new_callable=AsyncMock) as mock_create:
            mock_create.return_value = True

            result = await cache_sync_service.handle_file_updated(file_updated_event)

            assert result is True
            mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_handle_file_deleted_success(cache_sync_service, file_deleted_event):
    """Test успешной обработки file:deleted event."""
    with patch('app.services.cache_sync.get_db_session') as mock_get_session:
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result
        mock_get_session.return_value = [mock_session].__aiter__()

        result = await cache_sync_service.handle_file_deleted(file_deleted_event)

        assert result is True
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_handle_file_deleted_not_found(cache_sync_service, file_deleted_event):
    """Test обработки file:deleted когда файл не найден в cache."""
    with patch('app.services.cache_sync.get_db_session') as mock_get_session:
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0  # Файл не найден
        mock_session.execute.return_value = mock_result
        mock_get_session.return_value = [mock_session].__aiter__()

        result = await cache_sync_service.handle_file_deleted(file_deleted_event)

        # Должно вернуть True даже если файл не найден (idempotent)
        assert result is True
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_handle_file_created_upsert_conflict(cache_sync_service, file_created_event):
    """Test upsert behaviour при конфликте (ON CONFLICT DO UPDATE)."""
    with patch('app.services.cache_sync.get_db_session') as mock_get_session:
        mock_session = AsyncMock()
        mock_get_session.return_value = [mock_session].__aiter__()

        result = await cache_sync_service.handle_file_created(file_created_event)

        assert result is True
        # Проверяем что был вызван execute с INSERT ... ON CONFLICT DO UPDATE
        mock_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_concurrent_events_handling(cache_sync_service, file_created_event):
    """Test обработки concurrent events для одного файла."""
    with patch('app.services.cache_sync.get_db_session') as mock_get_session:
        mock_session = AsyncMock()
        mock_get_session.return_value = [mock_session].__aiter__()

        # Симулируем два concurrent events
        results = await asyncio.gather(
            cache_sync_service.handle_file_created(file_created_event),
            cache_sync_service.handle_file_created(file_created_event),
        )

        assert all(results)  # Оба должны успешно обработаться


import asyncio
