"""
Ingester Module - Configuration Management.

Centralized конфигурация с приоритетом environment variables над config файлом.
"""

from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def parse_bool_from_env(v) -> bool:
    """
    Парсинг boolean значения из формата on/off.

    Поддерживаемые форматы:
    - on/off (единственный допустимый)
    - Python bool (для внутреннего использования)

    Args:
        v: Значение для парсинга (str, bool)

    Returns:
        bool: Распарсенное boolean значение

    Raises:
        ValueError: Если значение невалидно
    """
    if isinstance(v, bool):
        return v

    if isinstance(v, str):
        v_lower = v.lower().strip()

        if v_lower == "on":
            return True
        if v_lower == "off":
            return False

    raise ValueError(
        f"Невалидное boolean значение: '{v}'. "
        f"Допустимые значения: on/off"
    )


class LogLevel(str, Enum):
    """Уровни логирования."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogFormat(str, Enum):
    """Форматы логирования."""
    JSON = "json"
    TEXT = "text"


class AppSettings(BaseSettings):
    """Настройки приложения."""

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        case_sensitive=False
    )

    name: str = "artstore-ingester"
    version: str = "0.1.0"
    debug: bool = False
    swagger_enabled: bool = False  # Production-first: Swagger отключен по умолчанию
    host: str = "0.0.0.0"
    port: int = 8020

    @field_validator("debug", "swagger_enabled", mode="before")
    @classmethod
    def parse_bool_fields(cls, v):
        """Парсинг boolean полей из environment variables."""
        return parse_bool_from_env(v)


class AuthSettings(BaseSettings):
    """Настройки аутентификации."""

    model_config = SettingsConfigDict(
        env_prefix="AUTH_",
        case_sensitive=False
    )

    enabled: bool = True
    public_key_path: Path = Path("./keys/public_key.pem")
    algorithm: str = "RS256"

    # Sprint 16: Admin Module URL для health checks и Service Discovery fallback
    admin_module_url: str = Field(
        default="http://admin-module:8000",
        description="URL Admin Module для health checks и Service Discovery fallback"
    )

    @field_validator("enabled", mode="before")
    @classmethod
    def parse_bool_fields(cls, v):
        """Парсинг boolean полей из environment variables."""
        return parse_bool_from_env(v)


class StorageElementSettings(BaseSettings):
    """
    HTTP client настройки для взаимодействия со Storage Elements.

    Sprint 16: base_url УДАЛЁН - endpoints получаются через Service Discovery.

    Endpoints выбираются динамически через:
    1. Redis Service Discovery (primary)
    2. Admin Module API (fallback)

    Эти настройки применяются к HTTP клиентам для всех SE endpoints.
    """

    model_config = SettingsConfigDict(
        env_prefix="STORAGE_ELEMENT_",
        case_sensitive=False
    )

    # Sprint 16: base_url УДАЛЁН - Service Discovery обязателен
    # Используйте StorageSelector для получения SE endpoints

    timeout: int = Field(
        default=30,
        description="HTTP request timeout в секундах"
    )
    max_retries: int = Field(
        default=3,
        description="Максимальное количество retry при ошибках"
    )
    connection_pool_size: int = Field(
        default=100,
        description="Размер HTTP connection pool для каждого SE endpoint"
    )


class RedisSettings(BaseSettings):
    """
    Настройки Redis для Service Discovery и Storage Registry.

    Sprint 14: Async Redis клиент для получения списка доступных SE.
    """

    model_config = SettingsConfigDict(
        env_prefix="REDIS_",
        case_sensitive=False
    )

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    pool_size: int = Field(default=10, alias="REDIS_POOL_SIZE")
    socket_timeout: float = Field(default=5.0, alias="REDIS_SOCKET_TIMEOUT")
    socket_connect_timeout: float = Field(default=5.0, alias="REDIS_SOCKET_CONNECT_TIMEOUT")

    # Circuit breaker настройки
    failure_threshold: int = Field(default=5, alias="REDIS_FAILURE_THRESHOLD")
    recovery_timeout: int = Field(default=60, alias="REDIS_RECOVERY_TIMEOUT")
    half_open_max_calls: int = Field(default=3, alias="REDIS_HALF_OPEN_MAX_CALLS")

    @property
    def url(self) -> str:
        """
        Формирование Redis URL.

        Returns:
            str: Redis URL в формате redis://[:password@]host:port/db
        """
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"


class CompressionSettings(BaseSettings):
    """Настройки сжатия файлов."""

    model_config = SettingsConfigDict(
        env_prefix="COMPRESSION_",
        case_sensitive=False
    )

    enabled: bool = True
    algorithm: str = "gzip"  # gzip или brotli
    level: int = 6  # 1-9 для gzip, 0-11 для brotli
    min_size: int = 1024  # Минимальный размер файла для сжатия (bytes)

    @field_validator("enabled", mode="before")
    @classmethod
    def parse_bool_fields(cls, v):
        """Парсинг boolean полей из environment variables."""
        return parse_bool_from_env(v)


class LoggingSettings(BaseSettings):
    """Настройки логирования."""

    model_config = SettingsConfigDict(
        env_prefix="LOG_",
        case_sensitive=False
    )

    level: LogLevel = LogLevel.INFO
    format: LogFormat = LogFormat.JSON
    file: Optional[Path] = None


class CapacityMonitorSettings(BaseSettings):
    """
    Настройки AdaptiveCapacityMonitor для geo-distributed capacity management.

    Sprint 17: HTTP polling к Storage Elements с Redis Leader Election.

    Leader Election:
    - Только 1 Ingester (LEADER) выполняет polling
    - Остальные (FOLLOWERS) читают из shared Redis cache
    - Automatic failover при падении Leader (TTL-based)

    Polling:
    - HTTP GET /api/v1/capacity к каждому SE
    - Exponential backoff при ошибках
    - Adaptive интервалы при стабильности/изменениях
    """

    model_config = SettingsConfigDict(
        env_prefix="CAPACITY_MONITOR_",
        case_sensitive=False
    )

    enabled: bool = Field(
        default=True,
        description="Включить Capacity Monitor (для geo-distributed SE)"
    )

    # Leader Election
    leader_lock_key: str = Field(
        default="capacity_monitor:leader_lock",
        description="Redis key для Leader lock"
    )
    leader_ttl: int = Field(
        default=30,
        description="TTL Leader lock в секундах"
    )
    leader_renewal_interval: int = Field(
        default=10,
        description="Интервал продления Leader lock в секундах"
    )

    # Polling intervals
    base_interval: int = Field(
        default=30,
        description="Базовый интервал polling в секундах"
    )
    max_interval: int = Field(
        default=300,
        description="Максимальный интервал polling (adaptive) в секундах"
    )
    min_interval: int = Field(
        default=10,
        description="Минимальный интервал polling в секундах"
    )

    # HTTP client
    http_timeout: int = Field(
        default=15,
        description="HTTP timeout для polling в секундах"
    )
    http_retries: int = Field(
        default=3,
        description="Количество retry при ошибках polling"
    )
    retry_base_delay: float = Field(
        default=2.0,
        description="Базовая задержка для exponential backoff в секундах"
    )

    # Cache TTL
    cache_ttl: int = Field(
        default=600,
        description="TTL для capacity cache в секундах"
    )
    health_ttl: int = Field(
        default=600,
        description="TTL для health cache в секундах"
    )

    # Circuit breaker
    failure_threshold: int = Field(
        default=3,
        description="Количество failures до пометки SE как unhealthy"
    )
    recovery_threshold: int = Field(
        default=2,
        description="Количество successes для восстановления SE"
    )

    # Adaptive logic
    stability_threshold: int = Field(
        default=5,
        description="Polls без изменений для увеличения интервала"
    )
    change_threshold: float = Field(
        default=5.0,
        description="Процент изменения capacity для уменьшения интервала"
    )

    # Sprint 18 Phase 3: Parallel Run configuration
    use_for_selection: bool = Field(
        default=True,
        description="Использовать AdaptiveCapacityMonitor как источник в StorageSelector"
    )
    fallback_to_push: bool = Field(
        default=True,
        description="Fallback на Redis PUSH модель если POLLING недоступен"
    )

    @field_validator("enabled", "use_for_selection", "fallback_to_push", mode="before")
    @classmethod
    def parse_bool_fields(cls, v):
        """Парсинг boolean полей из environment variables."""
        return parse_bool_from_env(v)


class CORSSettings(BaseSettings):
    """
    Настройки CORS для защиты от CSRF attacks.

    CORS (Cross-Origin Resource Sharing) защищает от unauthorized cross-origin requests.
    Sprint 16 Phase 1: Enhanced CORS configuration для production security.

    Security considerations:
    - Wildcard origins (*) запрещены в production
    - Wildcard headers (*) НЕ рекомендуются, используйте explicit list
    - allow_credentials требует explicit origins (не wildcard)
    - max_age кеширует preflight requests для performance
    """

    model_config = SettingsConfigDict(
        env_prefix="CORS_",
        case_sensitive=False
    )

    enabled: bool = True
    allow_origins: list[str] = Field(
        default=["http://localhost:4200", "http://localhost:8000"],
        description="Whitelist разрешенных origins. Production: explicit domains только!"
    )
    allow_credentials: bool = Field(
        default=True,
        description="Разрешить credentials (cookies, authorization headers). Requires explicit origins."
    )
    allow_methods: list[str] = Field(
        default=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        description="Разрешенные HTTP methods"
    )
    allow_headers: list[str] = Field(
        default=["Content-Type", "Authorization", "X-Request-ID", "X-Trace-ID"],
        description="Разрешенные request headers. Production: explicit list вместо wildcard!"
    )
    expose_headers: list[str] = Field(
        default=[],
        description="Headers, которые будут exposed в browser (e.g., Content-Length, Content-Range)"
    )
    max_age: int = Field(
        default=600,
        description="Preflight cache duration в seconds (default: 10 minutes)"
    )

    @field_validator("enabled", "allow_credentials", mode="before")
    @classmethod
    def parse_bool_fields(cls, v):
        """Парсинг boolean полей из environment variables."""
        return parse_bool_from_env(v)

    @field_validator("allow_origins")
    @classmethod
    def validate_no_wildcards_in_production(cls, v: list[str]) -> list[str]:
        """
        Проверка запрета wildcard origins в production окружении.

        Security requirement: CORS wildcards (*) запрещены в production
        для защиты от CSRF attacks.

        Raises:
            ValueError: Если wildcard origin в production environment
        """
        import os

        if "*" in v:
            environment = os.getenv("ENVIRONMENT", "development")
            if environment == "production":
                raise ValueError(
                    "Wildcard CORS origins ('*') are not allowed in production environment. "
                    "Please configure explicit origin whitelist via CORS_ALLOW_ORIGINS. "
                    "Example: CORS_ALLOW_ORIGINS=[\"https://admin.artstore.com\",\"https://ingester.artstore.com\"]"
                )
        return v

    @field_validator("allow_headers")
    @classmethod
    def warn_wildcard_headers(cls, v: list[str]) -> list[str]:
        """
        Warning для wildcard headers в любом environment.

        Wildcard headers (*) функционально работают, но не рекомендуются для security.
        Explicit header list provides better security и clearer configuration.

        Note: Не блокируем wildcard headers (backward compatibility),
        но логируем warning для production awareness.
        """
        import os
        import logging

        if "*" in v:
            logger = logging.getLogger(__name__)
            environment = os.getenv("ENVIRONMENT", "development")

            if environment == "production":
                logger.warning(
                    "CORS wildcard headers ('*') detected in production. "
                    "Consider explicit header whitelist for better security: "
                    "CORS_ALLOW_HEADERS=[\"Content-Type\",\"Authorization\",\"X-Request-ID\"]"
                )
            else:
                logger.info(
                    "CORS wildcard headers ('*') detected. "
                    "For production, use explicit header list."
                )

        return v

    @field_validator("allow_credentials", mode="after")
    @classmethod
    def validate_credentials_requires_explicit_origins(cls, v: bool, info) -> bool:
        """
        Валидация: allow_credentials требует explicit origins (не wildcard).

        CORS spec requirement: Credentials mode несовместим с wildcard origins.
        Browser отклонит такую configuration.

        Raises:
            ValueError: Если allow_credentials=True с wildcard origin
        """
        # Access other field via validation_context
        allow_origins = info.data.get("allow_origins", [])

        if v and "*" in allow_origins:
            raise ValueError(
                "CORS allow_credentials=True cannot be used with wildcard origins ('*'). "
                "This violates CORS specification. "
                "Either set allow_credentials=False OR use explicit origin whitelist."
            )

        return v


class ServiceAccountSettings(BaseSettings):
    """
    OAuth 2.0 Service Account configuration для machine-to-machine аутентификации.

    Service Account используется для получения JWT токенов от Admin Module,
    которые затем используются для аутентификации запросов в Storage Element.

    Configuration (ОБЯЗАТЕЛЬНЫЕ параметры):
        SERVICE_ACCOUNT_CLIENT_ID=sa_prod_ingester_module_11cafd4f
        SERVICE_ACCOUNT_CLIENT_SECRET=:hC%=#>a9q,GwunR
        SERVICE_ACCOUNT_ADMIN_MODULE_URL=http://artstore_admin_module:8000

    Security:
    - client_secret должен храниться в защищенной конфигурации (secrets management)
    - НЕ коммитить client_secret в git
    - Использовать environment variables или Docker secrets
    - В production использовать secret rotation каждые 90 дней
    """
    model_config = SettingsConfigDict(
        env_prefix="SERVICE_ACCOUNT_",
        case_sensitive=False
    )

    client_id: str = Field(
        description="Service Account Client ID от Admin Module"
    )
    client_secret: str = Field(
        description="Service Account Client Secret от Admin Module"
    )
    admin_module_url: str = Field(
        default="http://artstore_admin_module:8000",
        description="URL Admin Module для OAuth 2.0 token requests"
    )
    timeout: int = Field(
        default=10,
        description="HTTP request timeout в секундах"
    )


class Settings(BaseSettings):
    """Главный класс настроек Ingester Module."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    app: AppSettings = Field(default_factory=AppSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    service_account: ServiceAccountSettings = Field(default_factory=ServiceAccountSettings)
    storage_element: StorageElementSettings = Field(default_factory=StorageElementSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    compression: CompressionSettings = Field(default_factory=CompressionSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    cors: CORSSettings = Field(default_factory=CORSSettings)
    capacity_monitor: CapacityMonitorSettings = Field(default_factory=CapacityMonitorSettings)


# Singleton instance
settings = Settings()
