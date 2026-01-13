"""
Event Publisher Service для Redis Pub/Sub синхронизации.

PHASE 1: Sprint 16 - Query Module Sync Repair.

EventPublisher отвечает за публикацию events о file operations в Redis.
Query Module подписывается на эти events и синхронизирует свой cache.

Архитектура:
- Admin Module (EventPublisher) → Redis Pub/Sub → Query Module (EventSubscriber)
- Events: file:created, file:updated, file:deleted
- Async Redis (redis.asyncio) для неблокирующей работы
- Graceful degradation при Redis unavailable
"""

import logging
import json
from typing import Optional
from uuid import UUID
from datetime import datetime

from redis.asyncio import Redis

from app.core.redis import get_redis
from app.core.config import settings
from app.schemas.events import (
    FileCreatedEvent,
    FileUpdatedEvent,
    FileDeletedEvent,
    FileMetadataEvent,
)

logger = logging.getLogger(__name__)


class EventPublisher:
    """
    Сервис для публикации file events в Redis Pub/Sub.

    PHASE 1: Публикация events после успешных file operations.
    Query Module подписывается на эти events и обновляет cache.

    Usage:
        publisher = EventPublisher()
        await publisher.publish_file_created(file_id, storage_element_id, metadata)
    """

    def __init__(self):
        """Инициализация EventPublisher."""
        self.redis: Optional[Redis] = None
        self._initialized = False

    async def initialize(self) -> None:
        """
        Асинхронная инициализация EventPublisher.

        Вызывается при startup приложения (lifespan).
        Получает Redis client для publishing.
        """
        if not settings.event_publishing.enabled:
            logger.info("Event publishing disabled")
            return

        try:
            self.redis = await get_redis()
            self._initialized = True
            logger.info(
                "EventPublisher initialized",
                extra={
                    "channels": [
                        settings.event_publishing.channel_file_created,
                        settings.event_publishing.channel_file_updated,
                        settings.event_publishing.channel_file_deleted,
                    ]
                }
            )
        except Exception as e:
            logger.error(f"Failed to initialize EventPublisher: {e}", exc_info=True)
            self._initialized = False

    async def publish_file_created(
        self,
        file_id: UUID,
        storage_element_id: int,
        metadata: FileMetadataEvent,
    ) -> bool:
        """
        Публикация file:created event.

        Вызывается после успешной регистрации файла (FileService.register_file).

        Args:
            file_id: UUID созданного файла
            storage_element_id: ID Storage Element где хранится файл
            metadata: Полные метаданные файла

        Returns:
            bool: True если event успешно опубликован, False иначе

        Example:
            metadata = FileMetadataEvent(
                file_id=file.file_id,
                original_filename=file.original_filename,
                ...
            )
            success = await publisher.publish_file_created(
                file.file_id,
                file.storage_element_id,
                metadata
            )
        """
        if not self._initialized or not self.redis:
            logger.warning(
                "EventPublisher not initialized, skipping file:created event",
                extra={"file_id": str(file_id)}
            )
            return False

        if not settings.event_publishing.enabled:
            return False

        try:
            # Создаем event
            event = FileCreatedEvent(
                file_id=file_id,
                storage_element_id=storage_element_id,
                metadata=metadata,
            )

            # Сериализуем в JSON
            event_json = event.model_dump_json()

            # Публикуем в Redis channel
            channel = settings.event_publishing.channel_file_created
            subscribers = await self.redis.publish(channel, event_json)

            logger.info(
                "Published file:created event",
                extra={
                    "file_id": str(file_id),
                    "storage_element_id": storage_element_id,
                    "channel": channel,
                    "subscribers": subscribers,
                }
            )

            return True

        except Exception as e:
            logger.error(
                "Failed to publish file:created event",
                extra={
                    "file_id": str(file_id),
                    "storage_element_id": storage_element_id,
                    "error": str(e),
                },
                exc_info=True
            )
            return False

    async def publish_file_updated(
        self,
        file_id: UUID,
        storage_element_id: int,
        metadata: FileMetadataEvent,
    ) -> bool:
        """
        Публикация file:updated event.

        Вызывается после успешного обновления файла (FileService.update_file).

        Args:
            file_id: UUID обновленного файла
            storage_element_id: ID Storage Element где хранится файл
            metadata: Обновленные метаданные файла

        Returns:
            bool: True если event успешно опубликован, False иначе
        """
        if not self._initialized or not self.redis:
            logger.warning(
                "EventPublisher not initialized, skipping file:updated event",
                extra={"file_id": str(file_id)}
            )
            return False

        if not settings.event_publishing.enabled:
            return False

        try:
            # Создаем event
            event = FileUpdatedEvent(
                file_id=file_id,
                storage_element_id=storage_element_id,
                metadata=metadata,
            )

            # Сериализуем в JSON
            event_json = event.model_dump_json()

            # Публикуем в Redis channel
            channel = settings.event_publishing.channel_file_updated
            subscribers = await self.redis.publish(channel, event_json)

            logger.info(
                "Published file:updated event",
                extra={
                    "file_id": str(file_id),
                    "storage_element_id": storage_element_id,
                    "channel": channel,
                    "subscribers": subscribers,
                }
            )

            return True

        except Exception as e:
            logger.error(
                "Failed to publish file:updated event",
                extra={
                    "file_id": str(file_id),
                    "storage_element_id": storage_element_id,
                    "error": str(e),
                },
                exc_info=True
            )
            return False

    async def publish_file_deleted(
        self,
        file_id: UUID,
        storage_element_id: int,
        deleted_at: Optional[datetime] = None,
    ) -> bool:
        """
        Публикация file:deleted event.

        Вызывается после успешного удаления файла (FileService.delete_file).

        Args:
            file_id: UUID удаленного файла
            storage_element_id: ID Storage Element где хранился файл
            deleted_at: Timestamp удаления (опционально)

        Returns:
            bool: True если event успешно опубликован, False иначе
        """
        if not self._initialized or not self.redis:
            logger.warning(
                "EventPublisher not initialized, skipping file:deleted event",
                extra={"file_id": str(file_id)}
            )
            return False

        if not settings.event_publishing.enabled:
            return False

        try:
            # Создаем event
            event = FileDeletedEvent(
                file_id=file_id,
                storage_element_id=storage_element_id,
                deleted_at=deleted_at or datetime.utcnow(),
            )

            # Сериализуем в JSON
            event_json = event.model_dump_json()

            # Публикуем в Redis channel
            channel = settings.event_publishing.channel_file_deleted
            subscribers = await self.redis.publish(channel, event_json)

            logger.info(
                "Published file:deleted event",
                extra={
                    "file_id": str(file_id),
                    "storage_element_id": storage_element_id,
                    "channel": channel,
                    "subscribers": subscribers,
                }
            )

            return True

        except Exception as e:
            logger.error(
                "Failed to publish file:deleted event",
                extra={
                    "file_id": str(file_id),
                    "storage_element_id": storage_element_id,
                    "error": str(e),
                },
                exc_info=True
            )
            return False

    async def close(self) -> None:
        """
        Закрытие EventPublisher.

        Вызывается при shutdown приложения (lifespan).
        Redis client закрывается глобально в close_redis().
        """
        logger.info("EventPublisher closed")
        self._initialized = False


# Глобальный экземпляр EventPublisher
event_publisher = EventPublisher()
