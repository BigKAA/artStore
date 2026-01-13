"""
Event Publisher Service для Redis Streams синхронизации.

PHASE 1: Sprint 16 - Query Module Sync Repair.
PHASE 2: Миграция с Pub/Sub на Streams для guaranteed delivery.

EventPublisher отвечает за публикацию events о file operations в Redis Streams (XADD).
Query Module подписывается через Consumer Groups (XREADGROUP) и синхронизирует cache.

Архитектура:
- Admin Module (EventPublisher) → Redis Streams (XADD) → Query Module (EventSubscriber)
- Events: file:created, file:updated, file:deleted
- Stream: file-events с automatic cleanup (MAXLEN)
- Consumer Groups с ACK mechanism для guaranteed delivery
- Async Redis (redis.asyncio) для неблокирующей работы
- Graceful degradation при Redis unavailable

Advantages over Pub/Sub:
- Events persisted in stream (не теряются при reconnect)
- Consumer Groups с ACK для tracking обработки
- Pending Entry List (PEL) для retry failed events
- MAXLEN для automatic cleanup старых events
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
    Сервис для публикации file events в Redis Streams (XADD).

    PHASE 1: Публикация events после успешных file operations.
    PHASE 2: Миграция на Streams для guaranteed delivery.

    Query Module подписывается через Consumer Groups и обновляет cache.

    Usage:
        publisher = EventPublisher()
        event_id = await publisher.publish_file_created(file_id, storage_element_id, metadata)
        # Returns event_id like "1234567890-0"
    """

    def __init__(self):
        """Инициализация EventPublisher."""
        self.redis: Optional[Redis] = None
        self._initialized = False

    async def initialize(self) -> None:
        """
        Асинхронная инициализация EventPublisher.

        Вызывается при startup приложения (lifespan).
        Получает Redis client для publishing в Streams.
        """
        if not settings.event_publishing.enabled:
            logger.info("Event publishing disabled")
            return

        try:
            self.redis = await get_redis()
            self._initialized = True
            logger.info(
                "EventPublisher initialized (Redis Streams)",
                extra={
                    "stream_name": settings.event_publishing.stream_name,
                    "stream_maxlen": settings.event_publishing.stream_maxlen,
                    "stream_retention_hours": settings.event_publishing.stream_retention_hours,
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
    ) -> Optional[str]:
        """
        Публикация file:created event в Redis Stream (XADD).

        Вызывается после успешной регистрации файла (FileService.register_file).

        Args:
            file_id: UUID созданного файла
            storage_element_id: ID Storage Element где хранится файл
            metadata: Полные метаданные файла

        Returns:
            Optional[str]: Event ID (например "1234567890-0") если успешно, None иначе

        Example:
            metadata = FileMetadataEvent(
                file_id=file.file_id,
                original_filename=file.original_filename,
                ...
            )
            event_id = await publisher.publish_file_created(
                file.file_id,
                file.storage_element_id,
                metadata
            )
            # event_id = "1736778635123-0"
        """
        if not self._initialized or not self.redis:
            logger.warning(
                "EventPublisher not initialized, skipping file:created event",
                extra={"file_id": str(file_id)}
            )
            return None

        if not settings.event_publishing.enabled:
            return None

        try:
            # Создаем flat dictionary для XADD
            # metadata сериализуется в JSON string как одно поле
            event_data = {
                "event_type": "file:created",
                "timestamp": datetime.utcnow().isoformat(),
                "file_id": str(file_id),
                "storage_element_id": str(storage_element_id),
                "metadata": metadata.model_dump_json(),
            }

            # XADD в Redis Stream с automatic cleanup
            event_id = await self.redis.xadd(
                name=settings.event_publishing.stream_name,
                fields=event_data,
                maxlen=settings.event_publishing.stream_maxlen,
                approximate=True,  # Approximate MAXLEN для performance
            )

            logger.info(
                "Published file:created event to stream",
                extra={
                    "event_id": event_id,
                    "file_id": str(file_id),
                    "storage_element_id": storage_element_id,
                    "stream_name": settings.event_publishing.stream_name,
                }
            )

            return event_id

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
            return None

    async def publish_file_updated(
        self,
        file_id: UUID,
        storage_element_id: int,
        metadata: FileMetadataEvent,
    ) -> Optional[str]:
        """
        Публикация file:updated event в Redis Stream (XADD).

        Вызывается после успешного обновления файла (FileService.update_file).

        Args:
            file_id: UUID обновленного файла
            storage_element_id: ID Storage Element где хранится файл
            metadata: Обновленные метаданные файла

        Returns:
            Optional[str]: Event ID если успешно, None иначе
        """
        if not self._initialized or not self.redis:
            logger.warning(
                "EventPublisher not initialized, skipping file:updated event",
                extra={"file_id": str(file_id)}
            )
            return None

        if not settings.event_publishing.enabled:
            return None

        try:
            # Создаем flat dictionary для XADD
            event_data = {
                "event_type": "file:updated",
                "timestamp": datetime.utcnow().isoformat(),
                "file_id": str(file_id),
                "storage_element_id": str(storage_element_id),
                "metadata": metadata.model_dump_json(),
            }

            # XADD в Redis Stream с automatic cleanup
            event_id = await self.redis.xadd(
                name=settings.event_publishing.stream_name,
                fields=event_data,
                maxlen=settings.event_publishing.stream_maxlen,
                approximate=True,
            )

            logger.info(
                "Published file:updated event to stream",
                extra={
                    "event_id": event_id,
                    "file_id": str(file_id),
                    "storage_element_id": storage_element_id,
                    "stream_name": settings.event_publishing.stream_name,
                }
            )

            return event_id

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
            return None

    async def publish_file_deleted(
        self,
        file_id: UUID,
        storage_element_id: int,
        deleted_at: Optional[datetime] = None,
    ) -> Optional[str]:
        """
        Публикация file:deleted event в Redis Stream (XADD).

        Вызывается после успешного удаления файла (FileService.delete_file).

        Args:
            file_id: UUID удаленного файла
            storage_element_id: ID Storage Element где хранился файл
            deleted_at: Timestamp удаления (опционально)

        Returns:
            Optional[str]: Event ID если успешно, None иначе
        """
        if not self._initialized or not self.redis:
            logger.warning(
                "EventPublisher not initialized, skipping file:deleted event",
                extra={"file_id": str(file_id)}
            )
            return None

        if not settings.event_publishing.enabled:
            return None

        try:
            # Создаем flat dictionary для XADD
            deleted_timestamp = deleted_at or datetime.utcnow()
            event_data = {
                "event_type": "file:deleted",
                "timestamp": datetime.utcnow().isoformat(),
                "file_id": str(file_id),
                "storage_element_id": str(storage_element_id),
                "deleted_at": deleted_timestamp.isoformat(),
            }

            # XADD в Redis Stream с automatic cleanup
            event_id = await self.redis.xadd(
                name=settings.event_publishing.stream_name,
                fields=event_data,
                maxlen=settings.event_publishing.stream_maxlen,
                approximate=True,
            )

            logger.info(
                "Published file:deleted event to stream",
                extra={
                    "event_id": event_id,
                    "file_id": str(file_id),
                    "storage_element_id": storage_element_id,
                    "stream_name": settings.event_publishing.stream_name,
                }
            )

            return event_id

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
            return None

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
