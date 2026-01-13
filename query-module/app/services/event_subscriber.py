"""
Event Subscriber Service для Redis Streams синхронизации.

PHASE 2: Sprint 16 - Query Module Sync Repair.
PHASE 3: Миграция с Pub/Sub на Streams для guaranteed delivery.

EventSubscriber отвечает за подписку на events от Admin Module через Redis Streams (XREADGROUP)
и делегирование обработки в CacheSyncService.

Архитектура:
- Admin Module (EventPublisher) → Redis Streams (XADD) → Query Module (EventSubscriber)
- Consumer Groups с ACK mechanism для guaranteed delivery
- Pending Entry List (PEL) для retry failed events
- EventSubscriber → CacheSyncService → PostgreSQL cache update
- Background asyncio task с graceful degradation при Redis unavailable

Advantages over Pub/Sub:
- Events persisted in stream (не теряются при reconnect)
- Consumer Groups с ACK для tracking обработки
- PEL для automatic retry failed events
- Batch processing для efficiency (count=10)
"""

import logging
import asyncio
import json
import uuid
from typing import Optional
from datetime import datetime

from redis.asyncio import Redis
import redis.exceptions

from app.core.redis import get_redis
from app.core.config import settings
from app.schemas.events import FileCreatedEvent, FileUpdatedEvent, FileDeletedEvent
from app.services.cache_sync import cache_sync_service

logger = logging.getLogger(__name__)


class EventSubscriber:
    """
    Сервис подписки на file events из Redis Streams (XREADGROUP).

    PHASE 2: Подписка на events и делегирование в CacheSyncService.
    PHASE 3: Миграция на Streams с Consumer Groups для guaranteed delivery.

    Background task запускается при startup приложения и работает непрерывно,
    обрабатывая events по мере их поступления через Consumer Groups.

    Consumer Groups обеспечивают:
    - Guaranteed delivery (ACK mechanism)
    - Load balancing между несколькими Query Module instances
    - Pending Entry List (PEL) для retry failed events

    Usage:
        subscriber = EventSubscriber()
        await subscriber.initialize()
        # Background task работает автоматически
    """

    def __init__(self):
        """Инициализация EventSubscriber."""
        self.redis: Optional[Redis] = None
        self._initialized = False
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._pending_task: Optional[asyncio.Task] = None

        # Redis Streams configuration (будет взято из settings после добавления в config)
        self.enabled = True
        self.stream_name = "file-events"
        self.consumer_group = "query-module-consumers"
        self.consumer_name = f"query-module-{uuid.uuid4().hex[:8]}"
        self.last_id = ">"  # Read only new messages (не обработанные этой Consumer Group)

        # Batch processing configuration
        self.batch_size = 10  # Количество events читаемых за раз
        self.block_ms = 5000  # Block для XREADGROUP (5 секунд)

        # PEL retry configuration
        self.pending_retry_ms = 60000  # 60 секунд idle time для retry
        self.pending_check_interval = 30  # Проверять PEL каждые 30 секунд

    async def initialize(self) -> None:
        """
        Асинхронная инициализация EventSubscriber.

        Вызывается при startup приложения (lifespan).
        Создает Consumer Group и запускает background tasks для consumption и PEL retry.
        """
        if not self.enabled:
            logger.info("Event subscription disabled")
            return

        try:
            self.redis = await get_redis()

            # Создаем Consumer Group если не существует
            try:
                await self.redis.xgroup_create(
                    name=self.stream_name,
                    groupname=self.consumer_group,
                    id="0",  # Start from beginning для новой group
                    mkstream=True,  # Создать stream если не существует
                )
                logger.info(
                    "Consumer group created",
                    extra={
                        "stream_name": self.stream_name,
                        "consumer_group": self.consumer_group,
                    }
                )
            except redis.exceptions.ResponseError as e:
                if "BUSYGROUP" not in str(e):
                    raise
                # Group already exists - OK
                logger.info(
                    "Consumer group already exists",
                    extra={"consumer_group": self.consumer_group}
                )

            self._initialized = True

            # Запускаем background tasks
            self._task = asyncio.create_task(self._consume_loop())
            self._pending_task = asyncio.create_task(self._pending_retry_loop())

            logger.info(
                "EventSubscriber initialized (Redis Streams)",
                extra={
                    "stream_name": self.stream_name,
                    "consumer_group": self.consumer_group,
                    "consumer_name": self.consumer_name,
                    "batch_size": self.batch_size,
                    "block_ms": self.block_ms,
                }
            )
        except Exception as e:
            logger.error(f"Failed to initialize EventSubscriber: {e}", exc_info=True)
            self._initialized = False

    async def _consume_loop(self) -> None:
        """
        Основной loop для чтения events из Redis Stream через Consumer Groups.

        Работает непрерывно в background task:
        1. XREADGROUP для чтения batch events (блокирующий read с timeout)
        2. Обработка каждого event через _handle_event
        3. XACK для подтверждения успешной обработки
        4. Graceful retry при ошибках

        Consumer Group обеспечивает:
        - Guaranteed delivery (events не теряются)
        - Load balancing между несколькими Query Module instances
        - PEL tracking для failed events
        """
        self._running = True
        logger.info("Consumer loop started")

        while self._running:
            try:
                if not self.redis:
                    logger.error("Redis client not available")
                    await asyncio.sleep(5)
                    continue

                # XREADGROUP BLOCK - efficient blocking read
                # Читаем batch events, блокируемся на block_ms если нет новых
                events = await self.redis.xreadgroup(
                    groupname=self.consumer_group,
                    consumername=self.consumer_name,
                    streams={self.stream_name: self.last_id},
                    count=self.batch_size,
                    block=self.block_ms,
                )

                if not events:
                    # Timeout, нет новых events - это нормально
                    continue

                # Process events batch
                for stream_name, messages in events:
                    for event_id, event_data in messages:
                        try:
                            # Обрабатываем event
                            await self._handle_event(event_id, event_data)

                            # ACK successful processing
                            await self.redis.xack(
                                self.stream_name,
                                self.consumer_group,
                                event_id,
                            )

                            logger.debug(
                                "Event processed and acknowledged",
                                extra={"event_id": event_id}
                            )

                        except Exception as e:
                            logger.error(
                                "Failed to process event, will retry from PEL",
                                extra={
                                    "event_id": event_id,
                                    "error": str(e),
                                },
                                exc_info=True
                            )
                            # Event остается в PEL, будет retry через _pending_retry_loop

            except asyncio.CancelledError:
                logger.info("Consumer loop cancelled")
                break

            except Exception as e:
                logger.error(
                    "Error in consumer loop, retrying",
                    extra={"error": str(e)},
                    exc_info=True
                )
                await asyncio.sleep(5)  # Backoff before retry

        self._running = False
        logger.info("Consumer loop stopped")

    async def _handle_event(self, event_id: str, event_data: dict) -> None:
        """
        Обработка single event из Redis Stream.

        Args:
            event_id: ID события в stream (например "1736778635123-0")
            event_data: Данные события (уже dict, не требует JSON parsing)

        Raises:
            Exception: При ошибке обработки, event остается в PEL для retry
        """
        try:
            event_type = event_data.get("event_type")

            if not event_type:
                logger.warning(
                    "Event without type",
                    extra={"event_id": event_id, "event_data": event_data}
                )
                return

            # Маршрутизация по типу события
            if event_type == "file:created":
                await self._handle_file_created(event_data)
            elif event_type == "file:updated":
                await self._handle_file_updated(event_data)
            elif event_type == "file:deleted":
                await self._handle_file_deleted(event_data)
            else:
                logger.warning(
                    "Unknown event type",
                    extra={"event_type": event_type, "event_id": event_id}
                )

        except Exception as e:
            logger.error(
                "Error handling event",
                extra={
                    "event_id": event_id,
                    "event_type": event_data.get("event_type"),
                    "error": str(e),
                },
                exc_info=True
            )
            # Re-raise для того чтобы event остался в PEL
            raise

    async def _handle_file_created(self, event_data: dict) -> None:
        """
        Обработка file:created event из Redis Stream.

        Args:
            event_data: Event data из stream (flat dictionary)
                - event_type, timestamp, file_id, storage_element_id
                - metadata: JSON string (нужно распарсить)
        """
        try:
            # Распарсить metadata из JSON string
            metadata_json = event_data.get("metadata")
            if not metadata_json:
                logger.error("Event missing metadata field")
                raise ValueError("Event missing metadata")

            metadata_dict = json.loads(metadata_json)

            # Создать FileCreatedEvent из flat fields + parsed metadata
            event = FileCreatedEvent(
                event_type=event_data.get("event_type", "file:created"),
                timestamp=datetime.fromisoformat(event_data.get("timestamp")),
                file_id=event_data.get("file_id"),
                storage_element_id=event_data.get("storage_element_id"),
                metadata=metadata_dict,  # Pydantic автоматически создаст FileMetadataEvent
            )

            logger.info(
                "Processing file:created event",
                extra={
                    "file_id": str(event.file_id),
                    "original_filename": event.metadata.original_filename,
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
                raise RuntimeError("CacheSyncService returned False")

        except Exception as e:
            logger.error(
                "Error processing file:created event",
                extra={"error": str(e)},
                exc_info=True
            )
            # Re-raise для PEL retry
            raise

    async def _handle_file_updated(self, event_data: dict) -> None:
        """
        Обработка file:updated event из Redis Stream.

        Args:
            event_data: Event data из stream (flat dictionary)
                - event_type, timestamp, file_id, storage_element_id
                - metadata: JSON string (нужно распарсить)
        """
        try:
            # Распарсить metadata из JSON string
            metadata_json = event_data.get("metadata")
            if not metadata_json:
                logger.error("Event missing metadata field")
                raise ValueError("Event missing metadata")

            metadata_dict = json.loads(metadata_json)

            # Создать FileUpdatedEvent из flat fields + parsed metadata
            event = FileUpdatedEvent(
                event_type=event_data.get("event_type", "file:updated"),
                timestamp=datetime.fromisoformat(event_data.get("timestamp")),
                file_id=event_data.get("file_id"),
                storage_element_id=event_data.get("storage_element_id"),
                metadata=metadata_dict,
            )

            logger.info(
                "Processing file:updated event",
                extra={
                    "file_id": str(event.file_id),
                    "original_filename": event.metadata.original_filename,
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
                raise RuntimeError("CacheSyncService returned False")

        except Exception as e:
            logger.error(
                "Error processing file:updated event",
                extra={"error": str(e)},
                exc_info=True
            )
            # Re-raise для PEL retry
            raise

    async def _handle_file_deleted(self, event_data: dict) -> None:
        """
        Обработка file:deleted event из Redis Stream.

        Args:
            event_data: Event data из stream (flat dictionary)
                - event_type, timestamp, file_id, storage_element_id, deleted_at
        """
        try:
            # Создать FileDeletedEvent из flat fields
            event = FileDeletedEvent(
                event_type=event_data.get("event_type", "file:deleted"),
                timestamp=datetime.fromisoformat(event_data.get("timestamp")),
                file_id=event_data.get("file_id"),
                storage_element_id=event_data.get("storage_element_id"),
                deleted_at=datetime.fromisoformat(event_data.get("deleted_at")),
            )

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
                raise RuntimeError("CacheSyncService returned False")

        except Exception as e:
            logger.error(
                "Error processing file:deleted event",
                extra={"error": str(e)},
                exc_info=True
            )
            # Re-raise для PEL retry
            raise

    async def _pending_retry_loop(self) -> None:
        """
        Background task для retry failed events из Pending Entry List (PEL).

        Периодически проверяет PEL на events которые не были acknowledged:
        1. XPENDING_RANGE для получения списка pending events
        2. Фильтрация по idle_time (события старше pending_retry_ms)
        3. XCLAIM для захвата ownership события
        4. Retry обработки через _handle_event
        5. XACK если успешно

        Запускается как отдельный background task каждые pending_check_interval секунд.
        """
        logger.info("Pending retry loop started")

        while self._running:
            try:
                await asyncio.sleep(self.pending_check_interval)

                if not self.redis or not self._initialized:
                    continue

                # Get pending events
                pending = await self.redis.xpending_range(
                    name=self.stream_name,
                    groupname=self.consumer_group,
                    min="-",
                    max="+",
                    count=100,
                )

                if not pending:
                    continue

                logger.debug(
                    "Checking pending events",
                    extra={"pending_count": len(pending)}
                )

                # Process pending events that are idle longer than retry threshold
                for event_info in pending:
                    event_id = event_info["message_id"]
                    idle_time = event_info["time_since_delivered"]

                    if idle_time > self.pending_retry_ms:
                        logger.info(
                            "Retrying pending event",
                            extra={
                                "event_id": event_id,
                                "idle_time_ms": idle_time,
                                "consumer": event_info["consumer"],
                            }
                        )

                        try:
                            # Claim ownership and retry
                            claimed = await self.redis.xclaim(
                                name=self.stream_name,
                                groupname=self.consumer_group,
                                consumername=self.consumer_name,
                                min_idle_time=self.pending_retry_ms,
                                message_ids=[event_id],
                            )

                            for stream_name, messages in claimed:
                                for claimed_event_id, event_data in messages:
                                    # Retry processing
                                    await self._handle_event(claimed_event_id, event_data)

                                    # ACK если успешно
                                    await self.redis.xack(
                                        self.stream_name,
                                        self.consumer_group,
                                        claimed_event_id,
                                    )

                                    logger.info(
                                        "Pending event retried successfully",
                                        extra={"event_id": claimed_event_id}
                                    )

                        except Exception as e:
                            logger.error(
                                "Failed to retry pending event",
                                extra={
                                    "event_id": event_id,
                                    "error": str(e),
                                },
                                exc_info=True
                            )
                            # Event остается в PEL, будет retry в следующей итерации

            except asyncio.CancelledError:
                logger.info("Pending retry loop cancelled")
                break

            except Exception as e:
                logger.error(
                    "Error in pending retry loop",
                    extra={"error": str(e)},
                    exc_info=True
                )
                await asyncio.sleep(5)

        logger.info("Pending retry loop stopped")

    async def close(self) -> None:
        """
        Закрытие EventSubscriber.

        Вызывается при shutdown приложения (lifespan).
        Останавливает background tasks (_consume_loop и _pending_retry_loop).
        """
        logger.info("Closing EventSubscriber")

        self._initialized = False
        self._running = False

        # Ждем завершения consume loop task
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        # Ждем завершения pending retry loop task
        if self._pending_task and not self._pending_task.done():
            self._pending_task.cancel()
            try:
                await self._pending_task
            except asyncio.CancelledError:
                pass

        logger.info("EventSubscriber closed")


# Глобальный экземпляр EventSubscriber
event_subscriber = EventSubscriber()
