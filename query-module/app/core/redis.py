"""
Асинхронное подключение к Redis для кеширования и Event Subscription.
Использует redis.asyncio с async connection pooling.

ВАЖНО: Redis работает в АСИНХРОННОМ режиме для всех операций Query Module.
Это обеспечивает неблокирующую работу с event loop FastAPI.
"""

import redis.asyncio as aioredis
from redis.asyncio import Redis
from redis.asyncio.client import PubSub
from typing import Optional
import logging

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
        redis_client = await get_redis()
        value = await redis_client.get("key")
    """
    global _redis_client

    if _redis_client is None:
        _redis_client = await aioredis.from_url(
            settings.redis.redis_url,
            max_connections=settings.redis.max_connections,
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


async def check_redis_with_error() -> tuple[bool, Optional[str]]:
    """
    Проверка подключения к Redis с возвратом текста ошибки.
    Используется в readiness health checks для детальной диагностики.

    Returns:
        tuple: (is_ok, error_message)
            - is_ok: True если подключение работает
            - error_message: Текст ошибки или None если всё в порядке
    """
    try:
        client = await get_redis()
        await client.ping()
        return True, None
    except Exception as e:
        error_message = str(e)
        logger.warning(f"Redis connection check failed: {error_message}")
        return False, error_message


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
