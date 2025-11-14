"""
Ingester Module - Configuration Management.

Centralized конфигурация с приоритетом environment variables над config файлом.
"""

from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    host: str = "0.0.0.0"
    port: int = 8020


class AuthSettings(BaseSettings):
    """Настройки аутентификации."""

    model_config = SettingsConfigDict(
        env_prefix="AUTH_",
        case_sensitive=False
    )

    enabled: bool = True
    public_key_path: Path = Path("./keys/public_key.pem")
    algorithm: str = "RS256"


class StorageElementSettings(BaseSettings):
    """Настройки взаимодействия со Storage Element."""

    model_config = SettingsConfigDict(
        env_prefix="STORAGE_ELEMENT_",
        case_sensitive=False
    )

    base_url: str = "http://localhost:8010"
    timeout: int = 30  # секунды
    max_retries: int = 3
    connection_pool_size: int = 100


class RedisSettings(BaseSettings):
    """Настройки Redis для Service Discovery."""

    model_config = SettingsConfigDict(
        env_prefix="REDIS_",
        case_sensitive=False
    )

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    max_connections: int = 50


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


class LoggingSettings(BaseSettings):
    """Настройки логирования."""

    model_config = SettingsConfigDict(
        env_prefix="LOG_",
        case_sensitive=False
    )

    level: LogLevel = LogLevel.INFO
    format: LogFormat = LogFormat.JSON
    file: Optional[Path] = None


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
    storage_element: StorageElementSettings = Field(default_factory=StorageElementSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    compression: CompressionSettings = Field(default_factory=CompressionSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)


# Singleton instance
settings = Settings()
