# План разработки Admin Module

## Введение

Данный план разработки предназначен для джуниор разработчиков и содержит пошаговое руководство по созданию модуля администрирования системы ArtStore. План учитывает микросервисную архитектуру, требования высокой доступности и комплексной безопасности.

**Важно**: В текущей версии функционал отказоустойчивости (Raft consensus, clustering) должен отключаться для стадии тестирования. Реализация начинается с single-instance варианта с возможностью последующего масштабирования.

## Технологический стек

### Backend
- **Язык**: Python 3.12+
- **Web Framework**: FastAPI (асинхронный веб-фреймворк)
- **ORM**: SQLAlchemy 2.0+ (async mode)
- **Валидация данных**: Pydantic v2
- **База данных**: PostgreSQL 15+
- **Кеш**: Redis 7+ (синхронное соединение)
- **Миграции БД**: Alembic

### Безопасность
- **JWT библиотека**: python-jose[cryptography]
- **Хеширование паролей**: passlib с bcrypt
- **Криптография**: cryptography (для RS256 ключей)

### Мониторинг и логирование
- **Metrics**: prometheus-client
- **Tracing**: opentelemetry-api, opentelemetry-sdk
- **Logging**: structlog (structured logging в JSON)

### Тестирование
- **Framework**: pytest, pytest-asyncio
- **Coverage**: pytest-cov
- **HTTP тестирование**: httpx (async client для FastAPI)

### Дополнительные библиотеки
- **Redis client**: redis-py
- **PostgreSQL driver**: asyncpg
- **Конфигурация**: pyyaml
- **LDAP интеграция**: python-ldap, ldap3 (современная async библиотека)
- **OAuth2 интеграция**: authlib (универсальный OAuth2/OIDC клиент)
- **HTTP клиент**: httpx (для OAuth2 запросов)

---

## Этап 1: Подготовка инфраструктуры проекта

### 1.1 Структура директорий

Создайте следующую структуру проекта:

```
admin-module/
├── app/
│   ├── __init__.py
│   ├── main.py                    # Точка входа FastAPI приложения
│   ├── config.py                  # Загрузка конфигурации из config.yaml
│   ├── dependencies.py            # FastAPI dependencies (DB session, auth, etc.)
│   │
│   ├── core/                      # Ядро системы
│   │   ├── __init__.py
│   │   ├── security.py           # JWT, хеширование паролей
│   │   ├── config_models.py      # Pydantic модели для конфигурации
│   │   └── exceptions.py         # Кастомные исключения
│   │
│   ├── db/                        # База данных
│   │   ├── __init__.py
│   │   ├── base.py               # Импорт всех моделей для Alembic
│   │   ├── session.py            # Async engine и session maker
│   │   └── models/               # SQLAlchemy модели
│   │       ├── __init__.py
│   │       ├── user.py           # Модель пользователя
│   │       ├── storage_element.py # Модель элемента хранения
│   │       └── audit_log.py      # Модель audit логов
│   │
│   ├── schemas/                   # Pydantic схемы (request/response)
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── auth.py
│   │   ├── storage_element.py
│   │   └── common.py             # Общие схемы (pagination, responses)
│   │
│   ├── services/                  # Бизнес-логика
│   │   ├── __init__.py
│   │   ├── auth_service.py       # Аутентификация и авторизация
│   │   ├── user_service.py       # Управление пользователями
│   │   ├── storage_service.py    # Управление storage elements
│   │   ├── jwt_key_service.py    # Управление JWT ключами и ротация
│   │   ├── audit_service.py      # Audit logging
│   │   ├── redis_service.py      # Service Discovery через Redis
│   │   ├── ldap_service.py       # LDAP интеграция
│   │   └── oauth2_service.py     # OAuth2 интеграция
│   │
│   ├── api/                       # API endpoints
│   │   ├── __init__.py
│   │   ├── router.py             # Главный роутер, объединяющий все endpoints
│   │   └── endpoints/
│   │       ├── __init__.py
│   │       ├── auth.py           # /api/auth/*
│   │       ├── users.py          # /api/users/*
│   │       ├── storage_elements.py # /api/storage-elements/*
│   │       ├── transactions.py   # /api/transactions/* (будущее)
│   │       ├── admin.py          # /api/admin/*
│   │       └── health.py         # /health/*, /metrics
│   │
│   ├── middleware/                # Middleware компоненты
│   │   ├── __init__.py
│   │   ├── logging_middleware.py # Structured logging
│   │   ├── tracing_middleware.py # OpenTelemetry tracing
│   │   └── error_handler.py      # Глобальная обработка ошибок
│   │
│   └── utils/                     # Утилиты
│       ├── __init__.py
│       ├── logger.py             # Настройка structlog
│       ├── metrics.py            # Prometheus metrics
│       └── helpers.py            # Вспомогательные функции
│
├── tests/                         # Unit и integration тесты
│   ├── __init__.py
│   ├── conftest.py               # Pytest fixtures
│   ├── test_auth.py
│   ├── test_users.py
│   └── test_storage_elements.py
│
├── alembic/                       # Миграции БД
│   ├── versions/
│   └── env.py
│
├── keys/                          # JWT ключи (НЕ коммитить!)
│   ├── jwt-private.pem
│   └── jwt-public.pem
│
├── config.yaml                    # Конфигурация приложения
├── requirements.txt               # Python зависимости
├── Dockerfile                     # Docker образ
└── README.md                      # Документация модуля
```

**Пояснения для джуниоров**:
- `app/` - основной код приложения
- `core/` - базовый функционал (security, config)
- `db/` - всё, что связано с базой данных
- `schemas/` - валидация входящих/исходящих данных через Pydantic
- `services/` - бизнес-логика (НЕ содержит FastAPI кода)
- `api/` - HTTP endpoints (используют services)
- `middleware/` - код, выполняющийся для каждого запроса
- `tests/` - автоматические тесты

### 1.2 Файл requirements.txt

Создайте `requirements.txt` со следующими зависимостями:

```txt
# Web Framework
fastapi==0.109.0
uvicorn[standard]==0.27.0
python-multipart==0.0.6

# Database
sqlalchemy[asyncio]==2.0.25
asyncpg==0.29.0
alembic==1.13.1

# Validation
pydantic==2.5.3
pydantic-settings==2.1.0
email-validator==2.1.0

# Security
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
cryptography==42.0.0

# Redis
redis==5.0.1

# Configuration
pyyaml==6.0.1

# Logging
structlog==24.1.0

# Monitoring
prometheus-client==0.19.0
opentelemetry-api==1.22.0
opentelemetry-sdk==1.22.0
opentelemetry-instrumentation-fastapi==0.43b0

# LDAP Integration
ldap3==2.9.1

# OAuth2 Integration
authlib==1.3.0
httpx==0.26.0

# Testing
pytest==7.4.4
pytest-asyncio==0.23.3
pytest-cov==4.1.0

# Development
black==23.12.1
flake8==7.0.0
mypy==1.8.0
```

**Установка зависимостей**:
```bash
cd admin-module
py -m pip install -r requirements.txt
```

### 1.3 Конфигурационный файл config.yaml

Создайте базовый `config.yaml`:

```yaml
# Настройки сервера
server:
  host: "0.0.0.0"
  port: 8000
  debug: true
  cors_origins:
    - "http://localhost:3000"
    - "http://localhost:4200"
  title: "ArtStore Admin Module API"
  version: "1.0.0"

# База данных PostgreSQL
database:
  url: "postgresql+asyncpg://artstore:password@localhost:5432/admin_module"
  pool_size: 10
  max_overflow: 20
  echo: false  # SQL logging (true для отладки)

# Redis для Service Discovery и кеширования
redis:
  host: "localhost"
  port: 6379
  db: 0
  decode_responses: true
  socket_connect_timeout: 5
  socket_timeout: 5

# Настройки аутентификации
auth:
  # JWT токены (RS256)
  jwt:
    algorithm: "RS256"
    private_key_path: "keys/jwt-private.pem"
    public_key_path: "keys/jwt-public.pem"
    access_token_expire_minutes: 30
    refresh_token_expire_days: 7
    issuer: "artstore-admin"

  # Административный пользователь по умолчанию
  default_admin:
    username: "admin"
    email: "admin@artstore.local"
    password: "admin123"  # ИЗМЕНИТЬ В PRODUCTION!
    full_name: "Системный администратор"
    description: "Пользователь администратора системы по умолчанию"

  # LDAP конфигурация (опционально)
  ldap:
    enabled: false
    server: "ldap://localhost:3389"
    bind_dn: "cn=Directory Manager"
    bind_password: "password"
    base_dn: "dc=example,dc=com"
    user_search_filter: "(uid={username})"
    user_attributes:
      username: "uid"
      email: "mail"
      full_name: "cn"
    group_search_filter: "(memberUid={username})"
    admin_groups:
      - "cn=admins,ou=groups,dc=example,dc=com"
    connection_timeout: 5
    use_ssl: false
    # Синхронизация пользователей из LDAP в локальную БД
    sync_users: true
    # Автоматическое создание пользователей при первом входе
    auto_create_users: true

  # OAuth2/OIDC конфигурация (опционально)
  oauth2:
    enabled: false
    providers:
      # Dex (OIDC провайдер)
      dex:
        enabled: true
        client_id: "artstore-admin"
        client_secret: "your-client-secret"
        server_metadata_url: "http://localhost:5556/dex/.well-known/openid-configuration"
        # Или явная конфигурация endpoints
        authorize_url: "http://localhost:5556/dex/auth"
        token_url: "http://localhost:5556/dex/token"
        userinfo_url: "http://localhost:5556/dex/userinfo"
        jwks_uri: "http://localhost:5556/dex/keys"
        scopes:
          - openid
          - profile
          - email
          - groups
        # Маппинг полей из OAuth2 в нашу систему
        user_mapping:
          username: "preferred_username"
          email: "email"
          full_name: "name"
          groups: "groups"
        # Группы администраторов в OAuth2
        admin_groups:
          - "admins"
        # Автоматическое создание пользователей
        auto_create_users: true

      # Google OAuth2 (пример)
      google:
        enabled: false
        client_id: "your-google-client-id.apps.googleusercontent.com"
        client_secret: "your-google-client-secret"
        server_metadata_url: "https://accounts.google.com/.well-known/openid-configuration"
        scopes:
          - openid
          - email
          - profile
        user_mapping:
          username: "email"
          email: "email"
          full_name: "name"
        # Для Google нет групп, администраторов назначаем по email
        admin_emails:
          - "admin@example.com"
        auto_create_users: true

# Логирование
logging:
  level: "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
  format: "json"  # json или text

  handlers:
    console:
      enabled: true
    file:
      enabled: false
      path: "/app/logs/admin-module.log"
      max_bytes: 104857600  # 100MB
      backup_count: 5
    network:
      enabled: false
      protocol: "syslog"  # syslog или http
      host: "log-server"
      port: 514

# Метрики Prometheus
metrics:
  enabled: true
  path: "/metrics"

# OpenTelemetry Tracing
tracing:
  enabled: true
  service_name: "admin-module"
  # Jaeger exporter (опционально)
  jaeger:
    enabled: false
    host: "localhost"
    port: 6831

# Настройки безопасности
security:
  # Защита системного администратора
  protect_default_admin: true
  # Минимальная длина пароля
  password_min_length: 8
  # Требовать сложные пароли
  password_require_complexity: true

# Feature flags (функции для будущей разработки)
features:
  # Высокая доступность (Raft consensus)
  clustering_enabled: false
  # Saga Orchestrator для распределенных транзакций
  saga_enabled: false
  # Vector Clock для упорядочивания событий
  vector_clock_enabled: false
  # LDAP интеграция
  ldap_enabled: false
  # OAuth2 интеграция
  oauth2_enabled: false
```

**Пояснения**:
- Конфигурация разделена на логические блоки
- Все пароли и секреты должны быть изменены в production
- Feature flags позволяют отключать сложные функции на этапе разработки
- Значения можно переопределить через переменные окружения

---

## Этап 2: Базовая инфраструктура (Core)

### 2.1 Конфигурация приложения (app/config.py)

**Цель**: Загрузка настроек из `config.yaml` и переменных окружения.

**Технологии**: Pydantic Settings, PyYAML

**Создайте файл `app/core/config_models.py`**:

```python
"""
Pydantic модели для конфигурации приложения.
Используются для валидации config.yaml и переменных окружения.
"""
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings
from typing import List, Literal, Optional, Dict


class ServerConfig(BaseSettings):
    """Настройки HTTP сервера"""
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    cors_origins: List[str] = []
    title: str = "ArtStore Admin Module"
    version: str = "1.0.0"


class DatabaseConfig(BaseSettings):
    """Настройки PostgreSQL"""
    url: str
    pool_size: int = 10
    max_overflow: int = 20
    echo: bool = False


class RedisConfig(BaseSettings):
    """Настройки Redis"""
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    decode_responses: bool = True
    socket_connect_timeout: int = 5
    socket_timeout: int = 5


class JWTConfig(BaseSettings):
    """Настройки JWT токенов"""
    algorithm: Literal["RS256"] = "RS256"
    private_key_path: str
    public_key_path: str
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    issuer: str = "artstore-admin"


class DefaultAdminConfig(BaseSettings):
    """Настройки администратора по умолчанию"""
    username: str
    email: str
    password: str
    full_name: str
    description: str = ""


class LDAPUserAttributesConfig(BaseSettings):
    """Маппинг LDAP атрибутов на поля пользователя"""
    username: str = "uid"
    email: str = "mail"
    full_name: str = "cn"


class LDAPConfig(BaseSettings):
    """Настройки LDAP интеграции"""
    enabled: bool = False
    server: str = "ldap://localhost:389"
    bind_dn: str = ""
    bind_password: str = ""
    base_dn: str = ""
    user_search_filter: str = "(uid={username})"
    user_attributes: LDAPUserAttributesConfig = LDAPUserAttributesConfig()
    group_search_filter: str = "(memberUid={username})"
    admin_groups: List[str] = []
    connection_timeout: int = 5
    use_ssl: bool = False
    sync_users: bool = True
    auto_create_users: bool = True


class OAuth2UserMappingConfig(BaseSettings):
    """Маппинг OAuth2 claims на поля пользователя"""
    username: str = "preferred_username"
    email: str = "email"
    full_name: str = "name"
    groups: str = "groups"


class OAuth2ProviderConfig(BaseSettings):
    """Настройки одного OAuth2 провайдера"""
    enabled: bool = False
    client_id: str = ""
    client_secret: str = ""
    server_metadata_url: Optional[str] = None
    # Explicit endpoints (если server_metadata_url не указан)
    authorize_url: Optional[str] = None
    token_url: Optional[str] = None
    userinfo_url: Optional[str] = None
    jwks_uri: Optional[str] = None
    scopes: List[str] = ["openid", "profile", "email"]
    user_mapping: OAuth2UserMappingConfig = OAuth2UserMappingConfig()
    admin_groups: List[str] = []
    admin_emails: List[str] = []
    auto_create_users: bool = True


class OAuth2Config(BaseSettings):
    """Настройки OAuth2/OIDC интеграции"""
    enabled: bool = False
    providers: Dict[str, OAuth2ProviderConfig] = {}


class AuthConfig(BaseSettings):
    """Настройки аутентификации"""
    jwt: JWTConfig
    default_admin: DefaultAdminConfig
    ldap: LDAPConfig = LDAPConfig()
    oauth2: OAuth2Config = OAuth2Config()


class LogHandlerConfig(BaseSettings):
    """Настройки обработчика логов"""
    enabled: bool = False


class LogFileHandlerConfig(LogHandlerConfig):
    """Настройки файлового обработчика логов"""
    path: str = "/app/logs/admin-module.log"
    max_bytes: int = 104857600  # 100MB
    backup_count: int = 5


class LogNetworkHandlerConfig(LogHandlerConfig):
    """Настройки сетевого обработчика логов"""
    protocol: Literal["syslog", "http"] = "syslog"
    host: str = "log-server"
    port: int = 514


class LogHandlersConfig(BaseSettings):
    """Все обработчики логов"""
    console: LogHandlerConfig
    file: LogFileHandlerConfig
    network: LogNetworkHandlerConfig


class LoggingConfig(BaseSettings):
    """Настройки логирования"""
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    format: Literal["json", "text"] = "json"
    handlers: LogHandlersConfig


class MetricsConfig(BaseSettings):
    """Настройки Prometheus метрик"""
    enabled: bool = True
    path: str = "/metrics"


class JaegerConfig(BaseSettings):
    """Настройки Jaeger exporter"""
    enabled: bool = False
    host: str = "localhost"
    port: int = 6831


class TracingConfig(BaseSettings):
    """Настройки OpenTelemetry tracing"""
    enabled: bool = True
    service_name: str = "admin-module"
    jaeger: JaegerConfig


class SecurityConfig(BaseSettings):
    """Настройки безопасности"""
    protect_default_admin: bool = True
    password_min_length: int = 8
    password_require_complexity: bool = True


class FeaturesConfig(BaseSettings):
    """Feature flags"""
    clustering_enabled: bool = False
    saga_enabled: bool = False
    vector_clock_enabled: bool = False
    ldap_enabled: bool = False
    oauth2_enabled: bool = False


class Config(BaseSettings):
    """Главная конфигурация приложения"""
    server: ServerConfig
    database: DatabaseConfig
    redis: RedisConfig
    auth: AuthConfig
    logging: LoggingConfig
    metrics: MetricsConfig
    tracing: TracingConfig
    security: SecurityConfig
    features: FeaturesConfig
```

**Создайте файл `app/config.py`**:

```python
"""
Загрузка конфигурации из config.yaml с возможностью переопределения через env vars.
"""
import yaml
from pathlib import Path
from app.core.config_models import Config


def load_config(config_path: str = "config.yaml") -> Config:
    """
    Загружает конфигурацию из YAML файла.

    Args:
        config_path: Путь к файлу config.yaml

    Returns:
        Объект Config с валидированными настройками

    Raises:
        FileNotFoundError: Если config.yaml не найден
        ValueError: Если конфигурация невалидна
    """
    config_file = Path(config_path)

    if not config_file.exists():
        raise FileNotFoundError(f"Конфигурационный файл {config_path} не найден")

    # Загрузка YAML
    with open(config_file, 'r', encoding='utf-8') as f:
        config_dict = yaml.safe_load(f)

    # Валидация через Pydantic
    # Переменные окружения автоматически переопределят значения из YAML
    config = Config(**config_dict)

    return config


# Глобальный экземпляр конфигурации
settings = load_config()
```

**Пояснения для джуниоров**:
1. **Pydantic Models** - автоматическая валидация типов данных
2. **BaseSettings** - поддержка переменных окружения
3. **Literal** - ограничение возможных значений (например, только "json" или "text")
4. **YAML safe_load** - безопасная загрузка YAML без выполнения кода

### 2.2 Генерация JWT ключей

**Цель**: Создать пару ключей RS256 для подписи JWT токенов.

**Создайте скрипт `scripts/generate_jwt_keys.py`**:

```python
"""
Скрипт для генерации пары ключей RS256 для JWT токенов.
Запускать: py scripts/generate_jwt_keys.py
"""
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from pathlib import Path


def generate_rsa_keypair(
    private_key_path: str = "keys/jwt-private.pem",
    public_key_path: str = "keys/jwt-public.pem"
):
    """
    Генерирует пару RSA ключей для JWT подписи.

    Args:
        private_key_path: Путь для сохранения приватного ключа
        public_key_path: Путь для сохранения публичного ключа
    """
    # Создаем директорию keys, если не существует
    keys_dir = Path("keys")
    keys_dir.mkdir(exist_ok=True)

    # Генерация приватного ключа RSA 2048 бит
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )

    # Сериализация приватного ключа в PEM формат
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()  # Без пароля
    )

    # Извлечение публичного ключа
    public_key = private_key.public_key()

    # Сериализация публичного ключа в PEM формат
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    # Сохранение ключей
    with open(private_key_path, 'wb') as f:
        f.write(private_pem)
    print(f"✓ Приватный ключ сохранен: {private_key_path}")

    with open(public_key_path, 'wb') as f:
        f.write(public_pem)
    print(f"✓ Публичный ключ сохранен: {public_key_path}")

    print("\n⚠️  ВАЖНО: Добавьте keys/ в .gitignore!")
    print("⚠️  НЕ коммитьте приватный ключ в репозиторий!")


if __name__ == "__main__":
    generate_rsa_keypair()
```

**Запуск**:
```bash
py scripts/generate_jwt_keys.py
```

**Добавьте в `.gitignore`**:
```
keys/
*.pem
```

**Пояснения**:
- **RS256** - асимметричный алгоритм (приватный ключ подписывает, публичный проверяет)
- **2048 бит** - безопасный размер ключа (больше = безопаснее, но медленнее)
- **PEM формат** - стандартный текстовый формат для ключей
- **NoEncryption** - ключ не защищен паролем (для упрощения, в production можно добавить)

### 2.3 Безопасность (app/core/security.py)

**Цель**: Функции для JWT токенов и хеширования паролей.

```python
"""
Функции безопасности: JWT токены, хеширование паролей, валидация.
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import jwt, JWTError
from passlib.context import CryptContext
from pathlib import Path
from app.config import settings

# Контекст для хеширования паролей (bcrypt)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def load_rsa_key(key_path: str, is_private: bool = False) -> str:
    """
    Загружает RSA ключ из файла.

    Args:
        key_path: Путь к PEM файлу
        is_private: True для приватного ключа, False для публичного

    Returns:
        Содержимое ключа в виде строки

    Raises:
        FileNotFoundError: Если файл ключа не найден
    """
    key_file = Path(key_path)
    if not key_file.exists():
        key_type = "приватного" if is_private else "публичного"
        raise FileNotFoundError(
            f"Файл {key_type} ключа не найден: {key_path}\n"
            f"Сгенерируйте ключи командой: py scripts/generate_jwt_keys.py"
        )

    with open(key_file, 'r') as f:
        return f.read()


# Загрузка ключей при старте приложения
PRIVATE_KEY = load_rsa_key(settings.auth.jwt.private_key_path, is_private=True)
PUBLIC_KEY = load_rsa_key(settings.auth.jwt.public_key_path, is_private=False)


def hash_password(password: str) -> str:
    """
    Хеширует пароль с использованием bcrypt.

    Args:
        password: Пароль в открытом виде

    Returns:
        Хешированный пароль

    Example:
        >>> hashed = hash_password("mypassword123")
        >>> verify_password("mypassword123", hashed)
        True
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Проверяет соответствие пароля хешу.

    Args:
        plain_password: Пароль в открытом виде
        hashed_password: Хешированный пароль

    Returns:
        True если пароль верный, иначе False
    """
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Создает JWT access токен, подписанный приватным ключом RS256.

    Args:
        data: Payload токена (например, {"sub": "user_id", "is_admin": True})
        expires_delta: Время жизни токена (по умолчанию из конфигурации)

    Returns:
        JWT токен в виде строки

    Example:
        >>> token = create_access_token({"sub": "123", "username": "admin"})
    """
    to_encode = data.copy()

    # Установка времени истечения
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.auth.jwt.access_token_expire_minutes
        )

    # Добавление стандартных JWT claims
    to_encode.update({
        "exp": expire,                          # Expiration time
        "iat": datetime.utcnow(),              # Issued at
        "iss": settings.auth.jwt.issuer,       # Issuer
        "type": "access"                       # Тип токена
    })

    # Подпись токена приватным ключом
    encoded_jwt = jwt.encode(
        to_encode,
        PRIVATE_KEY,
        algorithm=settings.auth.jwt.algorithm
    )
    return encoded_jwt


def create_refresh_token(data: Dict[str, Any]) -> str:
    """
    Создает JWT refresh токен с длительным сроком действия.

    Args:
        data: Payload токена (обычно только {"sub": "user_id"})

    Returns:
        JWT refresh токен
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(
        days=settings.auth.jwt.refresh_token_expire_days
    )

    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "iss": settings.auth.jwt.issuer,
        "type": "refresh"  # Важно: отличается от access токена
    })

    encoded_jwt = jwt.encode(
        to_encode,
        PRIVATE_KEY,
        algorithm=settings.auth.jwt.algorithm
    )
    return encoded_jwt


def decode_token(token: str) -> Dict[str, Any]:
    """
    Декодирует и валидирует JWT токен.

    Args:
        token: JWT токен для проверки

    Returns:
        Payload токена (dict)

    Raises:
        JWTError: Если токен невалиден или истек

    Example:
        >>> payload = decode_token(token)
        >>> user_id = payload["sub"]
    """
    try:
        payload = jwt.decode(
            token,
            PUBLIC_KEY,
            algorithms=[settings.auth.jwt.algorithm],
            issuer=settings.auth.jwt.issuer
        )
        return payload
    except JWTError as e:
        raise JWTError(f"Невалидный токен: {str(e)}")


def validate_password_strength(password: str) -> tuple[bool, Optional[str]]:
    """
    Проверяет надежность пароля согласно политике безопасности.

    Args:
        password: Пароль для проверки

    Returns:
        Tuple (валиден, сообщение об ошибке)

    Example:
        >>> valid, error = validate_password_strength("weak")
        >>> if not valid:
        >>>     print(error)
    """
    min_length = settings.security.password_min_length

    # Проверка минимальной длины
    if len(password) < min_length:
        return False, f"Пароль должен быть не менее {min_length} символов"

    # Проверка сложности (если включена)
    if settings.security.password_require_complexity:
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)

        if not (has_upper and has_lower and has_digit):
            return False, (
                "Пароль должен содержать заглавные и строчные буквы, "
                "а также цифры"
            )

    return True, None
```

**Пояснения для джуниоров**:
- **bcrypt** - современный алгоритм хеширования паролей (медленный = безопасный)
- **JWT payload** - данные, хранящиеся в токене (НЕ секретные!)
- **exp, iat, iss** - стандартные JWT claims
- **RS256** - только Admin Module может создавать токены, остальные только проверяют

---

## Этап 3: База данных и модели

### 3.1 Настройка SQLAlchemy (app/db/session.py)

**Цель**: Создать async engine и session maker для работы с PostgreSQL.

```python
"""
Настройка асинхронного подключения к PostgreSQL.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.config import settings

# Создание async engine
engine = create_async_engine(
    settings.database.url,
    pool_size=settings.database.pool_size,
    max_overflow=settings.database.max_overflow,
    echo=settings.database.echo,  # Логирование SQL запросов
    future=True
)

# Создание session maker
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Объекты доступны после commit
    autocommit=False,
    autoflush=False
)

# Базовый класс для моделей
Base = declarative_base()


async def get_db() -> AsyncSession:
    """
    Dependency для получения DB session в FastAPI endpoints.

    Usage:
        @app.get("/users/")
        async def get_users(db: AsyncSession = Depends(get_db)):
            ...

    Yields:
        AsyncSession для выполнения запросов
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """
    Инициализация БД: создание всех таблиц.
    Вызывается при старте приложения.
    """
    async with engine.begin() as conn:
        # Создание всех таблиц
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """
    Закрытие соединений с БД.
    Вызывается при остановке приложения.
    """
    await engine.dispose()
```

**Пояснения**:
- **async engine** - асинхронные запросы к БД (не блокируют event loop)
- **pool_size** - количество постоянных соединений
- **max_overflow** - дополнительные соединения при пиковой нагрузке
- **expire_on_commit=False** - объекты доступны после commit (важно для async)

### 3.2 Модель User (app/db/models/user.py)

**Цель**: SQLAlchemy модель для хранения пользователей.

```python
"""
Модель пользователя системы.
"""
from sqlalchemy import Column, String, Boolean, DateTime, Text, Integer
from sqlalchemy.sql import func
from app.db.session import Base
import uuid


def generate_uuid():
    """Генерация UUID v4 для ID пользователя"""
    return str(uuid.uuid4())


class User(Base):
    """
    Модель пользователя.

    Атрибуты:
        id: Уникальный идентификатор (UUID)
        username: Имя пользователя (уникальное)
        email: Email (уникальный)
        hashed_password: Bcrypt хеш пароля
        full_name: Полное имя
        is_active: Активен ли пользователь
        is_admin: Является ли администратором
        is_system: Системный пользователь (защищен от удаления)
        description: Описание пользователя
        created_at: Дата создания
        updated_at: Дата последнего обновления
    """
    __tablename__ = "users"

    # Первичный ключ
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)

    # Основные данные
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)

    # Статусы
    is_active = Column(Boolean, default=True, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    is_system = Column(Boolean, default=False, nullable=False)

    # Дополнительная информация
    description = Column(Text, nullable=True)

    # Метаданные
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<User(id={self.id}, username={self.username}, is_admin={self.is_admin})>"

    @property
    def is_protected(self) -> bool:
        """
        Проверка, защищен ли пользователь от изменений.
        Системный пользователь не может быть удален или лишен прав администратора.
        """
        return self.is_system
```

**Пояснения**:
- **UUID** - уникальный идентификатор (лучше чем auto-increment ID)
- **unique=True** - гарантия уникальности username и email на уровне БД
- **index=True** - ускорение поиска по колонке
- **server_default=func.now()** - значение по умолчанию на уровне БД
- **onupdate=func.now()** - автоматическое обновление при изменении записи
- **is_system** - флаг защиты для default admin

### 3.3 Модель Storage Element (app/db/models/storage_element.py)

```python
"""
Модель элемента хранения.
"""
from sqlalchemy import Column, String, Boolean, DateTime, Text, Integer, Enum, JSON
from sqlalchemy.sql import func
from app.db.session import Base
import uuid
import enum


def generate_uuid():
    return str(uuid.uuid4())


class StorageMode(str, enum.Enum):
    """Режимы работы элемента хранения"""
    EDIT = "edit"  # Полный CRUD
    RW = "rw"      # Read-Write без удаления
    RO = "ro"      # Read-Only
    AR = "ar"      # Archive (только метаданные)


class StorageElement(Base):
    """
    Модель элемента хранения.

    Атрибуты:
        id: Уникальный идентификатор
        name: Имя элемента (уникальное)
        description: Описание
        mode: Режим работы (edit, rw, ro, ar)
        base_url: URL для доступа к элементу
        storage_type: Тип хранения (local или s3)
        max_size_gb: Максимальный размер в ГБ
        retention_days: Срок хранения в днях (0 = без ограничений)
        is_active: Активен ли элемент
        health_check_url: URL для проверки здоровья
        metadata: Дополнительные метаданные (JSON)
        created_at: Дата создания
        updated_at: Дата обновления
    """
    __tablename__ = "storage_elements"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)

    # Основные данные
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    mode = Column(Enum(StorageMode), default=StorageMode.EDIT, nullable=False, index=True)

    # Конфигурация доступа
    base_url = Column(String(500), nullable=False)
    health_check_url = Column(String(500), nullable=True)

    # Параметры хранения
    storage_type = Column(String(20), default="local", nullable=False)  # local или s3
    max_size_gb = Column(Integer, nullable=True)  # NULL = без ограничений
    retention_days = Column(Integer, default=0, nullable=False)  # 0 = без ограничений

    # Статус
    is_active = Column(Boolean, default=True, nullable=False)

    # Дополнительные данные
    metadata = Column(JSON, nullable=True)

    # Метаданные
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<StorageElement(id={self.id}, name={self.name}, mode={self.mode})>"

    @property
    def can_write(self) -> bool:
        """Можно ли записывать файлы"""
        return self.mode in [StorageMode.EDIT, StorageMode.RW]

    @property
    def can_delete(self) -> bool:
        """Можно ли удалять файлы"""
        return self.mode == StorageMode.EDIT

    @property
    def is_archived(self) -> bool:
        """Находится ли в архивном режиме"""
        return self.mode == StorageMode.AR
```

**Пояснения**:
- **Enum** - ограниченный набор значений для mode
- **JSON** - гибкое хранение дополнительных параметров
- **Properties** - вычисляемые поля для удобства использования

### 3.4 Модель Audit Log (app/db/models/audit_log.py)

```python
"""
Модель журнала аудита (audit log).
"""
from sqlalchemy import Column, String, DateTime, Text, JSON, Index
from sqlalchemy.sql import func
from app.db.session import Base
import uuid


def generate_uuid():
    return str(uuid.uuid4())


class AuditLog(Base):
    """
    Журнал аудита всех операций в системе.

    Атрибуты:
        id: Уникальный идентификатор
        user_id: ID пользователя, выполнившего действие
        username: Имя пользователя (денормализация для быстрого поиска)
        action: Тип действия (login, create_user, delete_file, etc.)
        resource_type: Тип ресурса (user, storage_element, file)
        resource_id: ID ресурса
        details: Дополнительные детали операции (JSON)
        ip_address: IP адрес клиента
        user_agent: User-Agent браузера/клиента
        success: Успешно ли выполнена операция
        error_message: Сообщение об ошибке (если success=False)
        timestamp: Время операции
    """
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)

    # Информация о пользователе
    user_id = Column(String(36), nullable=True, index=True)  # NULL для анонимных действий
    username = Column(String(100), nullable=True, index=True)

    # Информация о действии
    action = Column(String(100), nullable=False, index=True)
    resource_type = Column(String(50), nullable=True, index=True)
    resource_id = Column(String(36), nullable=True, index=True)

    # Детали
    details = Column(JSON, nullable=True)

    # Информация о клиенте
    ip_address = Column(String(45), nullable=True)  # IPv6 поддержка
    user_agent = Column(Text, nullable=True)

    # Результат
    success = Column(Boolean, nullable=False, default=True, index=True)
    error_message = Column(Text, nullable=True)

    # Временная метка
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Композитные индексы для частых запросов
    __table_args__ = (
        Index('ix_audit_user_timestamp', 'user_id', 'timestamp'),
        Index('ix_audit_resource_timestamp', 'resource_type', 'resource_id', 'timestamp'),
        Index('ix_audit_action_timestamp', 'action', 'timestamp'),
    )

    def __repr__(self):
        return f"<AuditLog(id={self.id}, action={self.action}, user={self.username})>"
```

**Пояснения**:
- **Composite Indexes** - ускорение запросов по нескольким колонкам
- **Денормализация** - хранение username для быстрого поиска без JOIN
- **JSON details** - гибкое хранение разных типов деталей

### 3.5 Инициализация моделей (app/db/base.py)

```python
"""
Импорт всех моделей для Alembic.
ВАЖНО: Все модели должны быть импортированы здесь!
"""
from app.db.session import Base  # noqa
from app.db.models.user import User  # noqa
from app.db.models.storage_element import StorageElement  # noqa
from app.db.models.audit_log import AuditLog  # noqa
```

**Пояснения**:
- **noqa** - отключает предупреждения линтеров о неиспользуемых импортах
- Этот файл нужен для корректной работы Alembic миграций

---

**Итого на данный момент**: Мы создали базовую структуру проекта, конфигурацию, систему безопасности и модели базы данных.

---

## Этап 4: Интеграция с LDAP и OAuth2

### 4.1 Понимание архитектуры аутентификации

**Важная концепция**: Admin Module поддерживает три источника пользователей:

1. **Локальная БД** (local) - пользователи хранятся в PostgreSQL
2. **LDAP** - внешний каталог пользователей (Active Directory, OpenLDAP)
3. **OAuth2/OIDC** - федеративная аутентификация (Dex, Google, Azure AD)

**Гибридная модель**:
- **Внешняя аутентификация** (LDAP/OAuth2) - проверка учетных данных
- **Внутренняя авторизация** (JWT) - права доступа внутри системы
- **Синхронизация** - пользователи из внешних источников копируются в локальную БД

**Поток аутентификации**:
```
1. Пользователь → Admin Module (логин/пароль или OAuth2 redirect)
2. Admin Module → Внешний провайдер (LDAP/OAuth2) для проверки
3. Внешний провайдер → Admin Module (подтверждение или отказ)
4. Admin Module → Локальная БД (создание/обновление пользователя)
5. Admin Module → Пользователь (выдача внутреннего JWT токена RS256)
6. Пользователь → Другие модули (с JWT токеном)
7. Другие модули → Локальная валидация JWT (без обращения к Admin Module)
```

### 4.2 LDAP Service (app/services/ldap_service.py)

**Цель**: Аутентификация пользователей через LDAP/Active Directory.

**Технологии**: ldap3 (современная async библиотека)

```python
"""
Сервис для работы с LDAP.
Поддерживает аутентификацию, поиск пользователей и синхронизацию групп.
"""
from ldap3 import Server, Connection, ALL, SUBTREE
from ldap3.core.exceptions import LDAPException, LDAPBindError
from typing import Optional, Dict, List
from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class LDAPService:
    """
    Сервис для интеграции с LDAP.

    Основные функции:
    - Аутентификация пользователей
    - Поиск информации о пользователях
    - Получение групп пользователя
    - Проверка принадлежности к группам администраторов
    """

    def __init__(self):
        """Инициализация LDAP сервиса"""
        self.config = settings.auth.ldap

        if not self.config.enabled:
            logger.info("LDAP интеграция отключена")
            return

        # Создание LDAP сервера
        self.server = Server(
            self.config.server,
            get_info=ALL,
            use_ssl=self.config.use_ssl,
            connect_timeout=self.config.connection_timeout
        )

        logger.info(f"LDAP сервис инициализирован: {self.config.server}")

    def _get_admin_connection(self) -> Optional[Connection]:
        """
        Создает административное подключение к LDAP.
        Используется для поиска пользователей.

        Returns:
            Connection или None при ошибке
        """
        try:
            conn = Connection(
                self.server,
                user=self.config.bind_dn,
                password=self.config.bind_password,
                auto_bind=True
            )
            return conn
        except LDAPException as e:
            logger.error(f"Ошибка подключения к LDAP: {e}")
            return None

    def authenticate(self, username: str, password: str) -> tuple[bool, Optional[Dict]]:
        """
        Аутентификация пользователя через LDAP.

        Args:
            username: Имя пользователя
            password: Пароль

        Returns:
            Tuple (успех, данные_пользователя)
            данные_пользователя содержит: username, email, full_name, is_admin, groups

        Example:
            >>> success, user_data = ldap_service.authenticate("john", "password123")
            >>> if success:
            >>>     print(f"Пользователь {user_data['username']} успешно аутентифицирован")
        """
        if not self.config.enabled:
            logger.warning("LDAP отключен, но была попытка аутентификации")
            return False, None

        # Шаг 1: Поиск пользователя в LDAP через административное подключение
        admin_conn = self._get_admin_connection()
        if not admin_conn:
            return False, None

        try:
            # Формируем фильтр поиска
            search_filter = self.config.user_search_filter.format(username=username)

            # Поиск пользователя
            admin_conn.search(
                search_base=self.config.base_dn,
                search_filter=search_filter,
                search_scope=SUBTREE,
                attributes=['*']  # Получаем все атрибуты
            )

            if not admin_conn.entries:
                logger.warning(f"Пользователь {username} не найден в LDAP")
                return False, None

            # Получаем DN (Distinguished Name) пользователя
            user_entry = admin_conn.entries[0]
            user_dn = user_entry.entry_dn

            logger.info(f"Найден пользователь в LDAP: {user_dn}")

        except LDAPException as e:
            logger.error(f"Ошибка поиска пользователя в LDAP: {e}")
            return False, None
        finally:
            admin_conn.unbind()

        # Шаг 2: Попытка bind с учетными данными пользователя
        try:
            user_conn = Connection(
                self.server,
                user=user_dn,
                password=password,
                auto_bind=True
            )

            logger.info(f"Успешная аутентификация пользователя {username} через LDAP")

            # Шаг 3: Получение данных пользователя
            user_data = self._extract_user_data(user_entry)

            # Шаг 4: Получение групп пользователя
            groups = self._get_user_groups(user_dn, user_conn)
            user_data['groups'] = groups

            # Шаг 5: Проверка является ли администратором
            user_data['is_admin'] = self._is_admin_user(groups)

            user_conn.unbind()

            return True, user_data

        except LDAPBindError as e:
            logger.warning(f"Неверные учетные данные для пользователя {username}: {e}")
            return False, None
        except LDAPException as e:
            logger.error(f"Ошибка LDAP при аутентификации: {e}")
            return False, None

    def _extract_user_data(self, ldap_entry) -> Dict:
        """
        Извлекает данные пользователя из LDAP entry.

        Args:
            ldap_entry: Объект LDAP entry

        Returns:
            Dict с полями: username, email, full_name
        """
        attrs = self.config.user_attributes

        # Безопасное извлечение атрибутов
        def get_attr(attr_name: str, default: str = "") -> str:
            try:
                value = ldap_entry[attr_name].value
                return str(value) if value else default
            except (KeyError, AttributeError):
                return default

        return {
            'username': get_attr(attrs.username),
            'email': get_attr(attrs.email),
            'full_name': get_attr(attrs.full_name),
        }

    def _get_user_groups(self, user_dn: str, connection: Connection) -> List[str]:
        """
        Получает список групп, в которых состоит пользователь.

        Args:
            user_dn: Distinguished Name пользователя
            connection: Активное LDAP подключение

        Returns:
            Список DN групп
        """
        try:
            # Формируем фильтр для поиска групп
            search_filter = self.config.group_search_filter.format(
                username=user_dn
            )

            connection.search(
                search_base=self.config.base_dn,
                search_filter=search_filter,
                search_scope=SUBTREE,
                attributes=['cn', 'dn']
            )

            groups = [entry.entry_dn for entry in connection.entries]
            logger.debug(f"Найдено {len(groups)} групп для пользователя")

            return groups

        except LDAPException as e:
            logger.error(f"Ошибка получения групп пользователя: {e}")
            return []

    def _is_admin_user(self, user_groups: List[str]) -> bool:
        """
        Проверяет, является ли пользователь администратором.

        Args:
            user_groups: Список DN групп пользователя

        Returns:
            True если пользователь в одной из админских групп
        """
        admin_groups = self.config.admin_groups

        for group_dn in user_groups:
            if group_dn in admin_groups:
                logger.info(f"Пользователь является администратором (группа: {group_dn})")
                return True

        return False

    def search_user(self, username: str) -> Optional[Dict]:
        """
        Поиск пользователя в LDAP без аутентификации.
        Используется для синхронизации пользователей.

        Args:
            username: Имя пользователя для поиска

        Returns:
            Dict с данными пользователя или None
        """
        if not self.config.enabled:
            return None

        conn = self._get_admin_connection()
        if not conn:
            return None

        try:
            search_filter = self.config.user_search_filter.format(username=username)

            conn.search(
                search_base=self.config.base_dn,
                search_filter=search_filter,
                search_scope=SUBTREE,
                attributes=['*']
            )

            if conn.entries:
                user_entry = conn.entries[0]
                user_data = self._extract_user_data(user_entry)

                # Получаем группы
                groups = self._get_user_groups(user_entry.entry_dn, conn)
                user_data['groups'] = groups
                user_data['is_admin'] = self._is_admin_user(groups)

                return user_data

            return None

        except LDAPException as e:
            logger.error(f"Ошибка поиска пользователя {username}: {e}")
            return None
        finally:
            conn.unbind()


# Глобальный экземпляр сервиса
ldap_service = LDAPService()
```

**Пояснения для джуниоров**:
- **bind_dn** - административный пользователь для поиска в LDAP
- **Distinguished Name (DN)** - уникальный путь к объекту в LDAP (например: cn=john,ou=users,dc=example,dc=com)
- **search_filter** - LDAP запрос для поиска пользователей (например: (uid=john))
- **SUBTREE** - поиск во всех подразделах базового DN
- **auto_bind=True** - автоматическая попытка подключения при создании Connection

### 4.3 OAuth2 Service (app/services/oauth2_service.py)

**Цель**: Аутентификация через OAuth2/OIDC провайдеры (Dex, Google, etc).

**Технологии**: authlib (универсальная OAuth2 библиотека), httpx

```python
"""
Сервис для работы с OAuth2/OIDC провайдерами.
Поддерживает множественных провайдеров (Dex, Google, Azure AD и др.)
"""
from authlib.integrations.starlette_client import OAuth
from authlib.oauth2.rfc6749 import OAuth2Token
from typing import Optional, Dict, List
import httpx
from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class OAuth2Service:
    """
    Сервис для интеграции с OAuth2/OIDC провайдерами.

    Основные функции:
    - Инициализация OAuth2 клиентов для каждого провайдера
    - Получение authorization URL для redirect
    - Обмен authorization code на access token
    - Получение информации о пользователе
    - Проверка прав администратора
    """

    def __init__(self):
        """Инициализация OAuth2 сервиса"""
        self.config = settings.auth.oauth2
        self.oauth = OAuth()
        self.providers = {}

        if not self.config.enabled:
            logger.info("OAuth2 интеграция отключена")
            return

        # Регистрация всех активных провайдеров
        for provider_name, provider_config in self.config.providers.items():
            if provider_config.enabled:
                self._register_provider(provider_name, provider_config)

        logger.info(f"OAuth2 сервис инициализирован с {len(self.providers)} провайдерами")

    def _register_provider(self, name: str, config):
        """
        Регистрирует OAuth2 провайдера.

        Args:
            name: Имя провайдера (dex, google, etc)
            config: Конфигурация провайдера
        """
        try:
            # Authlib поддерживает автоматическое получение endpoints через .well-known
            if config.server_metadata_url:
                self.oauth.register(
                    name=name,
                    client_id=config.client_id,
                    client_secret=config.client_secret,
                    server_metadata_url=config.server_metadata_url,
                    client_kwargs={
                        'scope': ' '.join(config.scopes)
                    }
                )
            else:
                # Или явная конфигурация endpoints
                self.oauth.register(
                    name=name,
                    client_id=config.client_id,
                    client_secret=config.client_secret,
                    authorize_url=config.authorize_url,
                    access_token_url=config.token_url,
                    userinfo_endpoint=config.userinfo_url,
                    jwks_uri=config.jwks_uri,
                    client_kwargs={
                        'scope': ' '.join(config.scopes)
                    }
                )

            self.providers[name] = config
            logger.info(f"OAuth2 провайдер '{name}' зарегистрирован")

        except Exception as e:
            logger.error(f"Ошибка регистрации OAuth2 провайдера '{name}': {e}")

    def get_authorization_url(
        self,
        provider_name: str,
        redirect_uri: str
    ) -> Optional[tuple[str, str]]:
        """
        Получает URL для redirect пользователя на страницу авторизации провайдера.

        Args:
            provider_name: Имя провайдера (dex, google, etc)
            redirect_uri: URL для callback после авторизации

        Returns:
            Tuple (authorization_url, state) или None
            state используется для защиты от CSRF атак

        Example:
            >>> auth_url, state = oauth2_service.get_authorization_url("dex", "http://localhost:8000/callback")
            >>> # Сохраните state в session
            >>> # Redirect пользователя на auth_url
        """
        if provider_name not in self.providers:
            logger.error(f"Провайдер '{provider_name}' не найден")
            return None

        try:
            client = self.oauth.create_client(provider_name)

            # Authlib генерирует state автоматически
            authorization_url, state = client.create_authorization_url(
                redirect_uri=redirect_uri
            )

            logger.info(f"Создан authorization URL для провайдера '{provider_name}'")
            return authorization_url, state

        except Exception as e:
            logger.error(f"Ошибка создания authorization URL: {e}")
            return None

    async def handle_callback(
        self,
        provider_name: str,
        redirect_uri: str,
        authorization_response: str
    ) -> Optional[Dict]:
        """
        Обрабатывает callback после авторизации пользователя.
        Обменивает authorization code на access token и получает данные пользователя.

        Args:
            provider_name: Имя провайдера
            redirect_uri: URL callback (должен совпадать с тем, что был в authorization)
            authorization_response: Полный URL с query параметрами (code, state)

        Returns:
            Dict с данными пользователя или None
            содержит: username, email, full_name, is_admin, groups, provider

        Example:
            >>> # В FastAPI endpoint
            >>> user_data = await oauth2_service.handle_callback(
            >>>     "dex",
            >>>     "http://localhost:8000/callback",
            >>>     str(request.url)  # Полный URL с query params
            >>> )
        """
        if provider_name not in self.providers:
            logger.error(f"Провайдер '{provider_name}' не найден")
            return None

        try:
            client = self.oauth.create_client(provider_name)

            # Шаг 1: Обмен code на token
            token = await client.authorize_access_token(
                redirect_uri=redirect_uri,
                url=authorization_response
            )

            logger.info(f"Получен access token от провайдера '{provider_name}'")

            # Шаг 2: Получение информации о пользователе
            userinfo = await self._get_userinfo(provider_name, token)

            if not userinfo:
                return None

            # Шаг 3: Маппинг полей провайдера на нашу систему
            user_data = self._map_userinfo(provider_name, userinfo)

            # Шаг 4: Проверка прав администратора
            user_data['is_admin'] = self._is_admin_user(provider_name, userinfo)

            # Дополнительная информация
            user_data['provider'] = provider_name

            return user_data

        except Exception as e:
            logger.error(f"Ошибка обработки OAuth2 callback: {e}")
            return None

    async def _get_userinfo(
        self,
        provider_name: str,
        token: OAuth2Token
    ) -> Optional[Dict]:
        """
        Получает информацию о пользователе через userinfo endpoint.

        Args:
            provider_name: Имя провайдера
            token: OAuth2 токен

        Returns:
            Dict с данными пользователя от провайдера
        """
        try:
            client = self.oauth.create_client(provider_name)

            # Authlib автоматически использует userinfo_endpoint
            userinfo = await client.userinfo(token=token)

            logger.debug(f"Получен userinfo от '{provider_name}': {userinfo}")
            return dict(userinfo)

        except Exception as e:
            logger.error(f"Ошибка получения userinfo: {e}")
            return None

    def _map_userinfo(self, provider_name: str, userinfo: Dict) -> Dict:
        """
        Маппинг полей от OAuth2 провайдера на наши поля.

        Args:
            provider_name: Имя провайдера
            userinfo: Данные пользователя от провайдера

        Returns:
            Dict с нашими полями: username, email, full_name, groups
        """
        config = self.providers[provider_name]
        mapping = config.user_mapping

        # Безопасное извлечение значений
        def get_field(field_name: str, default: str = "") -> str:
            return userinfo.get(field_name, default)

        mapped_data = {
            'username': get_field(mapping.username),
            'email': get_field(mapping.email),
            'full_name': get_field(mapping.full_name),
        }

        # Группы (если есть)
        groups_field = mapping.groups
        groups = userinfo.get(groups_field, [])

        # Обеспечиваем что groups это список
        if isinstance(groups, str):
            groups = [groups]
        elif not isinstance(groups, list):
            groups = []

        mapped_data['groups'] = groups

        return mapped_data

    def _is_admin_user(self, provider_name: str, userinfo: Dict) -> bool:
        """
        Проверяет, является ли пользователь администратором.

        Args:
            provider_name: Имя провайдера
            userinfo: Данные пользователя от провайдера

        Returns:
            True если пользователь администратор
        """
        config = self.providers[provider_name]
        mapping = config.user_mapping

        # Проверка по группам
        if config.admin_groups:
            groups = userinfo.get(mapping.groups, [])

            if isinstance(groups, str):
                groups = [groups]

            for group in groups:
                if group in config.admin_groups:
                    logger.info(f"Пользователь администратор (группа OAuth2: {group})")
                    return True

        # Проверка по email (для провайдеров без групп, например Google)
        if config.admin_emails:
            email = userinfo.get(mapping.email)
            if email in config.admin_emails:
                logger.info(f"Пользователь администратор (email: {email})")
                return True

        return False

    def get_available_providers(self) -> List[str]:
        """
        Возвращает список доступных OAuth2 провайдеров.

        Returns:
            Список имен активных провайдеров
        """
        return list(self.providers.keys())


# Глобальный экземпляр сервиса
oauth2_service = OAuth2Service()
```

**Пояснения для джуниоров**:
- **OAuth2 flow**: redirect → authorization code → access token → userinfo
- **state parameter** - защита от CSRF атак (проверяем что ответ от нашего запроса)
- **scope** - разрешения, которые мы запрашиваем (openid, email, profile, groups)
- **OIDC (OpenID Connect)** - расширение OAuth2 для аутентификации (не только авторизации)
- **.well-known/openid-configuration** - стандартный endpoint для автоматического обнаружения

### 4.4 Модификация User модели для внешних провайдеров

Нужно добавить поле для отслеживания источника пользователя:

```python
# В app/db/models/user.py добавить:

    # Источник пользователя
    auth_provider = Column(
        String(50),
        default="local",
        nullable=False,
        index=True
    )  # local, ldap, dex, google, etc

    # Внешний ID пользователя (если из OAuth2/LDAP)
    external_id = Column(String(255), nullable=True, index=True)

    # Последняя синхронизация из внешнего источника
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
```

### 4.5 Модификация Auth Service для интеграции

Добавьте в `app/services/auth_service.py` методы для работы с внешними провайдерами:

```python
from app.services.ldap_service import ldap_service
from app.services.oauth2_service import oauth2_service

async def authenticate_ldap(
    db: AsyncSession,
    username: str,
    password: str
) -> Optional[User]:
    """
    Аутентификация через LDAP.
    Автоматически создает/обновляет пользователя в локальной БД.
    """
    # Аутентификация через LDAP
    success, ldap_user_data = ldap_service.authenticate(username, password)

    if not success:
        return None

    # Поиск или создание пользователя в локальной БД
    user = await get_user_by_username(db, username)

    if user:
        # Обновление существующего пользователя
        user.email = ldap_user_data['email']
        user.full_name = ldap_user_data['full_name']
        user.is_admin = ldap_user_data['is_admin']
        user.auth_provider = 'ldap'
        user.last_synced_at = datetime.utcnow()
        await db.commit()
    else:
        # Создание нового пользователя
        if not settings.auth.ldap.auto_create_users:
            logger.warning(f"Автосоздание пользователей LDAP отключено")
            return None

        user = User(
            username=username,
            email=ldap_user_data['email'],
            full_name=ldap_user_data['full_name'],
            hashed_password="",  # Пароль не храним для LDAP пользователей
            is_active=True,
            is_admin=ldap_user_data['is_admin'],
            auth_provider='ldap',
            last_synced_at=datetime.utcnow()
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return user


async def authenticate_oauth2(
    db: AsyncSession,
    provider_name: str,
    oauth2_user_data: Dict
) -> Optional[User]:
    """
    Аутентификация через OAuth2.
    Автоматически создает/обновляет пользователя в локальной БД.
    """
    username = oauth2_user_data['username']

    # Поиск пользователя по external_id или username
    external_id = oauth2_user_data.get('sub') or oauth2_user_data.get('id')

    user = None
    if external_id:
        result = await db.execute(
            select(User).where(
                User.external_id == external_id,
                User.auth_provider == provider_name
            )
        )
        user = result.scalar_one_or_none()

    if not user:
        user = await get_user_by_username(db, username)

    if user:
        # Обновление
        user.email = oauth2_user_data['email']
        user.full_name = oauth2_user_data['full_name']
        user.is_admin = oauth2_user_data['is_admin']
        user.auth_provider = provider_name
        user.external_id = external_id
        user.last_synced_at = datetime.utcnow()
        await db.commit()
    else:
        # Создание
        provider_config = settings.auth.oauth2.providers[provider_name]
        if not provider_config.auto_create_users:
            logger.warning(f"Автосоздание пользователей OAuth2 отключено")
            return None

        user = User(
            username=username,
            email=oauth2_user_data['email'],
            full_name=oauth2_user_data['full_name'],
            hashed_password="",  # Пароль не храним
            is_active=True,
            is_admin=oauth2_user_data['is_admin'],
            auth_provider=provider_name,
            external_id=external_id,
            last_synced_at=datetime.utcnow()
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return user
```

### 4.6 API Endpoints для OAuth2

Добавьте в `app/api/endpoints/auth.py`:

```python
@router.get("/oauth2/providers")
async def get_oauth2_providers():
    """
    Список доступных OAuth2 провайдеров.
    Используется UI для отображения кнопок "Login with ..."
    """
    if not settings.auth.oauth2.enabled:
        return {"providers": []}

    providers = oauth2_service.get_available_providers()
    return {"providers": providers}


@router.get("/oauth2/{provider}/login")
async def oauth2_login(
    provider: str,
    request: Request
):
    """
    Начало OAuth2 flow - redirect на провайдера.
    """
    # Формируем callback URL
    callback_url = str(request.url_for('oauth2_callback', provider=provider))

    # Получаем authorization URL
    result = oauth2_service.get_authorization_url(provider, callback_url)

    if not result:
        raise HTTPException(status_code=400, detail="Провайдер не найден")

    auth_url, state = result

    # Сохраняем state в session (для проверки в callback)
    request.session['oauth2_state'] = state
    request.session['oauth2_provider'] = provider

    # Redirect на провайдера
    return RedirectResponse(url=auth_url)


@router.get("/oauth2/{provider}/callback")
async def oauth2_callback(
    provider: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Callback после авторизации на провайдере.
    Обменивает code на token, получает userinfo, создает JWT.
    """
    # Проверка state (защита от CSRF)
    saved_state = request.session.get('oauth2_state')
    received_state = request.query_params.get('state')

    if not saved_state or saved_state != received_state:
        raise HTTPException(status_code=400, detail="Invalid state")

    # Получаем данные пользователя от OAuth2 провайдера
    callback_url = str(request.url_for('oauth2_callback', provider=provider))
    user_data = await oauth2_service.handle_callback(
        provider,
        callback_url,
        str(request.url)
    )

    if not user_data:
        raise HTTPException(status_code=401, detail="OAuth2 authentication failed")

    # Создаем/обновляем пользователя в локальной БД
    user = await authenticate_oauth2(db, provider, user_data)

    if not user:
        raise HTTPException(status_code=403, detail="User creation disabled")

    # Создаем наши внутренние JWT токены
    access_token = create_access_token({"sub": user.id, "username": user.username})
    refresh_token = create_refresh_token({"sub": user.id})

    # Audit log
    await audit_service.log_action(
        user_id=user.id,
        username=user.username,
        action="oauth2_login",
        details={"provider": provider}
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_admin": user.is_admin
        }
    }
```

### 4.7 Модификация логики логина

В `POST /api/auth/login` добавьте выбор источника аутентификации:

```python
@router.post("/login")
async def login(
    credentials: LoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Универсальный endpoint для логина.
    Последовательно пытается:
    1. Локальная БД
    2. LDAP (если включен)
    """
    user = None
    auth_method = "local"

    # Попытка 1: Локальная аутентификация
    user = await authenticate_local(db, credentials.username, credentials.password)

    # Попытка 2: LDAP аутентификация (если включена и локальная не удалась)
    if not user and settings.auth.ldap.enabled:
        user = await authenticate_ldap(db, credentials.username, credentials.password)
        if user:
            auth_method = "ldap"

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Неверные учетные данные"
        )

    # Создание JWT токенов
    access_token = create_access_token({"sub": user.id, "username": user.username})
    refresh_token = create_refresh_token({"sub": user.id})

    # Audit log
    await audit_service.log_action(
        user_id=user.id,
        username=user.username,
        action=f"login_{auth_method}",
        details={"auth_method": auth_method}
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "auth_method": auth_method
    }
```

### 4.8 Тестирование интеграции

**Тестирование LDAP**:

1. Запустите LDAP сервер из docker-compose (уже настроен в проекте)
2. Включите LDAP в config.yaml: `auth.ldap.enabled: true`
3. Попытайтесь войти с LDAP учетными данными: `admin` / `admin123`
4. Проверьте, что пользователь создан в БД с `auth_provider='ldap'`

**Тестирование OAuth2 (Dex)**:

1. Запустите Dex сервер из docker-compose
2. Включите OAuth2 в config.yaml: `auth.oauth2.enabled: true`
3. Настройте Dex провайдера с правильными client_id и client_secret
4. Откройте в браузере: `http://localhost:8000/api/auth/oauth2/dex/login`
5. Вы будете перенаправлены на Dex для входа
6. После успешного входа вернетесь на callback с JWT токенами

---

## Этап 5: Pydantic схемы для валидации

### 5.1 Понимание назначения схем

**Pydantic схемы** используются для:
- **Валидации входящих данных** (request body, query params)
- **Сериализации исходящих данных** (response body)
- **Автоматической генерации документации** OpenAPI/Swagger
- **Защиты от injection атак** через строгую типизацию

**Типы схем**:
1. **Request схемы** - данные от клиента в API
2. **Response схемы** - данные от API клиенту
3. **Internal схемы** - для внутренней передачи данных между слоями

**Соглашения по именованию**:
- `UserCreate` - создание пользователя (входящие данные)
- `UserUpdate` - обновление пользователя (входящие данные)
- `UserResponse` - пользователь в ответе (исходящие данные)
- `UserInDB` - пользователь как в БД (внутреннее использование)

### 5.2 Общие схемы (app/schemas/common.py)

**Цель**: Переиспользуемые схемы для пагинации, ответов, ошибок.

```python
"""
Общие Pydantic схемы, используемые в разных endpoints.
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Generic, TypeVar, List, Optional
from datetime import datetime


# Generic типы для пагинации
T = TypeVar('T')


class PaginationParams(BaseModel):
    """
    Параметры пагинации для списков.

    Используется как query параметры в GET запросах.
    """
    page: int = Field(default=1, ge=1, description="Номер страницы (начиная с 1)")
    size: int = Field(default=20, ge=1, le=100, description="Количество элементов на странице")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "page": 1,
                "size": 20
            }
        }
    )


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Обертка для пагинированных ответов.

    Generic класс - может содержать любой тип элементов.

    Example:
        >>> PaginatedResponse[UserResponse](
        >>>     items=[user1, user2],
        >>>     total=100,
        >>>     page=1,
        >>>     size=20,
        >>>     pages=5
        >>> )
    """
    items: List[T] = Field(description="Список элементов на текущей странице")
    total: int = Field(description="Общее количество элементов")
    page: int = Field(description="Текущая страница")
    size: int = Field(description="Размер страницы")
    pages: int = Field(description="Общее количество страниц")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "items": [],
                "total": 100,
                "page": 1,
                "size": 20,
                "pages": 5
            }
        }
    )


class SuccessResponse(BaseModel):
    """
    Стандартный ответ об успехе операции.

    Используется для операций без возврата данных (delete, activate, etc).
    """
    success: bool = Field(default=True, description="Статус операции")
    message: str = Field(description="Сообщение о результате")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Пользователь успешно удален"
            }
        }
    )


class ErrorDetail(BaseModel):
    """
    Детали ошибки валидации.
    """
    loc: List[str] = Field(description="Путь к полю с ошибкой")
    msg: str = Field(description="Сообщение об ошибке")
    type: str = Field(description="Тип ошибки")


class ErrorResponse(BaseModel):
    """
    Стандартный ответ об ошибке.

    Возвращается при HTTP 4xx и 5xx ошибках.
    """
    detail: str = Field(description="Общее описание ошибки")
    errors: Optional[List[ErrorDetail]] = Field(
        default=None,
        description="Детали ошибок валидации (если есть)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "detail": "Validation error",
                "errors": [
                    {
                        "loc": ["body", "email"],
                        "msg": "Invalid email format",
                        "type": "value_error.email"
                    }
                ]
            }
        }
    )


class TimestampMixin(BaseModel):
    """
    Mixin для добавления временных меток.

    Используется в response схемах для отображения created_at/updated_at.
    """
    created_at: datetime = Field(description="Дата создания")
    updated_at: datetime = Field(description="Дата последнего обновления")


class IDMixin(BaseModel):
    """
    Mixin для добавления ID.
    """
    id: str = Field(description="Уникальный идентификатор")
```

**Пояснения для джуниоров**:
- **Generic[T]** - позволяет создавать типизированные обертки (PaginatedResponse[User])
- **Field** - добавляет метаданные (описание, ограничения, примеры)
- **ge/le** - greater or equal / less or equal (валидация числовых значений)
- **ConfigDict** - конфигурация схемы (примеры для документации)
- **Mixin** - класс для переиспользования общих полей через наследование

### 5.3 Схемы пользователей (app/schemas/user.py)

См. продолжение в файле...

---

**Итого этап 5**: Мы создали полный набор Pydantic схем для валидации всех входящих и исходящих данных API. Схемы обеспечивают безопасность, автоматическую документацию и удобство разработки.

---

## Этап 6: Services (бизнес-логика)

### 6.1 Понимание слоя Services

**Service Layer** - это слой бизнес-логики, который:
- **Изолирует бизнес-правила** от HTTP endpoints
- **Обеспечивает переиспользование** кода между разными endpoints
- **Упрощает тестирование** (можно тестировать без FastAPI)
- **Координирует операции** с БД, внешними сервисами, кешем

**Принципы разработки Services**:
1. **Независимость от FastAPI** - не используют Request, Response, HTTPException
2. **Async/await** - все методы асинхронные для работы с async БД
3. **Transactional** - используют DB session для транзакций
4. **Single Responsibility** - каждый сервис отвечает за одну область
5. **Dependency Injection** - получают зависимости через конструктор

**Структура сервисов**:
```
services/
├── auth_service.py       # Аутентификация
├── user_service.py       # Управление пользователями
├── storage_service.py    # Управление storage elements
├── audit_service.py      # Логирование действий
├── redis_service.py      # Service Discovery
├── ldap_service.py       # LDAP (уже создан в этапе 4)
└── oauth2_service.py     # OAuth2 (уже создан в этапе 4)
```

### 6.2 User Service (app/services/user_service.py)

**Цель**: CRUD операции для пользователей с бизнес-правилами.

```python
"""
Сервис для работы с пользователями.
Содержит всю бизнес-логику управления пользователями.
"""
from typing import Optional, List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from sqlalchemy.exc import IntegrityError
from datetime import datetime

from app.db.models.user import User
from app.schemas.user import (
    UserCreate, UserUpdate, PasswordChange,
    UserSearchParams, UserStats
)
from app.core.security import hash_password, verify_password, validate_password_strength
from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class UserService:
    """
    Сервис управления пользователями.

    Все методы асинхронные и принимают DB session.
    """

    async def create_user(
        self,
        db: AsyncSession,
        user_data: UserCreate
    ) -> User:
        """
        Создает нового пользователя.

        Args:
            db: Database session
            user_data: Данные для создания пользователя

        Returns:
            Созданный пользователь

        Raises:
            ValueError: Если username или email уже существуют
            ValueError: Если пароль не соответствует требованиям
        """
        # Валидация пароля
        is_valid, error_message = validate_password_strength(user_data.password)
        if not is_valid:
            raise ValueError(error_message)

        # Проверка уникальности username
        existing_user = await self.get_user_by_username(db, user_data.username)
        if existing_user:
            raise ValueError(f"Пользователь с username '{user_data.username}' уже существует")

        # Проверка уникальности email
        existing_email = await self.get_user_by_email(db, user_data.email)
        if existing_email:
            raise ValueError(f"Пользователь с email '{user_data.email}' уже существует")

        # Хеширование пароля
        hashed_password = hash_password(user_data.password)

        # Создание пользователя
        user = User(
            username=user_data.username,
            email=user_data.email,
            full_name=user_data.full_name,
            hashed_password=hashed_password,
            is_active=True,
            is_admin=user_data.is_admin,
            is_system=False,
            description=user_data.description,
            auth_provider="local"
        )

        db.add(user)

        try:
            await db.commit()
            await db.refresh(user)
            logger.info(f"Создан пользователь: {user.username} (ID: {user.id})")
            return user
        except IntegrityError as e:
            await db.rollback()
            logger.error(f"Ошибка создания пользователя: {e}")
            raise ValueError("Ошибка создания пользователя. Возможно, данные не уникальны.")

    async def get_user_by_id(
        self,
        db: AsyncSession,
        user_id: str
    ) -> Optional[User]:
        """
        Получает пользователя по ID.

        Args:
            db: Database session
            user_id: ID пользователя

        Returns:
            User или None если не найден
        """
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_user_by_username(
        self,
        db: AsyncSession,
        username: str
    ) -> Optional[User]:
        """
        Получает пользователя по username.

        Args:
            db: Database session
            username: Имя пользователя

        Returns:
            User или None
        """
        result = await db.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()

    async def get_user_by_email(
        self,
        db: AsyncSession,
        email: str
    ) -> Optional[User]:
        """
        Получает пользователя по email.

        Args:
            db: Database session
            email: Email пользователя

        Returns:
            User или None
        """
        result = await db.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def update_user(
        self,
        db: AsyncSession,
        user_id: str,
        user_data: UserUpdate
    ) -> Optional[User]:
        """
        Обновляет данные пользователя.

        Args:
            db: Database session
            user_id: ID пользователя
            user_data: Данные для обновления

        Returns:
            Обновленный пользователь или None

        Raises:
            ValueError: Если email уже используется другим пользователем
        """
        user = await self.get_user_by_id(db, user_id)
        if not user:
            return None

        # Проверка защищенности системного пользователя
        if user.is_system:
            logger.warning(f"Попытка изменения системного пользователя: {user.username}")
            # Разрешаем менять только description
            if user_data.email or user_data.full_name:
                raise ValueError("Системный пользователь защищен от изменения")

            if user_data.description is not None:
                user.description = user_data.description
        else:
            # Обновление полей (только если они переданы)
            if user_data.email is not None:
                # Проверка уникальности нового email
                existing = await self.get_user_by_email(db, user_data.email)
                if existing and existing.id != user_id:
                    raise ValueError(f"Email '{user_data.email}' уже используется")
                user.email = user_data.email

            if user_data.full_name is not None:
                user.full_name = user_data.full_name

            if user_data.description is not None:
                user.description = user_data.description

        user.updated_at = datetime.utcnow()

        try:
            await db.commit()
            await db.refresh(user)
            logger.info(f"Обновлен пользователь: {user.username} (ID: {user.id})")
            return user
        except IntegrityError as e:
            await db.rollback()
            logger.error(f"Ошибка обновления пользователя: {e}")
            raise ValueError("Ошибка обновления пользователя")

    async def delete_user(
        self,
        db: AsyncSession,
        user_id: str
    ) -> bool:
        """
        Удаляет пользователя.

        Args:
            db: Database session
            user_id: ID пользователя

        Returns:
            True если удален, False если не найден или защищен

        Note:
            Системный пользователь не может быть удален
        """
        user = await self.get_user_by_id(db, user_id)
        if not user:
            return False

        # Защита системного пользователя
        if user.is_protected:
            logger.warning(f"Попытка удаления защищенного пользователя: {user.username}")
            return False

        await db.delete(user)
        await db.commit()
        logger.info(f"Удален пользователь: {user.username} (ID: {user.id})")
        return True

    async def change_password(
        self,
        db: AsyncSession,
        user_id: str,
        password_data: PasswordChange,
        verify_current: bool = True
    ) -> bool:
        """
        Меняет пароль пользователя.

        Args:
            db: Database session
            user_id: ID пользователя
            password_data: Данные смены пароля
            verify_current: Проверять ли текущий пароль

        Returns:
            True если успешно

        Raises:
            ValueError: Если текущий пароль неверен или новый пароль слабый
        """
        user = await self.get_user_by_id(db, user_id)
        if not user:
            raise ValueError("Пользователь не найден")

        # Проверка текущего пароля (если требуется)
        if verify_current:
            if not password_data.current_password:
                raise ValueError("Требуется указать текущий пароль")

            if not verify_password(password_data.current_password, user.hashed_password):
                raise ValueError("Неверный текущий пароль")

        # Валидация нового пароля
        is_valid, error_message = validate_password_strength(password_data.new_password)
        if not is_valid:
            raise ValueError(error_message)

        # Обновление пароля
        user.hashed_password = hash_password(password_data.new_password)
        user.updated_at = datetime.utcnow()

        await db.commit()
        logger.info(f"Изменен пароль пользователя: {user.username}")
        return True

    async def activate_user(
        self,
        db: AsyncSession,
        user_id: str
    ) -> bool:
        """
        Активирует пользователя.

        Args:
            db: Database session
            user_id: ID пользователя

        Returns:
            True если успешно
        """
        user = await self.get_user_by_id(db, user_id)
        if not user:
            return False

        user.is_active = True
        user.updated_at = datetime.utcnow()
        await db.commit()
        logger.info(f"Активирован пользователь: {user.username}")
        return True

    async def deactivate_user(
        self,
        db: AsyncSession,
        user_id: str
    ) -> bool:
        """
        Деактивирует пользователя.

        Args:
            db: Database session
            user_id: ID пользователя

        Returns:
            True если успешно

        Note:
            Системный пользователь не может быть деактивирован
        """
        user = await self.get_user_by_id(db, user_id)
        if not user:
            return False

        if user.is_protected:
            logger.warning(f"Попытка деактивации защищенного пользователя: {user.username}")
            return False

        user.is_active = False
        user.updated_at = datetime.utcnow()
        await db.commit()
        logger.info(f"Деактивирован пользователь: {user.username}")
        return True

    async def make_admin(
        self,
        db: AsyncSession,
        user_id: str
    ) -> bool:
        """
        Назначает пользователя администратором.

        Args:
            db: Database session
            user_id: ID пользователя

        Returns:
            True если успешно
        """
        user = await self.get_user_by_id(db, user_id)
        if not user:
            return False

        user.is_admin = True
        user.updated_at = datetime.utcnow()
        await db.commit()
        logger.info(f"Пользователь назначен администратором: {user.username}")
        return True

    async def remove_admin(
        self,
        db: AsyncSession,
        user_id: str
    ) -> bool:
        """
        Снимает права администратора.

        Args:
            db: Database session
            user_id: ID пользователя

        Returns:
            True если успешно

        Note:
            Системный администратор защищен от снятия прав
        """
        user = await self.get_user_by_id(db, user_id)
        if not user:
            return False

        if user.is_protected:
            logger.warning(f"Попытка снятия прав с защищенного администратора: {user.username}")
            return False

        user.is_admin = False
        user.updated_at = datetime.utcnow()
        await db.commit()
        logger.info(f"Сняты права администратора: {user.username}")
        return True

    async def list_users(
        self,
        db: AsyncSession,
        page: int = 1,
        size: int = 20,
        search: Optional[UserSearchParams] = None
    ) -> Tuple[List[User], int]:
        """
        Получает пагинированный список пользователей с фильтрацией.

        Args:
            db: Database session
            page: Номер страницы (начиная с 1)
            size: Размер страницы
            search: Параметры поиска и фильтрации

        Returns:
            Tuple (список пользователей, общее количество)
        """
        # Базовый запрос
        query = select(User)

        # Применение фильтров
        filters = []

        if search:
            # Поиск по username, email, full_name
            if search.search:
                search_pattern = f"%{search.search}%"
                filters.append(
                    or_(
                        User.username.ilike(search_pattern),
                        User.email.ilike(search_pattern),
                        User.full_name.ilike(search_pattern)
                    )
                )

            # Фильтр по роли администратора
            if search.is_admin is not None:
                filters.append(User.is_admin == search.is_admin)

            # Фильтр по активности
            if search.is_active is not None:
                filters.append(User.is_active == search.is_active)

            # Фильтр по источнику аутентификации
            if search.auth_provider:
                filters.append(User.auth_provider == search.auth_provider)

        # Применяем все фильтры
        if filters:
            query = query.where(and_(*filters))

        # Подсчет общего количества
        count_query = select(func.count()).select_from(User)
        if filters:
            count_query = count_query.where(and_(*filters))

        result = await db.execute(count_query)
        total = result.scalar()

        # Пагинация
        offset = (page - 1) * size
        query = query.offset(offset).limit(size)

        # Сортировка (по дате создания, новые сначала)
        query = query.order_by(User.created_at.desc())

        # Выполнение запроса
        result = await db.execute(query)
        users = result.scalars().all()

        return list(users), total

    async def search_users(
        self,
        db: AsyncSession,
        query: str,
        limit: int = 10
    ) -> List[User]:
        """
        Быстрый поиск пользователей (для autocomplete).

        Args:
            db: Database session
            query: Поисковый запрос
            limit: Максимальное количество результатов

        Returns:
            Список пользователей
        """
        search_pattern = f"%{query}%"

        stmt = select(User).where(
            or_(
                User.username.ilike(search_pattern),
                User.email.ilike(search_pattern),
                User.full_name.ilike(search_pattern)
            )
        ).limit(limit)

        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_user_stats(self, db: AsyncSession) -> UserStats:
        """
        Получает статистику пользователей.

        Args:
            db: Database session

        Returns:
            UserStats с общей статистикой
        """
        # Общее количество
        total_result = await db.execute(select(func.count(User.id)))
        total_users = total_result.scalar()

        # Активные пользователи
        active_result = await db.execute(
            select(func.count(User.id)).where(User.is_active == True)
        )
        active_users = active_result.scalar()

        # Неактивные пользователи
        inactive_users = total_users - active_users

        # Администраторы
        admin_result = await db.execute(
            select(func.count(User.id)).where(User.is_admin == True)
        )
        admin_users = admin_result.scalar()

        # Распределение по источникам аутентификации
        provider_result = await db.execute(
            select(User.auth_provider, func.count(User.id))
            .group_by(User.auth_provider)
        )
        by_auth_provider = {row[0]: row[1] for row in provider_result.all()}

        return UserStats(
            total_users=total_users,
            active_users=active_users,
            inactive_users=inactive_users,
            admin_users=admin_users,
            by_auth_provider=by_auth_provider
        )

    async def create_default_admin(self, db: AsyncSession) -> Optional[User]:
        """
        Создает администратора по умолчанию из конфигурации.
        Вызывается при первом запуске приложения.

        Args:
            db: Database session

        Returns:
            Созданный пользователь или None если уже существует
        """
        admin_config = settings.auth.default_admin

        # Проверяем, существует ли уже
        existing = await self.get_user_by_username(db, admin_config.username)
        if existing:
            logger.info(f"Администратор по умолчанию уже существует: {admin_config.username}")
            return None

        # Создаем системного администратора
        hashed_password = hash_password(admin_config.password)

        admin_user = User(
            username=admin_config.username,
            email=admin_config.email,
            full_name=admin_config.full_name,
            hashed_password=hashed_password,
            description=admin_config.description,
            is_active=True,
            is_admin=True,
            is_system=True,  # Защита от удаления
            auth_provider="local"
        )

        db.add(admin_user)
        await db.commit()
        await db.refresh(admin_user)

        logger.info(f"Создан системный администратор: {admin_user.username}")
        return admin_user


# Глобальный экземпляр сервиса
user_service = UserService()
```

**Пояснения для джуниоров**:
- **async/await** - все методы асинхронные для работы с async SQLAlchemy
- **DB session** - передается как параметр (не создается внутри)
- **IntegrityError** - ловим ошибки уникальности из БД
- **scalar_one_or_none()** - возвращает один результат или None
- **scalars().all()** - возвращает список скаляров (не Row объектов)
- **ilike** - case-insensitive LIKE для поиска
- **func.count()** - SQL агрегатная функция COUNT

### 6.3 Auth Service (app/services/auth_service.py)

**Цель**: Логика аутентификации через разные источники.

```python
"""
Сервис аутентификации.
Координирует аутентификацию через local/LDAP/OAuth2.
"""
from typing import Optional, Dict
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models.user import User
from app.core.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token
)
from app.services.user_service import user_service
from app.services.ldap_service import ldap_service
from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class AuthService:
    """
    Сервис аутентификации пользователей.
    """

    async def authenticate_local(
        self,
        db: AsyncSession,
        username: str,
        password: str
    ) -> Optional[User]:
        """
        Аутентификация через локальную БД.

        Args:
            db: Database session
            username: Имя пользователя
            password: Пароль

        Returns:
            User если аутентификация успешна, иначе None
        """
        # Получаем пользователя
        user = await user_service.get_user_by_username(db, username)

        if not user:
            logger.debug(f"Пользователь не найден: {username}")
            return None

        # Проверяем, что пользователь из локальной БД
        if user.auth_provider != "local":
            logger.debug(f"Пользователь не из локальной БД: {username}")
            return None

        # Проверяем пароль
        if not verify_password(password, user.hashed_password):
            logger.warning(f"Неверный пароль для пользователя: {username}")
            return None

        # Проверяем активность
        if not user.is_active:
            logger.warning(f"Попытка входа неактивного пользователя: {username}")
            return None

        logger.info(f"Успешная локальная аутентификация: {username}")
        return user

    async def authenticate_ldap(
        self,
        db: AsyncSession,
        username: str,
        password: str
    ) -> Optional[User]:
        """
        Аутентификация через LDAP.
        Автоматически создает/обновляет пользователя в локальной БД.

        Args:
            db: Database session
            username: Имя пользователя
            password: Пароль

        Returns:
            User если успешно, иначе None
        """
        if not settings.auth.ldap.enabled:
            return None

        # Аутентификация через LDAP
        success, ldap_user_data = ldap_service.authenticate(username, password)

        if not success:
            return None

        # Поиск или создание пользователя в локальной БД
        user = await user_service.get_user_by_username(db, username)

        if user:
            # Обновление существующего пользователя
            user.email = ldap_user_data['email']
            user.full_name = ldap_user_data['full_name']
            user.is_admin = ldap_user_data['is_admin']
            user.auth_provider = 'ldap'
            user.last_synced_at = datetime.utcnow()
            user.updated_at = datetime.utcnow()
            await db.commit()
            await db.refresh(user)
            logger.info(f"Обновлен LDAP пользователь: {username}")
        else:
            # Создание нового пользователя
            if not settings.auth.ldap.auto_create_users:
                logger.warning(f"Автосоздание LDAP пользователей отключено: {username}")
                return None

            user = User(
                username=username,
                email=ldap_user_data['email'],
                full_name=ldap_user_data['full_name'],
                hashed_password="",  # Пароль не храним для LDAP пользователей
                is_active=True,
                is_admin=ldap_user_data['is_admin'],
                auth_provider='ldap',
                last_synced_at=datetime.utcnow()
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            logger.info(f"Создан новый LDAP пользователь: {username}")

        return user

    async def authenticate(
        self,
        db: AsyncSession,
        username: str,
        password: str
    ) -> tuple[Optional[User], str]:
        """
        Универсальная аутентификация.
        Последовательно пытается: local → LDAP.

        Args:
            db: Database session
            username: Имя пользователя
            password: Пароль

        Returns:
            Tuple (User, auth_method) или (None, "")
        """
        # Попытка 1: Локальная аутентификация
        user = await self.authenticate_local(db, username, password)
        if user:
            return user, "local"

        # Попытка 2: LDAP аутентификация
        user = await self.authenticate_ldap(db, username, password)
        if user:
            return user, "ldap"

        logger.warning(f"Неудачная попытка аутентификации: {username}")
        return None, ""

    def create_tokens(self, user: User) -> Dict[str, str]:
        """
        Создает access и refresh токены для пользователя.

        Args:
            user: Пользователь

        Returns:
            Dict с токенами
        """
        # Payload для токенов
        token_data = {
            "sub": user.id,
            "username": user.username,
            "is_admin": user.is_admin
        }

        # Создание токенов
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token({"sub": user.id})

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": settings.auth.jwt.access_token_expire_minutes * 60
        }

    async def refresh_access_token(
        self,
        db: AsyncSession,
        refresh_token: str
    ) -> Optional[Dict[str, str]]:
        """
        Обновляет access токен используя refresh токен.

        Args:
            db: Database session
            refresh_token: Refresh токен

        Returns:
            Dict с новыми токенами или None если refresh токен невалиден
        """
        try:
            # Декодируем refresh токен
            payload = decode_token(refresh_token)

            # Проверяем тип токена
            if payload.get("type") != "refresh":
                logger.warning("Попытка использовать не refresh токен")
                return None

            # Получаем пользователя
            user_id = payload.get("sub")
            user = await user_service.get_user_by_id(db, user_id)

            if not user or not user.is_active:
                logger.warning(f"Пользователь не найден или неактивен: {user_id}")
                return None

            # Создаем новые токены
            return self.create_tokens(user)

        except Exception as e:
            logger.error(f"Ошибка обновления токена: {e}")
            return None

    async def validate_token(self, token: str) -> Optional[Dict]:
        """
        Валидирует токен и возвращает информацию о пользователе.

        Args:
            token: JWT токен

        Returns:
            Dict с информацией о пользователе или None
        """
        try:
            payload = decode_token(token)

            # Проверяем тип токена (должен быть access)
            if payload.get("type") != "access":
                return None

            return {
                "valid": True,
                "user_id": payload.get("sub"),
                "username": payload.get("username"),
                "is_admin": payload.get("is_admin"),
                "expires_at": datetime.fromtimestamp(payload.get("exp")).isoformat()
            }

        except Exception as e:
            logger.debug(f"Невалидный токен: {e}")
            return None


# Глобальный экземпляр сервиса
auth_service = AuthService()
```

**Пояснения**:
- **Каскадная аутентификация** - пробуем разные источники последовательно
- **Синхронизация** - LDAP пользователи копируются в локальную БД
- **Token refresh** - безопасное обновление токенов без повторного ввода пароля

### 6.4 Audit Service (app/services/audit_service.py)

**Цель**: Логирование всех действий пользователей.

```python
"""
Сервис audit logging.
Записывает все действия пользователей в БД.
"""
from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.audit_log import AuditLog
from app.utils.logger import get_logger

logger = get_logger(__name__)


class AuditService:
    """
    Сервис аудита действий пользователей.
    """

    async def log_action(
        self,
        db: AsyncSession,
        action: str,
        user_id: Optional[str] = None,
        username: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> AuditLog:
        """
        Записывает действие в audit log.

        Args:
            db: Database session
            action: Тип действия (login, create_user, delete_file, etc.)
            user_id: ID пользователя
            username: Имя пользователя
            resource_type: Тип ресурса (user, storage_element, file)
            resource_id: ID ресурса
            details: Дополнительные детали (JSON)
            ip_address: IP адрес клиента
            user_agent: User-Agent браузера
            success: Успешно ли выполнено действие
            error_message: Сообщение об ошибке

        Returns:
            Созданная запись audit log
        """
        audit_entry = AuditLog(
            user_id=user_id,
            username=username,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
            success=success,
            error_message=error_message
        )

        db.add(audit_entry)

        try:
            await db.commit()
            await db.refresh(audit_entry)

            log_message = f"Audit: {action}"
            if username:
                log_message += f" by {username}"
            if resource_type and resource_id:
                log_message += f" on {resource_type}:{resource_id}"

            logger.info(log_message)
            return audit_entry

        except Exception as e:
            await db.rollback()
            logger.error(f"Ошибка записи audit log: {e}")
            # Не поднимаем исключение, чтобы не прерывать основное действие
            return audit_entry


# Глобальный экземпляр сервиса
audit_service = AuditService()
```

**Важно**: Audit service не должен прерывать основные операции при ошибках логирования.

---

**Итого этап 6**: Мы создали services layer с полной бизнес-логикой для управления пользователями, аутентификации и аудита. Services изолированы от HTTP и легко тестируются.

**Следующие этапы**:
- Этап 7: API Endpoints (полная реализация)
- Этап 8: Middleware и обработка ошибок
- Этап 9: Мониторинг и логирование
- Этап 10: Тестирование
- Этап 11: Docker и развертывание

---

## Этап 7: API Endpoints (полная реализация)

### 7.1 Понимание структуры FastAPI роутеров

**Что такое Router?**
Router в FastAPI - это способ организовать endpoints в логические группы. Каждая группа получает свой префикс URL и набор общих зависимостей.

**Основные концепции**:
- **APIRouter**: Объект для группировки endpoints
- **Dependency Injection**: Передача зависимостей (DB сессия, текущий пользователь) через параметры функций
- **Path Parameters**: Параметры в URL (`/users/{user_id}`)
- **Query Parameters**: Параметры запроса (`?page=1&size=20`)
- **Request Body**: Данные в теле запроса (JSON)
- **Response Models**: Pydantic модели для автоматической валидации и документации ответов

**Структура директории для API**:
```
app/api/
├── __init__.py
├── deps.py           # Общие зависимости (get_db, get_current_user, etc.)
├── api.py            # Главный роутер, объединяющий все endpoints
└── endpoints/
    ├── __init__.py
    ├── auth.py       # Endpoints аутентификации
    ├── users.py      # Endpoints управления пользователями
    ├── storage_elements.py  # Endpoints управления элементами хранения
    ├── oauth2.py     # Endpoints OAuth2
    └── health.py     # Health check endpoints
```

### 7.2 Зависимости (Dependencies)

**Файл**: `app/api/deps.py`

```python
"""
Общие зависимости для API endpoints.
"""
from typing import AsyncGenerator, Optional
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from jose import JWTError, jwt

from app.db.session import async_session
from app.db.models.user import User
from app.core.config import settings
from app.core.security import decode_jwt_token


# OAuth2 bearer token scheme для Swagger UI
security = HTTPBearer(auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency для получения database сессии.

    Yields:
        AsyncSession: SQLAlchemy async сессия
    """
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """
    Dependency для получения текущего пользователя (опционально).
    Возвращает None если токен отсутствует или невалиден.

    Args:
        credentials: Bearer token из Authorization header
        db: Database сессия

    Returns:
        Optional[User]: Пользователь или None
    """
    if credentials is None:
        return None

    try:
        token = credentials.credentials
        payload = decode_jwt_token(token)
        user_id: int = int(payload.get("sub"))

        if user_id is None:
            return None

        # Загружаем пользователя из БД
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if user is None or not user.is_active:
            return None

        return user

    except (JWTError, ValueError, KeyError):
        return None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Dependency для получения текущего аутентифицированного пользователя.
    Возвращает 401 если токен отсутствует или невалиден.

    Args:
        credentials: Bearer token из Authorization header
        db: Database сессия

    Returns:
        User: Текущий пользователь

    Raises:
        HTTPException: 401 если токен невалиден
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        token = credentials.credentials
        payload = decode_jwt_token(token)
        user_id: int = int(payload.get("sub"))

        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user ID",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Загружаем пользователя из БД
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is deactivated"
            )

        return user

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_admin_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Dependency для проверки, что текущий пользователь - администратор.

    Args:
        current_user: Текущий пользователь

    Returns:
        User: Пользователь с ролью admin

    Raises:
        HTTPException: 403 если пользователь не администратор
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges required"
        )
    return current_user


async def get_current_superadmin_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Dependency для проверки, что текущий пользователь - суперадминистратор.

    Args:
        current_user: Текущий пользователь

    Returns:
        User: Пользователь с ролью superadmin

    Raises:
        HTTPException: 403 если пользователь не суперадминистратор
    """
    if current_user.role != "superadmin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superadministrator privileges required"
        )
    return current_user
```

**Объяснение**:
1. `get_db()` - создает database сессию для каждого запроса и автоматически закрывает её
2. `get_current_user_optional()` - извлекает пользователя из JWT токена, но не требует его обязательно
3. `get_current_user()` - требует валидный JWT токен, иначе возвращает 401
4. `get_current_admin_user()` - проверяет, что у пользователя роль admin
5. `get_current_superadmin_user()` - проверяет, что у пользователя роль superadmin

### 7.3 Auth Endpoints

**Файл**: `app/api/endpoints/auth.py`

```python
"""
API endpoints для аутентификации.
"""
from datetime import timedelta
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.db.models.user import User
from app.schemas.auth import (
    LoginRequest, LoginResponse, RefreshTokenRequest,
    TokenResponse, UserInfo
)
from app.services.auth import auth_service
from app.services.user import user_service
from app.services.audit import audit_service
from app.core.security import create_access_token, create_refresh_token, decode_jwt_token


router = APIRouter()


@router.post("/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def login(
    credentials: LoginRequest,
    db: AsyncSession = Depends(deps.get_db)
) -> Dict[str, Any]:
    """
    Аутентификация пользователя (локальная или LDAP).

    **Процесс**:
    1. Проверяет username/password через cascade authentication (local → LDAP)
    2. Генерирует access и refresh токены
    3. Логирует событие в audit log

    **Args**:
    - **username**: Имя пользователя
    - **password**: Пароль

    **Returns**:
    - **access_token**: JWT токен для доступа (30 минут)
    - **refresh_token**: JWT токен для обновления (7 дней)
    - **token_type**: Тип токена (bearer)
    - **user**: Информация о пользователе

    **Errors**:
    - **401**: Неверные credentials
    """
    # Аутентификация через auth service
    user, auth_method = await auth_service.authenticate(
        db, credentials.username, credentials.password
    )

    if user is None:
        # Логируем неудачную попытку входа
        await audit_service.log_action(
            db=db,
            user_id=None,
            action="login_failed",
            resource_type="auth",
            resource_id=None,
            details={"username": credentials.username, "method": auth_method}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )

    # Генерируем токены
    access_token = create_access_token(
        data={"sub": str(user.id), "role": user.role}
    )
    refresh_token = create_refresh_token(
        data={"sub": str(user.id)}
    )

    # Логируем успешный вход
    await audit_service.log_action(
        db=db,
        user_id=user.id,
        action="login",
        resource_type="auth",
        resource_id=None,
        details={"method": auth_method, "ip": "TODO"}  # TODO: добавить real IP
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "is_active": user.is_active
        }
    }


@router.post("/refresh", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def refresh_token(
    request: RefreshTokenRequest,
    db: AsyncSession = Depends(deps.get_db)
) -> Dict[str, Any]:
    """
    Обновление access токена используя refresh токен.

    **Args**:
    - **refresh_token**: Refresh токен

    **Returns**:
    - **access_token**: Новый JWT access токен
    - **token_type**: bearer

    **Errors**:
    - **401**: Невалидный refresh токен
    """
    try:
        payload = decode_jwt_token(request.refresh_token)
        user_id: int = int(payload.get("sub"))

        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )

        # Проверяем, что пользователь существует и активен
        user = await user_service.get_user(db, user_id)
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )

        # Генерируем новый access token
        access_token = create_access_token(
            data={"sub": str(user.id), "role": user.role}
        )

        return {
            "access_token": access_token,
            "token_type": "bearer"
        }

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db)
):
    """
    Выход пользователя из системы.

    **Note**: В JWT архитектуре logout - это client-side операция.
    Сервер только логирует событие для audit trail.

    **Errors**:
    - **401**: Не аутентифицирован
    """
    await audit_service.log_action(
        db=db,
        user_id=current_user.id,
        action="logout",
        resource_type="auth",
        resource_id=None,
        details={}
    )
    return None


@router.get("/me", response_model=UserInfo, status_code=status.HTTP_200_OK)
async def get_current_user_info(
    current_user: User = Depends(deps.get_current_user)
) -> Dict[str, Any]:
    """
    Получение информации о текущем аутентифицированном пользователе.

    **Returns**:
    - Информация о пользователе

    **Errors**:
    - **401**: Не аутентифицирован
    """
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "role": current_user.role,
        "is_active": current_user.is_active,
        "auth_provider": current_user.auth_provider,
        "created_at": current_user.created_at,
        "updated_at": current_user.updated_at
    }


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    old_password: str = Body(..., embed=True),
    new_password: str = Body(..., embed=True),
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db)
):
    """
    Изменение пароля текущего пользователя.

    **Args**:
    - **old_password**: Текущий пароль
    - **new_password**: Новый пароль

    **Errors**:
    - **400**: Неверный старый пароль или слабый новый пароль
    - **401**: Не аутентифицирован
    - **403**: Нельзя изменить пароль для external auth провайдеров
    """
    # Проверяем, что это локальный пользователь
    if current_user.auth_provider != "local":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot change password for external authentication"
        )

    # Меняем пароль через сервис
    success = await user_service.change_password(
        db, current_user.id, old_password, new_password
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid old password"
        )

    # Логируем изменение пароля
    await audit_service.log_action(
        db=db,
        user_id=current_user.id,
        action="password_changed",
        resource_type="user",
        resource_id=current_user.id,
        details={}
    )

    return None
```

### 7.4 User Management Endpoints

**Файл**: `app/api/endpoints/users.py`

```python
"""
API endpoints для управления пользователями.
"""
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.db.models.user import User
from app.schemas.user import (
    UserCreate, UserUpdate, UserInDB, UsersList,
    PasswordReset
)
from app.schemas.common import PaginationParams, PaginatedResponse
from app.services.user import user_service
from app.services.audit import audit_service


router = APIRouter()


@router.get("", response_model=PaginatedResponse[UserInDB])
async def list_users(
    page: int = Query(1, ge=1, description="Номер страницы"),
    size: int = Query(20, ge=1, le=100, description="Размер страницы"),
    search: str = Query(None, description="Поиск по username, email, full_name"),
    role: str = Query(None, description="Фильтр по роли"),
    is_active: bool = Query(None, description="Фильтр по статусу активности"),
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin_user)
) -> Dict[str, Any]:
    """
    Получение списка пользователей с пагинацией и фильтрацией.

    **Требует**: Роль admin или superadmin

    **Args**:
    - **page**: Номер страницы (начиная с 1)
    - **size**: Количество элементов на странице (1-100)
    - **search**: Текст для поиска в username, email, full_name
    - **role**: Фильтр по роли (user/admin/superadmin)
    - **is_active**: Фильтр по активности (true/false)

    **Returns**:
    - Список пользователей с пагинацией

    **Errors**:
    - **401**: Не аутентифицирован
    - **403**: Недостаточно прав
    """
    users, total = await user_service.get_users(
        db,
        skip=(page - 1) * size,
        limit=size,
        search=search,
        role=role,
        is_active=is_active
    )

    return {
        "items": [
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "full_name": u.full_name,
                "role": u.role,
                "is_active": u.is_active,
                "auth_provider": u.auth_provider,
                "created_at": u.created_at,
                "updated_at": u.updated_at
            }
            for u in users
        ],
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size
    }


@router.get("/{user_id}", response_model=UserInDB)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin_user)
) -> Dict[str, Any]:
    """
    Получение пользователя по ID.

    **Требует**: Роль admin или superadmin

    **Args**:
    - **user_id**: ID пользователя

    **Returns**:
    - Информация о пользователе

    **Errors**:
    - **401**: Не аутентифицирован
    - **403**: Недостаточно прав
    - **404**: Пользователь не найден
    """
    user = await user_service.get_user(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
        "auth_provider": user.auth_provider,
        "external_id": user.external_id,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "last_synced_at": user.last_synced_at
    }


@router.post("", response_model=UserInDB, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin_user)
) -> Dict[str, Any]:
    """
    Создание нового пользователя.

    **Требует**: Роль admin или superadmin

    **Args**:
    - **username**: Имя пользователя (уникальное)
    - **email**: Email (уникальный)
    - **password**: Пароль (минимум 8 символов)
    - **full_name**: Полное имя
    - **role**: Роль (user/admin/superadmin)

    **Returns**:
    - Созданный пользователь

    **Errors**:
    - **400**: Пользователь уже существует или слабый пароль
    - **401**: Не аутентифицирован
    - **403**: Недостаточно прав
    """
    # Проверка прав на создание superadmin
    if user_data.role == "superadmin" and current_user.role != "superadmin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only superadmin can create superadmin users"
        )

    try:
        user = await user_service.create_user(db, user_data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    # Логируем создание пользователя
    await audit_service.log_action(
        db=db,
        user_id=current_user.id,
        action="user_created",
        resource_type="user",
        resource_id=user.id,
        details={"username": user.username, "role": user.role}
    )

    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
        "auth_provider": user.auth_provider,
        "created_at": user.created_at,
        "updated_at": user.updated_at
    }


@router.patch("/{user_id}", response_model=UserInDB)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin_user)
) -> Dict[str, Any]:
    """
    Обновление пользователя.

    **Требует**: Роль admin или superadmin

    **Args**:
    - **user_id**: ID пользователя
    - **email**: Новый email (опционально)
    - **full_name**: Новое полное имя (опционально)
    - **role**: Новая роль (опционально)

    **Returns**:
    - Обновленный пользователь

    **Errors**:
    - **400**: Email уже используется
    - **401**: Не аутентифицирован
    - **403**: Недостаточно прав или попытка изменить system admin
    - **404**: Пользователь не найден
    """
    user = await user_service.get_user(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Проверка защиты system admin
    if user.username == "admin" and user_data.role and user_data.role != "superadmin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify system administrator role"
        )

    # Проверка прав на изменение роли superadmin
    if user_data.role == "superadmin" and current_user.role != "superadmin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only superadmin can assign superadmin role"
        )

    try:
        updated_user = await user_service.update_user(db, user_id, user_data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    # Логируем обновление
    await audit_service.log_action(
        db=db,
        user_id=current_user.id,
        action="user_updated",
        resource_type="user",
        resource_id=user_id,
        details=user_data.model_dump(exclude_unset=True)
    )

    return {
        "id": updated_user.id,
        "username": updated_user.username,
        "email": updated_user.email,
        "full_name": updated_user.full_name,
        "role": updated_user.role,
        "is_active": updated_user.is_active,
        "auth_provider": updated_user.auth_provider,
        "created_at": updated_user.created_at,
        "updated_at": updated_user.updated_at
    }


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_superadmin_user)
):
    """
    Удаление пользователя.

    **Требует**: Роль superadmin

    **Note**: System administrator (username='admin') не может быть удален.

    **Args**:
    - **user_id**: ID пользователя

    **Errors**:
    - **401**: Не аутентифицирован
    - **403**: Недостаточно прав или попытка удалить system admin
    - **404**: Пользователь не найден
    """
    user = await user_service.get_user(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Защита system admin от удаления
    if user.username == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete system administrator"
        )

    success = await user_service.delete_user(db, user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Логируем удаление
    await audit_service.log_action(
        db=db,
        user_id=current_user.id,
        action="user_deleted",
        resource_type="user",
        resource_id=user_id,
        details={"username": user.username}
    )

    return None


@router.post("/{user_id}/activate", status_code=status.HTTP_204_NO_CONTENT)
async def activate_user(
    user_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin_user)
):
    """
    Активация пользователя.

    **Требует**: Роль admin или superadmin

    **Args**:
    - **user_id**: ID пользователя

    **Errors**:
    - **401**: Не аутентифицирован
    - **403**: Недостаточно прав
    - **404**: Пользователь не найден
    """
    success = await user_service.activate_user(db, user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    await audit_service.log_action(
        db=db,
        user_id=current_user.id,
        action="user_activated",
        resource_type="user",
        resource_id=user_id,
        details={}
    )

    return None


@router.post("/{user_id}/deactivate", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(
    user_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin_user)
):
    """
    Деактивация пользователя.

    **Требует**: Роль admin или superadmin

    **Note**: System administrator (username='admin') не может быть деактивирован.

    **Args**:
    - **user_id**: ID пользователя

    **Errors**:
    - **401**: Не аутентифицирован
    - **403**: Недостаточно прав или попытка деактивировать system admin
    - **404**: Пользователь не найден
    """
    user = await user_service.get_user(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Защита system admin от деактивации
    if user.username == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot deactivate system administrator"
        )

    success = await user_service.deactivate_user(db, user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    await audit_service.log_action(
        db=db,
        user_id=current_user.id,
        action="user_deactivated",
        resource_type="user",
        resource_id=user_id,
        details={}
    )

    return None


@router.post("/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_user_password(
    user_id: int,
    password_data: PasswordReset,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_superadmin_user)
):
    """
    Сброс пароля пользователя (только для локальных пользователей).

    **Требует**: Роль superadmin

    **Args**:
    - **user_id**: ID пользователя
    - **new_password**: Новый пароль

    **Errors**:
    - **400**: Слабый пароль
    - **401**: Не аутентифицирован
    - **403**: Недостаточно прав или external auth провайдер
    - **404**: Пользователь не найден
    """
    user = await user_service.get_user(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if user.auth_provider != "local":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot reset password for external authentication"
        )

    try:
        await user_service.reset_password(db, user_id, password_data.new_password)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    await audit_service.log_action(
        db=db,
        user_id=current_user.id,
        action="password_reset",
        resource_type="user",
        resource_id=user_id,
        details={"reset_by": current_user.username}
    )

    return None


@router.get("/{user_id}/stats", response_model=Dict[str, Any])
async def get_user_stats(
    user_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin_user)
) -> Dict[str, Any]:
    """
    Получение статистики пользователя.

    **Требует**: Роль admin или superadmin

    **Args**:
    - **user_id**: ID пользователя

    **Returns**:
    - Статистика активности пользователя

    **Errors**:
    - **401**: Не аутентифицирован
    - **403**: Недостаточно прав
    - **404**: Пользователь не найден
    """
    user = await user_service.get_user(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    stats = await user_service.get_user_stats(db, user_id)
    return stats
```

### 7.5 OAuth2 Endpoints

**Файл**: `app/api/endpoints/oauth2.py`

```python
"""
API endpoints для OAuth2/OIDC аутентификации.
"""
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.schemas.auth import LoginResponse
from app.services.oauth2 import oauth2_service
from app.services.audit import audit_service
from app.core.security import create_access_token, create_refresh_token
from app.core.config import settings


router = APIRouter()


@router.get("/providers")
async def list_oauth2_providers() -> List[Dict[str, str]]:
    """
    Получение списка доступных OAuth2 провайдеров.

    **Returns**:
    - Список провайдеров с их названиями и идентификаторами
    """
    if not settings.oauth2.enabled:
        return []

    return [
        {
            "id": provider_id,
            "name": provider_id.capitalize()
        }
        for provider_id in settings.oauth2.providers.keys()
    ]


@router.get("/{provider}/login")
async def oauth2_login(
    provider: str,
    redirect_uri: str = Query(..., description="URL для redirect после успешной авторизации")
) -> RedirectResponse:
    """
    Инициирует OAuth2 authentication flow.

    **Args**:
    - **provider**: ID OAuth2 провайдера (например, 'dex')
    - **redirect_uri**: URL для redirect после успешной авторизации

    **Returns**:
    - Redirect на authorization endpoint провайдера

    **Errors**:
    - **400**: OAuth2 не включен или провайдер не настроен
    """
    if not settings.oauth2.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth2 authentication is not enabled"
        )

    if provider not in settings.oauth2.providers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth2 provider '{provider}' is not configured"
        )

    # Получаем authorization URL от OAuth2 service
    auth_url = await oauth2_service.get_authorization_url(provider, redirect_uri)

    return RedirectResponse(url=auth_url)


@router.get("/{provider}/callback", response_model=LoginResponse)
async def oauth2_callback(
    provider: str,
    code: str = Query(..., description="Authorization code from OAuth2 provider"),
    state: str = Query(..., description="State parameter для защиты от CSRF"),
    db: AsyncSession = Depends(deps.get_db)
) -> Dict[str, Any]:
    """
    Обработка OAuth2 callback после успешной авторизации.

    **Args**:
    - **provider**: ID OAuth2 провайдера
    - **code**: Authorization code от провайдера
    - **state**: State parameter для валидации

    **Returns**:
    - Access и refresh токены + информация о пользователе

    **Errors**:
    - **400**: Невалидный code или state
    """
    if not settings.oauth2.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth2 authentication is not enabled"
        )

    # Обмениваем authorization code на user info
    user = await oauth2_service.handle_callback(db, provider, code, state)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to authenticate with OAuth2 provider"
        )

    # Генерируем токены
    access_token = create_access_token(
        data={"sub": str(user.id), "role": user.role}
    )
    refresh_token = create_refresh_token(
        data={"sub": str(user.id)}
    )

    # Логируем успешный OAuth2 вход
    await audit_service.log_action(
        db=db,
        user_id=user.id,
        action="oauth2_login",
        resource_type="auth",
        resource_id=None,
        details={"provider": provider}
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "is_active": user.is_active
        }
    }
```

### 7.6 Health Check Endpoints

**Файл**: `app/api/endpoints/health.py`

```python
"""
API endpoints для health checks и мониторинга.
"""
from typing import Dict, Any
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.api import deps
from app.core.config import settings


router = APIRouter()


@router.get("/live")
async def liveness_check() -> Dict[str, str]:
    """
    Liveness probe для Kubernetes.

    Проверяет, что приложение запущено и отвечает.

    **Returns**:
    - status: "ok"
    """
    return {"status": "ok"}


@router.get("/ready")
async def readiness_check(
    db: AsyncSession = Depends(deps.get_db)
) -> Dict[str, Any]:
    """
    Readiness probe для Kubernetes.

    Проверяет, что приложение готово обрабатывать запросы:
    - Database доступна
    - Все зависимости работают

    **Returns**:
    - status: "ok"
    - checks: Результаты проверок зависимостей

    **Errors**:
    - **503**: Service unavailable (если DB недоступна)
    """
    checks = {}

    # Проверка database
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)}"
        from fastapi import Response
        return Response(
            content='{"status": "unhealthy", "checks": ' + str(checks) + '}',
            status_code=503,
            media_type="application/json"
        )

    return {
        "status": "ok",
        "checks": checks
    }


@router.get("/info")
async def app_info() -> Dict[str, Any]:
    """
    Информация о приложении.

    **Returns**:
    - version: Версия приложения
    - environment: Окружение
    - features: Включенные функции
    """
    return {
        "name": "ArtStore Admin Module",
        "version": "1.0.0",
        "environment": settings.environment,
        "features": {
            "ldap": settings.auth.ldap.enabled if settings.auth.ldap else False,
            "oauth2": settings.oauth2.enabled if settings.oauth2 else False
        }
    }
```

### 7.7 Главный API Router

**Файл**: `app/api/api.py`

```python
"""
Главный API router, объединяющий все endpoints.
"""
from fastapi import APIRouter

from app.api.endpoints import auth, users, oauth2, health


# Создаем главный router с префиксом /api
api_router = APIRouter()

# Auth endpoints
api_router.include_router(
    auth.router,
    prefix="/auth",
    tags=["Authentication"]
)

# User management endpoints
api_router.include_router(
    users.router,
    prefix="/users",
    tags=["Users"]
)

# OAuth2 endpoints (если включен)
api_router.include_router(
    oauth2.router,
    prefix="/oauth2",
    tags=["OAuth2"]
)

# Health check endpoints (отдельно, без /api префикса)
health_router = APIRouter()
health_router.include_router(
    health.router,
    prefix="/health",
    tags=["Health"]
)
```

### 7.8 Подключение API к приложению

**Обновить**: `app/main.py`

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.api import api_router, health_router
from app.core.config import settings


app = FastAPI(
    title="ArtStore Admin Module API",
    description="REST API для управления пользователями и элементами хранения",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем API routes
app.include_router(api_router, prefix="/api")
app.include_router(health_router)  # Health без префикса


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "ArtStore Admin Module API",
        "docs": "/docs",
        "health": "/health/live"
    }
```

### 7.9 Примеры использования API

**1. Логин**:
```bash
curl -X POST "http://localhost:8000/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "admin123"
  }'

# Response:
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "username": "admin",
    "email": "admin@artstore.com",
    "full_name": "System Administrator",
    "role": "superadmin",
    "is_active": true
  }
}
```

**2. Получить текущего пользователя**:
```bash
curl -X GET "http://localhost:8000/api/auth/me" \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc..."

# Response:
{
  "id": 1,
  "username": "admin",
  "email": "admin@artstore.com",
  "full_name": "System Administrator",
  "role": "superadmin",
  "is_active": true,
  "auth_provider": "local",
  "created_at": "2025-09-30T10:00:00",
  "updated_at": "2025-09-30T10:00:00"
}
```

**3. Создать пользователя**:
```bash
curl -X POST "http://localhost:8000/api/users" \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc..." \
  -H "Content-Type: application/json" \
  -d '{
    "username": "john_doe",
    "email": "john@example.com",
    "password": "SecurePass123!",
    "full_name": "John Doe",
    "role": "user"
  }'

# Response: 201 Created
{
  "id": 2,
  "username": "john_doe",
  "email": "john@example.com",
  "full_name": "John Doe",
  "role": "user",
  "is_active": true,
  "auth_provider": "local",
  "created_at": "2025-09-30T11:00:00",
  "updated_at": "2025-09-30T11:00:00"
}
```

**4. Список пользователей с пагинацией**:
```bash
curl -X GET "http://localhost:8000/api/users?page=1&size=20&search=john&role=user" \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc..."

# Response:
{
  "items": [
    {
      "id": 2,
      "username": "john_doe",
      "email": "john@example.com",
      "full_name": "John Doe",
      "role": "user",
      "is_active": true,
      "auth_provider": "local",
      "created_at": "2025-09-30T11:00:00",
      "updated_at": "2025-09-30T11:00:00"
    }
  ],
  "total": 1,
  "page": 1,
  "size": 20,
  "pages": 1
}
```

**5. Обновить пользователя**:
```bash
curl -X PATCH "http://localhost:8000/api/users/2" \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc..." \
  -H "Content-Type: application/json" \
  -d '{
    "email": "john.doe@example.com",
    "role": "admin"
  }'
```

**6. Деактивировать пользователя**:
```bash
curl -X POST "http://localhost:8000/api/users/2/deactivate" \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc..."

# Response: 204 No Content
```

**7. Health check**:
```bash
curl -X GET "http://localhost:8000/health/ready"

# Response:
{
  "status": "ok",
  "checks": {
    "database": "ok"
  }
}
```

**8. OAuth2 логин (Dex)**:
```bash
# Шаг 1: Получить authorization URL
curl -X GET "http://localhost:8000/api/oauth2/dex/login?redirect_uri=http://localhost:4200/auth/callback"

# Response: Redirect to Dex login page

# Шаг 2: После успешной авторизации, Dex redirect на callback
# http://localhost:8000/api/oauth2/dex/callback?code=AUTH_CODE&state=STATE

# Шаг 3: Обработка callback (автоматически)
# Response:
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "token_type": "bearer",
  "user": {
    "id": 3,
    "username": "john.doe@example.com",
    "email": "john.doe@example.com",
    "full_name": "John Doe",
    "role": "user",
    "is_active": true
  }
}
```

---

**Итого этап 7**: Создана полная API структура с endpoints для аутентификации, управления пользователями, OAuth2 integration, health checks. Все endpoints с proper authentication/authorization, error handling, audit logging.

**Следующие этапы**:
- Этап 8: Middleware и обработка ошибок
- Этап 9: Мониторинг и логирование
- Этап 10: Тестирование
- Этап 11: Docker и развертывание

---

## Этап 8: Middleware и обработка ошибок

### 8.1 Понимание Middleware в FastAPI

**Что такое Middleware?**
Middleware - это функции, которые выполняются для каждого HTTP запроса **до** и **после** обработки endpoint'а. Они позволяют добавлять cross-cutting concerns (сквозную функциональность) ко всему приложению.

**Основные концепции**:
- **Request Processing**: Middleware получает запрос перед endpoint'ом
- **Response Processing**: Middleware может модифицировать ответ после endpoint'а
- **Chain of Responsibility**: Middleware вызываются в порядке регистрации
- **Early Exit**: Middleware может прервать обработку и вернуть ответ немедленно

**Типичные use cases для Middleware**:
1. **CORS** - Cross-Origin Resource Sharing
2. **Request ID** - Уникальный идентификатор для трассировки запроса
3. **Logging** - Логирование всех запросов/ответов
4. **Timing** - Измерение времени обработки запроса
5. **Error Handling** - Централизованная обработка ошибок
6. **Rate Limiting** - Ограничение частоты запросов
7. **Authentication** - Проверка токенов (хотя лучше использовать dependencies)

### 8.2 Request ID Middleware

**Зачем нужен Request ID?**
Request ID - это уникальный идентификатор, который присваивается каждому HTTP запросу. Он позволяет:
- Отслеживать запрос через все слои приложения (distributed tracing)
- Коррелировать логи от разных сервисов
- Упрощает debugging в production

**Файл**: `app/middleware/request_id.py`

```python
"""
Middleware для добавления уникального Request ID к каждому запросу.
"""
import uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware для генерации и добавления Request ID.

    Request ID используется для:
    - Distributed tracing
    - Корреляции логов
    - Debugging в production
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Обрабатывает запрос и добавляет Request ID.

        Args:
            request: Входящий HTTP запрос
            call_next: Следующий middleware или endpoint

        Returns:
            Response с добавленным X-Request-ID header
        """
        # Проверяем, есть ли уже Request ID в заголовках
        # (например, от load balancer или API gateway)
        request_id = request.headers.get("X-Request-ID")

        # Если нет - генерируем новый
        if not request_id:
            request_id = str(uuid.uuid4())

        # Сохраняем Request ID в request state для доступа в endpoints
        request.state.request_id = request_id

        # Обрабатываем запрос
        response = await call_next(request)

        # Добавляем Request ID в response headers
        response.headers["X-Request-ID"] = request_id

        return response
```

**Объяснение**:
1. Проверяем наличие `X-Request-ID` header (может быть добавлен load balancer'ом)
2. Если нет - генерируем UUID
3. Сохраняем в `request.state` для доступа в endpoint'ах
4. Добавляем в response headers для клиента

### 8.3 Timing Middleware

**Зачем измерять время?**
Timing middleware позволяет:
- Отслеживать производительность каждого endpoint'а
- Обнаруживать медленные запросы
- Собирать метрики для мониторинга
- Оптимизировать узкие места

**Файл**: `app/middleware/timing.py`

```python
"""
Middleware для измерения времени обработки запросов.
"""
import time
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import structlog


logger = structlog.get_logger()


class TimingMiddleware(BaseHTTPMiddleware):
    """
    Middleware для измерения и логирования времени обработки запросов.
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Измеряет время обработки запроса.

        Args:
            request: Входящий HTTP запрос
            call_next: Следующий middleware или endpoint

        Returns:
            Response с добавленным X-Process-Time header
        """
        # Запоминаем время начала
        start_time = time.time()

        # Обрабатываем запрос
        response = await call_next(request)

        # Вычисляем время обработки
        process_time = time.time() - start_time

        # Добавляем в response headers (в секундах)
        response.headers["X-Process-Time"] = str(process_time)

        # Логируем запрос с timing информацией
        logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            process_time=process_time,
            request_id=getattr(request.state, "request_id", None)
        )

        # Если запрос медленный (>1 секунды) - логируем warning
        if process_time > 1.0:
            logger.warning(
                "slow_request",
                method=request.method,
                path=request.url.path,
                process_time=process_time,
                threshold=1.0
            )

        return response
```

**Объяснение**:
1. Засекаем время до обработки запроса
2. Вызываем endpoint
3. Вычисляем разницу времени
4. Добавляем в headers и логируем
5. Логируем warning для медленных запросов (>1 сек)

### 8.4 CORS Middleware

**Что такое CORS?**
CORS (Cross-Origin Resource Sharing) - механизм, позволяющий веб-приложениям с одного домена делать запросы к API на другом домене.

**Когда нужен CORS?**
- Frontend (localhost:4200) делает запросы к Backend (localhost:8000)
- Production: app.example.com → api.example.com

**Настройка в main.py** (уже добавлено в этап 7, но расширим):

**Файл**: `app/core/config.py` (дополнение)

```python
class Settings(BaseSettings):
    # ... существующие настройки ...

    # CORS settings
    cors_origins: List[str] = Field(
        default=["http://localhost:4200", "http://localhost:3000"],
        description="Allowed CORS origins"
    )
    cors_allow_credentials: bool = Field(
        default=True,
        description="Allow credentials (cookies, authorization headers)"
    )
    cors_allow_methods: List[str] = Field(
        default=["*"],
        description="Allowed HTTP methods"
    )
    cors_allow_headers: List[str] = Field(
        default=["*"],
        description="Allowed HTTP headers"
    )
```

**Обновление main.py**:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)
```

### 8.5 Централизованная обработка ошибок

**Зачем нужна централизованная обработка?**
- Единообразный формат ошибок для клиентов
- Логирование всех ошибок в одном месте
- Скрытие internal details от клиентов
- Proper HTTP status codes

**Типы ошибок**:
1. **HTTPException** - контролируемые ошибки (404, 403, 401)
2. **ValidationError** - ошибки валидации Pydantic
3. **DatabaseError** - ошибки базы данных
4. **UnexpectedError** - неожиданные исключения (500)

**Файл**: `app/middleware/error_handlers.py`

```python
"""
Централизованная обработка ошибок.
"""
from typing import Union
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.exc import SQLAlchemyError
import structlog

from app.schemas.common import ErrorResponse


logger = structlog.get_logger()


async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException
) -> JSONResponse:
    """
    Обработчик для HTTPException.

    Обрабатывает контролируемые ошибки (401, 403, 404, etc.)

    Args:
        request: HTTP запрос
        exc: HTTPException

    Returns:
        JSONResponse с информацией об ошибке
    """
    # Логируем ошибку
    logger.warning(
        "http_exception",
        status_code=exc.status_code,
        detail=exc.detail,
        path=request.url.path,
        method=request.method,
        request_id=getattr(request.state, "request_id", None)
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.status_code,
                "message": exc.detail,
                "request_id": getattr(request.state, "request_id", None)
            }
        }
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError
) -> JSONResponse:
    """
    Обработчик для ошибок валидации Pydantic.

    Возвращает подробную информацию о том, какие поля не прошли валидацию.

    Args:
        request: HTTP запрос
        exc: RequestValidationError

    Returns:
        JSONResponse с детальной информацией об ошибках валидации
    """
    # Логируем ошибку валидации
    logger.warning(
        "validation_error",
        errors=exc.errors(),
        body=exc.body,
        path=request.url.path,
        method=request.method,
        request_id=getattr(request.state, "request_id", None)
    )

    # Форматируем ошибки валидации для клиента
    errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"])
        errors.append({
            "field": field,
            "message": error["msg"],
            "type": error["type"]
        })

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": 422,
                "message": "Validation error",
                "details": errors,
                "request_id": getattr(request.state, "request_id", None)
            }
        }
    )


async def database_exception_handler(
    request: Request,
    exc: SQLAlchemyError
) -> JSONResponse:
    """
    Обработчик для ошибок базы данных.

    Скрывает internal детали от клиента и логирует полную информацию.

    Args:
        request: HTTP запрос
        exc: SQLAlchemyError

    Returns:
        JSONResponse с generic сообщением об ошибке БД
    """
    # Логируем полную информацию об ошибке БД
    logger.error(
        "database_error",
        error=str(exc),
        error_type=type(exc).__name__,
        path=request.url.path,
        method=request.method,
        request_id=getattr(request.state, "request_id", None),
        exc_info=True  # Включает stack trace
    )

    # Возвращаем generic сообщение клиенту (не раскрываем детали БД)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": 500,
                "message": "Database error occurred",
                "request_id": getattr(request.state, "request_id", None)
            }
        }
    )


async def unhandled_exception_handler(
    request: Request,
    exc: Exception
) -> JSONResponse:
    """
    Обработчик для всех неожиданных исключений.

    Catch-all для любых ошибок, которые не были обработаны другими handlers.

    Args:
        request: HTTP запрос
        exc: Exception

    Returns:
        JSONResponse с generic сообщением об internal error
    """
    # Логируем критическую ошибку с полным stack trace
    logger.error(
        "unhandled_exception",
        error=str(exc),
        error_type=type(exc).__name__,
        path=request.url.path,
        method=request.method,
        request_id=getattr(request.state, "request_id", None),
        exc_info=True  # Полный stack trace
    )

    # Возвращаем generic сообщение (не раскрываем internal детали)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": 500,
                "message": "Internal server error",
                "request_id": getattr(request.state, "request_id", None)
            }
        }
    )
```

**Объяснение**:
1. **http_exception_handler** - обрабатывает контролируемые ошибки (401, 404, etc.)
2. **validation_exception_handler** - форматирует ошибки валидации Pydantic в user-friendly вид
3. **database_exception_handler** - скрывает детали БД от клиента, логирует полную информацию
4. **unhandled_exception_handler** - catch-all для неожиданных ошибок

### 8.6 Custom Exception Classes

**Зачем нужны custom exceptions?**
- Более выразительный код (BusinessLogicError vs generic Exception)
- Специфичная обработка для разных типов ошибок
- Упрощает testing

**Файл**: `app/core/exceptions.py`

```python
"""
Custom exception classes для приложения.
"""
from typing import Optional, Any, Dict
from fastapi import status


class AppException(Exception):
    """
    Базовый класс для всех application exceptions.
    """
    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class AuthenticationError(AppException):
    """
    Ошибка аутентификации.

    Используется когда credentials невалидны.
    """
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED
        )


class AuthorizationError(AppException):
    """
    Ошибка авторизации.

    Используется когда пользователь не имеет прав на операцию.
    """
    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN
        )


class ResourceNotFoundError(AppException):
    """
    Ошибка "ресурс не найден".

    Используется когда запрашиваемый ресурс отсутствует.
    """
    def __init__(self, resource: str, resource_id: Any):
        super().__init__(
            message=f"{resource} with id {resource_id} not found",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"resource": resource, "id": str(resource_id)}
        )


class ResourceAlreadyExistsError(AppException):
    """
    Ошибка "ресурс уже существует".

    Используется при попытке создать дублирующий ресурс.
    """
    def __init__(self, resource: str, field: str, value: Any):
        super().__init__(
            message=f"{resource} with {field}={value} already exists",
            status_code=status.HTTP_409_CONFLICT,
            details={"resource": resource, "field": field, "value": str(value)}
        )


class ValidationError(AppException):
    """
    Ошибка бизнес-логики валидации.

    Отличается от Pydantic ValidationError - это логические правила.
    """
    def __init__(self, message: str, field: Optional[str] = None):
        details = {"field": field} if field else {}
        super().__init__(
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details
        )


class ExternalServiceError(AppException):
    """
    Ошибка внешнего сервиса (LDAP, OAuth2, etc.)
    """
    def __init__(self, service: str, message: str):
        super().__init__(
            message=f"{service} error: {message}",
            status_code=status.HTTP_502_BAD_GATEWAY,
            details={"service": service}
        )


class RateLimitError(AppException):
    """
    Ошибка превышения rate limit.
    """
    def __init__(self, retry_after: int):
        super().__init__(
            message=f"Rate limit exceeded. Retry after {retry_after} seconds",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details={"retry_after": retry_after}
        )
```

**Использование в коде**:

```python
from app.core.exceptions import ResourceNotFoundError, ValidationError

# В service layer
async def get_user(db: AsyncSession, user_id: int) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise ResourceNotFoundError("User", user_id)
    return user

# В business logic
async def create_user(db: AsyncSession, data: UserCreate) -> User:
    # Проверка на существование
    existing = await db.execute(
        select(User).where(User.username == data.username)
    )
    if existing.scalar_one_or_none():
        raise ResourceAlreadyExistsError("User", "username", data.username)

    # Валидация пароля
    if len(data.password) < 8:
        raise ValidationError("Password must be at least 8 characters", "password")

    # Создание пользователя
    # ...
```

**Обработчик для AppException**:

```python
# Добавить в app/middleware/error_handlers.py

async def app_exception_handler(
    request: Request,
    exc: AppException
) -> JSONResponse:
    """
    Обработчик для custom AppException.
    """
    logger.warning(
        "app_exception",
        message=exc.message,
        status_code=exc.status_code,
        details=exc.details,
        path=request.url.path,
        request_id=getattr(request.state, "request_id", None)
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.status_code,
                "message": exc.message,
                "details": exc.details,
                "request_id": getattr(request.state, "request_id", None)
            }
        }
    )
```

### 8.7 Rate Limiting Middleware

**Зачем нужен Rate Limiting?**
- Защита от DDoS атак
- Предотвращение abuse API
- Справедливое распределение ресурсов между клиентами
- Защита от brute-force атак на login

**Файл**: `app/middleware/rate_limit.py`

```python
"""
Rate limiting middleware используя Redis.
"""
import time
from typing import Callable, Optional
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import structlog
import redis.asyncio as redis

from app.core.config import settings
from app.core.exceptions import RateLimitError


logger = structlog.get_logger()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware для ограничения частоты запросов (rate limiting).

    Использует Redis для хранения счетчиков запросов.
    Алгоритм: Sliding Window.
    """

    def __init__(
        self,
        app: ASGIApp,
        redis_client: redis.Redis,
        default_limit: int = 100,  # запросов
        window: int = 60  # секунд
    ):
        super().__init__(app)
        self.redis = redis_client
        self.default_limit = default_limit
        self.window = window

    def _get_rate_limit_key(self, request: Request, identifier: str) -> str:
        """
        Генерирует ключ для Redis.

        Args:
            request: HTTP запрос
            identifier: Идентификатор клиента (IP или user_id)

        Returns:
            Ключ для Redis
        """
        # Формат: rate_limit:{path}:{identifier}:{window_start}
        window_start = int(time.time() / self.window) * self.window
        return f"rate_limit:{request.url.path}:{identifier}:{window_start}"

    def _get_client_identifier(self, request: Request) -> str:
        """
        Получает идентификатор клиента.

        Порядок приоритета:
        1. User ID (если аутентифицирован)
        2. IP адрес

        Args:
            request: HTTP запрос

        Returns:
            Идентификатор клиента
        """
        # Если пользователь аутентифицирован - используем user_id
        if hasattr(request.state, "user") and request.state.user:
            return f"user:{request.state.user.id}"

        # Иначе используем IP адрес
        # Проверяем X-Forwarded-For header (если за proxy)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Берем первый IP (клиент)
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            client_ip = request.client.host

        return f"ip:{client_ip}"

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Проверяет rate limit перед обработкой запроса.

        Args:
            request: HTTP запрос
            call_next: Следующий middleware или endpoint

        Returns:
            Response или RateLimitError
        """
        # Пропускаем health checks
        if request.url.path.startswith("/health"):
            return await call_next(request)

        # Получаем идентификатор клиента
        identifier = self._get_client_identifier(request)

        # Формируем ключ для Redis
        key = self._get_rate_limit_key(request, identifier)

        try:
            # Инкрементируем счетчик
            current = await self.redis.incr(key)

            # Если это первый запрос в окне - устанавливаем TTL
            if current == 1:
                await self.redis.expire(key, self.window)

            # Проверяем лимит
            if current > self.default_limit:
                # Получаем TTL для retry_after
                ttl = await self.redis.ttl(key)

                logger.warning(
                    "rate_limit_exceeded",
                    identifier=identifier,
                    path=request.url.path,
                    current=current,
                    limit=self.default_limit,
                    retry_after=ttl
                )

                raise RateLimitError(retry_after=ttl if ttl > 0 else self.window)

            # Добавляем rate limit headers в response
            response = await call_next(request)

            response.headers["X-RateLimit-Limit"] = str(self.default_limit)
            response.headers["X-RateLimit-Remaining"] = str(self.default_limit - current)
            response.headers["X-RateLimit-Reset"] = str(int(time.time()) + await self.redis.ttl(key))

            return response

        except RateLimitError:
            raise  # Re-raise для обработки error handler'ом
        except Exception as e:
            # Если Redis недоступен - логируем ошибку и пропускаем запрос
            logger.error(
                "rate_limit_redis_error",
                error=str(e),
                identifier=identifier
            )
            return await call_next(request)
```

**Объяснение алгоритма**:
1. **Sliding Window**: Каждое окно времени (например, 60 секунд) получает свой счетчик
2. **Идентификация клиента**: По user_id (если аутентифицирован) или IP
3. **Redis INCR**: Атомарная операция инкремента счетчика
4. **TTL**: Автоматическое удаление старых счетчиков
5. **Graceful Degradation**: Если Redis недоступен - пропускаем запрос

### 8.8 Интеграция Middleware и Error Handlers

**Файл**: `app/main.py` (полная версия с middleware)

```python
"""
Главный файл приложения FastAPI с middleware и error handlers.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.exc import SQLAlchemyError
import redis.asyncio as redis

from app.api.api import api_router, health_router
from app.core.config import settings
from app.core.exceptions import AppException
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.timing import TimingMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.error_handlers import (
    http_exception_handler,
    validation_exception_handler,
    database_exception_handler,
    unhandled_exception_handler,
    app_exception_handler
)


# Создаем FastAPI приложение
app = FastAPI(
    title="ArtStore Admin Module API",
    description="REST API для управления пользователями и элементами хранения",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)


# ============================================================================
# MIDDLEWARE (порядок важен! Выполняются сверху вниз)
# ============================================================================

# 1. CORS - должен быть первым
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)

# 2. Request ID - добавляет уникальный ID к каждому запросу
app.add_middleware(RequestIDMiddleware)

# 3. Timing - измеряет время обработки
app.add_middleware(TimingMiddleware)

# 4. Rate Limiting (опционально, требует Redis)
if settings.redis_url:
    redis_client = redis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True
    )
    app.add_middleware(
        RateLimitMiddleware,
        redis_client=redis_client,
        default_limit=100,  # 100 запросов
        window=60  # за 60 секунд
    )


# ============================================================================
# ERROR HANDLERS
# ============================================================================

# Custom AppException
app.add_exception_handler(AppException, app_exception_handler)

# HTTP ошибки (401, 404, etc.)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)

# Ошибки валидации Pydantic
app.add_exception_handler(RequestValidationError, validation_exception_handler)

# Ошибки базы данных
app.add_exception_handler(SQLAlchemyError, database_exception_handler)

# Catch-all для неожиданных ошибок
app.add_exception_handler(Exception, unhandled_exception_handler)


# ============================================================================
# ROUTES
# ============================================================================

# API endpoints
app.include_router(api_router, prefix="/api")

# Health checks (без префикса)
app.include_router(health_router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "ArtStore Admin Module API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health/live"
    }


# ============================================================================
# STARTUP & SHUTDOWN EVENTS
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """
    Действия при запуске приложения.
    """
    import structlog
    logger = structlog.get_logger()

    logger.info(
        "application_startup",
        version="1.0.0",
        environment=settings.environment
    )


@app.on_event("shutdown")
async def shutdown_event():
    """
    Действия при остановке приложения.
    """
    import structlog
    logger = structlog.get_logger()

    logger.info("application_shutdown")

    # Закрываем Redis connection если используется
    if settings.redis_url:
        await redis_client.close()
```

### 8.9 Примеры ответов с ошибками

**1. Validation Error (422)**:
```bash
curl -X POST "http://localhost:8000/api/users" \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "a",
    "email": "invalid-email"
  }'

# Response: 422
{
  "error": {
    "code": 422,
    "message": "Validation error",
    "details": [
      {
        "field": "username",
        "message": "ensure this value has at least 3 characters",
        "type": "value_error.any_str.min_length"
      },
      {
        "field": "email",
        "message": "value is not a valid email address",
        "type": "value_error.email"
      },
      {
        "field": "password",
        "message": "field required",
        "type": "value_error.missing"
      }
    ],
    "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
  }
}
```

**2. Authentication Error (401)**:
```bash
curl -X GET "http://localhost:8000/api/auth/me" \
  -H "Authorization: Bearer invalid_token"

# Response: 401
{
  "error": {
    "code": 401,
    "message": "Invalid token",
    "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
  }
}
```

**3. Authorization Error (403)**:
```bash
curl -X DELETE "http://localhost:8000/api/users/1" \
  -H "Authorization: Bearer USER_TOKEN"

# Response: 403
{
  "error": {
    "code": 403,
    "message": "Superadministrator privileges required",
    "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
  }
}
```

**4. Resource Not Found (404)**:
```bash
curl -X GET "http://localhost:8000/api/users/999" \
  -H "Authorization: Bearer TOKEN"

# Response: 404
{
  "error": {
    "code": 404,
    "message": "User with id 999 not found",
    "details": {
      "resource": "User",
      "id": "999"
    },
    "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
  }
}
```

**5. Resource Already Exists (409)**:
```bash
curl -X POST "http://localhost:8000/api/users" \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "email": "admin@artstore.com",
    "password": "password123"
  }'

# Response: 409
{
  "error": {
    "code": 409,
    "message": "User with username=admin already exists",
    "details": {
      "resource": "User",
      "field": "username",
      "value": "admin"
    },
    "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
  }
}
```

**6. Rate Limit Exceeded (429)**:
```bash
# После 100 запросов за минуту
curl -X GET "http://localhost:8000/api/users"

# Response: 429
{
  "error": {
    "code": 429,
    "message": "Rate limit exceeded. Retry after 45 seconds",
    "details": {
      "retry_after": 45
    },
    "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
  }
}
```

**7. Internal Server Error (500)**:
```bash
# При неожиданной ошибке
curl -X GET "http://localhost:8000/api/users/1"

# Response: 500
{
  "error": {
    "code": 500,
    "message": "Internal server error",
    "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
  }
}

# В логах будет полная информация об ошибке
```

### 8.10 Response Headers для всех запросов

**Успешный запрос**:
```
HTTP/1.1 200 OK
Content-Type: application/json
X-Request-ID: a1b2c3d4-e5f6-7890-abcd-ef1234567890
X-Process-Time: 0.0234
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 87
X-RateLimit-Reset: 1696070400
```

---

**Итого этап 8**: Создана полная система middleware и обработки ошибок:
- Request ID для distributed tracing
- Timing для мониторинга производительности
- CORS для frontend integration
- Централизованная обработка ошибок с proper logging
- Custom exception classes для выразительного кода
- Rate limiting для защиты от abuse
- Единообразный формат ошибок для клиентов
- Полное логирование всех ошибок

**Следующие этапы**:
- Этап 9: Мониторинг и логирование
- Этап 10: Тестирование
- Этап 11: Docker и развертывание

---

## Этап 9: Мониторинг и логирование

### 9.1 Понимание Observability (наблюдаемости)

**Что такое Observability?**
Observability - это способность понимать внутреннее состояние системы на основе её внешних выходных данных. В контексте приложений это означает три основных компонента:

**Три столпа Observability**:
1. **Logs (Логи)** - записи событий, происходящих в системе
2. **Metrics (Метрики)** - числовые данные о производительности и состоянии
3. **Traces (Трейсы)** - распределенное отслеживание запросов через микросервисы

**Зачем нужен мониторинг?**
- Обнаружение проблем до того, как пользователи их заметят
- Быстрое реагирование на инциденты
- Понимание производительности приложения
- Capacity planning и прогнозирование нагрузки
- Debugging в production окружении

### 9.2 Structured Logging с Structlog

**Почему structured logging?**
Вместо обычных текстовых логов:
```
2025-09-30 10:15:30 - User admin logged in from 192.168.1.1
```

Используем структурированные (JSON) логи:
```json
{
  "timestamp": "2025-09-30T10:15:30.123Z",
  "level": "info",
  "event": "user_login",
  "user_id": 1,
  "username": "admin",
  "ip": "192.168.1.1",
  "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

**Преимущества structured logging**:
- Легко парсить и анализировать (ELK, Grafana Loki, CloudWatch)
- Можно делать поиск и фильтрацию по полям
- Интеграция с monitoring системами
- Correlation между событиями через request_id

**Установка зависимостей**:
```bash
pip install structlog python-json-logger
```

**Файл**: `app/core/logging_config.py`

```python
"""
Настройка structured logging с structlog.
"""
import logging
import sys
from typing import Any
import structlog
from pythonjsonlogger import jsonlogger

from app.core.config import settings


def setup_logging() -> None:
    """
    Настраивает structured logging для приложения.

    Использует structlog для удобного API и JSON формат для вывода.
    """
    # Настройка стандартного Python logging
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO if settings.environment == "production" else logging.DEBUG)

    # Очищаем существующие handlers
    root_logger.handlers = []

    # Создаем handler для stdout
    handler = logging.StreamHandler(sys.stdout)

    # JSON formatter для structured logs
    if settings.environment == "production":
        formatter = jsonlogger.JsonFormatter(
            fmt="%(timestamp)s %(level)s %(event)s %(logger)s",
            rename_fields={
                "levelname": "level",
                "name": "logger",
                "asctime": "timestamp"
            }
        )
    else:
        # В development используем более читаемый формат
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Настройка structlog
    structlog.configure(
        processors=[
            # Добавляем имя logger'а
            structlog.stdlib.add_logger_name,
            # Добавляем уровень лога
            structlog.stdlib.add_log_level,
            # Добавляем timestamp
            structlog.processors.TimeStamper(fmt="iso"),
            # Добавляем stack trace для исключений
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            # Для development - цветной вывод
            structlog.dev.ConsoleRenderer() if settings.environment != "production"
            else structlog.processors.JSONRenderer()
        ],
        # Контекст для всех логов
        context_class=dict,
        # Используем стандартный logging
        logger_factory=structlog.stdlib.LoggerFactory(),
        # Кэшируем logger'ы
        cache_logger_on_first_use=True,
    )


# Вспомогательная функция для добавления контекста к логам
def get_logger(**initial_values: Any) -> structlog.BoundLogger:
    """
    Создает logger с начальным контекстом.

    Args:
        **initial_values: Начальные значения контекста

    Returns:
        Configured structlog logger

    Example:
        >>> logger = get_logger(module="user_service")
        >>> logger.info("user_created", user_id=123, username="john")
    """
    return structlog.get_logger().bind(**initial_values)
```

**Обновление**: `app/main.py` (добавить в startup)

```python
from app.core.logging_config import setup_logging

@app.on_event("startup")
async def startup_event():
    """
    Действия при запуске приложения.
    """
    # Настраиваем logging
    setup_logging()

    logger = structlog.get_logger()
    logger.info(
        "application_startup",
        version="1.0.0",
        environment=settings.environment
    )
```

**Примеры использования в коде**:

```python
import structlog

logger = structlog.get_logger()

# Простое событие
logger.info("user_login", user_id=123, username="admin")

# С контекстом
logger = logger.bind(user_id=123, username="admin")
logger.info("password_changed")
logger.info("email_updated", new_email="new@example.com")

# Ошибки с stack trace
try:
    result = risky_operation()
except Exception as e:
    logger.error(
        "operation_failed",
        operation="risky_operation",
        error=str(e),
        exc_info=True  # Добавляет stack trace
    )

# С request context (в endpoint'ах)
def endpoint(request: Request):
    logger = structlog.get_logger().bind(
        request_id=request.state.request_id,
        user_id=request.state.user.id if hasattr(request.state, "user") else None
    )
    logger.info("endpoint_called", path=request.url.path)
```

### 9.3 Prometheus Metrics

**Что такое Prometheus?**
Prometheus - это система мониторинга и time-series database. Она собирает метрики через HTTP endpoints и позволяет делать queries, alerts, и visualizations (обычно через Grafana).

**Типы метрик в Prometheus**:
1. **Counter** - всегда растет (количество запросов, ошибок)
2. **Gauge** - может увеличиваться и уменьшаться (текущие активные пользователи, память)
3. **Histogram** - распределение значений (latency, размеры запросов)
4. **Summary** - похож на histogram, но с квантилями

**Установка зависимостей**:
```bash
pip install prometheus-client
```

**Файл**: `app/core/metrics.py`

```python
"""
Prometheus метрики для мониторинга.
"""
from prometheus_client import Counter, Histogram, Gauge, Info
from prometheus_client import CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Request, Response


# Создаем registry для метрик
registry = CollectorRegistry()

# ============================================================================
# HTTP REQUEST METRICS
# ============================================================================

# Counter для общего количества HTTP запросов
http_requests_total = Counter(
    "http_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "status_code"],
    registry=registry
)

# Histogram для latency HTTP запросов
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    registry=registry
)

# Counter для ошибок HTTP
http_errors_total = Counter(
    "http_errors_total",
    "Total number of HTTP errors",
    ["method", "endpoint", "status_code"],
    registry=registry
)

# ============================================================================
# AUTHENTICATION METRICS
# ============================================================================

# Counter для попыток входа
auth_login_attempts_total = Counter(
    "auth_login_attempts_total",
    "Total number of login attempts",
    ["status", "method"],  # status: success/failed, method: local/ldap/oauth2
    registry=registry
)

# Counter для создания токенов
auth_tokens_created_total = Counter(
    "auth_tokens_created_total",
    "Total number of tokens created",
    ["token_type"],  # access/refresh
    registry=registry
)

# Counter для невалидных токенов
auth_invalid_tokens_total = Counter(
    "auth_invalid_tokens_total",
    "Total number of invalid token validations",
    registry=registry
)

# ============================================================================
# USER METRICS
# ============================================================================

# Gauge для текущего количества активных пользователей
users_active_total = Gauge(
    "users_active_total",
    "Current number of active users",
    registry=registry
)

# Counter для созданных пользователей
users_created_total = Counter(
    "users_created_total",
    "Total number of users created",
    ["role"],  # user/admin/superadmin
    registry=registry
)

# Counter для удаленных пользователей
users_deleted_total = Counter(
    "users_deleted_total",
    "Total number of users deleted",
    registry=registry
)

# ============================================================================
# DATABASE METRICS
# ============================================================================

# Counter для database queries
db_queries_total = Counter(
    "db_queries_total",
    "Total number of database queries",
    ["operation"],  # select/insert/update/delete
    registry=registry
)

# Histogram для database query latency
db_query_duration_seconds = Histogram(
    "db_query_duration_seconds",
    "Database query latency in seconds",
    ["operation"],
    registry=registry
)

# Counter для database errors
db_errors_total = Counter(
    "db_errors_total",
    "Total number of database errors",
    ["error_type"],
    registry=registry
)

# ============================================================================
# EXTERNAL SERVICE METRICS
# ============================================================================

# Counter для LDAP запросов
ldap_requests_total = Counter(
    "ldap_requests_total",
    "Total number of LDAP requests",
    ["operation", "status"],  # operation: auth/search, status: success/failed
    registry=registry
)

# Counter для OAuth2 запросов
oauth2_requests_total = Counter(
    "oauth2_requests_total",
    "Total number of OAuth2 requests",
    ["provider", "operation", "status"],
    registry=registry
)

# ============================================================================
# RATE LIMITING METRICS
# ============================================================================

# Counter для rate limit hits
rate_limit_hits_total = Counter(
    "rate_limit_hits_total",
    "Total number of rate limit hits",
    ["identifier_type"],  # user/ip
    registry=registry
)

# ============================================================================
# APPLICATION INFO
# ============================================================================

# Info metric для версии приложения
app_info = Info(
    "app",
    "Application information",
    registry=registry
)
app_info.info({
    "version": "1.0.0",
    "name": "artstore-admin-module"
})


def metrics_endpoint() -> Response:
    """
    Endpoint для Prometheus scraping.

    Returns:
        Response с метриками в формате Prometheus
    """
    data = generate_latest(registry)
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
```

**Добавление metrics endpoint**:

**Файл**: `app/api/endpoints/metrics.py`

```python
"""
Metrics endpoint для Prometheus.
"""
from fastapi import APIRouter
from fastapi.responses import Response

from app.core.metrics import metrics_endpoint


router = APIRouter()


@router.get("")
async def get_metrics() -> Response:
    """
    Prometheus metrics endpoint.

    Этот endpoint scraped Prometheus каждые N секунд.

    Returns:
        Метрики в Prometheus формате
    """
    return metrics_endpoint()
```

**Подключение в api.py**:

```python
from app.api.endpoints import metrics

# Metrics endpoint (отдельно от /api)
metrics_router = APIRouter()
metrics_router.include_router(
    metrics.router,
    prefix="/metrics",
    tags=["Metrics"]
)
```

**В main.py**:

```python
from app.api.api import metrics_router

# Metrics endpoint
app.include_router(metrics_router)
```

**Middleware для автоматического сбора HTTP метрик**:

**Файл**: `app/middleware/metrics.py`

```python
"""
Middleware для автоматического сбора Prometheus метрик.
"""
import time
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.metrics import (
    http_requests_total,
    http_request_duration_seconds,
    http_errors_total
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """
    Middleware для сбора метрик HTTP запросов.
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Собирает метрики для каждого HTTP запроса.
        """
        # Пропускаем сам metrics endpoint
        if request.url.path == "/metrics":
            return await call_next(request)

        # Засекаем время
        start_time = time.time()

        # Обрабатываем запрос
        response = await call_next(request)

        # Вычисляем длительность
        duration = time.time() - start_time

        # Извлекаем метаданные
        method = request.method
        endpoint = request.url.path
        status_code = response.status_code

        # Обновляем метрики
        http_requests_total.labels(
            method=method,
            endpoint=endpoint,
            status_code=status_code
        ).inc()

        http_request_duration_seconds.labels(
            method=method,
            endpoint=endpoint
        ).observe(duration)

        # Если ошибка - увеличиваем счетчик ошибок
        if status_code >= 400:
            http_errors_total.labels(
                method=method,
                endpoint=endpoint,
                status_code=status_code
            ).inc()

        return response
```

**Добавить в main.py**:

```python
from app.middleware.metrics import MetricsMiddleware

# После других middleware
app.add_middleware(MetricsMiddleware)
```

**Использование метрик в коде**:

```python
from app.core.metrics import (
    auth_login_attempts_total,
    users_created_total,
    db_queries_total
)

# В auth service
async def authenticate(username: str, password: str):
    try:
        user = await authenticate_user(username, password)
        auth_login_attempts_total.labels(
            status="success",
            method="local"
        ).inc()
        return user
    except:
        auth_login_attempts_total.labels(
            status="failed",
            method="local"
        ).inc()
        raise

# В user service
async def create_user(data: UserCreate):
    user = await create_user_in_db(data)
    users_created_total.labels(role=user.role).inc()
    return user

# В database layer
async def execute_query(query):
    with db_query_duration_seconds.labels(operation="select").time():
        result = await db.execute(query)
    db_queries_total.labels(operation="select").inc()
    return result
```

### 9.4 OpenTelemetry для Distributed Tracing

**Что такое Distributed Tracing?**
Distributed Tracing позволяет отслеживать путь запроса через все микросервисы. Это критически важно для debugging в распределенных системах.

**Концепции OpenTelemetry**:
- **Trace** - полный путь запроса от начала до конца
- **Span** - отдельная операция в рамках trace (DB query, HTTP call, function execution)
- **Context Propagation** - передача trace информации между сервисами

**Установка зависимостей**:
```bash
pip install opentelemetry-api opentelemetry-sdk opentelemetry-instrumentation-fastapi opentelemetry-instrumentation-sqlalchemy opentelemetry-instrumentation-redis opentelemetry-exporter-otlp
```

**Файл**: `app/core/tracing.py`

```python
"""
OpenTelemetry настройка для distributed tracing.
"""
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor

from app.core.config import settings


def setup_tracing(app) -> None:
    """
    Настраивает OpenTelemetry для distributed tracing.

    Args:
        app: FastAPI application instance
    """
    # Если tracing не включен - пропускаем
    if not settings.otlp_endpoint:
        return

    # Создаем resource с метаданными о сервисе
    resource = Resource.create({
        "service.name": "artstore-admin-module",
        "service.version": "1.0.0",
        "deployment.environment": settings.environment
    })

    # Создаем tracer provider
    tracer_provider = TracerProvider(resource=resource)

    # Настраиваем OTLP exporter (для отправки в Jaeger/Tempo/etc.)
    otlp_exporter = OTLPSpanExporter(
        endpoint=settings.otlp_endpoint,
        insecure=True  # В production использовать TLS
    )

    # Добавляем batch processor для эффективной отправки
    tracer_provider.add_span_processor(
        BatchSpanProcessor(otlp_exporter)
    )

    # Устанавливаем как глобальный tracer provider
    trace.set_tracer_provider(tracer_provider)

    # Автоматическое инструментирование FastAPI
    FastAPIInstrumentor.instrument_app(app)

    # Автоматическое инструментирование SQLAlchemy
    SQLAlchemyInstrumentor().instrument()

    # Автоматическое инструментирование Redis (если используется)
    if settings.redis_url:
        RedisInstrumentor().instrument()


# Получение tracer для manual instrumentation
def get_tracer(name: str = __name__):
    """
    Получает tracer для создания custom spans.

    Args:
        name: Имя tracer'а (обычно __name__ модуля)

    Returns:
        OpenTelemetry tracer
    """
    return trace.get_tracer(name)
```

**Обновление main.py**:

```python
from app.core.tracing import setup_tracing

@app.on_event("startup")
async def startup_event():
    # ... существующий код ...

    # Настраиваем tracing
    setup_tracing(app)
```

**Обновление config.py**:

```python
class Settings(BaseSettings):
    # ... существующие настройки ...

    # OpenTelemetry settings
    otlp_endpoint: Optional[str] = Field(
        default=None,
        description="OTLP endpoint for traces (e.g., http://localhost:4317)"
    )
```

**Manual instrumentation (custom spans)**:

```python
from app.core.tracing import get_tracer

tracer = get_tracer(__name__)

async def complex_operation():
    # Создаем parent span
    with tracer.start_as_current_span("complex_operation") as span:
        # Добавляем атрибуты к span
        span.set_attribute("user.id", user_id)
        span.set_attribute("operation.type", "data_processing")

        # Child span для database query
        with tracer.start_as_current_span("database_query") as db_span:
            db_span.set_attribute("db.system", "postgresql")
            db_span.set_attribute("db.statement", "SELECT * FROM users")
            result = await db.execute(query)

        # Child span для external API call
        with tracer.start_as_current_span("ldap_authentication") as ldap_span:
            ldap_span.set_attribute("ldap.server", "ldap://localhost:389")
            user = await ldap_service.authenticate(username, password)

            # Добавляем event к span
            ldap_span.add_event("authentication_successful", {
                "username": username
            })

        return result
```

### 9.5 Health Checks с детальной информацией

**Расширение health checks** (обновление `app/api/endpoints/health.py`):

```python
"""
Enhanced health check endpoints с детальной диагностикой.
"""
from typing import Dict, Any
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import redis.asyncio as redis
import structlog

from app.api import deps
from app.core.config import settings


router = APIRouter()
logger = structlog.get_logger()


@router.get("/live")
async def liveness_check() -> Dict[str, str]:
    """
    Liveness probe для Kubernetes.

    Проверяет, что приложение запущено и отвечает.
    """
    return {"status": "ok"}


@router.get("/ready")
async def readiness_check(
    db: AsyncSession = Depends(deps.get_db)
) -> Dict[str, Any]:
    """
    Readiness probe для Kubernetes.

    Проверяет все зависимости приложения.
    """
    checks = {}
    all_healthy = True

    # 1. Проверка PostgreSQL
    try:
        await db.execute(text("SELECT 1"))
        checks["postgresql"] = {
            "status": "healthy",
            "message": "Database connection is active"
        }
    except Exception as e:
        all_healthy = False
        checks["postgresql"] = {
            "status": "unhealthy",
            "message": f"Database error: {str(e)}"
        }
        logger.error("health_check_failed", component="postgresql", error=str(e))

    # 2. Проверка Redis (если используется)
    if settings.redis_url:
        try:
            redis_client = redis.from_url(settings.redis_url)
            await redis_client.ping()
            await redis_client.close()
            checks["redis"] = {
                "status": "healthy",
                "message": "Redis connection is active"
            }
        except Exception as e:
            all_healthy = False
            checks["redis"] = {
                "status": "unhealthy",
                "message": f"Redis error: {str(e)}"
            }
            logger.error("health_check_failed", component="redis", error=str(e))

    # 3. Проверка LDAP (если включен)
    if settings.auth.ldap and settings.auth.ldap.enabled:
        try:
            # Простая проверка подключения к LDAP
            from app.services.ldap import ldap_service
            connection_ok = ldap_service.test_connection()
            if connection_ok:
                checks["ldap"] = {
                    "status": "healthy",
                    "message": "LDAP server is reachable"
                }
            else:
                all_healthy = False
                checks["ldap"] = {
                    "status": "unhealthy",
                    "message": "LDAP server is not reachable"
                }
        except Exception as e:
            all_healthy = False
            checks["ldap"] = {
                "status": "unhealthy",
                "message": f"LDAP error: {str(e)}"
            }
            logger.error("health_check_failed", component="ldap", error=str(e))

    # Итоговый статус
    if all_healthy:
        return {
            "status": "healthy",
            "checks": checks
        }
    else:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "checks": checks
            }
        )


@router.get("/health")
async def detailed_health_check(
    db: AsyncSession = Depends(deps.get_db)
) -> Dict[str, Any]:
    """
    Детальный health check со статистикой.

    Включает информацию о версии, uptime, и статистику.
    """
    import time
    import psutil

    # Базовые health checks
    ready_result = await readiness_check(db)

    # Дополнительная информация
    health_info = {
        "application": {
            "name": "ArtStore Admin Module",
            "version": "1.0.0",
            "environment": settings.environment
        },
        "system": {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage('/').percent
        },
        "dependencies": ready_result.get("checks", {})
    }

    # Статистика из БД
    try:
        result = await db.execute(text("""
            SELECT
                (SELECT COUNT(*) FROM users WHERE is_active = true) as active_users,
                (SELECT COUNT(*) FROM users) as total_users
        """))
        row = result.fetchone()
        health_info["statistics"] = {
            "active_users": row[0],
            "total_users": row[1]
        }
    except Exception as e:
        logger.error("health_check_statistics_failed", error=str(e))

    return health_info
```

### 9.6 Пример docker-compose для мониторинга стека

**Файл**: `monitoring/docker-compose.yml`

```yaml
version: '3.8'

services:
  # Prometheus для метрик
  prometheus:
    image: prom/prometheus:latest
    container_name: artstore_prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
    networks:
      - monitoring

  # Grafana для визуализации
  grafana:
    image: grafana/grafana:latest
    container_name: artstore_grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_USERS_ALLOW_SIGN_UP=false
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/dashboards:/etc/grafana/provisioning/dashboards
      - ./grafana/datasources:/etc/grafana/provisioning/datasources
    networks:
      - monitoring

  # Jaeger для distributed tracing
  jaeger:
    image: jaegertracing/all-in-one:latest
    container_name: artstore_jaeger
    ports:
      - "16686:16686"  # UI
      - "4317:4317"    # OTLP gRPC
      - "4318:4318"    # OTLP HTTP
    environment:
      - COLLECTOR_OTLP_ENABLED=true
    networks:
      - monitoring

  # Loki для логов
  loki:
    image: grafana/loki:latest
    container_name: artstore_loki
    ports:
      - "3100:3100"
    command: -config.file=/etc/loki/local-config.yaml
    volumes:
      - loki_data:/loki
    networks:
      - monitoring

  # Promtail для отправки логов в Loki
  promtail:
    image: grafana/promtail:latest
    container_name: artstore_promtail
    volumes:
      - /var/log:/var/log
      - ./promtail-config.yml:/etc/promtail/config.yml
    command: -config.file=/etc/promtail/config.yml
    networks:
      - monitoring

volumes:
  prometheus_data:
  grafana_data:
  loki_data:

networks:
  monitoring:
    driver: bridge
```

**Файл**: `monitoring/prometheus.yml`

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  # Admin Module
  - job_name: 'admin-module'
    static_configs:
      - targets: ['host.docker.internal:8000']
    metrics_path: '/metrics'
```

### 9.7 Grafana Dashboard пример

**Файл**: `monitoring/grafana/dashboards/admin-module.json` (упрощенная версия)

```json
{
  "dashboard": {
    "title": "ArtStore Admin Module",
    "panels": [
      {
        "title": "Request Rate",
        "targets": [
          {
            "expr": "rate(http_requests_total[5m])",
            "legendFormat": "{{method}} {{endpoint}}"
          }
        ]
      },
      {
        "title": "Request Latency (p95)",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, http_request_duration_seconds_bucket)",
            "legendFormat": "{{endpoint}}"
          }
        ]
      },
      {
        "title": "Error Rate",
        "targets": [
          {
            "expr": "rate(http_errors_total[5m])",
            "legendFormat": "{{status_code}}"
          }
        ]
      },
      {
        "title": "Active Users",
        "targets": [
          {
            "expr": "users_active_total"
          }
        ]
      },
      {
        "title": "Login Success Rate",
        "targets": [
          {
            "expr": "rate(auth_login_attempts_total{status=\"success\"}[5m]) / rate(auth_login_attempts_total[5m])"
          }
        ]
      }
    ]
  }
}
```

### 9.8 Alerting с Prometheus

**Файл**: `monitoring/alerts.yml`

```yaml
groups:
  - name: admin_module_alerts
    interval: 30s
    rules:
      # High error rate
      - alert: HighErrorRate
        expr: rate(http_errors_total[5m]) > 10
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High error rate detected"
          description: "Error rate is {{ $value }} errors/sec"

      # High latency
      - alert: HighLatency
        expr: histogram_quantile(0.95, http_request_duration_seconds_bucket) > 1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High request latency"
          description: "P95 latency is {{ $value }} seconds"

      # Database connection issues
      - alert: DatabaseDown
        expr: up{job="admin-module"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Database is down"
          description: "Cannot connect to database"

      # High failed login rate
      - alert: HighFailedLoginRate
        expr: rate(auth_login_attempts_total{status="failed"}[5m]) > 5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High failed login rate"
          description: "Possible brute force attack: {{ $value }} failed logins/sec"

      # Rate limit hits
      - alert: HighRateLimitHits
        expr: rate(rate_limit_hits_total[5m]) > 50
        for: 5m
        labels:
          severity: info
        annotations:
          summary: "High rate limit hits"
          description: "{{ $value }} rate limit hits/sec"
```

### 9.9 Корреляция логов, метрик и трейсов

**Как связывать все вместе через Request ID**:

```python
import structlog
from app.core.metrics import http_requests_total
from app.core.tracing import get_tracer

tracer = get_tracer(__name__)
logger = structlog.get_logger()

async def process_request(request: Request):
    request_id = request.state.request_id

    # 1. Логирование с request_id
    logger = logger.bind(request_id=request_id)
    logger.info("request_started", path=request.url.path)

    # 2. Tracing с request_id как атрибут
    with tracer.start_as_current_span("process_request") as span:
        span.set_attribute("request.id", request_id)
        span.set_attribute("http.method", request.method)
        span.set_attribute("http.path", request.url.path)

        try:
            result = await handle_request(request)

            # 3. Метрики
            http_requests_total.labels(
                method=request.method,
                endpoint=request.url.path,
                status_code=200
            ).inc()

            logger.info("request_completed", status_code=200)
            return result

        except Exception as e:
            # Логируем ошибку
            logger.error("request_failed", error=str(e), exc_info=True)

            # Добавляем к span
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR))

            # Метрики ошибок
            http_errors_total.labels(
                method=request.method,
                endpoint=request.url.path,
                status_code=500
            ).inc()

            raise
```

**Теперь можно**:
1. **В Grafana Loki** найти логи по `request_id`
2. **В Jaeger** найти trace по тому же `request_id`
3. **В Prometheus/Grafana** посмотреть метрики за то же время

---

**Итого этап 9**: Создана полная система observability:
- Structured logging с structlog и JSON форматом
- Prometheus метрики для HTTP, authentication, database, external services
- OpenTelemetry для distributed tracing
- Расширенные health checks с диагностикой
- Docker compose для мониторинга стека (Prometheus, Grafana, Jaeger, Loki)
- Alerting rules для критических ситуаций
- Корреляция логов, метрик и трейсов через Request ID
- Grafana dashboards для визуализации

**Следующие этапы**:
- Этап 10: Тестирование
- Этап 11: Docker и развертывание

---

## Этап 10: Тестирование

### 10.1 Понимание тестирования в Python

**Типы тестов**:
1. **Unit Tests** - тестируют отдельные функции/методы в изоляции
2. **Integration Tests** - тестируют взаимодействие между компонентами
3. **End-to-End Tests** - тестируют полный user flow через API
4. **Performance Tests** - тестируют производительность под нагрузкой

**Test Pyramid**:
```
       /\
      /E2E\      <- Мало, медленные, дорогие
     /------\
    /Integration\ <- Среднее количество
   /------------\
  /  Unit Tests  \ <- Много, быстрые, дешевые
 /----------------\
```

**Инструменты**:
- **pytest** - основной framework для тестирования
- **pytest-asyncio** - поддержка async тестов
- **pytest-cov** - coverage reports
- **httpx** - HTTP client для тестирования API
- **faker** - генерация fake данных
- **factory-boy** - создание test fixtures

**Установка зависимостей**:
```bash
pip install pytest pytest-asyncio pytest-cov httpx faker factory-boy
```

### 10.2 Настройка pytest

**Файл**: `pytest.ini`

```ini
[pytest]
# Минимальная версия pytest
minversion = 7.0

# Директории для поиска тестов
testpaths = tests

# Паттерны для поиска тестовых файлов
python_files = test_*.py *_test.py

# Паттерны для поиска тестовых классов
python_classes = Test*

# Паттерны для поиска тестовых функций
python_functions = test_*

# Async режим
asyncio_mode = auto

# Опции по умолчанию
addopts =
    # Verbose output
    -v
    # Show summary of all test outcomes
    --tb=short
    # Show local variables in tracebacks
    -l
    # Coverage
    --cov=app
    --cov-report=html
    --cov-report=term-missing
    # Warnings
    -W ignore::DeprecationWarning
    # Parallel execution (опционально)
    # -n auto

# Маркеры для категоризации тестов
markers =
    unit: Unit tests
    integration: Integration tests
    e2e: End-to-end tests
    slow: Slow tests
    auth: Authentication tests
    database: Database tests
```

**Файл**: `tests/conftest.py` (главный файл с fixtures)

```python
"""
Pytest configuration и общие fixtures.
"""
import asyncio
from typing import AsyncGenerator, Generator
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.main import app
from app.db.base import Base
from app.core.config import settings
from app.api import deps


# ============================================================================
# DATABASE FIXTURES
# ============================================================================

@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """
    Create event loop для async тестов.
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_engine():
    """
    Создает test database engine.

    Использует отдельную test database.
    """
    # Создаем test database URL
    test_db_url = settings.database_url.replace("/artstore", "/artstore_test")

    # Создаем async engine с NullPool для тестов
    engine = create_async_engine(
        test_db_url,
        poolclass=NullPool,
        echo=False
    )

    # Создаем все таблицы
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Удаляем все таблицы после тестов
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Создает database session для каждого теста.

    После каждого теста делает rollback.
    """
    # Создаем session factory
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    async with async_session() as session:
        # Начинаем транзакцию
        await session.begin()

        yield session

        # Rollback после теста
        await session.rollback()


# ============================================================================
# API CLIENT FIXTURES
# ============================================================================

@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Создает HTTP client для тестирования API.

    Переопределяет database dependency для использования test DB.
    """
    async def override_get_db():
        yield db_session

    app.dependency_overrides[deps.get_db] = override_get_db

    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ============================================================================
# USER FIXTURES
# ============================================================================

@pytest.fixture
async def test_user(db_session: AsyncSession):
    """
    Создает test пользователя.
    """
    from app.db.models.user import User
    from app.core.security import hash_password

    user = User(
        username="testuser",
        email="test@example.com",
        full_name="Test User",
        hashed_password=hash_password("testpass123"),
        role="user",
        is_active=True,
        auth_provider="local"
    )

    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    return user


@pytest.fixture
async def test_admin(db_session: AsyncSession):
    """
    Создает test администратора.
    """
    from app.db.models.user import User
    from app.core.security import hash_password

    admin = User(
        username="testadmin",
        email="admin@example.com",
        full_name="Test Admin",
        hashed_password=hash_password("adminpass123"),
        role="admin",
        is_active=True,
        auth_provider="local"
    )

    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)

    return admin


@pytest.fixture
async def test_superadmin(db_session: AsyncSession):
    """
    Создает test суперадминистратора.
    """
    from app.db.models.user import User
    from app.core.security import hash_password

    superadmin = User(
        username="testsuperadmin",
        email="superadmin@example.com",
        full_name="Test Superadmin",
        hashed_password=hash_password("superpass123"),
        role="superadmin",
        is_active=True,
        auth_provider="local"
    )

    db_session.add(superadmin)
    await db_session.commit()
    await db_session.refresh(superadmin)

    return superadmin


# ============================================================================
# AUTHENTICATION FIXTURES
# ============================================================================

@pytest.fixture
def user_token(test_user) -> str:
    """
    Создает JWT token для обычного пользователя.
    """
    from app.core.security import create_access_token

    return create_access_token(
        data={"sub": str(test_user.id), "role": test_user.role}
    )


@pytest.fixture
def admin_token(test_admin) -> str:
    """
    Создает JWT token для администратора.
    """
    from app.core.security import create_access_token

    return create_access_token(
        data={"sub": str(test_admin.id), "role": test_admin.role}
    )


@pytest.fixture
def superadmin_token(test_superadmin) -> str:
    """
    Создает JWT token для суперадминистратора.
    """
    from app.core.security import create_access_token

    return create_access_token(
        data={"sub": str(test_superadmin.id), "role": test_superadmin.role}
    )


@pytest.fixture
def auth_headers(user_token: str) -> dict:
    """
    Создает authentication headers для запросов.
    """
    return {"Authorization": f"Bearer {user_token}"}


@pytest.fixture
def admin_headers(admin_token: str) -> dict:
    """
    Создает authentication headers для админа.
    """
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def superadmin_headers(superadmin_token: str) -> dict:
    """
    Создает authentication headers для суперадмина.
    """
    return {"Authorization": f"Bearer {superadmin_token}"}
```

### 10.3 Unit Tests - Core Security

**Файл**: `tests/unit/core/test_security.py`

```python
"""
Unit tests для core security функций.
"""
import pytest
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_jwt_token
)


class TestPasswordHashing:
    """Тесты для хеширования паролей."""

    def test_hash_password(self):
        """Тест создания hash пароля."""
        password = "mySecurePassword123"
        hashed = hash_password(password)

        assert hashed != password
        assert hashed.startswith("$2b$")
        assert len(hashed) == 60

    def test_verify_password_correct(self):
        """Тест проверки правильного пароля."""
        password = "mySecurePassword123"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """Тест проверки неправильного пароля."""
        password = "mySecurePassword123"
        wrong_password = "wrongPassword"
        hashed = hash_password(password)

        assert verify_password(wrong_password, hashed) is False

    def test_different_hashes_for_same_password(self):
        """Тест что один пароль дает разные hashes (salt)."""
        password = "mySecurePassword123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        assert hash1 != hash2
        assert verify_password(password, hash1)
        assert verify_password(password, hash2)


class TestJWTTokens:
    """Тесты для JWT токенов."""

    def test_create_access_token(self):
        """Тест создания access token."""
        data = {"sub": "123", "role": "user"}
        token = create_access_token(data)

        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_refresh_token(self):
        """Тест создания refresh token."""
        data = {"sub": "123"}
        token = create_refresh_token(data)

        assert isinstance(token, str)
        assert len(token) > 0

    def test_decode_jwt_token_valid(self):
        """Тест декодирования валидного токена."""
        data = {"sub": "123", "role": "admin"}
        token = create_access_token(data)

        decoded = decode_jwt_token(token)

        assert decoded["sub"] == "123"
        assert decoded["role"] == "admin"
        assert "exp" in decoded
        assert "iat" in decoded

    def test_decode_jwt_token_invalid(self):
        """Тест декодирования невалидного токена."""
        from jose import JWTError

        invalid_token = "invalid.token.here"

        with pytest.raises(JWTError):
            decode_jwt_token(invalid_token)

    def test_token_expiration(self):
        """Тест что токен содержит expiration."""
        from datetime import datetime, timezone

        data = {"sub": "123"}
        token = create_access_token(data)
        decoded = decode_jwt_token(token)

        exp = datetime.fromtimestamp(decoded["exp"], tz=timezone.utc)
        now = datetime.now(timezone.utc)

        # Токен должен истечь в будущем
        assert exp > now
```

### 10.4 Unit Tests - Services

**Файл**: `tests/unit/services/test_user_service.py`

```python
"""
Unit tests для UserService.
"""
import pytest
from unittest.mock import AsyncMock, patch
from app.services.user import user_service
from app.schemas.user import UserCreate, UserUpdate


@pytest.mark.unit
class TestUserService:
    """Тесты для UserService."""

    @pytest.mark.asyncio
    async def test_create_user_success(self, db_session):
        """Тест успешного создания пользователя."""
        user_data = UserCreate(
            username="newuser",
            email="newuser@example.com",
            password="securepass123",
            full_name="New User",
            role="user"
        )

        user = await user_service.create_user(db_session, user_data)

        assert user.id is not None
        assert user.username == "newuser"
        assert user.email == "newuser@example.com"
        assert user.full_name == "New User"
        assert user.role == "user"
        assert user.is_active is True
        assert user.auth_provider == "local"
        # Пароль должен быть захеширован
        assert user.hashed_password != "securepass123"

    @pytest.mark.asyncio
    async def test_create_user_duplicate_username(self, db_session, test_user):
        """Тест создания пользователя с существующим username."""
        user_data = UserCreate(
            username=test_user.username,  # Дубликат
            email="different@example.com",
            password="securepass123",
            full_name="Another User",
            role="user"
        )

        with pytest.raises(ValueError, match="already exists"):
            await user_service.create_user(db_session, user_data)

    @pytest.mark.asyncio
    async def test_create_user_weak_password(self, db_session):
        """Тест создания пользователя со слабым паролем."""
        user_data = UserCreate(
            username="newuser",
            email="newuser@example.com",
            password="123",  # Слишком короткий
            full_name="New User",
            role="user"
        )

        with pytest.raises(ValueError, match="at least 8 characters"):
            await user_service.create_user(db_session, user_data)

    @pytest.mark.asyncio
    async def test_get_user_by_id(self, db_session, test_user):
        """Тест получения пользователя по ID."""
        user = await user_service.get_user(db_session, test_user.id)

        assert user is not None
        assert user.id == test_user.id
        assert user.username == test_user.username

    @pytest.mark.asyncio
    async def test_get_user_not_found(self, db_session):
        """Тест получения несуществующего пользователя."""
        user = await user_service.get_user(db_session, 99999)

        assert user is None

    @pytest.mark.asyncio
    async def test_update_user(self, db_session, test_user):
        """Тест обновления пользователя."""
        update_data = UserUpdate(
            email="updated@example.com",
            full_name="Updated Name"
        )

        updated_user = await user_service.update_user(
            db_session, test_user.id, update_data
        )

        assert updated_user.email == "updated@example.com"
        assert updated_user.full_name == "Updated Name"
        # Username не должен измениться
        assert updated_user.username == test_user.username

    @pytest.mark.asyncio
    async def test_delete_user(self, db_session, test_user):
        """Тест удаления пользователя."""
        success = await user_service.delete_user(db_session, test_user.id)

        assert success is True

        # Проверяем что пользователь удален
        deleted_user = await user_service.get_user(db_session, test_user.id)
        assert deleted_user is None

    @pytest.mark.asyncio
    async def test_activate_user(self, db_session, test_user):
        """Тест активации пользователя."""
        # Сначала деактивируем
        test_user.is_active = False
        await db_session.commit()

        # Активируем
        success = await user_service.activate_user(db_session, test_user.id)

        assert success is True

        await db_session.refresh(test_user)
        assert test_user.is_active is True

    @pytest.mark.asyncio
    async def test_deactivate_user(self, db_session, test_user):
        """Тест деактивации пользователя."""
        success = await user_service.deactivate_user(db_session, test_user.id)

        assert success is True

        await db_session.refresh(test_user)
        assert test_user.is_active is False

    @pytest.mark.asyncio
    async def test_change_password_success(self, db_session, test_user):
        """Тест успешной смены пароля."""
        old_password = "testpass123"
        new_password = "newSecurePass456"

        success = await user_service.change_password(
            db_session, test_user.id, old_password, new_password
        )

        assert success is True

        # Проверяем что новый пароль работает
        from app.core.security import verify_password
        await db_session.refresh(test_user)
        assert verify_password(new_password, test_user.hashed_password)

    @pytest.mark.asyncio
    async def test_change_password_wrong_old_password(self, db_session, test_user):
        """Тест смены пароля с неправильным старым паролем."""
        wrong_old_password = "wrongpass"
        new_password = "newSecurePass456"

        success = await user_service.change_password(
            db_session, test_user.id, wrong_old_password, new_password
        )

        assert success is False
```

### 10.5 Integration Tests - API Auth

**Файл**: `tests/integration/api/test_auth.py`

```python
"""
Integration tests для authentication API.
"""
import pytest
from httpx import AsyncClient


@pytest.mark.integration
@pytest.mark.auth
class TestAuthAPI:
    """Integration тесты для auth endpoints."""

    @pytest.mark.asyncio
    async def test_login_success(self, client: AsyncClient, test_user):
        """Тест успешного логина."""
        response = await client.post(
            "/api/auth/login",
            json={
                "username": "testuser",
                "password": "testpass123"
            }
        )

        assert response.status_code == 200
        data = response.json()

        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert "user" in data
        assert data["user"]["username"] == "testuser"

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client: AsyncClient, test_user):
        """Тест логина с неправильным паролем."""
        response = await client.post(
            "/api/auth/login",
            json={
                "username": "testuser",
                "password": "wrongpassword"
            }
        )

        assert response.status_code == 401
        data = response.json()
        assert "error" in data

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, client: AsyncClient):
        """Тест логина несуществующего пользователя."""
        response = await client.post(
            "/api/auth/login",
            json={
                "username": "nonexistent",
                "password": "somepassword"
            }
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user(
        self, client: AsyncClient, test_user, auth_headers
    ):
        """Тест получения текущего пользователя."""
        response = await client.get(
            "/api/auth/me",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert data["id"] == test_user.id
        assert data["username"] == test_user.username
        assert data["email"] == test_user.email

    @pytest.mark.asyncio
    async def test_get_current_user_no_token(self, client: AsyncClient):
        """Тест получения пользователя без токена."""
        response = await client.get("/api/auth/me")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self, client: AsyncClient):
        """Тест получения пользователя с невалидным токеном."""
        response = await client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer invalid_token"}
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_token(self, client: AsyncClient, test_user):
        """Тест обновления access token через refresh token."""
        # Сначала получаем токены через логин
        login_response = await client.post(
            "/api/auth/login",
            json={
                "username": "testuser",
                "password": "testpass123"
            }
        )
        refresh_token = login_response.json()["refresh_token"]

        # Используем refresh token для получения нового access token
        response = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": refresh_token}
        )

        assert response.status_code == 200
        data = response.json()

        assert "access_token" in data
        assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_logout(self, client: AsyncClient, auth_headers):
        """Тест logout."""
        response = await client.post(
            "/api/auth/logout",
            headers=auth_headers
        )

        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_change_password(
        self, client: AsyncClient, test_user, auth_headers
    ):
        """Тест смены пароля."""
        response = await client.post(
            "/api/auth/change-password",
            headers=auth_headers,
            json={
                "old_password": "testpass123",
                "new_password": "newSecurePass456"
            }
        )

        assert response.status_code == 204

        # Проверяем что можем залогиниться с новым паролем
        login_response = await client.post(
            "/api/auth/login",
            json={
                "username": "testuser",
                "password": "newSecurePass456"
            }
        )

        assert login_response.status_code == 200
```

### 10.6 Integration Tests - API Users

**Файл**: `tests/integration/api/test_users.py`

```python
"""
Integration tests для users API.
"""
import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestUsersAPI:
    """Integration тесты для users endpoints."""

    @pytest.mark.asyncio
    async def test_list_users_as_admin(
        self, client: AsyncClient, test_user, admin_headers
    ):
        """Тест получения списка пользователей администратором."""
        response = await client.get(
            "/api/users",
            headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "size" in data
        assert len(data["items"]) > 0

    @pytest.mark.asyncio
    async def test_list_users_as_regular_user(
        self, client: AsyncClient, auth_headers
    ):
        """Тест получения списка пользователей обычным пользователем."""
        response = await client.get(
            "/api/users",
            headers=auth_headers
        )

        # Обычный пользователь не может получить список
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_create_user_as_admin(
        self, client: AsyncClient, admin_headers
    ):
        """Тест создания пользователя администратором."""
        response = await client.post(
            "/api/users",
            headers=admin_headers,
            json={
                "username": "newuser",
                "email": "newuser@example.com",
                "password": "securepass123",
                "full_name": "New User",
                "role": "user"
            }
        )

        assert response.status_code == 201
        data = response.json()

        assert data["username"] == "newuser"
        assert data["email"] == "newuser@example.com"
        assert data["role"] == "user"
        assert data["is_active"] is True

    @pytest.mark.asyncio
    async def test_create_user_duplicate_username(
        self, client: AsyncClient, test_user, admin_headers
    ):
        """Тест создания пользователя с дублирующимся username."""
        response = await client.post(
            "/api/users",
            headers=admin_headers,
            json={
                "username": test_user.username,  # Дубликат
                "email": "different@example.com",
                "password": "securepass123",
                "full_name": "Another User",
                "role": "user"
            }
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_get_user_by_id(
        self, client: AsyncClient, test_user, admin_headers
    ):
        """Тест получения пользователя по ID."""
        response = await client.get(
            f"/api/users/{test_user.id}",
            headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert data["id"] == test_user.id
        assert data["username"] == test_user.username

    @pytest.mark.asyncio
    async def test_get_nonexistent_user(
        self, client: AsyncClient, admin_headers
    ):
        """Тест получения несуществующего пользователя."""
        response = await client.get(
            "/api/users/99999",
            headers=admin_headers
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_user(
        self, client: AsyncClient, test_user, admin_headers
    ):
        """Тест обновления пользователя."""
        response = await client.patch(
            f"/api/users/{test_user.id}",
            headers=admin_headers,
            json={
                "email": "updated@example.com",
                "full_name": "Updated Name"
            }
        )

        assert response.status_code == 200
        data = response.json()

        assert data["email"] == "updated@example.com"
        assert data["full_name"] == "Updated Name"

    @pytest.mark.asyncio
    async def test_delete_user_as_superadmin(
        self, client: AsyncClient, test_user, superadmin_headers
    ):
        """Тест удаления пользователя суперадминистратором."""
        response = await client.delete(
            f"/api/users/{test_user.id}",
            headers=superadmin_headers
        )

        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_user_as_admin(
        self, client: AsyncClient, test_user, admin_headers
    ):
        """Тест удаления пользователя обычным админом."""
        response = await client.delete(
            f"/api/users/{test_user.id}",
            headers=admin_headers
        )

        # Обычный админ не может удалять
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_activate_user(
        self, client: AsyncClient, test_user, admin_headers, db_session
    ):
        """Тест активации пользователя."""
        # Сначала деактивируем
        test_user.is_active = False
        await db_session.commit()

        response = await client.post(
            f"/api/users/{test_user.id}/activate",
            headers=admin_headers
        )

        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_deactivate_user(
        self, client: AsyncClient, test_user, admin_headers
    ):
        """Тест деактивации пользователя."""
        response = await client.post(
            f"/api/users/{test_user.id}/deactivate",
            headers=admin_headers
        )

        assert response.status_code == 204
```

### 10.7 End-to-End Tests

**Файл**: `tests/e2e/test_user_workflow.py`

```python
"""
End-to-end тесты для полного user workflow.
"""
import pytest
from httpx import AsyncClient


@pytest.mark.e2e
@pytest.mark.slow
class TestUserWorkflow:
    """E2E тесты для полного user workflow."""

    @pytest.mark.asyncio
    async def test_complete_user_lifecycle(
        self, client: AsyncClient, superadmin_headers
    ):
        """
        Тест полного жизненного цикла пользователя:
        1. Создание
        2. Логин
        3. Получение своей информации
        4. Смена пароля
        5. Логин с новым паролем
        6. Деактивация
        7. Попытка логина (неудачная)
        8. Активация
        9. Логин (успешный)
        10. Удаление
        """
        # 1. Создание пользователя
        create_response = await client.post(
            "/api/users",
            headers=superadmin_headers,
            json={
                "username": "lifecycleuser",
                "email": "lifecycle@example.com",
                "password": "initialpass123",
                "full_name": "Lifecycle User",
                "role": "user"
            }
        )
        assert create_response.status_code == 201
        user_id = create_response.json()["id"]

        # 2. Логин
        login_response = await client.post(
            "/api/auth/login",
            json={
                "username": "lifecycleuser",
                "password": "initialpass123"
            }
        )
        assert login_response.status_code == 200
        access_token = login_response.json()["access_token"]
        user_headers = {"Authorization": f"Bearer {access_token}"}

        # 3. Получение своей информации
        me_response = await client.get(
            "/api/auth/me",
            headers=user_headers
        )
        assert me_response.status_code == 200
        assert me_response.json()["username"] == "lifecycleuser"

        # 4. Смена пароля
        change_pass_response = await client.post(
            "/api/auth/change-password",
            headers=user_headers,
            json={
                "old_password": "initialpass123",
                "new_password": "newpass456"
            }
        )
        assert change_pass_response.status_code == 204

        # 5. Логин с новым паролем
        new_login_response = await client.post(
            "/api/auth/login",
            json={
                "username": "lifecycleuser",
                "password": "newpass456"
            }
        )
        assert new_login_response.status_code == 200

        # 6. Деактивация
        deactivate_response = await client.post(
            f"/api/users/{user_id}/deactivate",
            headers=superadmin_headers
        )
        assert deactivate_response.status_code == 204

        # 7. Попытка логина деактивированным пользователем
        deactivated_login = await client.post(
            "/api/auth/login",
            json={
                "username": "lifecycleuser",
                "password": "newpass456"
            }
        )
        assert deactivated_login.status_code == 401

        # 8. Активация
        activate_response = await client.post(
            f"/api/users/{user_id}/activate",
            headers=superadmin_headers
        )
        assert activate_response.status_code == 204

        # 9. Логин после активации
        reactivated_login = await client.post(
            "/api/auth/login",
            json={
                "username": "lifecycleuser",
                "password": "newpass456"
            }
        )
        assert reactivated_login.status_code == 200

        # 10. Удаление
        delete_response = await client.delete(
            f"/api/users/{user_id}",
            headers=superadmin_headers
        )
        assert delete_response.status_code == 204
```

### 10.8 Запуск тестов

**Основные команды**:

```bash
# Запустить все тесты
pytest

# Запустить с coverage
pytest --cov=app --cov-report=html

# Запустить только unit tests
pytest -m unit

# Запустить только integration tests
pytest -m integration

# Запустить только e2e tests
pytest -m e2e

# Запустить конкретный файл
pytest tests/unit/core/test_security.py

# Запустить конкретный тест
pytest tests/unit/core/test_security.py::TestPasswordHashing::test_hash_password

# Запустить с verbose output
pytest -v

# Запустить с выводом print statements
pytest -s

# Запустить и остановиться на первой ошибке
pytest -x

# Запустить failed тесты из прошлого запуска
pytest --lf

# Запустить в параллель (требует pytest-xdist)
pytest -n auto
```

### 10.9 Coverage Reports

После запуска тестов с `--cov-report=html`:

```bash
# Открыть coverage report в браузере
start htmlcov/index.html  # Windows
open htmlcov/index.html   # macOS
xdg-open htmlcov/index.html  # Linux
```

**Целевые показатели coverage**:
- **Overall**: >80%
- **Core logic** (services): >90%
- **API endpoints**: >85%
- **Models**: >70%

### 10.10 CI/CD Integration

**Файл**: `.github/workflows/tests.yml`

```yaml
name: Tests

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main, develop ]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_USER: artstore
          POSTGRES_PASSWORD: password
          POSTGRES_DB: artstore_test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432

      redis:
        image: redis:7
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 6379:6379

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.12'

    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        pip install pytest pytest-asyncio pytest-cov httpx

    - name: Run tests
      env:
        DATABASE_URL: postgresql+asyncpg://artstore:password@localhost:5432/artstore_test
        REDIS_URL: redis://localhost:6379/0
      run: |
        pytest --cov=app --cov-report=xml --cov-report=term

    - name: Upload coverage to Codecov
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
        fail_ci_if_error: true
```

---

**Итого этап 10**: Создана полная система тестирования:
- Настройка pytest с async support и coverage
- Fixtures для database, API client, users, authentication
- Unit tests для core security и services
- Integration tests для API endpoints
- End-to-end tests для полных user workflows
- CI/CD integration с GitHub Actions
- Coverage reports (цель >80%)
- Команды для запуска разных типов тестов

**Следующий этап**:
- Этап 11: Docker и развертывание