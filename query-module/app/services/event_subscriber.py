"""
Event Subscriber Service для Redis Pub/Sub синхронизации.

PHASE 2: Sprint 16 - Query Module Sync Repair.

EventSubscriber отвечает за подписку на events от Admin Module через Redis Pub/Sub
и делегирование обработки в CacheSyncService.

Архитектура:
- Admin Module (EventPublisher) → Redis Pub/Sub → Query Module (EventSubscriber)
- EventSubscriber → CacheSyncService → PostgreSQL cache update
- Background asyncio task с graceful degradation при Redis unavailable
"""

import logging
import asyncio
import json
from typing import Optional
from datetime import datetime

from redis.asyncio import Redis
from redis.asyncio.client import PubSub

from app.core.redis import get_redis
from app.core.config import settings
from app.schemas.events import FileCreatedEvent, FileUpdatedEvent, FileDeletedEvent
from app.services.cache_sync import cache_sync_service

logger = logging.getLogger(__name__)


class EventSubscriber:
    """
    Сервис подписки на file events из Redis Pub/Sub.

    PHASE 2: Подписка на events и делегирование в CacheSyncService.

    Background task запускается при startup приложения и работает непрерывно,
    обрабатывая events по мере их поступления.

    Usage:
        subscriber = EventSubscriber()
        await subscriber.initialize()
        # Background task работает автоматически
    """

    def __init__(self):
        """Инициализация EventSubscriber."""
        self.redis: Optional[Redis] = None
        self.pubsub: Optional[PubSub] = None
        self._initialized = False
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # Configuration
        self.enabled = True  # Будет взято из settings после добавления в config
        self.channels = [
            "file:created",  # Будет из settings.event_subscription.channel_file_created
            "file:updated",
            "file:deleted",
        ]
        self.reconnect_delay = 5  # seconds
        self.max_reconnect_attempts = 10

    async def initialize(self) -> None:
        """
        Асинхронная инициализация EventSubscriber.

        Вызывается при startup приложения (lifespan).
        Запускает background task для subscription.
        """
        if not self.enabled:
            logger.info("Event subscription disabled")
            return

        try:
            self.redis = await get_redis()
            self._initialized = True

            # Запускаем background task для subscription
            self._task = asyncio.create_task(self._subscription_loop())

            logger.info(
                "EventSubscriber initialized",
                extra={
                    "channels": self.channels,
                    "reconnect_delay": self.reconnect_delay,
                    "max_reconnect_attempts": self.max_reconnect_attempts,
                }
            )
        except Exception as e:
            logger.error(f"Failed to initialize EventSubscriber: {e}", exc_info=True)
            self._initialized = False

    async def _subscription_loop(self) -> None:
        """
        Основной loop для подписки на Redis channels с reconnection logic.

        Работает непрерывно в background task:
        1. Subscribe к channels
        2. Listen к events
        3. Обработка events через CacheSyncService
        4. Reconnect при ошибках
        """
        reconnect_attempt = 0

        while self._initialized:
            try:
                if not self.redis:
                    logger.error("Redis client not available")
                    await asyncio.sleep(self.reconnect_delay)
                    continue

                # Создаем PubSub client
                self.pubsub = self.redis.pubsub()
                await self.pubsub.subscribe(*self.channels)

                logger.info(
                    "Subscribed to Redis channels",
                    extra={"channels": self.channels}
                )

                self._running = True
                reconnect_attempt = 0  # Reset counter при успешном подключении

                # Listen к events
                async for message in self.pubsub.listen():
                    if not self._initialized:
                        break

                    if message["type"] == "message":
                        await self._handle_message(message)

            except asyncio.CancelledError:
                logger.info("Subscription loop cancelled")
                break

            except Exception as e:
                reconnect_attempt += 1
                logger.error(
                    "Subscription error, attempting reconnect",
                    extra={
                        "error": str(e),
                        "attempt": reconnect_attempt,
                        "max_attempts": self.max_reconnect_attempts,
                    },
                    exc_info=True
                )

                if reconnect_attempt >= self.max_reconnect_attempts:
                    logger.critical(
                        "Max reconnect attempts reached, stopping subscription",
                        extra={"attempts": reconnect_attempt}
                    )
                    break

                # Exponential backoff
                delay = min(self.reconnect_delay * (2 ** (reconnect_attempt - 1)), 60)
                await asyncio.sleep(delay)

            finally:
                # Cleanup PubSub client
                if self.pubsub:
                    try:
                        await self.pubsub.unsubscribe(*self.channels)
                        await self.pubsub.close()
                    except Exception as e:
                        logger.warning(f"Error during pubsub cleanup: {e}")
                    finally:
                        self.pubsub = None

        self._running = False
        logger.info("Subscription loop stopped")

    async def _handle_message(self, message: dict) -> None:
        """
        Обработка полученного Redis Pub/Sub message.

        Args:
            message: Сообщение от Redis в формате {"type": "message", "data": "...", "channel": "..."}
        """
        try:
            channel = message.get("channel")
            data = message.get("data")

            if not data:
                logger.warning("Empty message received", extra={"channel": channel})
                return

            # Парсим JSON
            try:
                event_data = json.loads(data)
            except json.JSONDecodeError as e:
                logger.error(
                    "Failed to parse event JSON",
                    extra={"channel": channel, "error": str(e)},
                    exc_info=True
                )
                return

            # Определяем тип события и обрабатываем
            event_type = event_data.get("event_type")

            if event_type == "file:created":
                await self._handle_file_created(event_data)
            elif event_type == "file:updated":
                await self._handle_file_updated(event_data)
            elif event_type == "file:deleted":
                await self._handle_file_deleted(event_data)
            else:
                logger.warning(
                    "Unknown event type",
                    extra={"event_type": event_type, "channel": channel}
                )

        except Exception as e:
            logger.error(
                "Error handling message",
                extra={"error": str(e)},
                exc_info=True
            )

    async def _handle_file_created(self, event_data: dict) -> None:
        """
        Обработка file:created event.

        Args:
            event_data: Parsed JSON event data
        """
        try:
            event = FileCreatedEvent(**event_data)

            logger.info(
                "Processing file:created event",
                extra={
                    "file_id": str(event.file_id),
                    "filename": event.metadata.original_filename,
                    "storage_element_id": event.storage_element_id,
                }
            )

            # Делегируем обработку в CacheSyncService
            success = await cache_sync_service.handle_file_created(event)

            if not success:
                logger.error(
                    "Failed to process file:created event",
                    extra={"file_id": str(event.file_id)}
                )

        except Exception as e:
            logger.error(
                "Error processing file:created event",
                extra={"error": str(e)},
                exc_info=True
            )

    async def _handle_file_updated(self, event_data: dict) -> None:
        """
        Обработка file:updated event.

        Args:
            event_data: Parsed JSON event data
        """
        try:
            event = FileUpdatedEvent(**event_data)

            logger.info(
                "Processing file:updated event",
                extra={
                    "file_id": str(event.file_id),
                    "filename": event.metadata.original_filename,
                    "storage_element_id": event.storage_element_id,
                }
            )

            # Делегируем обработку в CacheSyncService
            success = await cache_sync_service.handle_file_updated(event)

            if not success:
                logger.error(
                    "Failed to process file:updated event",
                    extra={"file_id": str(event.file_id)}
                )

        except Exception as e:
            logger.error(
                "Error processing file:updated event",
                extra={"error": str(e)},
                exc_info=True
            )

    async def _handle_file_deleted(self, event_data: dict) -> None:
        """
        Обработка file:deleted event.

        Args:
            event_data: Parsed JSON event data
        """
        try:
            event = FileDeletedEvent(**event_data)

            logger.info(
                "Processing file:deleted event",
                extra={
                    "file_id": str(event.file_id),
                    "storage_element_id": event.storage_element_id,
                }
            )

            # Делегируем обработку в CacheSyncService
            success = await cache_sync_service.handle_file_deleted(event)

            if not success:
                logger.error(
                    "Failed to process file:deleted event",
                    extra={"file_id": str(event.file_id)}
                )

        except Exception as e:
            logger.error(
                "Error processing file:deleted event",
                extra={"error": str(e)},
                exc_info=True
            )

    async def close(self) -> None:
        """
        Закрытие EventSubscriber.

        Вызывается при shutdown приложения (lifespan).
        Останавливает background task и закрывает PubSub connections.
        """
        logger.info("Closing EventSubscriber")

        self._initialized = False

        # Ждем завершения background task
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        # Cleanup PubSub
        if self.pubsub:
            try:
                await self.pubsub.unsubscribe(*self.channels)
                await self.pubsub.close()
            except Exception as e:
                logger.warning(f"Error closing pubsub: {e}")
            finally:
                self.pubsub = None

        logger.info("EventSubscriber closed")


# Глобальный экземпляр EventSubscriber
event_subscriber = EventSubscriber()
