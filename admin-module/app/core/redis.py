"""
Подключение к Redis для кеширования и Service Discovery.
Использует синхронный redis-py с connection pooling.

ВАЖНО: Redis работает в СИНХРОННОМ режиме для всех модулей ArtStore.
Это архитектурное решение для упрощения координации и Service Discovery.
"""

import redis
from redis import Redis, ConnectionPool
from redis.client import PubSub
from typing import Optional
import logging
import json
from datetime import datetime

from .config import settings

logger = logging.getLogger(__name__)

# Global Redis connection pool
_redis_pool: Optional[ConnectionPool] = None
_redis_client: Optional[Redis] = None


def get_redis_pool() -> ConnectionPool:
    """
    Получение Redis connection pool.
    Создается только один раз при первом вызове.

    Returns:
        ConnectionPool: Redis connection pool
    """
    global _redis_pool

    if _redis_pool is None:
        _redis_pool = ConnectionPool.from_url(
            settings.redis.url,
            max_connections=settings.redis.pool_size,
            socket_timeout=settings.redis.socket_timeout,
            socket_connect_timeout=settings.redis.socket_connect_timeout,
            decode_responses=True,  # Автоматическая декодировка bytes в str
        )
        logger.info("Redis connection pool created (sync mode)")

    return _redis_pool


def get_redis() -> Redis:
    """
    Получение Redis client.
    Используется в FastAPI endpoints.

    Returns:
        Redis: Redis sync client

    Example:
        @app.get("/cache")
        def get_cache():
            redis_client = get_redis()
            value = redis_client.get("key")
            return {"value": value}
    """
    global _redis_client

    if _redis_client is None:
        pool = get_redis_pool()
        _redis_client = Redis(connection_pool=pool)
        logger.info("Redis client created (sync mode)")

    return _redis_client


def check_redis_connection() -> bool:
    """
    Проверка подключения к Redis.
    Используется в health checks.

    Returns:
        bool: True если подключение работает, False иначе
    """
    try:
        client = get_redis()
        client.ping()
        return True
    except Exception as e:
        logger.error(f"Redis connection check failed: {e}")
        return False


def close_redis() -> None:
    """
    Закрытие Redis подключений.
    Вызывается при shutdown приложения.
    """
    global _redis_client, _redis_pool

    if _redis_client:
        _redis_client.close()
        _redis_client = None
        logger.info("Redis client closed")

    if _redis_pool:
        _redis_pool.disconnect()
        _redis_pool = None
        logger.info("Redis connection pool closed")


class ServiceDiscovery:
    """
    Service Discovery через Redis Pub/Sub (синхронный режим).
    Admin Module публикует конфигурацию storage elements.
    Ingester/Query модули подписываются на обновления.

    ВАЖНО: Работает в синхронном режиме для упрощения координации.
    """

    def __init__(self):
        self.redis: Optional[Redis] = None
        self.pubsub: Optional[PubSub] = None

    def initialize(self):
        """Инициализация Service Discovery."""
        if not settings.service_discovery.enabled:
            logger.info("Service Discovery disabled")
            return

        self.redis = get_redis()
        logger.info("Service Discovery initialized (sync mode)")

    def publish_storage_element_config(self, config: dict) -> int:
        """
        Публикация конфигурации storage element.

        Args:
            config: Конфигурация storage element в формате dict

        Returns:
            int: Количество подписчиков, получивших сообщение
        """
        if not self.redis:
            logger.warning("Service Discovery not initialized")
            return 0

        try:
            # Сохраняем конфигурацию в Redis
            self.redis.set(
                settings.service_discovery.storage_element_config_key,
                json.dumps(config),
                ex=3600  # TTL 1 час
            )

            # Публикуем событие об обновлении
            subscribers = self.redis.publish(
                settings.service_discovery.redis_channel,
                json.dumps({
                    "event": "storage_element_config_updated",
                    "timestamp": datetime.utcnow().isoformat()
                })
            )

            logger.info(f"Published storage element config to {subscribers} subscribers")
            return subscribers

        except Exception as e:
            logger.error(f"Failed to publish storage element config: {e}")
            return 0

    def get_storage_element_config(self) -> Optional[dict]:
        """
        Получение текущей конфигурации storage elements.

        Returns:
            Optional[dict]: Конфигурация или None если не найдена
        """
        if not self.redis:
            logger.warning("Service Discovery not initialized")
            return None

        try:
            config_json = self.redis.get(
                settings.service_discovery.storage_element_config_key
            )

            if config_json:
                return json.loads(config_json)

            return None

        except Exception as e:
            logger.error(f"Failed to get storage element config: {e}")
            return None

    def subscribe_to_updates(self):
        """
        Подписка на обновления конфигурации (генератор).
        Используется Ingester/Query модулями.

        Yields:
            dict: Сообщения о обновлениях
        """
        if not self.redis:
            logger.warning("Service Discovery not initialized")
            return

        try:
            self.pubsub = self.redis.pubsub()
            self.pubsub.subscribe(settings.service_discovery.redis_channel)

            logger.info(f"Subscribed to {settings.service_discovery.redis_channel}")

            for message in self.pubsub.listen():
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
                self.pubsub.unsubscribe(settings.service_discovery.redis_channel)
                self.pubsub.close()

    def close(self):
        """Закрытие Service Discovery."""
        if self.pubsub:
            self.pubsub.close()
        logger.info("Service Discovery closed")


# Глобальный экземпляр Service Discovery
service_discovery = ServiceDiscovery()
