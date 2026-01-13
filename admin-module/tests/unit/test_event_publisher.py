"""
Unit tests для EventPublisher service.

PHASE 1: Sprint 16 - Query Module Sync Repair.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime

from app.services.event_publisher import EventPublisher
from app.schemas.events import FileMetadataEvent


@pytest.fixture
def event_publisher_instance():
    """Fixture для EventPublisher instance."""
    return EventPublisher()


@pytest.fixture
def sample_file_metadata():
    """Fixture для sample FileMetadataEvent."""
    return FileMetadataEvent(
        file_id=uuid4(),
        original_filename="test.pdf",
        storage_filename="test_user_20260113_uuid.pdf",
        file_size=1024,
        checksum_sha256="abc123",
        content_type="application/pdf",
        description="Test file",
        storage_element_id=1,
        storage_path="files/active",
        compressed=False,
        compression_algorithm=None,
        original_size=None,
        uploaded_by="test_user",
        upload_source_ip="127.0.0.1",
        created_at=datetime.utcnow(),
        updated_at=None,
        retention_policy="standard",
        ttl_expires_at=None,
        ttl_days=None,
        user_metadata={},
        tags=None,
    )


class TestEventPublisherInitialize:
    """Тесты для initialize метода."""

    @pytest.mark.asyncio
    async def test_initialize_success(self, event_publisher_instance):
        """Тест успешной инициализации."""
        with patch("app.services.event_publisher.get_redis") as mock_get_redis, \
             patch("app.services.event_publisher.settings") as mock_settings:

            mock_settings.event_publishing.enabled = True
            mock_redis = AsyncMock()
            mock_get_redis.return_value = mock_redis

            await event_publisher_instance.initialize()

            assert event_publisher_instance._initialized is True
            assert event_publisher_instance.redis is mock_redis

    @pytest.mark.asyncio
    async def test_initialize_disabled(self, event_publisher_instance):
        """Тест инициализации когда event publishing отключен."""
        with patch("app.services.event_publisher.settings") as mock_settings:
            mock_settings.event_publishing.enabled = False

            await event_publisher_instance.initialize()

            assert event_publisher_instance._initialized is False
            assert event_publisher_instance.redis is None


class TestEventPublisherPublishFileCreated:
    """Тесты для publish_file_created метода."""

    @pytest.mark.asyncio
    async def test_publish_file_created_success(
        self,
        event_publisher_instance,
        sample_file_metadata
    ):
        """Тест успешной публикации file:created event."""
        with patch("app.services.event_publisher.settings") as mock_settings:
            mock_settings.event_publishing.enabled = True
            mock_settings.event_publishing.channel_file_created = "file:created"

            # Mock Redis client
            mock_redis = AsyncMock()
            mock_redis.publish.return_value = 2  # 2 subscribers

            event_publisher_instance.redis = mock_redis
            event_publisher_instance._initialized = True

            # Act
            result = await event_publisher_instance.publish_file_created(
                file_id=sample_file_metadata.file_id,
                storage_element_id=sample_file_metadata.storage_element_id,
                metadata=sample_file_metadata
            )

            # Assert
            assert result is True
            mock_redis.publish.assert_called_once()
            call_args = mock_redis.publish.call_args
            assert call_args[0][0] == "file:created"  # channel

    @pytest.mark.asyncio
    async def test_publish_file_created_not_initialized(
        self,
        event_publisher_instance,
        sample_file_metadata
    ):
        """Тест публикации когда EventPublisher не инициализирован."""
        result = await event_publisher_instance.publish_file_created(
            file_id=sample_file_metadata.file_id,
            storage_element_id=sample_file_metadata.storage_element_id,
            metadata=sample_file_metadata
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_publish_file_created_redis_error(
        self,
        event_publisher_instance,
        sample_file_metadata
    ):
        """Тест обработки ошибки Redis при публикации."""
        with patch("app.services.event_publisher.settings") as mock_settings:
            mock_settings.event_publishing.enabled = True

            # Mock Redis client с ошибкой
            mock_redis = AsyncMock()
            mock_redis.publish.side_effect = Exception("Redis connection error")

            event_publisher_instance.redis = mock_redis
            event_publisher_instance._initialized = True

            # Act
            result = await event_publisher_instance.publish_file_created(
                file_id=sample_file_metadata.file_id,
                storage_element_id=sample_file_metadata.storage_element_id,
                metadata=sample_file_metadata
            )

            # Assert - graceful degradation
            assert result is False


class TestEventPublisherPublishFileUpdated:
    """Тесты для publish_file_updated метода."""

    @pytest.mark.asyncio
    async def test_publish_file_updated_success(
        self,
        event_publisher_instance,
        sample_file_metadata
    ):
        """Тест успешной публикации file:updated event."""
        with patch("app.services.event_publisher.settings") as mock_settings:
            mock_settings.event_publishing.enabled = True
            mock_settings.event_publishing.channel_file_updated = "file:updated"

            # Mock Redis client
            mock_redis = AsyncMock()
            mock_redis.publish.return_value = 1

            event_publisher_instance.redis = mock_redis
            event_publisher_instance._initialized = True

            # Act
            result = await event_publisher_instance.publish_file_updated(
                file_id=sample_file_metadata.file_id,
                storage_element_id=sample_file_metadata.storage_element_id,
                metadata=sample_file_metadata
            )

            # Assert
            assert result is True
            mock_redis.publish.assert_called_once()
            call_args = mock_redis.publish.call_args
            assert call_args[0][0] == "file:updated"


class TestEventPublisherPublishFileDeleted:
    """Тесты для publish_file_deleted метода."""

    @pytest.mark.asyncio
    async def test_publish_file_deleted_success(self, event_publisher_instance):
        """Тест успешной публикации file:deleted event."""
        with patch("app.services.event_publisher.settings") as mock_settings:
            mock_settings.event_publishing.enabled = True
            mock_settings.event_publishing.channel_file_deleted = "file:deleted"

            # Mock Redis client
            mock_redis = AsyncMock()
            mock_redis.publish.return_value = 1

            event_publisher_instance.redis = mock_redis
            event_publisher_instance._initialized = True

            # Act
            file_id = uuid4()
            storage_element_id = 1
            deleted_at = datetime.utcnow()

            result = await event_publisher_instance.publish_file_deleted(
                file_id=file_id,
                storage_element_id=storage_element_id,
                deleted_at=deleted_at
            )

            # Assert
            assert result is True
            mock_redis.publish.assert_called_once()
            call_args = mock_redis.publish.call_args
            assert call_args[0][0] == "file:deleted"


class TestEventPublisherClose:
    """Тесты для close метода."""

    @pytest.mark.asyncio
    async def test_close_success(self, event_publisher_instance):
        """Тест успешного закрытия EventPublisher."""
        event_publisher_instance._initialized = True

        await event_publisher_instance.close()

        assert event_publisher_instance._initialized is False
