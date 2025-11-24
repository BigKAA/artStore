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

    model_config = SettingsConfigDict(env_prefix="DB_", case_sensitive=False, extra="allow")

    @property
    def url(self) -> str:
        """Построение database URL для SQLAlchemy (async)."""
        return f"postgresql+asyncpg://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"

    @property
    def sync_url(self) -> str:
        """Построение database URL для Alembic (sync)."""
        return f"postgresql+psycopg2://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"


class RedisSettings(BaseSettings):
    """Настройки подключения к Redis."""

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
        """Построение Redis URL."""
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


class TLSSettings(BaseSettings):
    """
    Настройки TLS 1.3 транспортного шифрования и mTLS inter-service authentication.

    Sprint 16 Phase 4: TLS 1.3 + mTLS Infrastructure

    TLS 1.3 Features:
    - Транспортное шифрование всех HTTP соединений
    - Perfect Forward Secrecy (PFS) с эфемерными ключами
    - AEAD cipher suites only (AES-GCM, ChaCha20-Poly1305)
    - 0-RTT resumption для быстрых reconnects

    mTLS (Mutual TLS) Features:
    - Certificate-based client authentication
    - Service-to-service mutual authentication
    - CN whitelist для trusted services
    - Certificate rotation каждые 90 дней

    Configuration:
        # Basic TLS (HTTPS)
        TLS_ENABLED=true
        TLS_CERT_FILE=/app/tls/server-cert.pem
        TLS_KEY_FILE=/app/tls/server-key.pem
        TLS_PROTOCOL_VERSION=TLSv1.3

        # mTLS (Mutual Authentication)
        TLS_CA_CERT_FILE=/app/tls/ca-cert.pem
        TLS_VERIFY_MODE=CERT_REQUIRED  # Enforce client certificates

        # Advanced
        TLS_CIPHERS="TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256"

    References:
    - NIST SP 800-52 Rev. 2: Guidelines for TLS Implementations
    - RFC 8446: The Transport Layer Security (TLS) Protocol Version 1.3
    - Mozilla SSL Configuration Generator: https://ssl-config.mozilla.org/
    """

    model_config = SettingsConfigDict(
        env_prefix="TLS_",
        case_sensitive=False,
        extra="allow"
    )

    enabled: bool = Field(
        default=False,
        alias="enabled",
        description="Enable TLS 1.3 encryption. Set to true для HTTPS mode."
    )

    cert_file: str = Field(
        default="",
        alias="cert_file",
        description="Path to server certificate file (PEM format). "
                    "Required if enabled=true. "
                    "Example: /app/tls/server-cert.pem"
    )

    key_file: str = Field(
        default="",
        alias="key_file",
        description="Path to server private key file (PEM format). "
                    "Required if enabled=true. Must be protected (chmod 400). "
                    "Example: /app/tls/server-key.pem"
    )

    ca_cert_file: str = Field(
        default="",
        alias="ca_cert_file",
        description="Path to CA certificate for client validation (mTLS). "
                    "Required if verify_mode=CERT_REQUIRED. "
                    "Example: /app/tls/ca-cert.pem"
    )

    protocol_version: str = Field(
        default="TLSv1.3",
        alias="protocol_version",
        description="Minimum TLS protocol version. Options: TLSv1.2, TLSv1.3. "
                    "Рекомендуется TLSv1.3 для maximum security."
    )

    ciphers: str = Field(
        default="TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256:TLS_AES_128_GCM_SHA256",
        alias="ciphers",
        description="Allowed cipher suites (colon-separated). "
                    "AEAD cipher suites only для TLS 1.3. "
                    "Default includes AES-GCM and ChaCha20-Poly1305."
    )

    verify_mode: str = Field(
        default="CERT_OPTIONAL",
        alias="verify_mode",
        description="Certificate verification mode for client certificates. "
                    "Options: CERT_NONE (no client certs), "
                    "CERT_OPTIONAL (accept but don't require), "
                    "CERT_REQUIRED (enforce mTLS - require valid client cert). "
                    "Use CERT_REQUIRED для inter-service mTLS."
    )

    @field_validator("enabled")
    @classmethod
    def warn_if_disabled_in_production(cls, v: bool) -> bool:
        """
        Предупреждение если TLS отключен в production.

        Security Warning:
        - Production environments ДОЛЖНЫ использовать TLS 1.3
        - Незашифрованный трафик уязвим к MITM attacks
        - Credentials и sensitive data передаются в plaintext

        Returns:
            bool: enabled value (unchanged)
        """
        import os
        import logging

        environment = os.getenv("ENVIRONMENT", "development")

        if not v and environment == "production":
            logging.warning(
                "🔴 SECURITY WARNING: TLS disabled in production environment! "
                "All traffic is unencrypted and vulnerable to Man-in-the-Middle attacks. "
                "Set TLS_ENABLED=true and configure certificates immediately. "
                "See admin-module/tls-infrastructure/README.md for setup guide."
            )

        return v

    @field_validator("cert_file", "key_file")
    @classmethod
    def validate_cert_files_if_enabled(cls, v: str, info) -> str:
        """
        Валидация что certificate files указаны если TLS enabled.

        Args:
            v: cert_file или key_file value
            info: ValidationInfo с контекстом других полей

        Returns:
            str: cert/key file path (unchanged)

        Raises:
            ValueError: Если TLS enabled но cert/key files не указаны
        """
        import os

        # Access enabled field via validation_context
        enabled = info.data.get("enabled", False)

        if enabled and not v:
            field_name = info.field_name
            raise ValueError(
                f"TLS {field_name} is required when TLS_ENABLED=true. "
                f"Set TLS_{field_name.upper()} environment variable. "
                f"Example: TLS_{field_name.upper()}=/app/tls/server-{field_name.replace('_', '-')}.pem"
            )

        # Если файл указан, проверяем его existence
        if v and not os.path.exists(v):
            logging.warning(
                f"⚠️  TLS {info.field_name} file not found: {v}. "
                f"Certificate files will be validated at runtime."
            )

        return v

    @field_validator("protocol_version")
    @classmethod
    def validate_protocol_version(cls, v: str) -> str:
        """
        Валидация TLS protocol version.

        Args:
            v: protocol_version value

        Returns:
            str: Validated protocol version

        Raises:
            ValueError: Если указана unsupported version
        """
        import logging

        valid_versions = ["TLSv1.2", "TLSv1.3"]

        if v not in valid_versions:
            raise ValueError(
                f"Invalid TLS protocol version: {v}. "
                f"Supported versions: {', '.join(valid_versions)}. "
                f"Recommended: TLSv1.3"
            )

        if v == "TLSv1.2":
            logging.warning(
                "⚠️  TLS 1.2 is deprecated. Consider upgrading to TLS 1.3 for: "
                "- Improved security (removed weak ciphers) "
                "- Faster handshakes (1-RTT vs 2-RTT) "
                "- Perfect Forward Secrecy by default"
            )

        return v

    @field_validator("verify_mode")
    @classmethod
    def validate_verify_mode(cls, v: str) -> str:
        """
        Валидация certificate verification mode.

        Args:
            v: verify_mode value

        Returns:
            str: Validated verify mode

        Raises:
            ValueError: Если указан invalid mode
        """
        valid_modes = ["CERT_NONE", "CERT_OPTIONAL", "CERT_REQUIRED"]

        if v not in valid_modes:
            raise ValueError(
                f"Invalid TLS verify_mode: {v}. "
                f"Valid modes: {', '.join(valid_modes)}. "
                f"Use CERT_REQUIRED для mTLS inter-service authentication."
            )

        return v


class RateLimitSettings(BaseSettings):
    """Настройки rate limiting."""

    enabled: bool = Field(default=True, alias="RATE_LIMIT_ENABLED")
    requests_per_minute: int = Field(default=60, alias="RATE_LIMIT_REQUESTS_PER_MINUTE")
    burst: int = Field(default=10, alias="RATE_LIMIT_BURST")

    model_config = SettingsConfigDict(env_prefix="RATE_LIMIT_", case_sensitive=False, extra="allow")


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


class ServiceDiscoverySettings(BaseSettings):
    """Настройки Service Discovery."""

    enabled: bool = Field(default=True, alias="SERVICE_DISCOVERY_ENABLED")
    redis_channel: str = Field(default="artstore:service_discovery", alias="SERVICE_DISCOVERY_REDIS_CHANNEL")
    publish_interval_seconds: int = Field(default=30, alias="SERVICE_DISCOVERY_PUBLISH_INTERVAL")
    storage_element_config_key: str = Field(default="artstore:storage_elements", alias="SERVICE_DISCOVERY_STORAGE_ELEMENT_CONFIG_KEY")

    model_config = SettingsConfigDict(env_prefix="SERVICE_DISCOVERY_", case_sensitive=False, extra="allow")


class SagaSettings(BaseSettings):
    """Настройки Saga оркестрации."""

    enabled: bool = Field(default=True, alias="SAGA_ENABLED")
    timeout_seconds: int = Field(default=300, alias="SAGA_TIMEOUT_SECONDS")
    retry_attempts: int = Field(default=3, alias="SAGA_RETRY_ATTEMPTS")
    retry_backoff_seconds: int = Field(default=5, alias="SAGA_RETRY_BACKOFF_SECONDS")

    model_config = SettingsConfigDict(env_prefix="SAGA_", case_sensitive=False, extra="allow")


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

    model_config = SettingsConfigDict(env_prefix="SCHEDULER_", case_sensitive=False, extra="allow")

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


class Settings(BaseSettings):
    """Главные настройки приложения."""

    # Приложение
    app_name: str = Field(default="ArtStore Admin Module", alias="APP_NAME")
    app_version: str = Field(default="0.1.0", alias="APP_VERSION")
    debug: bool = Field(default=False, alias="APP_DEBUG")
    host: str = Field(default="0.0.0.0", alias="APP_HOST")
    port: int = Field(default=8000, alias="APP_PORT")

    # Вложенные настройки
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    jwt: JWTSettings = Field(default_factory=JWTSettings)
    cors: CORSSettings = Field(default_factory=CORSSettings)
    tls: TLSSettings = Field(default_factory=TLSSettings)  # Sprint 16 Phase 4
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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

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
