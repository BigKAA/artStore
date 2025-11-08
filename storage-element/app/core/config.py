"""
Configuration management для Storage Element.

Поддерживает загрузку из YAML файла с переопределением через environment variables.
"""

import os
from pathlib import Path
from typing import Optional, Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml


class DatabaseConfig(BaseSettings):
    """PostgreSQL database configuration."""

    host: str = Field(default="localhost", description="PostgreSQL host")
    port: int = Field(default=5432, description="PostgreSQL port")
    username: str = Field(default="artstore", description="Database username")
    password: str = Field(default="password", description="Database password")
    database: str = Field(default="artstore", description="Database name")
    table_prefix: str = Field(
        default="storage_elem_01",
        description="Table prefix для uniqueness в shared DB"
    )

    model_config = SettingsConfigDict(
        env_prefix="DB_",
        case_sensitive=False
    )

    @property
    def connection_url(self) -> str:
        """PostgreSQL connection URL."""
        return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"


class StorageConfig(BaseSettings):
    """Storage configuration."""

    type: Literal["local", "s3"] = Field(
        default="local",
        description="Storage type: local filesystem or S3"
    )
    max_file_size: int = Field(
        default=1024 * 1024 * 1024,  # 1GB
        description="Maximum file size in bytes"
    )

    # Local storage settings
    local_base_path: str = Field(
        default="./.data/storage",
        description="Base path для local filesystem storage"
    )

    # S3 storage settings
    s3_endpoint_url: Optional[str] = Field(
        default=None,
        description="S3 endpoint URL (для MinIO)"
    )
    s3_access_key: Optional[str] = Field(default=None, description="S3 access key")
    s3_secret_key: Optional[str] = Field(default=None, description="S3 secret key")
    s3_bucket_name: Optional[str] = Field(
        default="artstore-files",
        description="S3 bucket name"
    )
    s3_region: Optional[str] = Field(default="us-east-1", description="S3 region")

    model_config = SettingsConfigDict(
        env_prefix="STORAGE_",
        case_sensitive=False
    )


class RedisConfig(BaseSettings):
    """Redis configuration для Service Discovery."""

    enabled: bool = Field(
        default=False,
        description="Enable Redis Service Discovery"
    )
    host: str = Field(default="localhost", description="Redis host")
    port: int = Field(default=6379, description="Redis port")
    password: Optional[str] = Field(default=None, description="Redis password")
    db: int = Field(default=0, description="Redis database number")

    # Sentinel configuration
    sentinel_enabled: bool = Field(
        default=False,
        description="Use Redis Sentinel для HA"
    )
    sentinel_master: Optional[str] = Field(
        default=None,
        description="Sentinel master name"
    )
    sentinel_hosts: Optional[str] = Field(
        default=None,
        description="Comma-separated Sentinel hosts (host:port,host:port)"
    )

    model_config = SettingsConfigDict(
        env_prefix="REDIS_",
        case_sensitive=False
    )


class AuthConfig(BaseSettings):
    """JWT authentication configuration."""

    jwt_public_key_path: str = Field(
        default="./keys/public_key.pem",
        description="Path to JWT RS256 public key"
    )
    jwt_algorithm: str = Field(
        default="RS256",
        description="JWT algorithm"
    )

    model_config = SettingsConfigDict(
        env_prefix="AUTH_",
        case_sensitive=False
    )


class StorageModeConfig(BaseSettings):
    """Storage mode configuration."""

    mode: Literal["edit", "rw", "ro", "ar"] = Field(
        default="edit",
        description="Storage mode: edit, rw, ro, ar"
    )

    # Archive mode settings
    ar_cold_storage_path: Optional[str] = Field(
        default=None,
        description="Path to cold storage для AR mode"
    )

    model_config = SettingsConfigDict(
        env_prefix="MODE_",
        case_sensitive=False
    )


class RetentionConfig(BaseSettings):
    """File retention configuration."""

    default_retention_days: int = Field(
        default=365,
        description="Default retention period in days"
    )
    warning_days_before_expiry: int = Field(
        default=30,
        description="Days before expiry to send warning"
    )

    model_config = SettingsConfigDict(
        env_prefix="RETENTION_",
        case_sensitive=False
    )


class WALConfig(BaseSettings):
    """Write-Ahead Log configuration."""

    enabled: bool = Field(
        default=True,
        description="Enable WAL logging"
    )
    wal_dir: str = Field(
        default="./.data/wal",
        description="Directory для WAL files"
    )

    model_config = SettingsConfigDict(
        env_prefix="WAL_",
        case_sensitive=False
    )


class AppConfig(BaseSettings):
    """Main application configuration."""

    # Application settings
    app_name: str = Field(
        default="Storage Element",
        description="Application name"
    )
    app_version: str = Field(
        default="1.0.0",
        description="Application version"
    )
    debug: bool = Field(
        default=False,
        description="Debug mode"
    )

    # Server settings
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8010, description="Server port")
    workers: int = Field(default=4, description="Number of worker processes")

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging level"
    )
    log_format: Literal["json", "text"] = Field(
        default="json",
        description="Log format (json for production)"
    )

    # Sub-configurations
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    mode: StorageModeConfig = Field(default_factory=StorageModeConfig)
    retention: RetentionConfig = Field(default_factory=RetentionConfig)
    wal: WALConfig = Field(default_factory=WALConfig)

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__"
    )

    @classmethod
    def load_from_yaml(cls, config_path: str | Path) -> "AppConfig":
        """
        Загрузка конфигурации из YAML файла с переопределением через env vars.

        Args:
            config_path: Путь к YAML конфигурации

        Returns:
            AppConfig: Loaded configuration

        Examples:
            >>> config = AppConfig.load_from_yaml("config.yaml")
            >>> print(config.storage.type)
            'local'
        """
        config_path = Path(config_path)

        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, 'r', encoding='utf-8') as f:
            yaml_data = yaml.safe_load(f)

        if yaml_data is None:
            yaml_data = {}

        # Pydantic автоматически переопределит значения из env vars
        return cls(**yaml_data)

    @classmethod
    def load(cls, config_path: Optional[str | Path] = None) -> "AppConfig":
        """
        Загрузка конфигурации с автоматическим определением источника.

        Приоритет:
        1. YAML file (если указан config_path)
        2. Environment variables
        3. Default values

        Args:
            config_path: Optional path to YAML config

        Returns:
            AppConfig: Loaded configuration
        """
        # Проверяем environment variable для пути к конфигу
        if config_path is None:
            config_path = os.getenv("CONFIG_PATH", "config.yaml")

        config_path = Path(config_path)

        if config_path.exists():
            return cls.load_from_yaml(config_path)
        else:
            # Загрузка только из env vars и defaults
            return cls()


# Global configuration instance
_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """
    Получение глобального экземпляра конфигурации (singleton pattern).

    Returns:
        AppConfig: Application configuration
    """
    global _config
    if _config is None:
        _config = AppConfig.load()
    return _config


def reload_config(config_path: Optional[str | Path] = None) -> AppConfig:
    """
    Перезагрузка конфигурации (для тестов и runtime updates).

    Args:
        config_path: Optional path to YAML config

    Returns:
        AppConfig: Reloaded configuration
    """
    global _config
    _config = AppConfig.load(config_path)
    return _config
