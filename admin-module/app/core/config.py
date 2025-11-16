"""
Конфигурация приложения Admin Module.
Использует Pydantic Settings для загрузки из config.yaml и environment variables.
Environment variables имеют приоритет над config.yaml.
"""

from typing import Optional, List, Dict
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
    """Настройки JWT аутентификации."""

    algorithm: str = Field(default="RS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=30, alias="JWT_ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(default=7, alias="JWT_REFRESH_TOKEN_EXPIRE_DAYS")
    private_key_path: str = Field(default="/path/to/private_key.pem", alias="JWT_PRIVATE_KEY_PATH")
    public_key_path: str = Field(default="/path/to/public_key.pem", alias="JWT_PUBLIC_KEY_PATH")
    key_rotation_hours: int = Field(default=24, alias="JWT_KEY_ROTATION_HOURS")

    model_config = SettingsConfigDict(env_prefix="JWT_", case_sensitive=False, extra="allow")

    @field_validator("algorithm")
    @classmethod
    def validate_algorithm(cls, v: str) -> str:
        """Валидация алгоритма JWT."""
        if v != "RS256":
            raise ValueError("Only RS256 algorithm is supported for JWT")
        return v


class CORSSettings(BaseSettings):
    """Настройки CORS для защиты от CSRF attacks."""

    enabled: bool = Field(default=True, alias="CORS_ENABLED")
    allow_origins: List[str] = Field(default=["http://localhost:4200"], alias="CORS_ALLOW_ORIGINS")
    allow_credentials: bool = Field(default=True, alias="CORS_ALLOW_CREDENTIALS")
    allow_methods: List[str] = Field(default=["GET", "POST", "PUT", "DELETE", "PATCH"], alias="CORS_ALLOW_METHODS")
    allow_headers: List[str] = Field(default=["*"], alias="CORS_ALLOW_HEADERS")

    model_config = SettingsConfigDict(env_prefix="CORS_", case_sensitive=False, extra="allow")

    @field_validator("allow_origins")
    @classmethod
    def validate_no_wildcards_in_production(cls, v: List[str]) -> List[str]:
        """
        Проверка запрета wildcard origins в production окружении.

        Security requirement: CORS wildcards (*) запрещены в production
        для защиты от CSRF attacks.
        """
        import os

        if "*" in v:
            environment = os.getenv("ENVIRONMENT", "development")
            if environment == "production":
                raise ValueError(
                    "Wildcard CORS origins ('*') are not allowed in production environment. "
                    "Please configure explicit origin whitelist via CORS_ALLOW_ORIGINS."
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
    """Настройки безопасности."""

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
                    "Please set SECURITY_AUDIT_HMAC_SECRET environment variable."
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
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    monitoring: MonitoringSettings = Field(default_factory=MonitoringSettings)
    service_discovery: ServiceDiscoverySettings = Field(default_factory=ServiceDiscoverySettings)
    saga: SagaSettings = Field(default_factory=SagaSettings)
    health: HealthSettings = Field(default_factory=HealthSettings)
    scheduler: SchedulerSettings = Field(default_factory=SchedulerSettings)
    initial_admin: InitialAdminSettings = Field(default_factory=InitialAdminSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)

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
