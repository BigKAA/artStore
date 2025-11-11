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
    version: str = "1.0.0"
    debug: bool = False
    mode: StorageMode = StorageMode.RW
    rebuild_cache_on_startup: bool = False


class ServerSettings(BaseSettings):
    """Настройки веб-сервера"""
    model_config = SettingsConfigDict(
        env_prefix="SERVER_",
        case_sensitive=False
    )

    host: str = "0.0.0.0"
    port: int = 8010
    workers: int = 1
    reload: bool = False  # Hot reload для development


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
    database: str = "artstore"

    # Connection pooling
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30
    pool_recycle: int = 3600

    # Префикс таблиц для уникальности
    table_prefix: str = "storage_elem_01"

    @property
    def url(self) -> str:
        """Формирование Database URL для SQLAlchemy"""
        return f"postgresql+asyncpg://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"


class RedisSettings(BaseSettings):
    """Настройки Redis для Service Discovery и Master Election"""
    model_config = SettingsConfigDict(
        env_prefix="REDIS_",
        case_sensitive=False
    )

    # Standalone mode (для development)
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None

    # Master Election настройки
    master_key_prefix: str = "storage_master"
    master_ttl: int = 30  # Время жизни ключа мастера в секундах
    master_check_interval: int = 10  # Интервал проверки статуса мастера

    # Circuit Breaker для Redis failover
    failure_threshold: int = 5
    recovery_timeout: int = 60
    half_open_max_calls: int = 3


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

    @property
    def max_size_bytes(self) -> int:
        """Максимальный размер в байтах"""
        return self.max_size_gb * 1024 * 1024 * 1024


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


class HealthSettings(BaseSettings):
    """Настройки health checks"""
    model_config = SettingsConfigDict(
        env_prefix="HEALTH_",
        case_sensitive=False
    )

    liveness_path: str = "/health/live"
    readiness_path: str = "/health/ready"


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
        extra="ignore"
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
