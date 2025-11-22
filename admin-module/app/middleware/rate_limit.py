"""
Rate Limiting Middleware для Service Accounts.

Использует Redis для хранения счетчиков запросов.
Каждый Service Account имеет свой rate_limit (по умолчанию 100 req/min).
"""

import time
from typing import Callable, Optional
import logging

from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from redis import Redis

from app.core.config import settings

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate Limiting Middleware на основе Redis.

    Использует алгоритм Sliding Window для точного подсчета запросов.
    Лимиты настраиваются индивидуально для каждого Service Account.

    Алгоритм:
    1. Извлекаем client_id из JWT токена в заголовке Authorization
    2. Получаем rate_limit для этого Service Account из токена
    3. Проверяем количество запросов за последнюю минуту в Redis
    4. Если превышен лимит - возвращаем 429 Too Many Requests
    5. Иначе инкрементируем счетчик и пропускаем запрос
    """

    def __init__(self, app, redis_client: Optional[Redis] = None):
        """
        Инициализация middleware.

        Args:
            app: FastAPI приложение
            redis_client: Redis клиент (если None - создается новый)
        """
        super().__init__(app)
        self.redis_client = redis_client or self._create_redis_client()

    def _create_redis_client(self) -> Redis:
        """
        Создание Redis клиента.

        Returns:
            Redis: Синхронный Redis клиент
        """
        try:
            client = Redis(
                host=settings.redis.host,
                port=settings.redis.port,
                db=settings.redis.db,
                password=settings.redis.password if hasattr(settings.redis, 'password') else None,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            # Проверяем соединение
            client.ping()
            logger.info("Rate limiting Redis connection established")
            return client
        except Exception as e:
            logger.error(f"Failed to connect to Redis for rate limiting: {e}")
            # Возвращаем None - middleware будет работать без rate limiting
            return None

    def _extract_client_id_from_token(self, request: Request) -> Optional[str]:
        """
        Извлечение client_id из JWT токена в заголовке Authorization.

        Args:
            request: FastAPI Request объект

        Returns:
            Optional[str]: client_id если найден, None иначе
        """
        authorization = request.headers.get("Authorization")
        if not authorization:
            return None

        # Формат: "Bearer <token>"
        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return None

        token = parts[1]

        try:
            # Декодируем токен БЕЗ валидации (только для извлечения claims)
            from jose import jwt
            payload = jwt.decode(
                token,
                options={"verify_signature": False}  # Не проверяем подпись
            )

            # Проверяем что это токен Service Account (есть client_id)
            client_id = payload.get("client_id")
            rate_limit = payload.get("rate_limit")

            if client_id and rate_limit:
                return client_id, int(rate_limit)

            return None

        except Exception as e:
            logger.debug(f"Failed to extract client_id from token: {e}")
            return None

    def _check_rate_limit(
        self,
        client_id: str,
        rate_limit: int,
        window_seconds: int = 60
    ) -> tuple[bool, int, int]:
        """
        Проверка rate limit для client_id.

        Использует Redis Sorted Set для Sliding Window алгоритма.

        Args:
            client_id: Client ID Service Account
            rate_limit: Максимальное количество запросов в окне
            window_seconds: Размер окна в секундах (по умолчанию 60 сек)

        Returns:
            tuple[bool, int, int]: (allowed, current_count, retry_after_seconds)
        """
        if not self.redis_client:
            # Redis недоступен - пропускаем все запросы
            logger.warning("Rate limiting disabled: Redis unavailable")
            return True, 0, 0

        try:
            # Ключ в Redis для этого Service Account
            key = f"rate_limit:{client_id}"

            # Текущее время в секундах (с точностью до миллисекунд)
            now = time.time()
            window_start = now - window_seconds

            # Удаляем старые записи вне окна
            self.redis_client.zremrangebyscore(key, 0, window_start)

            # Получаем количество запросов в текущем окне
            current_count = self.redis_client.zcard(key)

            if current_count >= rate_limit:
                # Лимит превышен - вычисляем время до следующего окна
                oldest_timestamp = float(
                    self.redis_client.zrange(key, 0, 0, withscores=True)[0][1]
                )
                retry_after = int(oldest_timestamp + window_seconds - now) + 1
                return False, current_count, retry_after

            # Добавляем текущий запрос в sorted set
            # Score = timestamp, Value = уникальный ID запроса
            request_id = f"{now}:{id(self)}"
            self.redis_client.zadd(key, {request_id: now})

            # Устанавливаем TTL на ключ (2x окна для надежности)
            self.redis_client.expire(key, window_seconds * 2)

            return True, current_count + 1, 0

        except Exception as e:
            logger.error(f"Rate limit check failed: {e}")
            # При ошибке Redis - пропускаем запрос (fail-open)
            return True, 0, 0

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Обработка запроса с проверкой rate limit.

        Args:
            request: FastAPI Request
            call_next: Следующий middleware/handler

        Returns:
            Response: HTTP Response

        Raises:
            HTTPException: 429 Too Many Requests если лимит превышен
        """
        # Извлекаем client_id и rate_limit из токена
        result = self._extract_client_id_from_token(request)

        if result:
            client_id, rate_limit = result

            # Проверяем rate limit
            allowed, current_count, retry_after = self._check_rate_limit(
                client_id=client_id,
                rate_limit=rate_limit
            )

            if not allowed:
                # Лимит превышен - возвращаем 429
                logger.warning(
                    f"Rate limit exceeded for {client_id}: "
                    f"{current_count}/{rate_limit} requests"
                )

                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "error": "rate_limit_exceeded",
                        "message": f"Rate limit exceeded: {rate_limit} requests per minute",
                        "retry_after": retry_after,
                        "current_usage": current_count,
                        "limit": rate_limit
                    },
                    headers={
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(rate_limit),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(int(time.time() + retry_after))
                    }
                )

            # Добавляем заголовки с информацией о rate limit
            response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(rate_limit)
            response.headers["X-RateLimit-Remaining"] = str(rate_limit - current_count)
            response.headers["X-RateLimit-Reset"] = str(int(time.time() + 60))

            return response

        # Запрос без Service Account токена - пропускаем без rate limiting
        return await call_next(request)
