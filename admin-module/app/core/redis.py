"""
Асинхронное подключение к Redis для кеширования и Service Discovery.
Использует redis.asyncio с async connection pooling.

ВАЖНО: Redis работает в АСИНХРОННОМ режиме для всех операций Admin Module.
Это обеспечивает неблокирующую работу с event loop FastAPI.
"""

import redis.asyncio as aioredis
from redis.asyncio import Redis
from redis.asyncio.client import PubSub
from typing import Optional
import logging
import json
from datetime import datetime

from .config import settings

logger = logging.getLogger(__name__)

# Global async Redis client
_redis_client: Optional[Redis] = None


async def get_redis() -> Redis:
    """
    Получение асинхронного Redis клиента.
    Создается один раз при первом вызове (lazy initialization).

    Returns:
        Redis: Async Redis клиент

    Example:
        @app.get("/cache")
        async def get_cache():
            redis_client = await get_redis()
            value = await redis_client.get("key")
            return {"value": value}
    """
    global _redis_client

    if _redis_client is None:
        _redis_client = await aioredis.from_url(
            settings.redis.url,
            max_connections=settings.redis.pool_size,
            socket_timeout=settings.redis.socket_timeout,
            socket_connect_timeout=settings.redis.socket_connect_timeout,
            decode_responses=True,  # Автоматическая декодировка bytes в str
        )
        logger.info("Async Redis client created")

    return _redis_client


async def check_redis_connection() -> bool:
    """
    Проверка подключения к Redis (async).
    Используется в health checks.

    Returns:
        bool: True если подключение работает, False иначе
    """
    try:
        client = await get_redis()
        await client.ping()
        return True
    except Exception as e:
        logger.error(f"Redis connection check failed: {e}")
        return False


async def close_redis() -> None:
    """
    Закрытие Redis подключений (async).
    Вызывается при shutdown приложения.
    """
    global _redis_client

    if _redis_client:
        await _redis_client.close()
        _redis_client = None
        logger.info("Async Redis client closed")


class ServiceDiscovery:
    """
    Service Discovery через Redis Pub/Sub (АСИНХРОННЫЙ режим).
    Admin Module публикует конфигурацию storage elements.
    Ingester/Query модули подписываются на обновления.

    ВАЖНО: Все методы асинхронные для неблокирующей работы с event loop.
    """

    def __init__(self):
        self.redis: Optional[Redis] = None
        self.pubsub: Optional[PubSub] = None

    async def initialize(self) -> None:
        """
        Асинхронная инициализация Service Discovery.
        Вызывается при startup приложения.
        """
        if not settings.service_discovery.enabled:
            logger.info("Service Discovery disabled")
            return

        self.redis = await get_redis()
        logger.info("Service Discovery initialized (async mode)")

    async def publish_storage_element_config(
        self,
        config: dict,
        action: str = "manual",
        storage_element_id: Optional[int] = None,
        storage_element_name: Optional[str] = None
    ) -> int:
        """
        Асинхронная публикация конфигурации storage element.

        Args:
            config: Конфигурация storage elements в формате dict
            action: Тип действия (created/updated/deleted/synced/scheduled/startup)
            storage_element_id: ID измененного storage element (для событийных операций)
            storage_element_name: Имя измененного storage element

        Returns:
            int: Количество подписчиков, получивших сообщение
        """
        if not self.redis:
            logger.warning("Service Discovery not initialized")
            return 0

        try:
            # Сохраняем конфигурацию в Redis
            await self.redis.set(
                settings.service_discovery.storage_element_config_key,
                json.dumps(config),
                ex=3600  # TTL 1 час
            )

            # Формируем событие для Pub/Sub
            event = {
                "event": "storage_element_config_updated",
                "timestamp": datetime.utcnow().isoformat(),
                "action": action,
                "version": config.get("version", 1),
                "count": config.get("count", 0)
            }

            if storage_element_id:
                event["storage_element_id"] = storage_element_id
            if storage_element_name:
                event["storage_element_name"] = storage_element_name

            # Публикуем событие об обновлении
            subscribers = await self.redis.publish(
                settings.service_discovery.redis_channel,
                json.dumps(event)
            )

            logger.info(
                f"Published storage element config: action={action}, "
                f"count={config.get('count', 0)}, subscribers={subscribers}"
            )
            return subscribers

        except Exception as e:
            logger.error(f"Failed to publish storage element config: {e}")
            return 0

    async def get_storage_element_config(self) -> Optional[dict]:
        """
        Асинхронное получение текущей конфигурации storage elements.

        Returns:
            Optional[dict]: Конфигурация или None если не найдена
        """
        if not self.redis:
            logger.warning("Service Discovery not initialized")
            return None

        try:
            config_json = await self.redis.get(
                settings.service_discovery.storage_element_config_key
            )

            if config_json:
                return json.loads(config_json)

            return None

        except Exception as e:
            logger.error(f"Failed to get storage element config: {e}")
            return None

    async def subscribe_to_updates(self):
        """
        Асинхронная подписка на обновления конфигурации (async generator).
        Используется Ingester/Query модулями.

        Yields:
            dict: Сообщения о обновлениях

        Example:
            async for update in service_discovery.subscribe_to_updates():
                await handle_config_update(update)
        """
        if not self.redis:
            logger.warning("Service Discovery not initialized")
            return

        try:
            self.pubsub = self.redis.pubsub()
            await self.pubsub.subscribe(settings.service_discovery.redis_channel)

            logger.info(f"Subscribed to {settings.service_discovery.redis_channel}")

            async for message in self.pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        yield data
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to decode message: {e}")
                        continue

        except Exception as e:
            logger.error(f"Subscription error: {e}")

        finally:
            if self.pubsub:
                await self.pubsub.unsubscribe(settings.service_discovery.redis_channel)
                await self.pubsub.close()

    async def close(self) -> None:
        """
        Асинхронное закрытие Service Discovery.
        Вызывается при shutdown приложения.
        """
        if self.pubsub:
            await self.pubsub.close()
        logger.info("Service Discovery closed")


# Глобальный экземпляр Service Discovery
service_discovery = ServiceDiscovery()


async def publish_storage_element_config_standalone(
    config: dict,
    action: str = "manual",
    storage_element_id: Optional[int] = None,
    storage_element_name: Optional[str] = None
) -> int:
    """
    Standalone функция публикации конфигурации для background jobs.

    Создает собственный Redis client для использования в отдельном event loop
    (например, в APScheduler background jobs).

    ВАЖНО: НЕ ИСПОЛЬЗОВАТЬ в FastAPI endpoints - там используйте service_discovery.

    Args:
        config: Конфигурация storage elements
        action: Тип действия (created/updated/deleted/synced/scheduled/startup)
        storage_element_id: ID storage element (опционально)
        storage_element_name: Имя storage element (опционально)

    Returns:
        int: Количество подписчиков, получивших обновление
    """
    try:
        # Создаем standalone Redis client для этого event loop
        standalone_redis = await aioredis.from_url(
            settings.redis.url,
            max_connections=2,
            socket_timeout=settings.redis.socket_timeout,
            socket_connect_timeout=settings.redis.socket_connect_timeout,
            decode_responses=True,
        )

        try:
            # Сохраняем конфигурацию в Redis
            await standalone_redis.set(
                settings.service_discovery.storage_element_config_key,
                json.dumps(config),
                ex=3600  # TTL 1 час
            )

            # Формируем событие для Pub/Sub
            event = {
                "event": "storage_element_config_updated",
                "timestamp": datetime.utcnow().isoformat(),
                "action": action,
                "version": config.get("version", 1),
                "count": config.get("count", 0)
            }

            if storage_element_id:
                event["storage_element_id"] = storage_element_id
            if storage_element_name:
                event["storage_element_name"] = storage_element_name

            # Публикуем событие об обновлении
            subscribers = await standalone_redis.publish(
                settings.service_discovery.redis_channel,
                json.dumps(event)
            )

            logger.info(
                f"Published storage element config (standalone): action={action}, "
                f"count={config.get('count', 0)}, subscribers={subscribers}"
            )
            return subscribers

        finally:
            await standalone_redis.close()

    except Exception as e:
        logger.error(f"Failed to publish storage element config (standalone): {e}")
        return 0
