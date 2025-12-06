"""
>=D83C@0F8O Query Module.

A?>;L7C5B Pydantic Settings 4;O 703@C7:8 :>=D83C@0F88 87 environment variables
A ?>445@6:>9 .env D09;>2 8 20;840F859.
"""

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


class AuthSettings(BaseSettings):
    """0AB@>9:8 JWT 0CB5=B8D8:0F88 (RS256)."""

    model_config = SettingsConfigDict(env_prefix="AUTH_")

    public_key_path: Path = Field(
        default=Path("/app/keys/public_key.pem"),
        description="CBL : ?C1;8G=><C :;NGC 4;O 20;840F88 JWT B>:5=>2 (RS256)",
    )
    algorithm: str = Field(default="RS256", description=";3>@8B< JWT")

    @field_validator("public_key_path")
    @classmethod
    def validate_public_key_path(cls, v: Path) -> Path:
        """0;840F8O ?CB8 : ?C1;8G=><C :;NGC."""
        if not v.exists():
            raise ValueError(f"Public key file not found: {v}")
        return v


class DatabaseSettings(BaseSettings):
    """0AB@>9:8 ?>4:;NG5=8O : PostgreSQL (async)."""

    model_config = SettingsConfigDict(env_prefix="DB_", case_sensitive=False)

    host: str = Field(default="localhost", description="PostgreSQL E>AB")
    port: int = Field(default=5432, ge=1, le=65535, description="PostgreSQL ?>@B")
    username: str = Field(default="artstore", description="<O ?>;L7>20B5;O ")
    password: str = Field(default="password", description="0@>;L ")
    database: str = Field(default="artstore", description="<O 107K 40==KE")
    pool_size: int = Field(
        default=20, ge=5, le=100, description=" 07<5@ connection pool"
    )
    max_overflow: int = Field(
        default=10, ge=0, le=50, description="0:A8<0;L=>5 overflow A>548=5=89"
    )
    pool_timeout: int = Field(
        default=30, ge=5, le=300, description="Timeout ?>;CG5=8O A>548=5=8O (A5:)"
    )
    echo: bool = Field(default=False, description=">38@>20=85 SQL 70?@>A>2")
    
    # SSL Configuration
    ssl_enabled: bool = Field(
        default=False,
        description="Enable SSL for PostgreSQL connection"
    )
    ssl_mode: str = Field(
        default="require",
        description="SSL mode: disable, allow, prefer, require, verify-ca, verify-full"
    )
    ssl_ca_cert: Optional[str] = Field(
        default=None,
        description="Path to CA certificate file for SSL verification"
    )
    ssl_client_cert: Optional[str] = Field(
        default=None,
        description="Path to client certificate file for SSL"
    )
    ssl_client_key: Optional[str] = Field(
        default=None,
        description="Path to client private key file for SSL"
    )

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
    def database_url(self) -> str:
        """$>@<8@>20=85 async PostgreSQL connection string."""
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
    """0AB@>9:8 ?>4:;NG5=8O : Redis (SYNC @568< A>3;0A=> 0@E8B5:BC@5)."""

    model_config = SettingsConfigDict(env_prefix="REDIS_")

    host: str = Field(default="localhost", description="Redis E>AB")
    port: int = Field(default=6379, ge=1, le=65535, description="Redis ?>@B")
    db: int = Field(default=0, ge=0, le=15, description="><5@ Redis 107K 40==KE")
    password: Optional[str] = Field(default=None, description="0@>;L Redis")
    socket_timeout: int = Field(default=5, ge=1, le=60, description="Socket timeout (A5:)")
    socket_connect_timeout: int = Field(
        default=5, ge=1, le=60, description="Connect timeout (A5:)"
    )
    max_connections: int = Field(
        default=50, ge=10, le=500, description="0:A8<C< A>548=5=89 2 pool"
    )

    @property
    def redis_url(self) -> str:
        """$>@<8@>20=85 Redis connection string."""
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"


class StorageSettings(BaseSettings):
    """0AB@>9:8 ?>4:;NG5=8O : Storage Elements."""

    model_config = SettingsConfigDict(env_prefix="STORAGE_")

    default_timeout: int = Field(
        default=30, ge=5, le=300, description="HTTP request timeout (A5:)"
    )
    max_connections: int = Field(
        default=100, ge=10, le=500, description="0:A8<C< HTTP A>548=5=89"
    )
    max_keepalive_connections: int = Field(
        default=20, ge=5, le=100, description="0:A8<C< keepalive A>548=5=89"
    )
    retry_attempts: int = Field(
        default=3, ge=1, le=10, description=">;8G5AB2> retry ?>?KB>:"
    )
    retry_delay: float = Field(
        default=1.0, ge=0.1, le=10.0, description="045@6:0 <564C retry (A5:)"
    )


class CacheSettings(BaseSettings):
    """0AB@>9:8 <=>3>C@>2=52>3> :5H8@>20=8O."""

    model_config = SettingsConfigDict(env_prefix="CACHE_")

    # Local cache (in-memory)
    local_enabled: bool = Field(default=True, description=":;NG8BL local cache")
    local_ttl: int = Field(
        default=300, ge=10, le=3600, description="TTL local cache (A5:)"
    )
    local_max_size: int = Field(
        default=1000, ge=100, le=10000, description="0:A8<C< M;5<5=B>2 2 local cache"
    )

    # Redis cache
    redis_enabled: bool = Field(default=True, description=":;NG8BL Redis cache")
    redis_ttl: int = Field(
        default=1800, ge=60, le=86400, description="TTL Redis cache (A5:)"
    )

    # Cache strategy
    cache_search_results: bool = Field(
        default=True, description="5H8@>20BL @57C;LB0BK ?>8A:0"
    )
    cache_file_metadata: bool = Field(
        default=True, description="5H8@>20BL <5B040==K5 D09;>2"
    )

    @field_validator("local_enabled", "redis_enabled", "cache_search_results", "cache_file_metadata", mode="before")
    @classmethod
    def parse_bool_fields(cls, v):
        """Парсинг boolean полей из environment variables."""
        return parse_bool_from_env(v)


class SearchSettings(BaseSettings):
    """0AB@>9:8 PostgreSQL Full-Text Search."""

    model_config = SettingsConfigDict(env_prefix="SEARCH_")

    # Full-Text Search configuration
    default_language: str = Field(
        default="russian", description="/7K: 4;O FTS (russian, english)"
    )
    max_results: int = Field(
        default=100, ge=10, le=1000, description="0:A8<C< @57C;LB0B>2 ?>8A:0"
    )
    min_query_length: int = Field(
        default=2, ge=1, le=10, description="8=8<0;L=0O 4;8=0 ?>8A:>2>3> 70?@>A0"
    )

    # Search ranking weights
    rank_title_weight: float = Field(
        default=1.0, ge=0.0, le=1.0, description="5A 703>;>2:0 2 @0=68@>20=88"
    )
    rank_content_weight: float = Field(
        default=0.5, ge=0.0, le=1.0, description="5A A>45@68<>3> 2 @0=68@>20=88"
    )
    rank_tags_weight: float = Field(
        default=0.8, ge=0.0, le=1.0, description="5A B53>2 2 @0=68@>20=88"
    )



class DownloadSettings(BaseSettings):
    """Настройки скачивания файлов."""

    model_config = SettingsConfigDict(env_prefix="DOWNLOAD_")

    # HTTP client timeouts
    connect_timeout: int = Field(
        default=10, ge=1, le=60, description="Timeout подключения к Storage Element (секунды)"
    )
    read_timeout: int = Field(
        default=300, ge=10, le=600, description="Timeout чтения данных (секунды, для больших файлов)"
    )
    write_timeout: int = Field(
        default=60, ge=5, le=300, description="Timeout записи данных (секунды)"
    )
    pool_timeout: int = Field(
        default=10, ge=1, le=60, description="Timeout получения соединения из pool"
    )

    # Connection pool settings
    max_connections: int = Field(
        default=100, ge=10, le=500, description="Максимальное количество соединений"
    )
    max_keepalive_connections: int = Field(
        default=20, ge=5, le=100, description="Максимум keepalive соединений"
    )

    # Download settings
    chunk_size: int = Field(
        default=8192, ge=1024, le=1048576, description="Размер chunk для streaming (bytes)"
    )
    enable_resume: bool = Field(
        default=True, description="Разрешить resumable downloads"
    )

    @field_validator("enable_resume", mode="before")
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

    model_config = SettingsConfigDict(env_prefix="CORS_", case_sensitive=False)

    enabled: bool = Field(default=True, description="Включить CORS middleware")
    allow_origins: list[str] = Field(
        default=["http://localhost:4200", "http://localhost:8000"],
        description="Whitelist разрешенных origins. Production: explicit domains только!",
    )
    allow_credentials: bool = Field(
        default=True,
        description="Разрешить credentials (cookies, authorization headers). Requires explicit origins.",
    )
    allow_methods: list[str] = Field(
        default=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        description="Разрешенные HTTP methods",
    )
    allow_headers: list[str] = Field(
        default=["Content-Type", "Authorization", "X-Request-ID", "X-Trace-ID"],
        description="Разрешенные request headers. Production: explicit list вместо wildcard!",
    )
    expose_headers: list[str] = Field(
        default=[],
        description="Headers, которые будут exposed в browser (e.g., Content-Length, Content-Range)",
    )
    max_age: int = Field(
        default=600,
        description="Preflight cache duration в seconds (default: 10 minutes)",
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
                    "Example: CORS_ALLOW_ORIGINS=[\"https://admin.artstore.com\",\"https://query.artstore.com\"]"
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


# ========================================
# Main Settings (Composite)
# ========================================


class QueryModuleSettings(BaseSettings):
    """;02=K5 =0AB@>9:8 Query Module."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # A=>2=K5 =0AB@>9:8
    app_name: str = Field(default="query-module", description="0720=85 ?@8;>65=8O")
    debug: bool = Field(default=False, description="Debug @568<")
    swagger_enabled: bool = Field(default=False, description="Swagger UI (production-first: >B:;NG5=> ?> C<>;G0=8N)")
    host: str = Field(default="0.0.0.0", description="%>AB 4;O 70?CA:0")
    port: int = Field(default=8030, ge=1024, le=65535, description=">@B 4;O 70?CA:0")

    # Logging
    log_level: str = Field(
        default="INFO", description="#@>25=L ;>38@>20=8O (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    )
    log_format: str = Field(
        default="json", description="$>@<0B ;>3>2 (json 8;8 text)"
    )

    # ;>65==K5 =0AB@>9:8
    auth: AuthSettings = Field(default_factory=AuthSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)
    search: SearchSettings = Field(default_factory=SearchSettings)
    download: DownloadSettings = Field(default_factory=DownloadSettings)
    cors: CORSSettings = Field(default_factory=CORSSettings)

    @field_validator("debug", "swagger_enabled", mode="before")
    @classmethod
    def parse_bool_fields(cls, v):
        """Парсинг boolean полей из environment variables."""
        return parse_bool_from_env(v)

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """0;840F8O C@>2=O ;>38@>20=8O."""
        allowed = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in allowed:
            raise ValueError(f"Log level must be one of {allowed}")
        return v.upper()

    @field_validator("log_format")
    @classmethod
    def validate_log_format(cls, v: str) -> str:
        """0;840F8O D>@<0B0 ;>3>2."""
        allowed = ["json", "text"]
        if v.lower() not in allowed:
            raise ValueError(f"Log format must be one of {allowed}")
        return v.lower()


# ;>10;L=K9 M:75<?;O@ =0AB@>5:
settings = QueryModuleSettings()
