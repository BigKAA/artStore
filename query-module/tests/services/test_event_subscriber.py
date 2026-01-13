"""
Unit tests для EventSubscriber service.

PHASE 2: Sprint 16 - Query Module Sync Repair.
"""

import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from uuid import uuid4

from app.services.event_subscriber import EventSubscriber
from app.schemas.events import FileCreatedEvent, FileMetadataEvent


@pytest.fixture
def event_subscriber():
    """Fixture для EventSubscriber instance."""
    subscriber = EventSubscriber()
    subscriber.enabled = True
    subscriber.channels = ["file:created", "file:updated", "file:deleted"]
    return subscriber


@pytest.fixture
def sample_file_created_event():
    """Fixture для file:created event."""
    file_id = uuid4()
    return {
        "event_type": "file:created",
        "timestamp": datetime.utcnow().isoformat(),
        "file_id": str(file_id),
        "storage_element_id": 1,
        "metadata": {
            "file_id": str(file_id),
            "original_filename": "test_document.pdf",
            "storage_filename": "test_document_user_20260113_123456.pdf",
            "file_size": 1024000,
            "checksum_sha256": "abc123" * 10 + "abcd",  # 64 chars
            "content_type": "application/pdf",
            "description": "Test document",
            "storage_element_id": 1,
            "storage_path": "/files/active",
            "compressed": False,
            "compression_algorithm": None,
            "original_size": None,
            "uploaded_by": "test_user",
            "upload_source_ip": "127.0.0.1",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": None,
            "retention_policy": "standard",
            "ttl_expires_at": None,
            "ttl_days": 365,
            "user_metadata": {},
            "tags": ["test", "document"],
        }
    }


@pytest.mark.asyncio
async def test_initialize_success(event_subscriber):
    """Test успешной инициализации EventSubscriber."""
    with patch('app.services.event_subscriber.get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        await event_subscriber.initialize()

        assert event_subscriber._initialized is True
        assert event_subscriber._task is not None
        mock_get_redis.assert_called_once()


@pytest.mark.asyncio
async def test_initialize_disabled(event_subscriber):
    """Test инициализации когда subscription disabled."""
    event_subscriber.enabled = False

    await event_subscriber.initialize()

    assert event_subscriber._initialized is False
    assert event_subscriber._task is None


@pytest.mark.asyncio
async def test_handle_file_created_success(event_subscriber, sample_file_created_event):
    """Test успешной обработки file:created event."""
    with patch('app.services.event_subscriber.cache_sync_service') as mock_cache_sync:
        mock_cache_sync.handle_file_created = AsyncMock(return_value=True)

        await event_subscriber._handle_file_created(sample_file_created_event)

        mock_cache_sync.handle_file_created.assert_called_once()
        call_args = mock_cache_sync.handle_file_created.call_args[0][0]
        assert isinstance(call_args, FileCreatedEvent)
        assert str(call_args.file_id) == sample_file_created_event["file_id"]


@pytest.mark.asyncio
async def test_handle_message_file_created(event_subscriber, sample_file_created_event):
    """Test обработки Redis message с file:created event."""
    message = {
        "type": "message",
        "channel": "file:created",
        "data": json.dumps(sample_file_created_event)
    }

    with patch.object(event_subscriber, '_handle_file_created', new_callable=AsyncMock) as mock_handle:
        await event_subscriber._handle_message(message)

        mock_handle.assert_called_once()
        call_args = mock_handle.call_args[0][0]
        assert call_args["event_type"] == "file:created"


@pytest.mark.asyncio
async def test_handle_message_invalid_json(event_subscriber):
    """Test обработки message с невалидным JSON."""
    message = {
        "type": "message",
        "channel": "file:created",
        "data": "invalid json {"
    }

    # Не должно вызвать exception, только залогировать ошибку
    await event_subscriber._handle_message(message)


@pytest.mark.asyncio
async def test_handle_message_unknown_event_type(event_subscriber):
    """Test обработки message с неизвестным event_type."""
    message = {
        "type": "message",
        "channel": "unknown:event",
        "data": json.dumps({
            "event_type": "unknown:event",
            "timestamp": datetime.utcnow().isoformat()
        })
    }

    # Не должно вызвать exception, только залогировать warning
    await event_subscriber._handle_message(message)


@pytest.mark.asyncio
async def test_close_stops_task(event_subscriber):
    """Test что close() останавливает background task."""
    with patch('app.services.event_subscriber.get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        await event_subscriber.initialize()

        # Даем время для запуска task
        await asyncio.sleep(0.1)

        await event_subscriber.close()

        assert event_subscriber._initialized is False
        assert event_subscriber._task.cancelled() or event_subscriber._task.done()


@pytest.mark.asyncio
async def test_reconnection_logic():
    """Test reconnection logic при ошибках подключения."""
    subscriber = EventSubscriber()
    subscriber.enabled = True
    subscriber.reconnect_delay = 0.1  # Быстрый reconnect для теста
    subscriber.max_reconnect_attempts = 3

    with patch('app.services.event_subscriber.get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_pubsub = AsyncMock()
        mock_redis.pubsub.return_value = mock_pubsub

        # Симулируем ошибку subscribe
        mock_pubsub.subscribe = AsyncMock(side_effect=Exception("Connection failed"))
        mock_get_redis.return_value = mock_redis

        await subscriber.initialize()

        # Даем время для нескольких попыток reconnect
        await asyncio.sleep(0.5)

        await subscriber.close()

        # Проверяем что были попытки reconnect
        assert mock_pubsub.subscribe.call_count >= 2
