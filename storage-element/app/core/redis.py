"""
Асинхронный Redis клиент для Storage Element.

Используется для:
- Health Reporting в Redis registry
- Публикации статуса SE для Service Discovery
- Master Election (при наличии нескольких SE)

ВАЖНО: Использует redis.asyncio (async), НЕ синхронный redis-py!
"""

from typing import Optional

import redis.asyncio as aioredis
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Глобальный singleton клиент
_redis_client: Optional[Redis] = None


async def get_redis_client() -> Redis:
    """
    Получить async Redis client singleton.

    Создаёт новое подключение при первом вызове,
    повторно использует существующее при последующих.

    Returns:
        Redis: Async Redis client с connection pool

    Raises:
        RedisError: При ошибке подключения к Redis
    """
    global _redis_client

    if _redis_client is None:
        try:
            _redis_client = await aioredis.from_url(
                settings.redis.url,
                max_connections=settings.redis.pool_size,
                socket_timeout=settings.redis.socket_timeout,
                socket_connect_timeout=settings.redis.socket_connect_timeout,
                decode_responses=True,  # Автоматически декодируем bytes → str
            )

            # Проверяем подключение
            await _redis_client.ping()

            logger.info(
                "Redis client initialized",
                extra={
                    "host": settings.redis.host,
                    "port": settings.redis.port,
                    "db": settings.redis.db,
                    "pool_size": settings.redis.pool_size,
                }
            )
        except RedisError as e:
            logger.error(
                f"Failed to connect to Redis: {e}",
                extra={
                    "host": settings.redis.host,
                    "port": settings.redis.port,
                    "error": str(e),
                }
            )
            raise

    return _redis_client


async def close_redis_client() -> None:
    """
    Закрыть Redis подключение при shutdown приложения.

    Должен вызываться в lifespan событии FastAPI.
    """
    global _redis_client

    if _redis_client is not None:
        try:
            await _redis_client.close()
            logger.info("Redis client closed successfully")
        except RedisError as e:
            logger.error(f"Error closing Redis client: {e}")
        finally:
            _redis_client = None


async def check_redis_health() -> tuple[bool, str]:
    """
    Проверка доступности Redis для health checks.

    Returns:
        tuple[bool, str]: (is_healthy, status_message)
    """
    try:
        client = await get_redis_client()
        await client.ping()
        return True, "Redis connection healthy"
    except RedisError as e:
        return False, f"Redis connection failed: {e}"
    except Exception as e:
        return False, f"Redis check error: {e}"


class RedisCircuitBreaker:
    """
    Circuit Breaker для Redis операций.

    Предотвращает cascade failures при недоступности Redis.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        half_open_max_calls: int = 3
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._state = "closed"  # closed, open, half-open

    @property
    def is_open(self) -> bool:
        """Проверка, открыт ли circuit breaker."""
        if self._state == "closed":
            return False

        if self._state == "open":
            import time
            if self._last_failure_time:
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self.recovery_timeout:
                    self._state = "half-open"
                    return False
            return True

        return False  # half-open позволяет пробные запросы

    def record_success(self) -> None:
        """Зафиксировать успешный запрос."""
        self._failure_count = 0
        self._state = "closed"

    def record_failure(self) -> None:
        """Зафиксировать неудачный запрос."""
        import time

        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._failure_count >= self.failure_threshold:
            self._state = "open"
            logger.warning(
                f"Redis circuit breaker opened after {self._failure_count} failures",
                extra={"state": self._state, "recovery_timeout": self.recovery_timeout}
            )


# Глобальный экземпляр circuit breaker
redis_circuit_breaker = RedisCircuitBreaker(
    failure_threshold=settings.redis.failure_threshold,
    recovery_timeout=settings.redis.recovery_timeout,
    half_open_max_calls=settings.redis.half_open_max_calls,
)
