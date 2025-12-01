# Admin Module - Центр управления и аутентификации ArtStore

## Назначение модуля

**Admin Module Cluster** — это отказоустойчивый центр управления всей системой ArtStore, обеспечивающий:
- **OAuth 2.0 аутентификацию** через Client Credentials flow
- **Управление Service Accounts** и их правами доступа
- **Координацию распределенных транзакций** (Saga Pattern)
- **Service Discovery** через публикацию конфигурации в Redis
- **Высокую доступность** через Raft consensus протокол (3+ узла)

## Ключевые возможности

### 1. Аутентификация и авторизация

#### OAuth 2.0 Client Credentials Flow
- **Client ID / Client Secret**: Аутентификация machine-to-machine
- **JWT RS256 tokens**: Подписанные приватным ключом Admin Module
- **Распределенная валидация**: Другие модули проверяют токены через публичный ключ
- **Automatic token expiration**: 30 минут для access tokens

#### Service Accounts Management
- **CRUD операции** для Service Accounts
- **Роли**: ADMIN, USER, AUDITOR, READONLY
- **Fine-grained permissions**: Resource-level access control
- **Rate limiting**: Настраиваемые лимиты запросов (100 req/min по умолчанию)
- **Status management**: ACTIVE, SUSPENDED, EXPIRED

#### Automated Security Features
- **JWT Key Rotation**: Автоматическая ротация каждые 24 часа с плавным переходом
- **Client Secret Rotation**: Каждые 90 дней с уведомлениями за 7 дней
- **Webhook Support**: Уведомления о критических событиях безопасности

### 1.5 Типы учетных записей

Admin Module поддерживает **два типа** учетных записей:

#### 1. System Administrators (AdminUser)

**Назначение**: Администраторы системы с доступом к Admin UI

**Атрибуты**:
- Username (уникальный)
- Email (уникальный)
- ФИО (first_name, last_name)
- Организация (organization)
- Password (bcrypt hash, work factor 12)
- Role: SUPER_ADMIN, ADMIN, READONLY
- Status: enabled/disabled

**Аутентификация**: Login/Password через `/api/admin-auth/login`

**Use Cases**:
- Управление системой через Admin UI
- Создание и управление Service Accounts
- Мониторинг и администрирование Storage Elements

**Инициализация**: Автоматическое создание initial admin user при первом запуске через `INITIAL_ADMIN_*` переменные окружения.

#### 2. Service Accounts (Клиентские учетные записи)

**Назначение**: Machine-to-machine API доступ для внешних систем/приложений

**Атрибуты**:
- Client ID (автогенерация, формат: `sa_<env>_<name>_<random>`)
- Client Secret (bcrypt hash, work factor 12)
- Name (человекочитаемое название)
- Description (опционально)
- Role: ADMIN, USER, AUDITOR, READONLY
- Status: ACTIVE, SUSPENDED, EXPIRED, DELETED
- Rate Limit (default: 100 req/min)

**Аутентификация**: OAuth 2.0 Client Credentials через `/api/auth/token`

**Use Cases**:
- API интеграции с внешними системами
- Автоматизированные процессы и скрипты
- Межсервисное взаимодействие

**Инициализация**: Автоматическое создание initial service account при первом запуске через `INITIAL_ACCOUNT_*` переменные окружения.

### 2. Управление Storage Elements

- **Auto-discovery**: Автоматическое получение информации от storage element по URL
- **Синхронизация**: Периодическая и ручная синхронизация данных (mode, capacity, used, files)
- **Monitoring статусов**: edit, rw, ro, ar режимы (только чтение, изменение через config storage element)
- **Публикация в Service Discovery**: Redis pub/sub для обновлений
- **Health checking**: Периодическая проверка доступности

**ВАЖНО**: Mode Storage Element определяется ТОЛЬКО его конфигурацией при запуске.
Для изменения mode необходимо изменить конфигурацию storage element и перезапустить его.

### 3. Координация распределенных транзакций

#### Saga Orchestrator
- **Upload Saga**: Загрузка файла → Валидация → Индексация → Service Discovery publish
- **Delete Saga**: Проверка прав → Удаление из storage → Cleanup cache → Audit log
- **Transfer Saga**: Validate → Copy to destination → Verify → Delete from source

#### Compensating Actions
- Автоматический rollback при сбоях на любом этапе
- Идемпотентные операции для retry
- Audit logging всех транзакций

### 4. High Availability (Raft Consensus)

#### Кластерная архитектура
- **3+ узла** для обеспечения кворума
- **Automatic leader election**: Переизбрание лидера за < 15 секунд
- **Multi-master active-active**: Consistent hashing для распределения нагрузки
- **Split-brain protection**: Кворумные решения предотвращают разделение

#### Graceful Failover
- **RTO < 15 секунд** при недоступности leader узла
- **Zero-downtime operations**: Rolling updates без прерывания сервиса
- **State replication**: Синхронизация состояния между узлами

## Технологический стек

### Backend Framework
- **Python 3.12+** с async/await для конкурентной обработки
- **FastAPI** для REST API с автоматической документацией (OpenAPI/Swagger)
- **Uvicorn** с uvloop для максимальной производительности
- **Pydantic** для валидации данных и настроек

### Database & Caching
- **PostgreSQL 15+** (asyncpg) для хранения:
  - Service Accounts и их метаданных
  - Storage Elements конфигурации
  - Audit logs
  - Saga transactions state
- **Alembic** для миграций схемы БД
- **Redis 7** (sync redis-py) для:
  - Service Discovery (pub/sub)
  - Distributed locking
  - Master election coordination

### Security
- **PyJWT** для генерации и валидации JWT токенов
- **Cryptography** для RS256 key pair management
- **Passlib (bcrypt)** для хеширования client secrets
- **python-jose** для дополнительных crypto операций

### Observability
- **OpenTelemetry** для distributed tracing
- **Prometheus client** для экспорта метрик
- **Structured logging** (JSON format) для интеграции с ELK/Splunk

## Архитектура модуля

### API Endpoints

#### Admin Authentication (`/api/v1/admin-auth/*`)
```
POST /api/v1/admin-auth/login
  - Admin User login через username/password
  - Input: {"username": "admin", "password": "..."}
  - Output: {"access_token": "eyJ...", "refresh_token": "...", "token_type": "Bearer", "expires_in": 1800}

POST /api/v1/admin-auth/refresh
  - Обновление access token по refresh token
  - Input: {"refresh_token": "..."}
  - Output: {"access_token": "eyJ...", "refresh_token": "...", "token_type": "Bearer", "expires_in": 1800}

POST /api/v1/admin-auth/logout
  - Logout текущего Admin User (requires JWT)
  - Output: {"success": true, "message": "Successfully logged out"}

GET /api/v1/admin-auth/me
  - Получение информации о текущем Admin User (requires JWT)
  - Output: AdminUserResponse с id, username, email, role, enabled, last_login_at, created_at

POST /api/v1/admin-auth/change-password
  - Смена пароля (requires JWT и current password)
  - Input: {"current_password": "...", "new_password": "...", "confirm_password": "..."}
  - Output: {"success": true, "message": "Password changed successfully", "password_changed_at": "..."}
```

#### Service Account Authentication (`/api/v1/auth/*`)
```
POST /api/v1/auth/token
  - OAuth 2.0 Client Credentials authentication для Service Accounts (RFC 6749 Section 4.4)
  - Input: {"client_id": "...", "client_secret": "..."}
  - Output: {"access_token": "eyJ...", "refresh_token": "...", "token_type": "Bearer", "expires_in": 1800, "issued_at": "..."}
  - Errors: invalid_client (401), access_denied (403)
```

#### Admin Users Management (`/api/v1/admin-users/*`)
```
POST /api/v1/admin-users/
  - Создание нового Admin User (SUPER_ADMIN only)
  - Input: {"username": "...", "email": "...", "password": "...", "role": "admin", "enabled": true}
  - Output: AdminUserResponse

GET /api/v1/admin-users/
  - Список Admin Users с пагинацией и фильтрацией
  - Query: page, page_size, role, enabled, search
  - Output: {"items": [...], "total": N, "page": N, "page_size": N}

GET /api/v1/admin-users/{admin_id}
  - Детали конкретного Admin User по UUID
  - Output: AdminUserResponse

PUT /api/v1/admin-users/{admin_id}
  - Обновление Admin User (SUPER_ADMIN only)
  - Input: {"email": "...", "role": "...", "enabled": true/false}
  - Ограничения: системный админ (is_system=true) не может быть изменен

DELETE /api/v1/admin-users/{admin_id}
  - Удаление Admin User (SUPER_ADMIN only)
  - Ограничения: системный админ не может быть удален, нельзя удалить себя

POST /api/v1/admin-users/{admin_id}/reset-password
  - Сброс пароля Admin User (SUPER_ADMIN only)
  - Input: {"new_password": "..."}
  - Эффекты: сбрасывает блокировку, обнуляет failed login attempts
```

#### Service Accounts (`/api/v1/service-accounts/*`)
```
POST /api/v1/service-accounts/
  - Создание нового Service Account (SUPER_ADMIN only)
  - Input: {"name": "...", "role": "USER", "description": "...", "rate_limit": 100, "environment": "prod"}
  - Output: ServiceAccountCreateResponse с client_id и client_secret (secret показывается ТОЛЬКО при создании!)

GET /api/v1/service-accounts/
  - Список Service Accounts с пагинацией и фильтрацией
  - Query: skip, limit, role, status, search
  - Output: {"items": [...], "total": N, "skip": N, "limit": N}

GET /api/v1/service-accounts/{service_account_id}
  - Детали Service Account по UUID (без client_secret)
  - Output: ServiceAccountResponse

PUT /api/v1/service-accounts/{service_account_id}
  - Обновление Service Account (SUPER_ADMIN only)
  - Input: {"name": "...", "description": "...", "role": "...", "rate_limit": N, "status": "ACTIVE/SUSPENDED"}
  - Ограничения: системные аккаунты (is_system=true) не могут быть изменены

DELETE /api/v1/service-accounts/{service_account_id}
  - Удаление Service Account (SUPER_ADMIN only, soft delete → status=DELETED)
  - Ограничения: системные аккаунты не могут быть удалены

POST /api/v1/service-accounts/{service_account_id}/rotate-secret
  - Ротация client_secret (SUPER_ADMIN only)
  - Output: {"id": "...", "name": "...", "client_id": "...", "new_client_secret": "...", "secret_expires_at": "..."}
  - ВАЖНО: new_client_secret показывается ТОЛЬКО при ротации!
```

#### Storage Elements (`/api/v1/storage-elements/*`)

**ВАЖНО**: Mode Storage Element определяется ТОЛЬКО его конфигурацией при запуске.
Изменить mode можно только через изменение конфигурации и перезапуск storage element.
Admin Module НЕ МОЖЕТ изменять mode через API.

```
POST /api/v1/storage-elements/discover
  - Auto-discovery Storage Element по URL (preview без регистрации)
  - Input: {"api_url": "http://storage:8010"}
  - Output: Информация о storage element + флаг already_registered

POST /api/v1/storage-elements/sync/{storage_element_id}
  - Синхронизация данных одного Storage Element
  - Обновляет: mode, capacity_bytes, used_bytes, file_count, status
  - Публикует изменения в Redis для Service Discovery
  - Output: {"storage_element_id": N, "name": "...", "success": true, "changes": [...], "synced_at": "..."}

POST /api/v1/storage-elements/sync-all
  - Массовая синхронизация всех Storage Elements (SUPER_ADMIN only)
  - Query: only_online=true (default)
  - Output: {"total": N, "synced": N, "failed": N, "results": [...]}

GET /api/v1/storage-elements/stats/summary
  - Сводная статистика по всем Storage Elements
  - Output: {total_count, by_status, by_mode, by_type, total_capacity_gb, total_used_gb, total_files, average_usage_percent}

POST /api/v1/storage-elements/
  - Регистрация нового Storage Element с auto-discovery (SUPER_ADMIN only)
  - Input: {"api_url": "http://storage:8010", "name": "optional", "description": "optional", "api_key": "optional"}
  - mode, storage_type, base_path, capacity_bytes получаются автоматически от storage element
  - Публикует в Redis для Service Discovery

GET /api/v1/storage-elements/
  - Список Storage Elements с пагинацией и фильтрацией
  - Query: skip, limit, mode, status, storage_type, search
  - Output: {"items": [...], "total": N, "skip": N, "limit": N}

GET /api/v1/storage-elements/{storage_element_id}
  - Детали Storage Element по ID
  - Включает computed fields: capacity_gb, used_gb, usage_percent, is_available, is_writable

PUT /api/v1/storage-elements/{storage_element_id}
  - Обновление Storage Element (SUPER_ADMIN only)
  - ВАЖНО: mode НЕ может быть изменен через API
  - Доступные поля: name, description, api_url, api_key, status, retention_days, replica_count

DELETE /api/v1/storage-elements/{storage_element_id}
  - Удаление Storage Element (SUPER_ADMIN only)
  - Ограничения: нельзя удалить storage element с файлами (file_count > 0)
```

#### JWT Keys Management (`/api/v1/jwt-keys/*`)
```
GET /api/v1/jwt-keys/status
  - Получение статуса JWT key rotation (ADMIN only)
  - Output: {rotation_enabled, rotation_interval_hours, active_keys_count, latest_key, next_rotation_at, last_rotation_at}

GET /api/v1/jwt-keys/active
  - Список активных JWT ключей (ADMIN only)
  - Output: {"total": N, "keys": [{version, algorithm, created_at, expires_at, is_active}, ...]}

POST /api/v1/jwt-keys/rotate
  - Ручная ротация JWT ключей (ADMIN only)
  - Input: {"force": false} - если true, игнорирует недавние ротации
  - Output: {"success": true, "message": "...", "new_key_version": "...", "deactivated_keys": N}

GET /api/v1/jwt-keys/history
  - История ротаций JWT ключей (ADMIN only)
  - Query: limit (default: 50, max: 100)
  - Output: {"total": N, "entries": [...], "oldest_active_key": "...", "newest_key": "..."}
```

#### Health & Monitoring
```
GET /health/live
  - Liveness probe (is service running?)
  - Output: {"status": "alive", "timestamp": "...", "service": "...", "version": "..."}

GET /health/ready
  - Readiness probe (can handle traffic?)
  - Проверяет: PostgreSQL (critical), Redis (non-critical)
  - Output: {"status": "ready/not_ready", "dependencies": {"database": {...}, "redis": {...}}}

GET /health/startup
  - Startup probe (has service started?)
  - Проверяет: PostgreSQL connection
  - Output: {"status": "started/starting", ...}

GET /health/metrics
  - Prometheus metrics endpoint
  - Requires PROMETHEUS_METRICS_ENABLED=true
```

### Внутренняя архитектура

```
admin-module/
├── app/
│   ├── __init__.py
│   ├── main.py                      # FastAPI application entry point
│   │
│   ├── core/                        # Ядро приложения
│   │   ├── __init__.py
│   │   ├── config.py                # Pydantic Settings configuration
│   │   ├── database.py              # PostgreSQL async/sync session management
│   │   ├── redis.py                 # Redis connection и health checks
│   │   ├── exceptions.py            # Custom exceptions
│   │   ├── logging_config.py        # Structured logging (JSON format)
│   │   ├── metrics.py               # Prometheus metrics helpers
│   │   ├── observability.py         # OpenTelemetry tracing
│   │   ├── password_policy.py       # Password strength validation
│   │   ├── scheduler.py             # APScheduler для JWT key rotation
│   │   └── secrets.py               # Cryptographic utilities (JWT keys, hashing)
│   │
│   ├── api/                         # REST API layer
│   │   ├── __init__.py
│   │   ├── dependencies/            # FastAPI dependencies
│   │   │   ├── __init__.py
│   │   │   ├── auth.py              # Service Account JWT validation
│   │   │   └── admin_auth.py        # Admin User JWT validation, require_role
│   │   └── v1/
│   │       ├── __init__.py
│   │       └── endpoints/
│   │           ├── __init__.py
│   │           ├── auth.py              # OAuth 2.0 token endpoint для Service Accounts
│   │           ├── admin_auth.py        # Admin User authentication (login, refresh, logout)
│   │           ├── admin_users.py       # Admin Users CRUD API
│   │           ├── service_accounts.py  # Service Accounts CRUD API
│   │           ├── storage_elements.py  # Storage Elements CRUD + discovery + sync
│   │           ├── jwt_keys.py          # JWT key rotation management
│   │           └── health.py            # Health probes (live, ready, startup, metrics)
│   │
│   ├── models/                      # SQLAlchemy ORM models
│   │   ├── __init__.py
│   │   ├── base.py                  # SQLAlchemy declarative base
│   │   ├── admin_user.py            # AdminUser model (system administrators)
│   │   ├── service_account.py       # ServiceAccount model (API clients)
│   │   ├── storage_element.py       # StorageElement model
│   │   ├── jwt_key.py               # JWTKey model (key rotation storage)
│   │   └── audit_log.py             # AuditLog model
│   │
│   ├── schemas/                     # Pydantic request/response schemas
│   │   ├── __init__.py
│   │   ├── auth.py                  # Legacy auth schemas
│   │   ├── admin_auth.py            # Admin authentication schemas
│   │   ├── admin_user.py            # Admin user CRUD schemas
│   │   ├── service_account.py       # Service account schemas (OAuth2, CRUD)
│   │   ├── storage_element.py       # Storage element schemas (discovery, sync)
│   │   └── jwt_key.py               # JWT key rotation schemas
│   │
│   ├── services/                    # Business logic layer
│   │   ├── __init__.py
│   │   ├── admin_auth_service.py        # Admin authentication business logic
│   │   ├── admin_user_service.py        # Admin user management
│   │   ├── service_account_service.py   # Service account management
│   │   ├── token_service.py             # JWT token generation (access + refresh)
│   │   ├── storage_discovery_service.py # Auto-discovery storage elements
│   │   ├── storage_sync_service.py      # Storage element synchronization
│   │   ├── storage_element_publish_service.py # Redis Service Discovery publishing
│   │   ├── jwt_key_rotation_service.py  # Automated JWT key rotation
│   │   └── audit_service.py             # Audit logging service
│   │
│   ├── middleware/                  # HTTP middleware
│   │   ├── __init__.py
│   │   ├── audit_middleware.py      # Audit logging middleware
│   │   └── rate_limit.py            # Rate limiting middleware
│   │
│   ├── db/                          # Database utilities
│   │   ├── __init__.py
│   │   └── init_db.py               # Database initialization (initial admin/SA)
│   │
│   └── utils/                       # Utility modules
│       └── __init__.py
│
├── alembic/                         # Database migrations
│   ├── env.py                       # Alembic environment configuration
│   ├── script.py.mako               # Migration script template
│   └── versions/                    # Migration files
│
├── tests/                           # Test suite
│   ├── __init__.py
│   ├── conftest.py                  # Pytest fixtures
│   ├── test_logging.py              # Logging tests
│   ├── unit/                        # Unit tests
│   │   ├── __init__.py
│   │   ├── test_health.py           # Health endpoint tests
│   │   └── test_service_account.py  # Service account logic tests
│   └── integration/                 # Integration tests
│       ├── __init__.py
│       ├── test_oauth2_flow.py      # OAuth 2.0 flow tests
│       ├── test_oauth2_simple.py    # Simple OAuth2 tests
│       └── test_service_accounts_api.py  # Service accounts API tests
│
├── Dockerfile                       # Production Docker image
├── Dockerfile.dev                   # Development Docker image
├── requirements.txt                 # Python dependencies
├── pytest.ini                       # Pytest configuration
├── alembic.ini                      # Alembic configuration
├── config.yaml                      # Application configuration
├── .env.example                     # Example environment variables
└── AUTH-MECHANICS.md                # Detailed authentication documentation
```

## Принципы разработки

### Security-First Approach
- **Principle of Least Privilege**: Service Accounts получают минимально необходимые права
- **Defense in Depth**: Многоуровневая защита (JWT validation, RBAC, rate limiting, audit logging)
- **Secure by Default**: Безопасные настройки по умолчанию, explicit opt-in для расширенных прав
- **Zero Trust**: Валидация всех запросов даже внутри доверенной сети

### High Availability Design
- **Stateless Services**: Все узлы Admin Module Cluster stateless для горизонтального масштабирования
- **Automatic Failover**: Raft consensus обеспечивает автоматическое переизбрание лидера
- **Graceful Degradation**: Работоспособность при недоступности Redis (fallback на локальную конфигурацию)
- **Health Checks**: Liveness и readiness probes для Kubernetes/Docker Swarm

### Data Consistency
- **ACID Transactions**: PostgreSQL транзакции для критических операций
- **Saga Pattern**: Координация долгосрочных распределенных операций
- **Idempotency**: Все операции идемпотентны для безопасного retry
- **Audit Trail**: Полное логирование всех изменений состояния

## Тестирование

### Unit Tests (pytest)
- **Coverage target**: минимум 80% для production кода
- **Mock external dependencies**: PostgreSQL, Redis через fixtures
- **Тестируемые компоненты**:
  - `auth_service.py`: Генерация/валидация JWT, key rotation
  - `account_service.py`: CRUD операции, secret rotation
  - `saga_orchestrator.py`: Координация транзакций, compensating actions

### Integration Tests
- **Real dependencies**: Использование test PostgreSQL и Redis containers
- **End-to-end scenarios**:
  - OAuth 2.0 authentication flow
  - Service Account lifecycle (create → use → rotate secret → suspend → delete)
  - Storage Element registration and mode transitions
  - Saga transactions with compensation

### Running Tests

```bash
# Активация виртуального окружения (из корня проекта)
source /home/artur/Projects/artStore/.venv/bin/activate

# Unit tests
pytest admin-module/tests/unit/ -v

# Integration tests
pytest admin-module/tests/integration/ -v

# Coverage report
pytest admin-module/tests/ --cov=app --cov-report=html

# Docker-based testing (рекомендуется)
docker-compose build admin-module
docker-compose run --rm admin-module pytest tests/ -v
```

## Конфигурация

### Environment Variables

**ВАЖНО**: Boolean значения используют формат `on/off` (не `true/false`).

```bash
# ═══════════════════════════════════════════════════════════════════════════
# APPLICATION SETTINGS
# ═══════════════════════════════════════════════════════════════════════════
APP_NAME=ArtStore Admin Module
APP_VERSION=0.1.0
APP_DEBUG=off                           # Режим отладки (on/off)
APP_SWAGGER_ENABLED=off                 # Swagger UI (production: off)
APP_HOST=0.0.0.0
APP_PORT=8000

# ═══════════════════════════════════════════════════════════════════════════
# DATABASE (PostgreSQL)
# ═══════════════════════════════════════════════════════════════════════════
DB_HOST=localhost
DB_PORT=5432
DB_USERNAME=artstore
DB_PASSWORD=password
DB_DATABASE=artstore_admin
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
DB_ECHO=off                             # SQL запросы в логи (development only)

# PostgreSQL SSL Configuration (опционально, для production)
DB_SSL_ENABLED=off                      # Включить SSL для PostgreSQL
DB_SSL_MODE=require                     # Режимы: disable, allow, prefer, require, verify-ca, verify-full
# DB_SSL_CA_CERT=/path/to/ca-cert.pem         # CA certificate (для verify-ca/verify-full)
# DB_SSL_CLIENT_CERT=/path/to/client-cert.pem # Client certificate (опционально)
# DB_SSL_CLIENT_KEY=/path/to/client-key.pem   # Client key (опционально)

# ═══════════════════════════════════════════════════════════════════════════
# REDIS (Service Discovery, Pub/Sub, Caching)
# ═══════════════════════════════════════════════════════════════════════════
# Вариант 1: Прямой URL (высший приоритет)
REDIS_URL=redis://localhost:6379/0

# Вариант 2: Компоненты (если REDIS_URL не задан)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=                         # Опционально
REDIS_DB=0
REDIS_POOL_SIZE=10
REDIS_SOCKET_TIMEOUT=5
REDIS_SOCKET_CONNECT_TIMEOUT=5

# ═══════════════════════════════════════════════════════════════════════════
# JWT AUTHENTICATION (RS256)
# ═══════════════════════════════════════════════════════════════════════════
JWT_ALGORITHM=RS256                     # Только RS256 поддерживается
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7
JWT_PRIVATE_KEY_PATH=.keys/private_key.pem
JWT_PUBLIC_KEY_PATH=.keys/public_key.pem
JWT_KEY_ROTATION_HOURS=24               # Интервал автоматической ротации ключей

# Platform-Agnostic Secret Management для JWT ключей:
# 1. Kubernetes Secret: JWT_PRIVATE_KEY / JWT_PUBLIC_KEY (полное PEM содержимое)
# 2. Environment Variables: JWT_PRIVATE_KEY_PATH / JWT_PUBLIC_KEY_PATH
# 3. File-based secrets: ./secrets/ directory

# ═══════════════════════════════════════════════════════════════════════════
# CORS (Cross-Origin Resource Sharing)
# ═══════════════════════════════════════════════════════════════════════════
CORS_ENABLED=on
CORS_ALLOW_ORIGINS=http://localhost:4200  # Production: explicit domains only!
CORS_ALLOW_CREDENTIALS=on
CORS_ALLOW_METHODS=GET,POST,PUT,DELETE,PATCH,OPTIONS
CORS_ALLOW_HEADERS=Content-Type,Authorization,X-Request-ID,X-Trace-ID
CORS_MAX_AGE=600                        # Preflight cache duration (seconds)

# ═══════════════════════════════════════════════════════════════════════════
# RATE LIMITING
# ═══════════════════════════════════════════════════════════════════════════
RATE_LIMIT_ENABLED=on
RATE_LIMIT_REQUESTS_PER_MINUTE=60
RATE_LIMIT_BURST=10

# ═══════════════════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════════════════
LOG_LEVEL=INFO                          # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FORMAT=json                         # json (production) / text (development)
# LOG_FILE=/path/to/logfile.log         # Опционально

# ═══════════════════════════════════════════════════════════════════════════
# MONITORING
# ═══════════════════════════════════════════════════════════════════════════
PROMETHEUS_ENABLED=on
OPENTELEMETRY_ENABLED=on
OPENTELEMETRY_SERVICE_NAME=artstore-admin-module
# OPENTELEMETRY_EXPORTER_ENDPOINT=http://localhost:4317

# ═══════════════════════════════════════════════════════════════════════════
# SERVICE DISCOVERY (Redis Pub/Sub)
# ═══════════════════════════════════════════════════════════════════════════
SERVICE_DISCOVERY_ENABLED=on
SERVICE_DISCOVERY_REDIS_CHANNEL=artstore:service_discovery
SERVICE_DISCOVERY_PUBLISH_INTERVAL=30   # Интервал публикации в секундах
SERVICE_DISCOVERY_STORAGE_ELEMENT_CONFIG_KEY=artstore:storage_elements

# ═══════════════════════════════════════════════════════════════════════════
# SAGA ORCHESTRATION
# ═══════════════════════════════════════════════════════════════════════════
SAGA_ENABLED=on
SAGA_TIMEOUT_SECONDS=300
SAGA_RETRY_ATTEMPTS=3
SAGA_RETRY_BACKOFF_SECONDS=5

# ═══════════════════════════════════════════════════════════════════════════
# HEALTH CHECKS
# ═══════════════════════════════════════════════════════════════════════════
HEALTH_STARTUP_TIMEOUT=30
HEALTH_LIVENESS_TIMEOUT=5
HEALTH_READINESS_TIMEOUT=10

# ═══════════════════════════════════════════════════════════════════════════
# SCHEDULER (APScheduler Background Jobs)
# ═══════════════════════════════════════════════════════════════════════════
SCHEDULER_ENABLED=on
SCHEDULER_TIMEZONE=UTC
SCHEDULER_JWT_ROTATION_ENABLED=on
SCHEDULER_JWT_ROTATION_INTERVAL_HOURS=24
SCHEDULER_STORAGE_HEALTH_CHECK_ENABLED=on
SCHEDULER_STORAGE_HEALTH_CHECK_INTERVAL_SECONDS=60  # 10-3600

# ═══════════════════════════════════════════════════════════════════════════
# INITIAL ADMINISTRATOR (создается при первом запуске)
# ═══════════════════════════════════════════════════════════════════════════
INITIAL_ADMIN_ENABLED=on
INITIAL_ADMIN_USERNAME=admin
INITIAL_ADMIN_PASSWORD=ChangeMe123!     # ОБЯЗАТЕЛЬНО сменить в production!
INITIAL_ADMIN_EMAIL=admin@artstore.local
INITIAL_ADMIN_FIRSTNAME=System
INITIAL_ADMIN_LASTNAME=Administrator

# ═══════════════════════════════════════════════════════════════════════════
# INITIAL SERVICE ACCOUNT (OAuth 2.0 Client Credentials)
# ═══════════════════════════════════════════════════════════════════════════
INITIAL_ACCOUNT_ENABLED=on
INITIAL_ACCOUNT_NAME=admin-service
INITIAL_ACCOUNT_PASSWORD=               # Пустой = автогенерация (выводится в логи)
INITIAL_ACCOUNT_ROLE=ADMIN              # ADMIN, USER, AUDITOR, READONLY

# ═══════════════════════════════════════════════════════════════════════════
# PASSWORD POLICY
# ═══════════════════════════════════════════════════════════════════════════
PASSWORD_MIN_LENGTH=12                  # Минимальная длина (8-128)
PASSWORD_REQUIRE_UPPERCASE=on
PASSWORD_REQUIRE_LOWERCASE=on
PASSWORD_REQUIRE_DIGITS=on
PASSWORD_REQUIRE_SPECIAL=on             # Требовать !@#$%^&* и т.д.
PASSWORD_MAX_AGE_DAYS=90               # Срок действия (30-365)
PASSWORD_HISTORY_SIZE=5                 # Количество запрещенных старых паролей (0-24)
PASSWORD_EXPIRATION_WARNING_DAYS=14     # За сколько дней предупреждать

# ═══════════════════════════════════════════════════════════════════════════
# SECURITY (HMAC, Audit)
# ═══════════════════════════════════════════════════════════════════════════
SECURITY_AUDIT_HMAC_SECRET=change-me-in-production-to-secure-random-value  # Минимум 32 символа!
SECURITY_AUDIT_RETENTION_DAYS=2555      # ~7 лет (compliance requirement)
```

### config.yaml (опционально, переопределяется через ENV)

```yaml
app:
  name: "ArtStore Admin Module"
  version: "0.1.0"
  debug: false
  swagger_enabled: false
  host: "0.0.0.0"
  port: 8000

database:
  host: "localhost"
  port: 5432
  username: "artstore"
  password: "password"
  database: "artstore_admin"
  pool_size: 10
  max_overflow: 20
  echo: false
  ssl_enabled: false
  ssl_mode: "require"
  # ssl_ca_cert: "/path/to/ca-cert.pem"
  # ssl_client_cert: "/path/to/client-cert.pem"
  # ssl_client_key: "/path/to/client-key.pem"

redis:
  host: "localhost"
  port: 6379
  password: null
  db: 0
  pool_size: 10

jwt:
  algorithm: "RS256"
  access_token_expire_minutes: 30
  refresh_token_expire_days: 7
  private_key_path: ".keys/private_key.pem"
  public_key_path: ".keys/public_key.pem"
  key_rotation_hours: 24

cors:
  enabled: true
  allow_origins:
    - "http://localhost:4200"
  allow_credentials: true
  allow_methods:
    - "GET"
    - "POST"
    - "PUT"
    - "DELETE"
    - "PATCH"
    - "OPTIONS"
  allow_headers:
    - "Content-Type"
    - "Authorization"
    - "X-Request-ID"
    - "X-Trace-ID"
  max_age: 600

rate_limit:
  enabled: true
  requests_per_minute: 60
  burst: 10

logging:
  level: "INFO"
  format: "json"

monitoring:
  prometheus:
    enabled: true
  opentelemetry:
    enabled: true
    service_name: "artstore-admin-module"
    exporter_endpoint: null

service_discovery:
  enabled: true
  redis_channel: "artstore:service_discovery"
  publish_interval_seconds: 30
  storage_element_config_key: "artstore:storage_elements"

saga:
  enabled: true
  timeout_seconds: 300
  retry_attempts: 3
  retry_backoff_seconds: 5

health:
  startup_timeout_seconds: 30
  liveness_timeout_seconds: 5
  readiness_timeout_seconds: 10

scheduler:
  enabled: true
  timezone: "UTC"
  jwt_rotation_enabled: true
  jwt_rotation_interval_hours: 24
  storage_health_check_enabled: true
  storage_health_check_interval_seconds: 60

initial_admin:
  enabled: true
  username: "admin"
  password: "ChangeMe123!"  # ОБЯЗАТЕЛЬНО сменить в production!
  email: "admin@artstore.local"
  firstname: "System"
  lastname: "Administrator"

security:
  audit_hmac_secret: "change-me-in-production-to-secure-random-value"
  audit_retention_days: 2555

password:
  min_length: 12
  require_uppercase: true
  require_lowercase: true
  require_digits: true
  require_special: true
  max_age_days: 90
  history_size: 5
  expiration_warning_days: 14
```

### Platform-Agnostic Secret Management

JWT ключи и другие секреты могут быть загружены из нескольких источников (в порядке приоритета):

1. **Kubernetes Secrets** (автоматически в k8s/k3s):
   ```yaml
   apiVersion: v1
   kind: Secret
   metadata:
     name: artstore-jwt-keys
   stringData:
     JWT_PRIVATE_KEY: |
       -----BEGIN RSA PRIVATE KEY-----
       ...
       -----END RSA PRIVATE KEY-----
     JWT_PUBLIC_KEY: |
       -----BEGIN PUBLIC KEY-----
       ...
       -----END PUBLIC KEY-----
   ```

2. **Environment Variables** (docker-compose, development)
3. **File-based secrets** (./secrets/ directory)

## Мониторинг и метрики

### Prometheus Metrics (`/metrics`)

#### Standard Metrics
- `http_requests_total`: Количество HTTP запросов
- `http_request_duration_seconds`: Latency HTTP запросов
- `http_request_size_bytes`: Размер HTTP запросов
- `http_response_size_bytes`: Размер HTTP ответов

#### Custom Business Metrics
- `artstore_auth_token_generated_total`: Количество сгенерированных JWT токенов
- `artstore_auth_token_validation_duration_seconds`: Время валидации токенов
- `artstore_service_accounts_total`: Количество Service Accounts по статусу
- `artstore_jwt_key_rotations_total`: Количество ротаций JWT ключей
- `artstore_storage_elements_total`: Количество Storage Elements по режиму
- `artstore_storage_health_check_duration_seconds`: Время выполнения health check storage elements

### OpenTelemetry Tracing

Distributed tracing для всех операций:
- **Span name**: `artstore.admin.{operation}`
- **Trace correlation**: Уникальный trace_id через все микросервисы
- **Context propagation**: Через HTTP headers (`traceparent`, `tracestate`)

### Structured Logging (JSON)

```json
{
  "timestamp": "2025-01-01T12:00:00.000Z",
  "level": "INFO",
  "logger": "artstore.admin.auth",
  "message": "JWT token generated",
  "module": "auth_service",
  "function": "generate_token",
  "line": 42,
  "trace_id": "abc123...",
  "span_id": "def456...",
  "client_id": "service-account-uuid",
  "operation": "token_generation",
  "duration_ms": 15
}
```

## Deployment

### Docker

```bash
# Build production image
docker build -t artstore-admin-module:latest -f Dockerfile .

# Run standalone (для тестирования)
docker run -d \
  --name admin-module \
  -p 8000:8000 \
  -e DB_HOST=postgres \
  -e DB_PORT=5432 \
  -e DB_USERNAME=artstore \
  -e DB_PASSWORD=password \
  -e DB_DATABASE=artstore_admin \
  -e REDIS_HOST=redis \
  -e REDIS_PORT=6379 \
  artstore-admin-module:latest

# Docker Compose (рекомендуется для разработки)
# ВСЕГДА запускать из корня проекта!
cd /home/artur/Projects/artStore
docker-compose build admin-module
docker-compose up -d admin-module
```

### Production Deployment

```bash
# Production с отключенным debug и swagger
docker run -d \
  --name admin-module \
  -p 8000:8000 \
  -e APP_DEBUG=off \
  -e APP_SWAGGER_ENABLED=off \
  -e DB_HOST=postgres-prod \
  -e DB_SSL_ENABLED=on \
  -e DB_SSL_MODE=verify-full \
  -e INITIAL_ADMIN_PASSWORD=SecurePassword123! \
  -e SECURITY_AUDIT_HMAC_SECRET=your-32-character-production-secret \
  artstore-admin-module:latest
```

## Troubleshooting

### Проблемы с аутентификацией

**Проблема**: "Invalid JWT signature"
**Решение**: Проверьте, что все модули используют актуальный публичный ключ. Проверьте `GET /api/auth/public-key`.

**Проблема**: "Token expired"
**Решение**: Время жизни токена 30 минут. Запросите новый токен через `POST /api/auth/token`.

### Проблемы с кластером

**Проблема**: "No leader elected"
**Решение**: Убедитесь что минимум 3 узла запущены и могут взаимодействовать друг с другом. Проверьте `RAFT_CLUSTER_NODES` конфигурацию.

**Проблема**: "Split-brain detected"
**Решение**: Остановите все узлы, очистите Raft state, перезапустите кластер с одного узла.

### Проблемы с производительностью

**Проблема**: Высокая latency на `/api/auth/token`
**Решение**: Проверьте connection pool к PostgreSQL. Увеличьте `DB_POOL_SIZE` если нужно.

**Проблема**: Redis connection timeout
**Решение**: Проверьте сетевое соединение к Redis. Увеличьте Redis connection pool и timeouts.

## Security Considerations

### Production Checklist

- [ ] Изменить `INITIAL_CLIENT_SECRET` на secure random value
- [ ] Использовать TLS 1.3 для всех соединений
- [ ] Настроить automated JWT key rotation (24 часа)
- [ ] Настроить automated client secret rotation (90 дней)
- [ ] Включить audit logging в tamper-proof storage
- [ ] Настроить rate limiting для защиты от brute-force
- [ ] Настроить webhook уведомления для security events
- [ ] Регулярный мониторинг Grafana dashboards для suspicious activity
- [ ] Настроить alerting для critical security events

### Best Practices

1. **Никогда не логировать** client secrets или JWT tokens в plain text
2. **Ротация ключей** должна быть автоматизирована, не полагайтесь на manual rotation
3. **Rate limiting** настроить индивидуально для каждого Service Account
4. **Audit logs** должны быть immutable и храниться минимум 7 лет
5. **Webhook URLs** должны быть HTTPS only в production

## Ссылки на документацию

- [Главная документация проекта](../README.md)
- [OAuth 2.0 Client Credentials Flow](https://oauth.net/2/grant-types/client-credentials/)
- [JWT RS256](https://datatracker.ietf.org/doc/html/rfc7519)
- [Raft Consensus](https://raft.github.io/)
- [Saga Pattern](https://microservices.io/patterns/data/saga.html)
