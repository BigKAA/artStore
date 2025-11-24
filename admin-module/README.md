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

### 2. Управление Storage Elements

- **Регистрация и конфигурирование** Storage Elements
- **Monitoring статусов**: edit, rw, ro, ar режимы
- **Публикация в Service Discovery**: Redis pub/sub для обновлений
- **Health checking**: Периодическая проверка доступности

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

#### Authentication (`/api/auth/*`)
```
POST /api/auth/token
  - OAuth 2.0 Client Credentials authentication
  - Input: {"client_id": "...", "client_secret": "..."}
  - Output: {"access_token": "eyJ...", "token_type": "Bearer", "expires_in": 1800}

GET /api/auth/public-key
  - Получение публичного ключа для валидации JWT
  - Output: PEM-formatted public key

POST /api/auth/rotate-keys
  - Ручная ротация JWT ключей (admin only)
  - Автоматическая ротация каждые 24 часа
```

#### Service Accounts (`/api/service-accounts/*`)
```
GET /api/service-accounts
  - Список всех Service Accounts (с пагинацией)
  - Фильтры: role, status, created_after

POST /api/service-accounts
  - Создание нового Service Account
  - Auto-generated client_id и client_secret

GET /api/service-accounts/{id}
  - Детали конкретного Service Account

PATCH /api/service-accounts/{id}
  - Обновление Service Account (role, rate_limit, description)

DELETE /api/service-accounts/{id}
  - Удаление Service Account (запрещено для is_system=True)

POST /api/service-accounts/{id}/rotate-secret
  - Ручная ротация client secret
  - Возвращает новый secret (показывается один раз)

POST /api/service-accounts/{id}/suspend
  - Приостановка Service Account (status → SUSPENDED)

POST /api/service-accounts/{id}/activate
  - Активация Service Account (status → ACTIVE)
```

#### Storage Elements (`/api/storage-elements/*`)
```
GET /api/storage-elements
  - Список всех Storage Elements
  - Фильтры: mode, status, location

POST /api/storage-elements
  - Регистрация нового Storage Element

GET /api/storage-elements/{id}
  - Детали конкретного Storage Element

PATCH /api/storage-elements/{id}
  - Обновление конфигурации Storage Element

DELETE /api/storage-elements/{id}
  - Удаление Storage Element (проверка отсутствия файлов)

POST /api/storage-elements/{id}/change-mode
  - Смена режима работы (rw → ro, ro → ar)
  - Two-Phase Commit для консистентности
```

#### Webhooks (`/api/webhooks/*`)
```
GET /api/webhooks
  - Список зарегистрированных webhooks

POST /api/webhooks
  - Регистрация нового webhook
  - Events: file_restored, restore_failed, file_expiring, security_alert

GET /api/webhooks/{id}
  - Детали webhook

PATCH /api/webhooks/{id}
  - Обновление webhook

DELETE /api/webhooks/{id}
  - Удаление webhook

POST /api/webhooks/{id}/test
  - Тестовая отправка webhook
```

#### Transactions (Saga Orchestrator) (`/api/transactions/*`)
```
GET /api/transactions
  - Список всех транзакций (с фильтрацией по status)

GET /api/transactions/{id}
  - Детали конкретной транзакции
  - Показывает все шаги и их статусы

POST /api/transactions/{id}/compensate
  - Запуск compensating actions для отката транзакции

GET /api/transactions/{id}/audit
  - Полный audit trail транзакции
```

#### Health & Monitoring
```
GET /health/live
  - Liveness probe (is service running?)

GET /health/ready
  - Readiness probe (can handle traffic?)
  - Проверяет: PostgreSQL, Redis connectivity

GET /metrics
  - Prometheus metrics endpoint
```

### Внутренняя архитектура

```
admin-module/
├── app/
│   ├── main.py                      # FastAPI application entry point
│   ├── core/
│   │   ├── config.py                # Pydantic Settings configuration
│   │   ├── security.py              # JWT generation, validation
│   │   ├── raft.py                  # Raft consensus implementation
│   │   └── exceptions.py            # Custom exceptions
│   ├── api/
│   │   ├── deps.py                  # FastAPI dependencies (get_db, get_current_user)
│   │   └── v1/
│   │       ├── router.py            # Main API router
│   │       └── endpoints/
│   │           ├── auth.py          # Authentication endpoints
│   │           ├── service_accounts.py
│   │           ├── storage_elements.py
│   │           ├── webhooks.py
│   │           ├── transactions.py
│   │           └── health.py
│   ├── models/
│   │   ├── service_account.py       # ServiceAccount ORM model
│   │   ├── storage_element.py       # StorageElement ORM model
│   │   ├── webhook.py               # Webhook ORM model
│   │   ├── transaction.py           # Transaction ORM model
│   │   └── audit_log.py             # AuditLog ORM model
│   ├── schemas/
│   │   ├── auth.py                  # Auth request/response schemas
│   │   ├── service_account.py       # Service account schemas
│   │   ├── storage_element.py       # Storage element schemas
│   │   └── webhook.py               # Webhook schemas
│   ├── services/
│   │   ├── auth_service.py          # Authentication business logic
│   │   ├── account_service.py       # Service account management
│   │   ├── storage_service.py       # Storage element management
│   │   ├── webhook_service.py       # Webhook management
│   │   ├── saga_orchestrator.py     # Saga pattern coordinator
│   │   ├── service_discovery.py     # Redis pub/sub for config
│   │   └── key_rotation.py          # Automated JWT key rotation
│   ├── db/
│   │   ├── session.py               # Database session management
│   │   └── base.py                  # SQLAlchemy declarative base
│   └── utils/
│       ├── crypto.py                # Cryptographic utilities
│       ├── redis_utils.py           # Redis helpers
│       └── metrics.py               # Prometheus metrics helpers
├── alembic/
│   └── versions/                    # Database migrations
├── tests/
│   ├── unit/                        # Unit tests
│   │   ├── test_auth_service.py
│   │   ├── test_account_service.py
│   │   └── test_saga_orchestrator.py
│   └── integration/                 # Integration tests
│       ├── test_auth_api.py
│       ├── test_accounts_api.py
│       └── test_transactions_api.py
├── Dockerfile                       # Production Docker image
├── Dockerfile.dev                   # Development Docker image
├── requirements.txt                 # Python dependencies
├── pytest.ini                       # Pytest configuration
└── .env.example                     # Example environment variables
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

```bash
# Application Settings
APP_NAME=artstore-admin-module
APP_VERSION=1.0.0
LOG_LEVEL=INFO
LOG_FORMAT=json  # json для production, text для development

# Database
DATABASE_URL=postgresql+asyncpg://artstore:password@localhost:5432/artstore
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=10

# Redis
REDIS_URL=redis://localhost:6379/0
REDIS_SENTINEL_ENABLED=false
REDIS_SENTINEL_HOSTS=sentinel1:26379,sentinel2:26379,sentinel3:26379
REDIS_MASTER_NAME=mymaster

# JWT Configuration
JWT_ALGORITHM=RS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_PRIVATE_KEY_PATH=/secrets/jwt_private_key.pem
JWT_PUBLIC_KEY_PATH=/secrets/jwt_public_key.pem
JWT_KEY_ROTATION_HOURS=24

# Raft Consensus (для кластера)
RAFT_NODE_ID=node1
RAFT_CLUSTER_NODES=node1:8000,node2:8001,node3:8002
RAFT_ELECTION_TIMEOUT_MS=150
RAFT_HEARTBEAT_INTERVAL_MS=50

# Security
CLIENT_SECRET_ROTATION_DAYS=90
RATE_LIMIT_PER_MINUTE=100
WEBHOOK_TIMEOUT_SECONDS=10

# Monitoring
PROMETHEUS_METRICS_ENABLED=true
OPENTELEMETRY_ENABLED=true
OPENTELEMETRY_ENDPOINT=http://localhost:4317

# Initial System Account (автосоздание при первом запуске)
INITIAL_ACCOUNT_ENABLED=true
INITIAL_ACCOUNT_NAME=admin-service
INITIAL_CLIENT_ID=  # Auto-generated если не указан
INITIAL_CLIENT_SECRET=  # Auto-generated, ИЗМЕНИТЬ В PRODUCTION!
INITIAL_ACCOUNT_ROLE=ADMIN
```

### config.yaml (опционально, переопределяется через ENV)

```yaml
app:
  name: artstore-admin-module
  version: "1.0.0"
  debug: false

database:
  url: "postgresql+asyncpg://artstore:password@localhost:5432/artstore"
  pool_size: 20
  max_overflow: 10
  echo: false

redis:
  url: "redis://localhost:6379/0"
  sentinel_enabled: false

jwt:
  algorithm: "RS256"
  access_token_expire_minutes: 30
  key_rotation_hours: 24

security:
  client_secret_rotation_days: 90
  rate_limit_per_minute: 100

logging:
  level: "INFO"
  format: "json"
```

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
- `artstore_saga_transactions_total`: Количество Saga транзакций по типу
- `artstore_saga_compensations_total`: Количество compensating actions
- `artstore_storage_elements_total`: Количество Storage Elements по режиму
- `artstore_webhook_deliveries_total`: Webhook доставки (success/failure)

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
  -e DATABASE_URL=postgresql+asyncpg://... \
  -e REDIS_URL=redis://... \
  artstore-admin-module:latest

# Docker Compose (рекомендуется для разработки)
# ВСЕГДА запускать из корня проекта!
cd /home/artur/Projects/artStore
docker-compose build admin-module
docker-compose up -d admin-module
```

### High Availability Cluster (Production)

```bash
# 3-узловой кластер с Raft consensus
docker-compose -f docker-compose.prod.yml up -d \
  admin-module-node1 \
  admin-module-node2 \
  admin-module-node3

# Load balancer (HAProxy/Nginx)
docker-compose -f docker-compose.prod.yml up -d load-balancer

# Проверка статуса кластера
curl http://localhost:8000/api/cluster/status
{
  "leader": "node1",
  "nodes": [
    {"id": "node1", "state": "leader", "healthy": true},
    {"id": "node2", "state": "follower", "healthy": true},
    {"id": "node3", "state": "follower", "healthy": true}
  ]
}
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
