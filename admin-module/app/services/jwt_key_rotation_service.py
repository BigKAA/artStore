"""
JWT Key Rotation Service с distributed locking через Redis.

Функции:
- Автоматическая ротация RSA ключей каждые 24 часа
- Distributed locking для cluster-safe операций
- Graceful transition period (25h validity = 24h + 1h overlap)
- Cleanup expired keys с сохранением audit trail
- Prometheus metrics для monitoring
"""

from datetime import datetime, timezone
import logging
from typing import Optional
import time

from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from app.core.redis import get_redis
from app.models.jwt_key import JWTKey

logger = logging.getLogger(__name__)


class JWTKeyRotationService:
    """
    Сервис ротации JWT ключей с distributed locking.

    Features:
    - Redis distributed lock для cluster-safe rotation
    - Automatic cleanup expired keys
    - Graceful transition period (25h validity)
    - Comprehensive error handling и logging
    - Prometheus metrics integration
    """

    # Redis lock configuration
    LOCK_KEY = "jwt_rotation_lock"
    LOCK_TIMEOUT = 60  # 60 секунд (достаточно для rotation операции)
    LOCK_RETRY_DELAY = 1  # 1 секунда между retry attempts
    LOCK_MAX_RETRIES = 3  # Максимум 3 попытки получить lock

    # Key rotation configuration
    KEY_VALIDITY_HOURS = 25  # 24h + 1h grace period

    def __init__(self, redis_client: Optional[Redis] = None):
        """
        Инициализация JWT Key Rotation Service.

        Args:
            redis_client: Redis client (если None, использует get_redis())
        """
        self.redis = redis_client or get_redis()

    def rotate_keys(self, session: Session) -> bool:
        """
        Выполнение ротации JWT ключей с distributed locking.

        Процесс:
        1. Получение distributed lock через Redis
        2. Cleanup expired keys
        3. Создание нового ключа
        4. Commit транзакции
        5. Освобождение lock

        Args:
            session: Database session

        Returns:
            bool: True если ротация успешна, False иначе

        Example:
            success = rotation_service.rotate_keys(db_session)
            if success:
                logger.info("JWT key rotation completed successfully")
        """
        lock_acquired = False
        lock_value = f"{int(time.time() * 1000)}"  # Уникальный идентификатор lock

        try:
            # Попытка получить distributed lock с retry logic
            lock_acquired = self._acquire_lock(lock_value)

            if not lock_acquired:
                logger.warning(
                    "Failed to acquire rotation lock after retries. "
                    "Another instance may be performing rotation."
                )
                return False

            logger.info("Acquired rotation lock, starting key rotation")

            # Cleanup expired keys
            deactivated_count = JWTKey.cleanup_expired_keys(session)
            logger.info(f"Deactivated {deactivated_count} expired keys")

            # Создание нового ключа
            new_key = JWTKey.create_new_key(
                session=session,
                validity_hours=self.KEY_VALIDITY_HOURS
            )

            # Инкремент rotation_count для всех активных ключей
            active_keys = JWTKey.get_active_keys(session)
            for key in active_keys:
                key.rotation_count += 1

            # Добавление нового ключа в БД
            session.add(new_key)
            session.commit()

            logger.info(
                f"JWT key rotation completed successfully. "
                f"New key version: {new_key.version[:8]}..., "
                f"expires_at: {new_key.expires_at.isoformat()}"
            )

            # Метрики для Prometheus
            self._record_rotation_metrics(success=True, deactivated_count=deactivated_count)

            return True

        except Exception as e:
            logger.error(f"JWT key rotation failed: {e}", exc_info=True)
            session.rollback()

            # Метрики для Prometheus
            self._record_rotation_metrics(success=False, error=str(e))

            return False

        finally:
            # Обязательно освобождаем lock
            if lock_acquired:
                self._release_lock(lock_value)
                logger.info("Released rotation lock")

    def _acquire_lock(self, lock_value: str) -> bool:
        """
        Получение distributed lock через Redis с retry logic.

        Args:
            lock_value: Уникальный идентификатор lock

        Returns:
            bool: True если lock получен, False иначе
        """
        for attempt in range(self.LOCK_MAX_RETRIES):
            try:
                # SET key value NX EX timeout
                # NX = Set if Not eXists (получить lock только если его нет)
                # EX = EXpire time в секундах
                acquired = self.redis.set(
                    self.LOCK_KEY,
                    lock_value,
                    nx=True,  # Only set if key doesn't exist
                    ex=self.LOCK_TIMEOUT  # Expire after LOCK_TIMEOUT seconds
                )

                if acquired:
                    logger.debug(f"Lock acquired on attempt {attempt + 1}")
                    return True

                # Lock занят, ждем перед retry
                if attempt < self.LOCK_MAX_RETRIES - 1:
                    logger.debug(
                        f"Lock not available (attempt {attempt + 1}/{self.LOCK_MAX_RETRIES}), "
                        f"retrying in {self.LOCK_RETRY_DELAY}s"
                    )
                    time.sleep(self.LOCK_RETRY_DELAY)

            except RedisError as e:
                logger.error(f"Redis error during lock acquisition: {e}")
                return False

        return False

    def _release_lock(self, lock_value: str) -> bool:
        """
        Освобождение distributed lock через Redis.

        Использует Lua script для atomic check-and-delete:
        - Проверяет что текущий lock принадлежит нам (lock_value совпадает)
        - Удаляет lock только если он наш

        Args:
            lock_value: Уникальный идентификатор lock

        Returns:
            bool: True если lock освобожден, False иначе
        """
        try:
            # Lua script для atomic check-and-delete
            # Проверяем что lock принадлежит нам перед удалением
            lua_script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
            """

            result = self.redis.eval(lua_script, 1, self.LOCK_KEY, lock_value)

            if result == 1:
                logger.debug("Lock released successfully")
                return True
            else:
                logger.warning("Lock not released - value mismatch or already expired")
                return False

        except RedisError as e:
            logger.error(f"Redis error during lock release: {e}")
            return False

    def check_rotation_needed(self, session: Session) -> bool:
        """
        Проверка необходимости ротации ключей.

        Ротация нужна если:
        - Нет активных ключей
        - Самый новый ключ скоро истечет (< 1 час до expiration)

        Args:
            session: Database session

        Returns:
            bool: True если ротация необходима, False иначе
        """
        try:
            latest_key = JWTKey.get_latest_active_key(session)

            if not latest_key:
                logger.warning("No active JWT keys found, rotation needed")
                return True

            # Проверка времени до истечения
            now = datetime.now(timezone.utc)
            time_until_expiry = (latest_key.expires_at - now).total_seconds() / 3600  # hours

            if time_until_expiry < 1:
                logger.info(
                    f"Latest key expires soon ({time_until_expiry:.1f}h remaining), "
                    "rotation needed"
                )
                return True

            logger.debug(
                f"Latest key still valid ({time_until_expiry:.1f}h remaining), "
                "rotation not needed"
            )
            return False

        except Exception as e:
            logger.error(f"Error checking rotation needed: {e}")
            # В случае ошибки лучше попробовать ротацию
            return True

    def get_rotation_status(self, session: Session) -> dict:
        """
        Получение статуса JWT key rotation.

        Args:
            session: Database session

        Returns:
            dict: Статус ротации с метриками

        Example:
            {
                "active_keys_count": 2,
                "latest_key_version": "a1b2c3d4-...",
                "latest_key_expires_at": "2025-11-16T16:00:00Z",
                "hours_until_expiry": 23.5,
                "rotation_needed": false
            }
        """
        try:
            active_keys = JWTKey.get_active_keys(session)
            latest_key = JWTKey.get_latest_active_key(session)

            if not latest_key:
                return {
                    "active_keys_count": 0,
                    "latest_key_version": None,
                    "latest_key_expires_at": None,
                    "hours_until_expiry": None,
                    "rotation_needed": True,
                    "error": "No active keys found"
                }

            now = datetime.now(timezone.utc)
            hours_until_expiry = (latest_key.expires_at - now).total_seconds() / 3600

            return {
                "active_keys_count": len(active_keys),
                "latest_key_version": latest_key.version,
                "latest_key_expires_at": latest_key.expires_at.isoformat(),
                "hours_until_expiry": round(hours_until_expiry, 2),
                "rotation_needed": hours_until_expiry < 1,
                "lock_status": self._check_lock_status()
            }

        except Exception as e:
            logger.error(f"Error getting rotation status: {e}")
            return {
                "error": str(e)
            }

    def _check_lock_status(self) -> dict:
        """
        Проверка статуса distributed lock.

        Returns:
            dict: Статус lock
        """
        try:
            lock_value = self.redis.get(self.LOCK_KEY)

            if lock_value:
                ttl = self.redis.ttl(self.LOCK_KEY)
                return {
                    "locked": True,
                    "ttl_seconds": ttl
                }
            else:
                return {
                    "locked": False
                }

        except RedisError as e:
            logger.error(f"Error checking lock status: {e}")
            return {
                "error": str(e)
            }

    def _record_rotation_metrics(
        self,
        success: bool,
        deactivated_count: int = 0,
        error: Optional[str] = None
    ) -> None:
        """
        Запись метрик ротации для Prometheus.

        Args:
            success: Успешность ротации
            deactivated_count: Количество деактивированных ключей
            error: Текст ошибки если ротация failed

        Note:
            Placeholder для будущей интеграции с Prometheus.
            Будет реализовано в Phase 2 с остальными metrics.
        """
        # TODO: Интеграция с Prometheus metrics
        # Пример будущей реализации:
        # from prometheus_client import Counter, Gauge
        #
        # jwt_rotation_total = Counter('jwt_rotation_total', 'Total JWT key rotations')
        # jwt_rotation_success = Counter('jwt_rotation_success', 'Successful JWT key rotations')
        # jwt_rotation_failed = Counter('jwt_rotation_failed', 'Failed JWT key rotations')
        # jwt_keys_deactivated = Counter('jwt_keys_deactivated', 'Deactivated JWT keys')
        #
        # jwt_rotation_total.inc()
        # if success:
        #     jwt_rotation_success.inc()
        #     jwt_keys_deactivated.inc(deactivated_count)
        # else:
        #     jwt_rotation_failed.inc()

        log_data = {
            "success": success,
            "deactivated_count": deactivated_count,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        if error:
            log_data["error"] = error

        logger.info("JWT rotation metrics recorded", extra=log_data)


# Singleton instance для использования в background tasks
_rotation_service: Optional[JWTKeyRotationService] = None


def get_rotation_service() -> JWTKeyRotationService:
    """
    Получение singleton instance JWTKeyRotationService.

    Returns:
        JWTKeyRotationService: Rotation service instance

    Example:
        service = get_rotation_service()
        success = service.rotate_keys(db_session)
    """
    global _rotation_service

    if _rotation_service is None:
        _rotation_service = JWTKeyRotationService()
        logger.info("JWT Key Rotation Service initialized")

    return _rotation_service
