"""
Конфигурация приложения Storage Element через Pydantic Settings.

Приоритет настроек:
1. Environment variables (высший приоритет)
2. config.yaml файл
3. Значения по умолчанию
"""

from enum import Enum
from pathlib import Path
from typing import Literal, Optional

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


class StorageMode(str, Enum):
    """Режимы работы Storage Element"""
    EDIT = "edit"  # Полный CRUD
    RW = "rw"      # Read-Write без удаления
    RO = "ro"      # Read-Only
    AR = "ar"      # Archive (только метаданные)


class StorageType(str, Enum):
    """Типы физического хранилища"""
    LOCAL = "local"
    S3 = "s3"


class LogFormat(str, Enum):
    """Форматы логирования"""
    JSON = "json"  # Production
    TEXT = "text"  # Development


class AppSettings(BaseSettings):
    """Настройки приложения"""
    model_config = SettingsConfigDict(
        env_prefix="APP_",
        case_sensitive=False
    )

    name: str = "storage-element"
    display_name: str = "Storage Element"  # Читаемое имя для auto-discovery
    version: str = "1.0.0"
    debug: bool = False
    swagger_enabled: bool = False
    mode: StorageMode = StorageMode.RW
    rebuild_cache_on_startup: bool = False

    @field_validator("debug", "swagger_enabled", "rebuild_cache_on_startup", mode="before")
    @classmethod
    def parse_bool_fields(cls, v):
        """Парсинг boolean полей из environment variables."""
        return parse_bool_from_env(v)


class ServerSettings(BaseSettings):
    """Настройки веб-сервера"""
    model_config = SettingsConfigDict(
        env_prefix="SERVER_",
        case_sensitive=False
    )

    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1
    reload: bool = False  # Hot reload для development

    @field_validator("reload", mode="before")
    @classmethod
    def parse_bool_fields(cls, v):
        """Парсинг boolean полей из environment variables."""
        return parse_bool_from_env(v)


class DatabaseSettings(BaseSettings):
    """Настройки PostgreSQL"""
    model_config = SettingsConfigDict(
        env_prefix="DB_",
        case_sensitive=False
    )

    host: str = "localhost"
    port: int = 5432
    username: str = "artstore"
    password: str = "password"
    database: str = "artstore_storage_01"

    # Connection pooling
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30
    pool_recycle: int = 3600

    # Префикс таблиц для уникальности
    table_prefix: str = "storage_elem_01"

    # SSL Configuration
    ssl_enabled: bool = Field(
        default=False,
        alias="SSL_ENABLED",
        description="Enable SSL for PostgreSQL connection"
    )
    ssl_mode: str = Field(
        default="require",
        alias="SSL_MODE",
        description="SSL mode: disable, allow, prefer, require, verify-ca, verify-full"
    )
    ssl_ca_cert: Optional[str] = Field(
        default=None,
        alias="SSL_CA_CERT",
        description="Path to CA certificate file for SSL verification"
    )
    ssl_client_cert: Optional[str] = Field(
        default=None,
        alias="SSL_CLIENT_CERT",
        description="Path to client certificate file for SSL"
    )
    ssl_client_key: Optional[str] = Field(
        default=None,
        alias="SSL_CLIENT_KEY",
        description="Path to client private key file for SSL"
    )

    @field_validator("ssl_enabled", mode="before")
    @classmethod
    def parse_bool_fields(cls, v):
        """Парсинг boolean полей из environment variables."""
        return parse_bool_from_env(v)

    @field_validator("ssl_mode")
    @classmethod
    def validate_ssl_mode(cls, v: str) -> str:
        """Валидация SSL mode"""
        valid_modes = ["disable", "allow", "prefer", "require", "verify-ca", "verify-full"]
        if v not in valid_modes:
            raise ValueError(
                f"Invalid DB_SSL_MODE: {v}. "
                f"Valid modes: {', '.join(valid_modes)}"
            )
        return v

    @property
    def url(self) -> str:
        """Формирование Database URL для SQLAlchemy"""
        base_url = f"postgresql+asyncpg://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"

        if self.ssl_enabled:
            ssl_params = []
            ssl_params.append(f"ssl={self.ssl_mode}")

            if self.ssl_ca_cert:
                ssl_params.append(f"sslrootcert={self.ssl_ca_cert}")

            if self.ssl_client_cert:
                ssl_params.append(f"sslcert={self.ssl_client_cert}")

            if self.ssl_client_key:
                ssl_params.append(f"sslkey={self.ssl_client_key}")

            if ssl_params:
                base_url += "?" + "&".join(ssl_params)

        return base_url


class RedisSettings(BaseSettings):
    """Настройки Redis для Service Discovery, Master Election и Health Reporting"""
    model_config = SettingsConfigDict(
        env_prefix="REDIS_",
        case_sensitive=False
    )

    # Standalone mode (для development)
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None

    # Connection pool
    pool_size: int = 10
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0

    # Master Election настройки
    master_key_prefix: str = "storage_master"
    master_ttl: int = 30  # Время жизни ключа мастера в секундах
    master_check_interval: int = 10  # Интервал проверки статуса мастера

    # Circuit Breaker для Redis failover
    failure_threshold: int = 5
    recovery_timeout: int = 60
    half_open_max_calls: int = 3

    @property
    def url(self) -> str:
        """Формирование Redis URL для aioredis"""
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"


class LocalStorageSettings(BaseSettings):
    """Настройки локального хранилища"""
    model_config = SettingsConfigDict(
        env_prefix="STORAGE_LOCAL_",
        case_sensitive=False
    )

    base_path: Path = Path("./.data/storage")

    @field_validator("base_path", mode="before")
    @classmethod
    def validate_base_path(cls, v):
        """Преобразование строки в Path"""
        if isinstance(v, str):
            return Path(v)
        return v


class S3StorageSettings(BaseSettings):
    """Настройки S3 хранилища (MinIO)"""
    model_config = SettingsConfigDict(
        env_prefix="STORAGE_S3_",
        case_sensitive=False
    )

    endpoint_url: str = "http://localhost:9000"
    access_key_id: str = "minioadmin"
    secret_access_key: str = "minioadmin"
    bucket_name: str = "artstore-files"
    region: str = "us-east-1"
    app_folder: str = "storage_element_01"

    # Soft capacity limit для S3 (байты)
    # S3 практически unlimited, используем soft limit для capacity management
    soft_capacity_limit: int = Field(
        default=10 * 1024 * 1024 * 1024 * 1024,  # 10 TB
        alias="STORAGE_S3_SOFT_CAPACITY_LIMIT",
        description="Soft capacity limit для S3 хранилища в байтах"
    )


class StorageSettings(BaseSettings):
    """Общие настройки хранилища"""
    model_config = SettingsConfigDict(
        env_prefix="STORAGE_",
        case_sensitive=False
    )

    type: StorageType = StorageType.LOCAL
    max_size_gb: int = 1  # Максимальный размер в гигабайтах

    # Sub-settings
    local: LocalStorageSettings = Field(default_factory=LocalStorageSettings)
    s3: S3StorageSettings = Field(default_factory=S3StorageSettings)

    # Health Reporting Settings (Sprint 14)
    # Уникальный идентификатор Storage Element для Redis registry
    element_id: str = Field(
        default="se-local-01",
        alias="STORAGE_ELEMENT_ID",
        description="Уникальный ID Storage Element для Redis registry"
    )
    # Приоритет для Sequential Fill алгоритма (меньше = выше приоритет)
    priority: int = Field(
        default=100,
        alias="STORAGE_PRIORITY",
        description="Приоритет SE для выбора (меньше = выше приоритет)"
    )
    # Внешний URL для доступа к этому SE из других сервисов
    external_endpoint: str = Field(
        default="http://localhost:8010",
        alias="STORAGE_EXTERNAL_ENDPOINT",
        description="Внешний URL этого SE для доступа из Ingester/Query"
    )
    # Географическое расположение (datacenter location)
    datacenter_location: str = Field(
        default="dc1",
        alias="STORAGE_DATACENTER_LOCATION",
        description="Географическое расположение Storage Element (dc1, dc2, etc.)"
    )
    # Интервал публикации статуса в Redis (секунды)
    health_report_interval: int = Field(
        default=30,
        alias="HEALTH_REPORT_INTERVAL",
        ge=5,
        le=300,
        description="Интервал публикации health status в Redis (5-300 секунд)"
    )
    # Множитель TTL для Redis ключей (TTL = interval * multiplier)
    health_report_ttl_multiplier: int = Field(
        default=3,
        alias="HEALTH_REPORT_TTL_MULTIPLIER",
        ge=2,
        le=10,
        description="Множитель для TTL Redis ключей (TTL = interval * multiplier)"
    )

    # Adaptive Capacity Thresholds (опциональные override для тестирования)
    # Если заданы - используются вместо автоматического расчёта
    # Значения в процентах заполнения (0-100)
    capacity_warning_threshold: Optional[float] = Field(
        default=None,
        alias="CAPACITY_WARNING_THRESHOLD",
        ge=0,
        le=100,
        description="Override для WARNING порога (% заполнения). None = автоматический расчёт"
    )
    capacity_critical_threshold: Optional[float] = Field(
        default=None,
        alias="CAPACITY_CRITICAL_THRESHOLD",
        ge=0,
        le=100,
        description="Override для CRITICAL порога (% заполнения). None = автоматический расчёт"
    )
    capacity_full_threshold: Optional[float] = Field(
        default=None,
        alias="CAPACITY_FULL_THRESHOLD",
        ge=0,
        le=100,
        description="Override для FULL порога (% заполнения). None = автоматический расчёт"
    )

    def get_capacity_thresholds_override(self) -> Optional[dict]:
        """
        Возвращает override пороги, если все три заданы.

        Returns:
            dict с порогами или None если используется автоматический расчёт
        """
        if (self.capacity_warning_threshold is not None and
            self.capacity_critical_threshold is not None and
            self.capacity_full_threshold is not None):
            return {
                "warning_threshold": self.capacity_warning_threshold,
                "critical_threshold": self.capacity_critical_threshold,
                "full_threshold": self.capacity_full_threshold,
                # Для override режима free_gb не используются
                "warning_free_gb": 0,
                "critical_free_gb": 0,
                "full_free_gb": 0,
            }
        return None

    @property
    def max_size_bytes(self) -> int:
        """Максимальный размер в байтах"""
        return self.max_size_gb * 1024 * 1024 * 1024

    @property
    def health_report_ttl(self) -> int:
        """TTL для Redis ключей в секундах"""
        return self.health_report_interval * self.health_report_ttl_multiplier

    @property
    def local_storage_path(self) -> Path:
        """Путь к локальному хранилищу (для совместимости)"""
        return self.local.base_path


class JWTSettings(BaseSettings):
    """Настройки JWT аутентификации"""
    model_config = SettingsConfigDict(
        env_prefix="JWT_",
        case_sensitive=False
    )

    public_key_path: Optional[str] = None
    algorithm: str = "RS256"

    @field_validator("public_key_path")
    @classmethod
    def validate_public_key_path(cls, v):
        """Валидация пути к публичному ключу"""
        if v and not Path(v).exists():
            raise ValueError(f"JWT public key not found at: {v}")
        return v


class LoggingSettings(BaseSettings):
    """Настройки логирования"""
    model_config = SettingsConfigDict(
        env_prefix="LOG_",
        case_sensitive=False
    )

    level: str = "INFO"
    format: LogFormat = LogFormat.JSON  # JSON по умолчанию для production
    file_path: Optional[Path] = None
    max_bytes: int = 104857600  # 100MB
    backup_count: int = 5


class MetricsSettings(BaseSettings):
    """Настройки Prometheus метрик"""
    model_config = SettingsConfigDict(
        env_prefix="METRICS_",
        case_sensitive=False
    )

    enabled: bool = True
    path: str = "/metrics"

    @field_validator("enabled", mode="before")
    @classmethod
    def parse_bool_fields(cls, v):
        """Парсинг boolean полей из environment variables."""
        return parse_bool_from_env(v)


class HealthSettings(BaseSettings):
    """Настройки health checks"""
    model_config = SettingsConfigDict(
        env_prefix="HEALTH_",
        case_sensitive=False
    )

    liveness_path: str = "/health/live"
    readiness_path: str = "/health/ready"


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
                    "Example: CORS_ALLOW_ORIGINS=[\"https://admin.artstore.com\",\"https://storage.artstore.com\"]"
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


class Settings(BaseSettings):
    """
    Главная конфигурация Storage Element.

    Загружается из:
    1. Environment variables (приоритет)
    2. config.yaml файл (опционально)
    3. Defaults
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_nested_delimiter="__"  # Для чтения вложенных settings: APP__SWAGGER_ENABLED -> app.swagger_enabled
    )

    # Вложенные настройки
    app: AppSettings = Field(default_factory=AppSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    jwt: JWTSettings = Field(default_factory=JWTSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    metrics: MetricsSettings = Field(default_factory=MetricsSettings)
    health: HealthSettings = Field(default_factory=HealthSettings)
    cors: CORSSettings = Field(default_factory=CORSSettings)

    # WAL настройки
    wal_dir: Path = Path("./.data/wal")

    @field_validator("wal_dir", mode="before")
    @classmethod
    def validate_wal_dir(cls, v):
        """Преобразование строки в Path"""
        if isinstance(v, str):
            return Path(v)
        return v


# Глобальный экземпляр настроек
settings = Settings()


def get_config() -> Settings:
    """
    Получить глобальный экземпляр настроек.

    Returns:
        Settings: Глобальная конфигурация приложения
    """
    return settings
