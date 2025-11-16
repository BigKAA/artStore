"""
Prometheus Metrics для Admin Module.
Custom business metrics помимо стандартных HTTP metrics от OpenTelemetry.
"""

from prometheus_client import Counter, Gauge, Histogram
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# JWT KEY ROTATION METRICS
# ============================================================================

# Counter: Количество успешных ротаций ключей
jwt_rotation_total = Counter(
    "jwt_rotation_total",
    "Total number of JWT key rotations",
    ["status"]  # success, failed
)

# Gauge: Количество активных JWT ключей
jwt_active_keys_gauge = Gauge(
    "jwt_active_keys",
    "Number of active JWT keys in database"
)

# Gauge: Количество всего JWT ключей (включая деактивированные)
jwt_total_keys_gauge = Gauge(
    "jwt_total_keys",
    "Total number of JWT keys in database (active + inactive)"
)

# Histogram: Время выполнения ротации ключей (в секундах)
jwt_rotation_duration_seconds = Histogram(
    "jwt_rotation_duration_seconds",
    "Time taken to rotate JWT keys",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
)

# Gauge: Количество часов до истечения latest активного ключа
jwt_key_expiry_hours = Gauge(
    "jwt_key_expiry_hours",
    "Hours until the latest active JWT key expires"
)

# Counter: Количество попыток получения distributed lock для ротации
jwt_rotation_lock_attempts = Counter(
    "jwt_rotation_lock_attempts",
    "Number of attempts to acquire rotation lock",
    ["result"]  # acquired, failed, timeout
)


# ============================================================================
# AUTHENTICATION METRICS
# ============================================================================

# Counter: Количество попыток аутентификации
auth_attempts_total = Counter(
    "auth_attempts_total",
    "Total number of authentication attempts",
    ["type", "status"]  # type: user/service_account, status: success/failed
)

# Counter: Количество созданных токенов
tokens_created_total = Counter(
    "tokens_created_total",
    "Total number of JWT tokens created",
    ["token_type", "key_source"]  # token_type: access/refresh, key_source: database/file
)

# Counter: Количество валидаций токенов
token_validations_total = Counter(
    "token_validations_total",
    "Total number of token validation attempts",
    ["status", "key_source"]  # status: success/failed/expired, key_source: database/file/multiversion
)

# Histogram: Время создания токена (в секундах)
token_creation_duration_seconds = Histogram(
    "token_creation_duration_seconds",
    "Time taken to create JWT token",
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0]
)

# Histogram: Время валидации токена (в секундах)
token_validation_duration_seconds = Histogram(
    "token_validation_duration_seconds",
    "Time taken to validate JWT token",
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0]
)


# ============================================================================
# SERVICE ACCOUNT METRICS
# ============================================================================

# Gauge: Количество активных Service Accounts
service_accounts_active_gauge = Gauge(
    "service_accounts_active",
    "Number of active service accounts"
)

# Counter: Количество ротаций client secrets
service_account_secret_rotations_total = Counter(
    "service_account_secret_rotations_total",
    "Total number of service account secret rotations",
    ["status"]  # success, failed
)

# Counter: Количество истекших client secrets
service_account_expired_secrets_total = Counter(
    "service_account_expired_secrets_total",
    "Total number of expired service account secrets detected"
)


# ============================================================================
# SYSTEM METRICS
# ============================================================================

# Gauge: Redis connection status
redis_connection_status = Gauge(
    "redis_connection_status",
    "Redis connection status (1=connected, 0=disconnected)"
)

# Gauge: PostgreSQL connection status
postgres_connection_status = Gauge(
    "postgres_connection_status",
    "PostgreSQL connection status (1=connected, 0=disconnected)"
)

# Counter: Service Discovery events
service_discovery_events_total = Counter(
    "service_discovery_events_total",
    "Total number of service discovery events",
    ["event_type"]  # publish, subscribe, update, error
)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def record_jwt_rotation(success: bool, duration_seconds: float):
    """
    Запись метрик JWT key rotation.

    Args:
        success: Успешность ротации
        duration_seconds: Время выполнения в секундах
    """
    status = "success" if success else "failed"
    jwt_rotation_total.labels(status=status).inc()
    jwt_rotation_duration_seconds.observe(duration_seconds)
    logger.debug(f"Recorded JWT rotation: status={status}, duration={duration_seconds}s")


def update_jwt_keys_count(active_count: int, total_count: int):
    """
    Обновление счетчиков JWT ключей.

    Args:
        active_count: Количество активных ключей
        total_count: Общее количество ключей
    """
    jwt_active_keys_gauge.set(active_count)
    jwt_total_keys_gauge.set(total_count)
    logger.debug(f"Updated JWT keys count: active={active_count}, total={total_count}")


def update_jwt_key_expiry(hours_until_expiry: float):
    """
    Обновление времени до истечения latest ключа.

    Args:
        hours_until_expiry: Часы до истечения
    """
    jwt_key_expiry_hours.set(hours_until_expiry)
    logger.debug(f"Updated JWT key expiry: {hours_until_expiry} hours")


def record_rotation_lock_attempt(result: str):
    """
    Запись попытки получения distributed lock.

    Args:
        result: Результат попытки (acquired, failed, timeout)
    """
    jwt_rotation_lock_attempts.labels(result=result).inc()
    logger.debug(f"Recorded rotation lock attempt: result={result}")


def record_auth_attempt(auth_type: str, success: bool):
    """
    Запись попытки аутентификации.

    Args:
        auth_type: Тип аутентификации (user, service_account)
        success: Успешность аутентификации
    """
    status = "success" if success else "failed"
    auth_attempts_total.labels(type=auth_type, status=status).inc()
    logger.debug(f"Recorded auth attempt: type={auth_type}, status={status}")


def record_token_created(token_type: str, key_source: str, duration_seconds: float):
    """
    Запись создания токена.

    Args:
        token_type: Тип токена (access, refresh)
        key_source: Источник ключа (database, file)
        duration_seconds: Время создания в секундах
    """
    tokens_created_total.labels(token_type=token_type, key_source=key_source).inc()
    token_creation_duration_seconds.observe(duration_seconds)
    logger.debug(
        f"Recorded token creation: type={token_type}, source={key_source}, "
        f"duration={duration_seconds}s"
    )


def record_token_validation(status: str, key_source: str, duration_seconds: float):
    """
    Запись валидации токена.

    Args:
        status: Статус валидации (success, failed, expired)
        key_source: Источник ключа (database, file, multiversion)
        duration_seconds: Время валидации в секундах
    """
    token_validations_total.labels(status=status, key_source=key_source).inc()
    token_validation_duration_seconds.observe(duration_seconds)
    logger.debug(
        f"Recorded token validation: status={status}, source={key_source}, "
        f"duration={duration_seconds}s"
    )


def update_service_accounts_count(active_count: int):
    """
    Обновление количества активных Service Accounts.

    Args:
        active_count: Количество активных Service Accounts
    """
    service_accounts_active_gauge.set(active_count)
    logger.debug(f"Updated service accounts count: {active_count}")


def record_secret_rotation(success: bool):
    """
    Запись ротации client secret.

    Args:
        success: Успешность ротации
    """
    status = "success" if success else "failed"
    service_account_secret_rotations_total.labels(status=status).inc()
    logger.debug(f"Recorded secret rotation: status={status}")


def record_expired_secret():
    """Запись обнаружения истекшего client secret."""
    service_account_expired_secrets_total.inc()
    logger.debug("Recorded expired secret detection")


def update_redis_status(connected: bool):
    """
    Обновление статуса подключения к Redis.

    Args:
        connected: Статус подключения
    """
    redis_connection_status.set(1 if connected else 0)
    logger.debug(f"Updated Redis status: {'connected' if connected else 'disconnected'}")


def update_postgres_status(connected: bool):
    """
    Обновление статуса подключения к PostgreSQL.

    Args:
        connected: Статус подключения
    """
    postgres_connection_status.set(1 if connected else 0)
    logger.debug(f"Updated Postgres status: {'connected' if connected else 'disconnected'}")


def record_service_discovery_event(event_type: str):
    """
    Запись Service Discovery события.

    Args:
        event_type: Тип события (publish, subscribe, update, error)
    """
    service_discovery_events_total.labels(event_type=event_type).inc()
    logger.debug(f"Recorded service discovery event: {event_type}")
