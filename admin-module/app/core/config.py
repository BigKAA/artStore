"""
Конфигурация приложения Admin Module.
Использует Pydantic Settings для загрузки из config.yaml и environment variables.
Environment variables имеют приоритет над config.yaml.
"""

from typing import Optional, List, Dict, Any
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml
from pathlib import Path


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


class DatabaseSettings(BaseSettings):
    """Настройки подключения к PostgreSQL."""

    host: str = Field(default="localhost", alias="DB_HOST")
    port: int = Field(default=5432, alias="DB_PORT")
    username: str = Field(default="artstore", alias="DB_USERNAME")
    password: str = Field(default="password", alias="DB_PASSWORD")
    database: str = Field(default="artstore_admin", alias="DB_DATABASE")
    pool_size: int = Field(default=10, alias="DB_POOL_SIZE")
    max_overflow: int = Field(default=20, alias="DB_MAX_OVERFLOW")
    echo: bool = Field(default=False, alias="DB_ECHO")

    # SSL Configuration
    ssl_enabled: bool = Field(
        default=False,
        alias="DB_SSL_ENABLED",
        description="Enable SSL for PostgreSQL connection"
    )
    ssl_mode: str = Field(
        default="require",
        alias="DB_SSL_MODE",
        description="SSL mode: disable, allow, prefer, require, verify-ca, verify-full"
    )
    ssl_ca_cert: Optional[str] = Field(
        default=None,
        alias="DB_SSL_CA_CERT",
        description="Path to CA certificate file for SSL verification"
    )
    ssl_client_cert: Optional[str] = Field(
        default=None,
        alias="DB_SSL_CLIENT_CERT",
        description="Path to client certificate file for SSL"
    )
    ssl_client_key: Optional[str] = Field(
        default=None,
        alias="DB_SSL_CLIENT_KEY",
        description="Path to client private key file for SSL"
    )

    model_config = SettingsConfigDict(env_prefix="DB_", case_sensitive=False, extra="allow")

    @field_validator("echo", "ssl_enabled", mode="before")
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
        """Построение database URL для SQLAlchemy (async)."""
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

    @property
    def sync_url(self) -> str:
        """Построение database URL для Alembic (sync)."""
        base_url = f"postgresql+psycopg2://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"

        if self.ssl_enabled:
            ssl_params = []
            ssl_params.append(f"sslmode={self.ssl_mode}")

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
    """Настройки подключения к Redis."""

    # Прямой URL (высший приоритет)
    url_override: Optional[str] = Field(default=None, alias="REDIS_URL")

    # Компоненты URL (используются если url_override не задан)
    host: str = Field(default="localhost", alias="REDIS_HOST")
    port: int = Field(default=6379, alias="REDIS_PORT")
    password: Optional[str] = Field(default=None, alias="REDIS_PASSWORD")
    db: int = Field(default=0, alias="REDIS_DB")
    pool_size: int = Field(default=10, alias="REDIS_POOL_SIZE")
    socket_timeout: int = Field(default=5, alias="REDIS_SOCKET_TIMEOUT")
    socket_connect_timeout: int = Field(default=5, alias="REDIS_SOCKET_CONNECT_TIMEOUT")

    model_config = SettingsConfigDict(env_prefix="REDIS_", case_sensitive=False, extra="allow")

    @property
    def url(self) -> str:
        """
        Построение Redis URL.

        Приоритет: REDIS_URL > построение из компонентов (host/port/db)
        """
        # Если задан прямой URL - используем его
        if self.url_override:
            return self.url_override

        # Иначе строим из компонентов
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"


class JWTSettings(BaseSettings):
    """
    Настройки JWT аутентификации с Platform-Agnostic Secret Management.

    JWT ключи могут быть загружены из:
    1. Kubernetes Secrets (полное PEM содержимое)
    2. Environment Variables (путь к файлу или PEM содержимое)
    3. File-based secrets (путь к файлу)

    Приоритет: k8s → env → file → default path
    """

    algorithm: str = Field(default="RS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=30, alias="JWT_ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(default=7, alias="JWT_REFRESH_TOKEN_EXPIRE_DAYS")
    private_key_path: str = Field(default=".keys/private_key.pem", alias="JWT_PRIVATE_KEY_PATH")
    public_key_path: str = Field(default=".keys/public_key.pem", alias="JWT_PUBLIC_KEY_PATH")
    key_rotation_hours: int = Field(default=24, alias="JWT_KEY_ROTATION_HOURS")

    model_config = SettingsConfigDict(env_prefix="JWT_", case_sensitive=False, extra="allow")

    @field_validator("private_key_path", mode="before")
    @classmethod
    def load_private_key_from_provider(cls, v: str) -> str:
        """
        Загрузка private key через SecretProvider с fallback chain.

        Порядок загрузки:
        1. Kubernetes Secret JWT_PRIVATE_KEY (полное PEM содержимое)
        2. Environment Variable JWT_PRIVATE_KEY или JWT_PRIVATE_KEY_PATH
        3. File-based secret (если ./secrets/ существует)
        4. Provided value (default path)

        Returns:
            str: File path или PEM content (TokenService определяет тип)

        Example (Kubernetes):
            # k8s Secret с полным PEM содержимым:
            apiVersion: v1
            kind: Secret
            metadata:
              name: artstore-jwt-keys
            stringData:
              JWT_PRIVATE_KEY: |
                -----BEGIN RSA PRIVATE KEY-----
                MIIEpAIBAAKCAQEA...
                -----END RSA PRIVATE KEY-----
        """
        # Lazy import для избежания circular dependency
        from app.core.secrets import get_secret

        # Пробуем загрузить из SecretProvider
        secret_from_provider = get_secret("JWT_PRIVATE_KEY")

        if secret_from_provider:
            return secret_from_provider

        # Fallback на provided value (env path или default)
        return v if v else ".keys/private_key.pem"

    @field_validator("public_key_path", mode="before")
    @classmethod
    def load_public_key_from_provider(cls, v: str) -> str:
        """
        Загрузка public key через SecretProvider с fallback chain.

        Порядок загрузки:
        1. Kubernetes Secret JWT_PUBLIC_KEY (полное PEM содержимое)
        2. Environment Variable JWT_PUBLIC_KEY или JWT_PUBLIC_KEY_PATH
        3. File-based secret (если ./secrets/ существует)
        4. Provided value (default path)

        Returns:
            str: File path или PEM content (TokenService определяет тип)

        Example (Kubernetes):
            # k8s Secret с полным PEM содержимым:
            apiVersion: v1
            kind: Secret
            metadata:
              name: artstore-jwt-keys
            stringData:
              JWT_PUBLIC_KEY: |
                -----BEGIN PUBLIC KEY-----
                MIIBIjANBgkqhkiG9w0BAQEF...
                -----END PUBLIC KEY-----
        """
        # Lazy import для избежания circular dependency
        from app.core.secrets import get_secret

        # Пробуем загрузить из SecretProvider
        secret_from_provider = get_secret("JWT_PUBLIC_KEY")

        if secret_from_provider:
            return secret_from_provider

        # Fallback на provided value (env path или default)
        return v if v else ".keys/public_key.pem"

    @field_validator("algorithm")
    @classmethod
    def validate_algorithm(cls, v: str) -> str:
        """Валидация алгоритма JWT."""
        if v != "RS256":
            raise ValueError("Only RS256 algorithm is supported for JWT")
        return v


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

    enabled: bool = Field(default=True, alias="CORS_ENABLED")
    allow_origins: List[str] = Field(
        default=["http://localhost:4200"],
        alias="CORS_ALLOW_ORIGINS",
        description="Whitelist разрешенных origins. Production: explicit domains только!"
    )
    allow_credentials: bool = Field(
        default=True,
        alias="CORS_ALLOW_CREDENTIALS",
        description="Разрешить credentials (cookies, authorization headers). Requires explicit origins."
    )
    allow_methods: List[str] = Field(
        default=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        alias="CORS_ALLOW_METHODS",
        description="Разрешенные HTTP methods"
    )
    allow_headers: List[str] = Field(
        default=["Content-Type", "Authorization", "X-Request-ID", "X-Trace-ID"],
        alias="CORS_ALLOW_HEADERS",
        description="Разрешенные request headers. Production: explicit list вместо wildcard!"
    )
    max_age: int = Field(
        default=600,
        alias="CORS_MAX_AGE",
        description="Preflight cache duration в seconds (default: 10 minutes)"
    )

    model_config = SettingsConfigDict(env_prefix="CORS_", case_sensitive=False, extra="allow")

    @field_validator("enabled", "allow_credentials", mode="before")
    @classmethod
    def parse_bool_fields(cls, v):
        """Парсинг boolean полей из environment variables."""
        return parse_bool_from_env(v)

    @field_validator("allow_origins")
    @classmethod
    def validate_no_wildcards_in_production(cls, v: List[str]) -> List[str]:
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
                    "Example: CORS_ALLOW_ORIGINS=[\"https://admin.artstore.com\",\"https://api.artstore.com\"]"
                )
        return v

    @field_validator("allow_headers")
    @classmethod
    def warn_wildcard_headers(cls, v: List[str]) -> List[str]:
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
        # Note: info.data содержит уже валидированные поля
        allow_origins = info.data.get("allow_origins", [])

        if v and "*" in allow_origins:
            raise ValueError(
                "CORS allow_credentials=True cannot be used with wildcard origins ('*'). "
                "This violates CORS specification. "
                "Either set allow_credentials=False OR use explicit origin whitelist."
            )

        return v


class RateLimitSettings(BaseSettings):
    """Настройки rate limiting."""

    enabled: bool = Field(default=True, alias="RATE_LIMIT_ENABLED")
    requests_per_minute: int = Field(default=60, alias="RATE_LIMIT_REQUESTS_PER_MINUTE")
    burst: int = Field(default=10, alias="RATE_LIMIT_BURST")

    model_config = SettingsConfigDict(env_prefix="RATE_LIMIT_", case_sensitive=False, extra="allow")

    @field_validator("enabled", mode="before")
    @classmethod
    def parse_bool_fields(cls, v):
        """Парсинг boolean полей из environment variables."""
        return parse_bool_from_env(v)


class LoggingSettings(BaseSettings):
    """Настройки логирования."""

    level: str = Field(default="INFO", alias="LOG_LEVEL")
    format: str = Field(default="json", alias="LOG_FORMAT")
    log_file: Optional[str] = Field(default=None, alias="LOG_FILE")

    model_config = SettingsConfigDict(env_prefix="LOG_", case_sensitive=False, extra="allow")

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        """Валидация уровня логирования."""
        allowed_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in allowed_levels:
            raise ValueError(f"Log level must be one of {allowed_levels}")
        return v.upper()


class MonitoringSettings(BaseSettings):
    """Настройки мониторинга."""

    prometheus_enabled: bool = Field(default=True, alias="PROMETHEUS_ENABLED")
    opentelemetry_enabled: bool = Field(default=True, alias="OPENTELEMETRY_ENABLED")
    opentelemetry_service_name: str = Field(default="artstore-admin-module", alias="OPENTELEMETRY_SERVICE_NAME")
    opentelemetry_exporter_endpoint: Optional[str] = Field(default=None, alias="OPENTELEMETRY_EXPORTER_ENDPOINT")

    model_config = SettingsConfigDict(env_prefix="MONITORING_", case_sensitive=False, extra="allow")

    @field_validator("prometheus_enabled", "opentelemetry_enabled", mode="before")
    @classmethod
    def parse_bool_fields(cls, v):
        """Парсинг boolean полей из environment variables."""
        return parse_bool_from_env(v)


class ServiceDiscoverySettings(BaseSettings):
    """Настройки Service Discovery."""

    enabled: bool = Field(default=True, alias="SERVICE_DISCOVERY_ENABLED")
    redis_channel: str = Field(default="artstore:service_discovery", alias="SERVICE_DISCOVERY_REDIS_CHANNEL")
    publish_interval_seconds: int = Field(default=30, alias="SERVICE_DISCOVERY_PUBLISH_INTERVAL")
    storage_element_config_key: str = Field(default="artstore:storage_elements", alias="SERVICE_DISCOVERY_STORAGE_ELEMENT_CONFIG_KEY")

    model_config = SettingsConfigDict(env_prefix="SERVICE_DISCOVERY_", case_sensitive=False, extra="allow")

    @field_validator("enabled", mode="before")
    @classmethod
    def parse_bool_fields(cls, v):
        """Парсинг boolean полей из environment variables."""
        return parse_bool_from_env(v)


class SagaSettings(BaseSettings):
    """Настройки Saga оркестрации."""

    enabled: bool = Field(default=True, alias="SAGA_ENABLED")
    timeout_seconds: int = Field(default=300, alias="SAGA_TIMEOUT_SECONDS")
    retry_attempts: int = Field(default=3, alias="SAGA_RETRY_ATTEMPTS")
    retry_backoff_seconds: int = Field(default=5, alias="SAGA_RETRY_BACKOFF_SECONDS")

    model_config = SettingsConfigDict(env_prefix="SAGA_", case_sensitive=False, extra="allow")

    @field_validator("enabled", mode="before")
    @classmethod
    def parse_bool_fields(cls, v):
        """Парсинг boolean полей из environment variables."""
        return parse_bool_from_env(v)


class HealthSettings(BaseSettings):
    """Настройки health checks."""

    startup_timeout_seconds: int = Field(default=30, alias="HEALTH_STARTUP_TIMEOUT")
    liveness_timeout_seconds: int = Field(default=5, alias="HEALTH_LIVENESS_TIMEOUT")
    readiness_timeout_seconds: int = Field(default=10, alias="HEALTH_READINESS_TIMEOUT")

    model_config = SettingsConfigDict(env_prefix="HEALTH_", case_sensitive=False, extra="allow")


class InitialAdminSettings(BaseSettings):
    """
    Настройки для автоматического создания администратора при первом запуске.

    При первом старте системы, если в БД нет пользователей, автоматически создается
    учетная запись администратора с параметрами из этой конфигурации.

    ВАЖНО: В production окружении ОБЯЗАТЕЛЬНО установить безопасный пароль через
    environment variable INITIAL_ADMIN_PASSWORD.
    """

    enabled: bool = Field(
        default=True,
        alias="INITIAL_ADMIN_ENABLED",
        description="Включить автоматическое создание администратора"
    )
    username: str = Field(
        default="admin",
        alias="INITIAL_ADMIN_USERNAME",
        description="Username администратора"
    )
    password: str = Field(
        default="admin123",
        alias="INITIAL_ADMIN_PASSWORD",
        description="Пароль администратора (минимум 8 символов)"
    )
    email: str = Field(
        default="admin@artstore.local",
        alias="INITIAL_ADMIN_EMAIL",
        description="Email администратора"
    )
    firstname: str = Field(
        default="System",
        alias="INITIAL_ADMIN_FIRSTNAME",
        description="Имя администратора"
    )
    lastname: str = Field(
        default="Administrator",
        alias="INITIAL_ADMIN_LASTNAME",
        description="Фамилия администратора"
    )

    model_config = SettingsConfigDict(
        env_prefix="INITIAL_ADMIN_",
        case_sensitive=False,
        extra="allow"
    )

    @field_validator("enabled", mode="before")
    @classmethod
    def parse_bool_fields(cls, v):
        """Парсинг boolean полей из environment variables."""
        return parse_bool_from_env(v)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """
        Валидация минимальной сложности пароля.

        Args:
            v: Пароль для валидации

        Returns:
            str: Валидированный пароль

        Raises:
            ValueError: Если пароль слишком короткий
        """
        if len(v) < 8:
            raise ValueError("Initial admin password must be at least 8 characters")
        return v

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """
        Валидация username.

        Args:
            v: Username для валидации

        Returns:
            str: Валидированный username

        Raises:
            ValueError: Если username пустой или содержит недопустимые символы
        """
        if not v or not v.strip():
            raise ValueError("Initial admin username cannot be empty")

        # Проверка на допустимые символы (alphanumeric + underscore + dash)
        import re
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError("Initial admin username can only contain alphanumeric characters, underscore and dash")

        return v.strip()


class SchedulerSettings(BaseSettings):
    """Настройки APScheduler для background задач."""

    enabled: bool = Field(default=True, alias="SCHEDULER_ENABLED")
    jwt_rotation_enabled: bool = Field(default=True, alias="SCHEDULER_JWT_ROTATION_ENABLED")
    jwt_rotation_interval_hours: int = Field(default=24, alias="SCHEDULER_JWT_ROTATION_INTERVAL_HOURS")
    timezone: str = Field(default="UTC", alias="SCHEDULER_TIMEZONE")

    # Storage Health Check - периодический опрос состояния storage elements
    storage_health_check_enabled: bool = Field(
        default=True,
        alias="SCHEDULER_STORAGE_HEALTH_CHECK_ENABLED",
        description="Включить периодическую проверку состояния storage elements"
    )
    storage_health_check_interval_seconds: int = Field(
        default=60,
        ge=10,
        le=3600,
        alias="SCHEDULER_STORAGE_HEALTH_CHECK_INTERVAL_SECONDS",
        description="Интервал проверки storage elements в секундах (10-3600)"
    )

    # Readiness Health Check - периодическая проверка состояния БД и Redis для /health/ready
    readiness_check_enabled: bool = Field(
        default=True,
        alias="SCHEDULER_READINESS_CHECK_ENABLED",
        description="Включить периодическую проверку готовности приложения (БД + Redis)"
    )
    readiness_check_interval_seconds: int = Field(
        default=60,
        ge=5,
        le=300,
        alias="SCHEDULER_READINESS_CHECK_INTERVAL_SECONDS",
        description="Интервал проверки готовности в секундах (5-300)"
    )

    # Garbage Collection - периодическая очистка файлов
    gc_enabled: bool = Field(
        default=True,
        alias="SCHEDULER_GC_ENABLED",
        description="Включить периодическую очистку файлов (GC job)"
    )
    gc_interval_hours: int = Field(
        default=6,
        ge=1,
        le=168,
        alias="SCHEDULER_GC_INTERVAL_HOURS",
        description="Интервал запуска GC job в часах (1-168, default: 6)"
    )
    gc_batch_size: int = Field(
        default=100,
        ge=10,
        le=1000,
        alias="SCHEDULER_GC_BATCH_SIZE",
        description="Максимальный batch size для GC операций (10-1000)"
    )
    gc_safety_margin_hours: int = Field(
        default=24,
        ge=1,
        le=168,
        alias="SCHEDULER_GC_SAFETY_MARGIN_HOURS",
        description="Safety margin после финализации перед удалением (1-168 часов)"
    )
    gc_orphan_grace_days: int = Field(
        default=7,
        ge=1,
        le=30,
        alias="SCHEDULER_GC_ORPHAN_GRACE_DAYS",
        description="Grace period для orphaned файлов (1-30 дней)"
    )

    model_config = SettingsConfigDict(env_prefix="SCHEDULER_", case_sensitive=False, extra="allow")

    @field_validator("enabled", "jwt_rotation_enabled", "storage_health_check_enabled", "readiness_check_enabled", "gc_enabled", mode="before")
    @classmethod
    def parse_bool_fields(cls, v):
        """Парсинг boolean полей из environment variables."""
        return parse_bool_from_env(v)

    @field_validator("jwt_rotation_interval_hours")
    @classmethod
    def validate_rotation_interval(cls, v: int) -> int:
        """Валидация интервала ротации."""
        if v < 1 or v > 168:  # 1 час - 1 неделя
            raise ValueError("JWT rotation interval must be between 1 and 168 hours")
        return v


class SecuritySettings(BaseSettings):
    """
    Настройки безопасности с Platform-Agnostic Secret Management.

    Secrets могут быть загружены из:
    1. Kubernetes Secrets (автоматически в k8s/k3s)
    2. Environment Variables (docker-compose, development)
    3. File-based secrets (./secrets/ directory)

    Приоритет загрузки: k8s → env → file → default
    """

    audit_hmac_secret: str = Field(
        default="change-me-in-production-to-secure-random-value",
        alias="SECURITY_AUDIT_HMAC_SECRET",
        description="Секретный ключ для HMAC подписей audit logs (минимум 32 символа)"
    )
    audit_retention_days: int = Field(
        default=2555,  # ~7 лет (365 * 7)
        alias="SECURITY_AUDIT_RETENTION_DAYS",
        description="Срок хранения audit logs в днях (minimum 7 лет для compliance)"
    )

    model_config = SettingsConfigDict(env_prefix="SECURITY_", case_sensitive=False, extra="allow")

    @field_validator("audit_hmac_secret", mode="before")
    @classmethod
    def load_hmac_secret_from_provider(cls, v: Any) -> str:
        """
        Загрузка HMAC secret через SecretProvider с fallback chain.

        Порядок загрузки:
        1. Kubernetes Secret (если в k8s)
        2. Environment Variable (если установлен)
        3. File-based secret (если ./secrets/ существует)
        4. Provided value (default)

        Args:
            v: Текущее значение (из env или default)

        Returns:
            str: Loaded secret value

        Example (Kubernetes):
            # k8s Secret manifest:
            apiVersion: v1
            kind: Secret
            metadata:
              name: artstore-secrets
            stringData:
              SECURITY_AUDIT_HMAC_SECRET: "production-hmac-secret-32-chars-min"

            # Volume mount в Pod spec:
            volumes:
            - name: secrets
              secret:
                secretName: artstore-secrets
            containers:
            - volumeMounts:
              - name: secrets
                mountPath: /var/run/secrets/artstore
        """
        # Lazy import для избежания circular dependency
        from app.core.secrets import get_secret

        # Пробуем загрузить из SecretProvider
        secret_from_provider = get_secret("SECURITY_AUDIT_HMAC_SECRET")

        if secret_from_provider:
            return secret_from_provider

        # Fallback на provided value (env или default)
        return v if v else "change-me-in-production-to-secure-random-value"

    @field_validator("audit_hmac_secret")
    @classmethod
    def validate_hmac_secret(cls, v: str) -> str:
        """
        Валидация HMAC secret.

        Args:
            v: HMAC secret для валидации

        Returns:
            str: Валидированный secret

        Raises:
            ValueError: Если secret слишком короткий
        """
        if len(v) < 32:
            raise ValueError("HMAC secret must be at least 32 characters for security")

        # Warning для production
        import os
        if v == "change-me-in-production-to-secure-random-value":
            environment = os.getenv("ENVIRONMENT", "development")
            if environment == "production":
                raise ValueError(
                    "Default HMAC secret cannot be used in production. "
                    "Please set SECURITY_AUDIT_HMAC_SECRET via environment variable, "
                    "Kubernetes Secret, or file-based secret."
                )

        return v

    @field_validator("audit_retention_days")
    @classmethod
    def validate_retention_period(cls, v: int) -> int:
        """
        Валидация срока хранения audit logs.

        Args:
            v: Срок хранения в днях

        Returns:
            int: Валидированный срок хранения

        Raises:
            ValueError: Если срок хранения меньше минимального (7 лет)
        """
        min_retention_days = 365 * 7  # 7 лет minimum для compliance
        if v < min_retention_days:
            raise ValueError(f"Audit log retention must be at least {min_retention_days} days (7 years) for compliance")

        return v


class PasswordSettings(BaseSettings):
    """
    Настройки Password Policy для повышенной безопасности.

    Sprint 16 Phase 1: Strong Random Password Infrastructure

    Compliance requirements:
    - NIST рекомендует минимум 8 символов, мы используем 12 для повышенной безопасности
    - Обязательная сложность паролей (uppercase, lowercase, digits, special chars)
    - Password rotation каждые 90 дней
    - Запрет reuse последних 5 паролей
    """

    min_length: int = Field(
        default=12,
        ge=8,
        le=128,
        alias="PASSWORD_MIN_LENGTH",
        description="Минимальная длина пароля (рекомендуется 12+)"
    )
    require_uppercase: bool = Field(
        default=True,
        alias="PASSWORD_REQUIRE_UPPERCASE",
        description="Требовать uppercase буквы (A-Z)"
    )
    require_lowercase: bool = Field(
        default=True,
        alias="PASSWORD_REQUIRE_LOWERCASE",
        description="Требовать lowercase буквы (a-z)"
    )
    require_digits: bool = Field(
        default=True,
        alias="PASSWORD_REQUIRE_DIGITS",
        description="Требовать цифры (0-9)"
    )
    require_special: bool = Field(
        default=True,
        alias="PASSWORD_REQUIRE_SPECIAL",
        description="Требовать специальные символы (!@#$%^&*...)"
    )
    max_age_days: int = Field(
        default=90,
        ge=30,
        le=365,
        alias="PASSWORD_MAX_AGE_DAYS",
        description="Максимальный возраст пароля в днях (рекомендуется 90)"
    )
    history_size: int = Field(
        default=5,
        ge=0,
        le=24,
        alias="PASSWORD_HISTORY_SIZE",
        description="Количество старых паролей для проверки reuse (рекомендуется 5)"
    )
    expiration_warning_days: int = Field(
        default=14,
        ge=1,
        le=30,
        alias="PASSWORD_EXPIRATION_WARNING_DAYS",
        description="За сколько дней предупреждать о скором истечении пароля"
    )

    model_config = SettingsConfigDict(env_prefix="PASSWORD_", case_sensitive=False, extra="allow")

    @field_validator("require_uppercase", "require_lowercase", "require_digits", "require_special", mode="before")
    @classmethod
    def parse_bool_fields(cls, v):
        """Парсинг boolean полей из environment variables."""
        return parse_bool_from_env(v)

    @field_validator("min_length")
    @classmethod
    def validate_min_length(cls, v: int) -> int:
        """
        Валидация минимальной длины пароля.

        Args:
            v: Минимальная длина

        Returns:
            int: Валидированная длина

        Raises:
            ValueError: Если длина меньше рекомендуемой
        """
        if v < 12:
            import logging
            logging.warning(
                f"Password min_length={v} is below recommended value of 12. "
                "Consider increasing for better security."
            )
        return v

    @field_validator("max_age_days")
    @classmethod
    def validate_max_age(cls, v: int) -> int:
        """
        Валидация максимального возраста пароля.

        Args:
            v: Максимальный возраст в днях

        Returns:
            int: Валидированный возраст

        Raises:
            ValueError: Если возраст слишком большой
        """
        if v > 180:
            import logging
            logging.warning(
                f"Password max_age_days={v} is longer than recommended 180 days. "
                "Consider shorter rotation period for better security."
            )
        return v


class InitialServiceAccountSettings(BaseSettings):
    """
    Настройки для автоматического создания initial Service Account при первом запуске.

    При первом старте системы, если в БД нет Service Account с заданным именем, автоматически
    создается учетная запись с параметрами из этой конфигурации.

    ВАЖНО: Если INITIAL_ACCOUNT_PASSWORD не задан, client_secret будет сгенерирован автоматически
    и выведен в логи при создании (это единственный момент когда он доступен в plain text).
    """

    enabled: bool = Field(
        default=True,
        alias="INITIAL_ACCOUNT_ENABLED",
        description="Включить автоматическое создание Service Account"
    )
    name: str = Field(
        default="admin-service",
        alias="INITIAL_ACCOUNT_NAME",
        description="Имя Service Account"
    )
    password: Optional[str] = Field(
        default=None,
        alias="INITIAL_ACCOUNT_PASSWORD",
        description="Client secret для Service Account (если не задан - автогенерация)"
    )
    role: str = Field(
        default="ADMIN",
        alias="INITIAL_ACCOUNT_ROLE",
        description="Роль Service Account (ADMIN, USER, AUDITOR, READONLY)"
    )

    model_config = SettingsConfigDict(
        env_prefix="INITIAL_ACCOUNT_",
        case_sensitive=False,
        extra="allow"
    )

    @field_validator("enabled", mode="before")
    @classmethod
    def parse_bool_fields(cls, v):
        """Парсинг boolean полей из environment variables."""
        return parse_bool_from_env(v)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """
        Валидация имени Service Account.

        Args:
            v: Имя для валидации

        Returns:
            str: Валидированное имя

        Raises:
            ValueError: Если имя пустое или содержит недопустимые символы
        """
        if not v or not v.strip():
            raise ValueError("Initial service account name cannot be empty")

        # Проверка на допустимые символы (alphanumeric + underscore + dash)
        import re
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError("Initial service account name can only contain alphanumeric characters, underscore and dash")

        return v.strip()

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        """
        Валидация роли Service Account.

        Args:
            v: Роль для валидации

        Returns:
            str: Валидированная роль в uppercase

        Raises:
            ValueError: Если роль не входит в список допустимых
        """
        allowed_roles = ["ADMIN", "USER", "AUDITOR", "READONLY"]
        v_upper = v.upper()

        if v_upper not in allowed_roles:
            raise ValueError(f"Invalid role: {v}. Must be one of {allowed_roles}")

        return v_upper

    @field_validator("password", mode="before")
    @classmethod
    def validate_password_if_provided(cls, v: Optional[str]) -> Optional[str]:
        """
        Валидация пароля если он задан.

        Args:
            v: Пароль для валидации (может быть None для автогенерации)

        Returns:
            Optional[str]: Валидированный пароль или None

        Raises:
            ValueError: Если пароль задан но слишком короткий
        """
        # Treat empty strings as None (for auto-generation)
        if isinstance(v, str):
            v = v.strip() if v.strip() else None

        if v is not None and len(v) < 12:
            raise ValueError("Initial service account password must be at least 12 characters if provided")

        return v


class Settings(BaseSettings):
    """Главные настройки приложения."""

    # Приложение
    app_name: str = Field(default="ArtStore Admin Module", alias="APP_NAME")
    app_version: str = Field(default="0.1.0", alias="APP_VERSION")
    debug: bool = Field(default=False, alias="APP_DEBUG")
    swagger_enabled: bool = Field(default=False, alias="APP_SWAGGER_ENABLED", description="Production-first: Swagger отключен по умолчанию")
    host: str = Field(default="0.0.0.0", alias="APP_HOST")
    port: int = Field(default=8000, alias="APP_PORT")

    # Вложенные настройки
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    jwt: JWTSettings = Field(default_factory=JWTSettings)
    cors: CORSSettings = Field(default_factory=CORSSettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    monitoring: MonitoringSettings = Field(default_factory=MonitoringSettings)
    service_discovery: ServiceDiscoverySettings = Field(default_factory=ServiceDiscoverySettings)
    saga: SagaSettings = Field(default_factory=SagaSettings)
    health: HealthSettings = Field(default_factory=HealthSettings)
    scheduler: SchedulerSettings = Field(default_factory=SchedulerSettings)
    initial_admin: InitialAdminSettings = Field(default_factory=InitialAdminSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    password: PasswordSettings = Field(default_factory=PasswordSettings)
    initial_service_account: InitialServiceAccountSettings = Field(default_factory=InitialServiceAccountSettings)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    @field_validator("debug", "swagger_enabled", mode="before")
    @classmethod
    def parse_bool_fields(cls, v):
        """Парсинг boolean полей из environment variables."""
        return parse_bool_from_env(v)

    @classmethod
    def load_from_yaml(cls, config_path: str = "config.yaml") -> "Settings":
        """
        Загрузка настроек из YAML файла с возможностью переопределения через environment variables.

        Args:
            config_path: Путь к config.yaml файлу

        Returns:
            Settings: Загруженные настройки
        """
        config_file = Path(config_path)

        if not config_file.exists():
            # Если config.yaml не найден, используем настройки по умолчанию + env vars
            return cls()

        with open(config_file, "r", encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f)

        # Преобразуем YAML структуру в плоскую структуру для Pydantic
        flat_config = {}

        # App settings
        if "app" in yaml_data:
            app = yaml_data["app"]
            flat_config.update({
                "app_name": app.get("name"),
                "app_version": app.get("version"),
                "debug": app.get("debug"),
                "host": app.get("host"),
                "port": app.get("port")
            })

        # Database settings
        if "database" in yaml_data:
            flat_config["database"] = DatabaseSettings(**yaml_data["database"])

        # Redis settings
        if "redis" in yaml_data:
            flat_config["redis"] = RedisSettings(**yaml_data["redis"])

        # JWT settings
        if "jwt" in yaml_data:
            flat_config["jwt"] = JWTSettings(**yaml_data["jwt"])

        # CORS settings
        if "cors" in yaml_data:
            flat_config["cors"] = CORSSettings(**yaml_data["cors"])

        # Rate limit settings
        if "rate_limit" in yaml_data:
            flat_config["rate_limit"] = RateLimitSettings(**yaml_data["rate_limit"])

        # Logging settings
        if "logging" in yaml_data:
            flat_config["logging"] = LoggingSettings(**yaml_data["logging"])

        # Monitoring settings
        if "monitoring" in yaml_data:
            monitoring = yaml_data["monitoring"]
            flat_config["monitoring"] = MonitoringSettings(
                prometheus_enabled=monitoring.get("prometheus", {}).get("enabled", True),
                opentelemetry_enabled=monitoring.get("opentelemetry", {}).get("enabled", True),
                opentelemetry_service_name=monitoring.get("opentelemetry", {}).get("service_name", "artstore-admin-module"),
                opentelemetry_exporter_endpoint=monitoring.get("opentelemetry", {}).get("exporter_endpoint")
            )

        # Service Discovery settings
        if "service_discovery" in yaml_data:
            flat_config["service_discovery"] = ServiceDiscoverySettings(**yaml_data["service_discovery"])

        # Saga settings
        if "saga" in yaml_data:
            flat_config["saga"] = SagaSettings(**yaml_data["saga"])

        # Health settings
        if "health" in yaml_data:
            flat_config["health"] = HealthSettings(**yaml_data["health"])

        # Scheduler settings
        if "scheduler" in yaml_data:
            flat_config["scheduler"] = SchedulerSettings(**yaml_data["scheduler"])

        # Initial Admin settings
        if "initial_admin" in yaml_data:
            flat_config["initial_admin"] = InitialAdminSettings(**yaml_data["initial_admin"])

        # Security settings
        if "security" in yaml_data:
            flat_config["security"] = SecuritySettings(**yaml_data["security"])

        return cls(**flat_config)


# Глобальный экземпляр настроек
settings = Settings.load_from_yaml()
