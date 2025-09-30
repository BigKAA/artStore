"""
Pydantic модели для конфигурации приложения.
Используются для валидации config.yaml и переменных окружения.
"""
from typing import Dict, List, Literal, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class ServerConfig(BaseSettings):
    """Настройки HTTP сервера"""

    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 4
    reload: bool = False
    log_level: str = "info"


class AppConfig(BaseSettings):
    """Информация о приложении"""

    name: str = "ArtStore Admin Module"
    version: str = "1.0.0"
    description: str = "Центр аутентификации и управления системой ArtStore"
    debug: bool = False


class DatabaseConfig(BaseSettings):
    """Настройки PostgreSQL"""

    host: str = "localhost"
    port: int = 5432
    username: str = "artstore"
    password: str = "password"
    database: str = "artstore_admin"
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30
    pool_recycle: int = 3600
    echo: bool = False

    @property
    def url(self) -> str:
        """Генерирует URL подключения к PostgreSQL"""
        return f"postgresql+asyncpg://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"


class RedisClusterNodeConfig(BaseSettings):
    """Настройки одного узла Redis Cluster"""

    host: str = "localhost"
    port: int = 6379


class RedisClusterConfig(BaseSettings):
    """Настройки Redis Cluster"""

    # Список узлов кластера (минимум 6: 3 master + 3 replica)
    nodes: List[RedisClusterNodeConfig] = [
        RedisClusterNodeConfig(host="redis-cluster-1", port=6379),
        RedisClusterNodeConfig(host="redis-cluster-2", port=6379),
        RedisClusterNodeConfig(host="redis-cluster-3", port=6379),
        RedisClusterNodeConfig(host="redis-cluster-4", port=6379),
        RedisClusterNodeConfig(host="redis-cluster-5", port=6379),
        RedisClusterNodeConfig(host="redis-cluster-6", port=6379),
    ]
    password: str = ""
    # Максимальное количество редиректов
    max_redirects: int = 3
    # Таймаут на инициализацию кластера
    cluster_init_timeout: int = 10


class RedisConfig(BaseSettings):
    """Настройки Redis"""

    mode: Literal["standalone", "cluster"] = "standalone"

    # Standalone режим (для разработки)
    host: str = "localhost"
    port: int = 6379
    password: str = ""
    db: int = 0

    # Cluster режим (для production)
    cluster: Optional[RedisClusterConfig] = None

    # Connection pool
    max_connections: int = 50
    socket_timeout: int = 5
    socket_connect_timeout: int = 5


class JWTKeyRotationConfig(BaseSettings):
    """Настройки ротации JWT ключей"""

    enabled: bool = True
    interval_hours: int = 24


class PasswordPolicyConfig(BaseSettings):
    """Политика паролей"""

    min_length: int = 12
    require_uppercase: bool = True
    require_lowercase: bool = True
    require_digits: bool = True
    require_special: bool = True
    max_age_days: int = 90


class JWTConfig(BaseSettings):
    """Настройки JWT токенов"""

    algorithm: Literal["RS256"] = "RS256"
    private_key_path: str = "./keys/jwt-private.pem"
    public_key_path: str = "./keys/jwt-public.pem"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7


class LDAPConfig(BaseSettings):
    """Настройки LDAP интеграции"""

    enabled: bool = False
    server: str = "ldap://localhost:389"
    bind_dn: str = "cn=admin,dc=example,dc=com"
    bind_password: str = "admin_password"
    base_dn: str = "dc=example,dc=com"
    user_search_filter: str = "(uid={username})"
    timeout: int = 10


class OAuth2ProviderConfig(BaseSettings):
    """Настройки одного OAuth2 провайдера"""

    client_id: str = ""
    client_secret: str = ""
    authorize_url: str = ""
    token_url: str = ""


class OAuth2Config(BaseSettings):
    """Настройки OAuth2/OIDC интеграции"""

    enabled: bool = False
    providers: Dict[str, OAuth2ProviderConfig] = {}


class AuthConfig(BaseSettings):
    """Настройки аутентификации"""

    jwt: JWTConfig = JWTConfig()
    key_rotation: JWTKeyRotationConfig = JWTKeyRotationConfig()
    password_policy: PasswordPolicyConfig = PasswordPolicyConfig()


class ServiceDiscoveryConfig(BaseSettings):
    """Настройки Service Discovery"""

    enabled: bool = True
    publish_interval_seconds: int = 30
    health_check_interval_seconds: int = 10
    service_ttl_seconds: int = 60


class RaftNodeConfig(BaseSettings):
    """Настройки узла Raft кластера"""

    id: str
    host: str
    port: int


class RaftConfig(BaseSettings):
    """Настройки Raft Consensus"""

    enabled: bool = False
    node_id: str = "admin-node-1"
    cluster_nodes: List[RaftNodeConfig] = []
    election_timeout_ms: int = 1000
    heartbeat_interval_ms: int = 100
    data_dir: str = "./raft-data"


class VectorClockConfig(BaseSettings):
    """Настройки Vector Clocks"""

    enabled: bool = True
    node_id: str = "admin-node-1"


class SagaConfig(BaseSettings):
    """Настройки Saga Pattern"""

    enabled: bool = True
    timeout_seconds: int = 300
    retry_attempts: int = 3
    retry_delay_seconds: int = 5


class KafkaConfig(BaseSettings):
    """Настройки Kafka"""

    enabled: bool = False
    bootstrap_servers: List[str] = ["localhost:9092"]
    topic_prefix: str = "artstore"
    consumer_group: str = "admin-module"


class PrometheusConfig(BaseSettings):
    """Настройки Prometheus метрик"""

    enabled: bool = True
    endpoint: str = "/metrics"


class TracingConfig(BaseSettings):
    """Настройки OpenTelemetry трейсинга"""

    enabled: bool = True
    jaeger_host: str = "localhost"
    jaeger_port: int = 6831
    service_name: str = "admin-module"


class HealthConfig(BaseSettings):
    """Настройки health checks"""

    enabled: bool = True
    liveness: str = "/health/live"
    readiness: str = "/health/ready"


class MonitoringConfig(BaseSettings):
    """Настройки мониторинга"""

    prometheus: PrometheusConfig = PrometheusConfig()
    tracing: TracingConfig = TracingConfig()
    health: HealthConfig = HealthConfig()


class AuditConfig(BaseSettings):
    """Настройки audit логирования"""

    enabled: bool = True
    log_all_requests: bool = False
    log_auth_events: bool = True
    log_admin_actions: bool = True


class LoggingConfig(BaseSettings):
    """Настройки логирования"""

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    format: Literal["json", "text"] = "json"
    output: Literal["stdout", "file"] = "stdout"
    file_path: str = "./logs/admin-module.log"
    max_file_size_mb: int = 100
    backup_count: int = 5
    audit: AuditConfig = AuditConfig()


class CORSConfig(BaseSettings):
    """Настройки CORS"""

    enabled: bool = True
    allow_origins: List[str] = ["http://localhost:4200", "http://localhost:3000"]
    allow_credentials: bool = True
    allow_methods: List[str] = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    allow_headers: List[str] = ["Authorization", "Content-Type", "X-Request-ID"]


class RateLimitEndpointConfig(BaseSettings):
    """Настройки rate limit для конкретного endpoint"""

    limit: int
    period_seconds: int


class RateLimitingConfig(BaseSettings):
    """Настройки rate limiting"""

    enabled: bool = True
    default_limit: int = 100
    default_period_seconds: int = 60
    endpoints: Dict[str, RateLimitEndpointConfig] = {}


class TLSConfig(BaseSettings):
    """Настройки TLS/SSL"""

    enabled: bool = False
    cert_file: str = "./certs/server.crt"
    key_file: str = "./certs/server.key"


class BruteForceProtectionConfig(BaseSettings):
    """Защита от брутфорса"""

    enabled: bool = True
    max_attempts: int = 5
    lockout_duration_minutes: int = 15


class IPWhitelistConfig(BaseSettings):
    """IP Whitelisting"""

    enabled: bool = False
    addresses: List[str] = ["127.0.0.1", "::1"]


class SecurityConfig(BaseSettings):
    """Настройки безопасности"""

    tls: TLSConfig = TLSConfig()
    brute_force_protection: BruteForceProtectionConfig = BruteForceProtectionConfig()
    ip_whitelist: IPWhitelistConfig = IPWhitelistConfig()


class SystemConfig(BaseSettings):
    """Системные настройки"""

    protect_system_admin: bool = True
    system_admin_username: str = "admin"


class BackupConfig(BaseSettings):
    """Настройки резервного копирования"""

    enabled: bool = True
    schedule: str = "0 2 * * *"
    retention_days: int = 30
    backup_dir: str = "./backups"


class Config(BaseSettings):
    """Главная конфигурация приложения"""

    app: AppConfig = AppConfig()
    server: ServerConfig = ServerConfig()
    database: DatabaseConfig = DatabaseConfig()
    redis: RedisConfig = RedisConfig()
    auth: AuthConfig = AuthConfig()
    ldap: LDAPConfig = LDAPConfig()
    oauth: OAuth2Config = OAuth2Config()
    service_discovery: ServiceDiscoveryConfig = ServiceDiscoveryConfig()
    raft: RaftConfig = RaftConfig()
    vector_clock: VectorClockConfig = VectorClockConfig()
    saga: SagaConfig = SagaConfig()
    kafka: KafkaConfig = KafkaConfig()
    monitoring: MonitoringConfig = MonitoringConfig()
    logging: LoggingConfig = LoggingConfig()
    cors: CORSConfig = CORSConfig()
    rate_limiting: RateLimitingConfig = RateLimitingConfig()
    security: SecurityConfig = SecurityConfig()
    system: SystemConfig = SystemConfig()
    backup: BackupConfig = BackupConfig()
