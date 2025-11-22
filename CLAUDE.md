# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ArtStore - это распределенная система файлового хранилища с микросервисной архитектурой, предназначенная для долгосрочного хранения документов с различными сроками хранения. Система реализует принципы отказоустойчивости, горизонтального масштабирования и обеспечивает разделение оперативного и архивного хранения.

## Общие вопросы

Если не знаешь ответ, так и скажи - Не знаю ответ. Не ври.

Если видишь, что выполнение задач зациклилось - остановись, спроси что делать дальше.

Пиши подробные комментарии в коде на русском языке.

Отвечай на русском языке.

## 🔴 КРИТИЧЕСКИ ВАЖНО: Docker Compose

**ОБЯЗАТЕЛЬНОЕ ТРЕБОВАНИЕ №1**: Для запуска, тестирования и работы с проектом использовать ТОЛЬКО файлы `docker-compose*.yml` из **КОРНЯ ПРОЕКТА** (`/home/artur/Projects/artStore/`).

**ВСЕГДА**:
- ✅ `cd /home/artur/Projects/artStore` перед любыми docker-compose командами
- ✅ Использовать корневой `docker-compose.yml` для всех операций
- ✅ Запускать `docker-compose build [module-name]` из корня
- ✅ Запускать `docker-compose up -d [module-name]` из корня

**НИКОГДА**:
- ❌ НЕ использовать docker-compose из поддиректорий (admin-module/, ingester-module/, etc.)
- ❌ НЕ создавать собственные docker-compose файлы
- ❌ НЕ запускать модули напрямую без Docker

## Набор утилит

Базовые утилиты запускай в docker или podman при помощи docker-compose.yml:

- postgres
- redis
- minio

Логины и пароли администраторов приложений доступны в `docker-compose.yml`.

Для работы с postgres используй инструменты, находящиеся в контейнере postgres. Если необходимой базы данных нет - создавай ее сам.

**Примечание**: LDAP и Dex OIDC были удалены в Sprint 13. Система использует только OAuth 2.0 Client Credentials authentication.

### Core Architecture Concepts

**Attribute-First Storage Model**: Система использует файлы атрибутов (`*.attr.json`) как единственный источник истины для метаданных файлов. Это критически важно для обеспечения backup'а элементов хранения как набора простых файлов без необходимости работы с отдельными таблицами БД.

**Distributed Storage Elements**: Элементы хранения могут располагаться в разных ЦОД и иметь свои собственные кеш-БД для повышения производительности.

**JWT-based Authentication (RS256)**: Центральная аутентификация через Admin Module с распределенной валидацией токенов через публичный ключ.

**Service Discovery**: Координация через Redis Cluster - Admin Module Cluster публикует конфигурацию storage-element, а Ingester/Query кластеры подписываются на эти обновления с fallback на локальную конфигурацию.

**ВАЖНО: Redis работает в СИНХРОННОМ режиме**: Все модули используют синхронный redis-py (не redis.asyncio). Это архитектурное решение для упрощения координации между микросервисами и обеспечения предсказуемости Service Discovery через Redis Pub/Sub. Database (PostgreSQL) использует async (asyncpg), Redis - sync (redis-py).

**High Availability Architecture**: Полное устранение Single Points of Failure:
- **Load Balancer Cluster**: HAProxy/Nginx с keepalived для распределения трафика
- **Admin Module Cluster**: Raft consensus с 3+ узлами и automatic leader election (RTO < 15 сек)
- **Redis Cluster**: 6+ узлов (минимум 3 master + 3 replica) с automatic failover и горизонтальным масштабированием (RTO < 30 сек)
- **Storage Element Clusters**: Кластеризация с shared storage и master election
- **Circuit Breaker Patterns**: Graceful degradation при недоступности dependencies

**Data Consistency Framework**: Система обеспечивает строгую консистентность данных через:
- **Saga Pattern**: Для долгосрочных операций с файлами (загрузка → валидация → индексация)
- **Two-Phase Commit**: Для критических операций изменения метаданных и смены режимов
- **Write-Ahead Log**: Атомарность операций записи файлов и атрибутов
- **Automatic Reconciliation**: Автоматическое восстановление консистентности при расхождениях
- **Template Schema**: Гибкая эволюция метаданных без breaking changes через schema versioning

**Performance Optimization Framework**: Комплексная стратегия повышения производительности:
- **Multi-Level Caching**: CDN → Redis Cluster → Local Cache → Database Cache
- **PostgreSQL Full-Text Search**: Встроенные возможности поиска с GIN индексами для метаданных
- **Streaming & Compression**: Chunked uploads/downloads с Brotli/GZIP compression
- **Connection Pooling**: HTTP/2 persistent connections между всеми сервисами
- **Async Processing**: Background tasks через Kafka для heavy operations

**Comprehensive Security Framework**: Многоуровневая система защиты данных:
- **TLS 1.3 Transit Encryption**: Все межсервисные соединения защищены современным протоколом TLS 1.3
- **Secure Key Management**: Защищенное управление JWT ключами через Admin Module Cluster
- **Automated JWT Key Rotation**: Ротация RS256 ключей каждые 24 часа с плавным переходом

**Advanced Monitoring и Observability Framework**: Комплексная система наблюдаемости:
- **OpenTelemetry Distributed Tracing**: Полное отслеживание запросов через все микросервисы
- **Custom Business Metrics**: File upload latency, search performance, storage utilization, authentication metrics
- **Third-party Analytics Integration**: Экспорт метрик для внешних систем аналитики

## Development Environment Setup

### КРИТИЧЕСКИ ВАЖНО: Docker Compose в корне проекта

**ОБЯЗАТЕЛЬНОЕ ТРЕБОВАНИЕ**: Для запуска и тестирования проекта использовать ТОЛЬКО файлы `docker-compose*.yml`, расположенные в **КОРНЕ ПРОЕКТА** (`/home/artur/Projects/artStore/`).

**ЗАПРЕЩЕНО**:
- ❌ Использовать docker-compose.yml из поддиректорий модулей (admin-module/, ingester-module/, storage-element/, query-module/)
- ❌ Запускать отдельные модули через их локальные docker-compose.yml
- ❌ Создавать собственные docker-compose конфигурации вне корня проекта

**ПРАВИЛЬНЫЙ ПОДХОД**:
- ✅ Всегда работать с `/home/artur/Projects/artStore/docker-compose.yml` (базовая инфраструктура)
- ✅ Использовать `/home/artur/Projects/artStore/docker-compose.monitoring.yml` (мониторинг)
- ✅ Запускать все команды docker-compose из корня проекта

**Причина**: Корневые docker-compose файлы управляют всей инфраструктурой проекта как единым целым, обеспечивая:
- Правильную настройку сетей между модулями
- Единую конфигурацию зависимостей (PostgreSQL, Redis, MinIO)
- Корректный порядок запуска сервисов
- Согласованные environment variables

### Prerequisites

```bash
# ВСЕГДА запускать из корня проекта!
cd /home/artur/Projects/artStore

# Базовая инфраструктура
docker-compose up -d

# Мониторинг (опционально)
docker-compose -f docker-compose.monitoring.yml up -d
```

### Python Virtual Environment

**ВАЖНО: Проект использует ЕДИНЫЙ глобальный virtual environment**

Система использует externally-managed Python environment, поэтому установка зависимостей через pip требует использования venv.

**Все Python модули проекта используют ОБЩИЙ venv, расположенный в корне проекта: `/home/artur/Projects/artStore/.venv`**

```bash
# Создание глобального virtual environment (выполняется ОДИН РАЗ в корне проекта)
cd /home/artur/Projects/artStore
python3 -m venv .venv

# Активация venv (выполняется перед работой с любым Python модулем)
source /home/artur/Projects/artStore/.venv/bin/activate  # Linux/macOS
# или
C:\path\to\artStore\.venv\Scripts\activate  # Windows

# Установка зависимостей для всех модулей
pip install -r admin-module/requirements.txt
pip install -r storage-element/requirements.txt
pip install -r ingester-module/requirements.txt
pip install -r query-module/requirements.txt

# Деактивация venv (когда закончите работу)
deactivate
```

**Требования**:
- **ЕДИНЫЙ .venv в корне проекта** `/home/artur/Projects/artStore/.venv` для всех Python модулей
- .venv добавлен в .gitignore корневой директории
- Все команды python/pip выполняются внутри активированного глобального venv
- Скрипты и утилиты запускаются через `/home/artur/Projects/artStore/.venv/bin/python`
- Перед работой с любым модулем активируйте глобальный venv

### Database Access

```bash
# Access PostgreSQL container for database operations
docker exec -it artstore_postgres psql -U artstore -d artstore

# Create additional databases as needed within the container
```

### Service Ports
- **PostgreSQL**: 5432
- **PgAdmin**: 5050 (admin@admin.com / password)
- **Redis**: 6379
- **MinIO**: 9000 (console: 9001, minioadmin / minioadmin)
- **Admin Module**: 8000-8009
- **Storage Elements**: 8010-8019
- **Ingester Module**: 8020-8029
- **Query Module**: 8030-8039
- **Admin UI**: 4200

## Module Architecture

### 1. Admin Module Cluster (admin-module/)
**Role**: Отказоустойчивый центр аутентификации и управления системой
- **Raft Consensus Cluster**: Автоматическое лидерство с выборами в кластере 3+ узлов
- **Multi-Master Active-Active**: Consistent hashing для распределения нагрузки
- **Zero-Downtime Operations**: Rolling updates и graceful failover (RTO < 15 сек)
- **JWT token generation (RS256)** с распределенной валидацией через публичный ключ
- **Service Account Management**: OAuth 2.0 Client Credentials для machine-to-machine аутентификации
- **Automated Secret Rotation**: Ротация client secrets каждые 90 дней
- **Saga Orchestrator**: Координация распределенных транзакций (Upload, Delete, Transfer файлов)
- **Conflict Resolution**: Автоматическое обнаружение и устранение несоответствий между attr.json и DB cache
- Service account and storage element management
- Service Discovery publishing to Redis Sentinel Cluster
- Webhook management для уведомлений о событиях (file_restored, restore_failed, file_expiring)
- Prometheus metrics endpoint

**Key APIs**:
- `/api/auth/token` - OAuth 2.0 Client Credentials authentication (client_id + client_secret → JWT)
- `/api/service-accounts/*` - Service account management (CRUD operations)
- `/api/service-accounts/{id}/rotate-secret` - Manual secret rotation
- `/api/service-accounts/{id}/webhooks` - Webhook configuration для service accounts
- `/api/storage-elements/*` - Storage element management
- `/api/transactions/*` - Saga orchestration status и compensating actions
- `/api/batch/*` - Batch operations (upload, delete до 100 файлов / 1GB)
- `/health/*` - Health checks (liveness, readiness)
- `/metrics` - Prometheus metrics

### 2. Storage Element Clusters (storage-element/)
**Role**: Отказоустойчивое физическое хранение файлов с кешированием метаданных

**Deployment Options**:
- **Standalone Mode**: Одиночный узел без репликации (упрощенная конфигурация для некритичных данных)
- **Replicated Mode** (опционально): Кластер из 3+ узлов с синхронной или асинхронной репликацией для критичных данных

**Core Features**:
- File storage (local filesystem or S3)
- **Write-Ahead Log**: Журнал транзакций для атомарности операций
- **Saga Participant**: Участие в распределенных транзакциях координируемых Admin Module
- Metadata caching in PostgreSQL Cluster
- Four operational modes: edit, rw, ro, ar

**Critical Implementation Details**:
- **Attribute files** (`*.attr.json`): Единственный источник истины для метаданных
  - Максимальный размер: 4KB (гарантия атомарности записи)
  - Атомарная запись: WAL → Temporary file → fsync → Atomic Rename
- **File Naming Convention**: `{name_without_ext}_{username}_{timestamp}_{uuid}.{ext}`
  - Original filename первым для human-readability при сортировке
  - Гарантирует уникальность при одновременной загрузке файлов с одинаковыми именами
  - **Автоматическое обрезание** длинных имен до 200 символов (полное имя в attr.json)
  - Пример: `report_ivanov_20250102T153045_a1b2c3d4.pdf`
  - Implementation:
    ```python
    from pathlib import Path

    def generate_storage_filename(original_name, username, timestamp, uuid, max_len=200):
        name_stem = Path(original_name).stem
        name_ext = Path(original_name).suffix
        fixed_len = 1 + len(username) + 1 + len(timestamp) + 1 + len(uuid) + len(name_ext)
        available = max_len - fixed_len
        if len(name_stem) > available:
            name_stem = name_stem[:available]
        return f"{name_stem}_{username}_{timestamp}_{uuid}{name_ext}"
    ```
- **Consistency Protocol**: WAL → Attr File → DB Cache → Service Discovery → Commit
- **Automatic Reconciliation**: Обнаружение и устранение несоответствий между attr.json и DB cache
- **Directory structure**: `/year/month/day/hour/` для удобства резервного копирования
- **Mode transitions**: edit (fixed) → rw → ro → ar

**Replicated Mode Configuration** (опционально):
```yaml
replication:
  enabled: true
  mode: sync | async
  replicas: 2
  quorum: majority

sync_replication:
  min_replicas: 2
  write_timeout: 5s
  consistency: strong
  rto: < 30s
  rpo: 0  # Zero data loss

async_replication:
  batch_size: 100
  interval: 60s
  retry_failed: true
  rto: < 30s
  rpo: ~60s  # Last batch
```

**Master Election** (только replicated mode):
- Redis Sentinel координация для режимов edit/rw
- Automatic failover за < 30 секунд
- Split-brain protection через quorum

### 3. Ingester Cluster (ingester-module/)
**Role**: Высокопроизводительное отказоустойчивое добавление и управление файлами
- **Streaming Upload**: Chunked загрузка с progress tracking и resumable uploads
- **Parallel Processing**: Одновременная обработка множественных файлов
- **Compression On-the-fly**: Автоматическое сжатие (Brotli/GZIP) при загрузке
- **CDN Pre-upload**: Автоматическая репликация на CDN для популярных файлов
- **Kafka Integration**: Асинхронная обработка через message queue
- **Circuit Breaker Integration**: Graceful degradation при недоступности storage-element
- **Redis Cluster Client**: Подключение к HA Redis Cluster для Service Discovery
- **Local Config Fallback**: Кеширование конфигурации при недоступности Service Discovery
- **Saga Transactions**: Координируемые операции загрузки файлов
- **Compensating Actions**: Автоматический откат при сбоях
- File upload to storage elements with optimization
- File deletion (edit mode only) with async cleanup
- File transfer between storage elements with Two-Phase Commit

### 4. Query Cluster (query-module/)
**Role**: Высокопроизводительный отказоустойчивый поиск и получение файлов
- **PostgreSQL Full-Text Search**: Мгновенный поиск через встроенные GIN индексы PostgreSQL
- **Multi-Level Caching**: Local → Redis → PostgreSQL Query Cache
- **Real-time Search**: Auto-complete и suggestions на основе популярных запросов
- **CDN Integration**: Автоматическое направление на ближайший CDN endpoint
- **Connection Pooling**: HTTP/2 persistent connections к storage-element
- **Load Balanced Cluster**: Множественные узлы за Load Balancer для высокой доступности
- **Circuit Breaker Pattern**: Автоматическое отключение недоступных storage-element
- **Redis Cluster Integration**: HA подключение к Service Discovery
- **Read Consistency**: Гарантии согласованности при чтении через WAL + Saga Pattern
- **Automatic Reconciliation**: Обнаружение и устранение несоответствий метаданных
- File search by metadata with full-text capabilities
- Optimized file download with resumable transfers
- Digital signature verification

### 5. Admin UI (admin-ui/)
**Role**: Angular-based administrative interface
- User management interface
- Storage element monitoring
- File manager
- System statistics dashboard

## Development Commands

### Docker Containerization (ОБЯЗАТЕЛЬНО)

**ВАЖНО: ВСЕ модули ДОЛЖНЫ разрабатываться и тестироваться в Docker контейнерах**

Каждый Python модуль должен иметь:
- `Dockerfile` - многоступенчатый образ для production
- `docker-compose.yml` - локальная разработка и тестирование
- `.dockerignore` - исключение ненужных файлов из образа

**Требования к логированию**:
- **JSON формат по умолчанию**: Все production логи ДОЛЖНЫ быть в JSON формате для интеграции с ELK Stack, Splunk и другими системами анализа
- **Structured logging**: Использовать python-json-logger или аналоги для структурированного логирования
- **Text формат**: Разрешен ТОЛЬКО в development режиме (docker-compose.dev.yml) для удобства отладки
- **Обязательные поля в логах**: timestamp, level, logger, message, module, function, line
- **Дополнительные поля**: request_id, user_id, trace_id (для OpenTelemetry интеграции)

### Running Applications

**КРИТИЧЕСКИ ВАЖНО**: Использовать ТОЛЬКО docker-compose из корня проекта!

```bash
# ВСЕГДА работать из корня проекта
cd /home/artur/Projects/artStore

# Запуск базовой инфраструктуры (PostgreSQL, Redis, MinIO) + все модули
docker-compose up -d

# Просмотр логов конкретного модуля
docker-compose logs -f ingester-module
docker-compose logs -f admin-module
docker-compose logs -f storage-element
docker-compose logs -f query-module

# Остановка всех сервисов
docker-compose down

# Пересборка конкретного модуля после изменений
docker-compose build ingester-module
docker-compose up -d ingester-module

# Пересборка всех модулей
docker-compose build
docker-compose up -d

# Запуск мониторинга (Prometheus, Grafana)
docker-compose -f docker-compose.monitoring.yml up -d
```

**ОБЯЗАТЕЛЬНЫЕ ПРАВИЛА Docker**:
- ✅ ВСЕГДА использовать `docker-compose` из `/home/artur/Projects/artStore/`
- ✅ ВСЕГДА работать с корневым `docker-compose.yml`
- ✅ ВСЕГДА тестировать в Docker окружении
- ❌ НЕ использовать docker-compose.yml из поддиректорий модулей
- ❌ НЕ запускать `python -m uvicorn` напрямую
- ❌ НЕ использовать локальный venv для тестирования
- ❌ НЕ создавать отдельные docker-compose конфигурации

### Testing
Always create and run unit tests for modified code:
```bash
# Run tests for specific module
cd [module-name]
py -m pytest tests/ -v

# Run with coverage
py -m pytest tests/ --cov=app --cov-report=html
```

### Database Operations
```bash
# Create new database within container
docker exec -it artstore_postgres createdb -U artstore new_database_name

# Access database
docker exec -it artstore_postgres psql -U artstore -d [database_name]
```

## Key Configuration Patterns

### Authentication Configuration
```yaml
auth:
  jwt:
    public_key_path: "/path/to/public_key.pem"
    algorithm: "RS256"
```

### Storage Configuration
```yaml
storage:
  type: "local"  # or "s3"
  max_size: 1Gb
  local:
    base_path: "./.data/storage"
  s3:
    endpoint_url: "http://localhost:9000"
    bucket_name: "artstore-files"
```

### Database Configuration
```yaml
database:
  host: "localhost"
  port: 5432
  username: "artstore"
  password: "password"
  database: "artstore"
  table_prefix: "storage_elem_01"  # For uniqueness in shared DB
```

### Logging Configuration
```yaml
logging:
  level: "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
  format: "json"  # ОБЯЗАТЕЛЬНО "json" для production, "text" только для development
  log_file: null  # Путь к файлу лога, null для stdout
```

**Production Environment Variables (docker-compose.yml)**:
```yaml
environment:
  LOG_LEVEL: "INFO"
  LOG_FORMAT: "json"  # ОБЯЗАТЕЛЬНО json
```

**Development Environment Variables (docker-compose.dev.yml)**:
```yaml
environment:
  LOG_LEVEL: "DEBUG"
  LOG_FORMAT: "text"  # Разрешен text только в dev режиме
```

## Storage Element Modes and Transitions

**Mode Definitions**:
- `edit`: Full CRUD operations (default for active storage)
- `rw`: Read-write, no deletion (transitional state)
- `ro`: Read-only (archived but accessible)
- `ar`: Archive mode (metadata only, files on cold storage)

**Transition Rules**:
- edit → Cannot be changed via API
- rw → ro (via API)
- ro → ar (via API)
- ar → other modes (configuration change + restart only)

## Development Workflow

1. **Module Development Order**: admin-module → storage-element → ingester-module → query-module → admin-ui
2. **Container Usage**: Each module gets its own Docker container; admin-ui uses nginx
3. **Configuration Priority**: Environment variables override config file settings
4. **Language**: All comments and documentation should be in Russian
5. **Platform**: Development on Windows 11 using cmd.exe or PowerShell commands

## Testing Credentials

**Initial Service Account (Auto-created on first startup)**:
- Name: `admin-service` (configurable via `INITIAL_ACCOUNT_NAME`)
- Client ID: Auto-generated UUID (configurable via `INITIAL_CLIENT_ID`)
- Client Secret: Auto-generated secure string (configurable via `INITIAL_CLIENT_SECRET`)
- Role: `ADMIN` (full permissions)
- **ВАЖНО**: Автоматически создается при первом запуске если в БД нет service accounts
- **ВАЖНО**: Имеет флаг `is_system=True` - не может быть удален через API
- **ВАЖНО**: В production ОБЯЗАТЕЛЬНО изменить client_secret через environment variable!

**Configuration (`.env`):**
```bash
INITIAL_ACCOUNT_ENABLED=true  # Отключить автосоздание можно установив false
INITIAL_ACCOUNT_NAME=admin-service
INITIAL_CLIENT_ID=auto-generated  # Автогенерация если не указан
INITIAL_CLIENT_SECRET=auto-generated  # Автогенерация если не указан, ИЗМЕНИТЬ В PRODUCTION!
INITIAL_ACCOUNT_ROLE=ADMIN
INITIAL_ACCOUNT_DESCRIPTION="System administrative service account"
```

**OAuth 2.0 Authentication Example**:
```bash
# Получение JWT токена
curl -X POST http://localhost:8000/api/auth/token \
  -H "Content-Type: application/json" \
  -d '{"client_id": "${CLIENT_ID}", "client_secret": "${CLIENT_SECRET}"}'

# Response: {"access_token": "eyJ...", "token_type": "Bearer", "expires_in": 1800}
```

**Infrastructure Credentials**:
- PostgreSQL: artstore / password
- PgAdmin: admin@admin.com / password
- MinIO: minioadmin / minioadmin

## Critical Implementation Notes

### High Availability Requirements
1. **No Single Points of Failure**: Все компоненты развернуты в кластерной конфигурации
2. **Load Balancer Cluster**: HAProxy/Nginx + keepalived для устранения SPOF входного трафика
3. **Admin Module Cluster**: Raft consensus кластер 3+ узлов с automatic leader election (RTO < 15 сек)
4. **Redis Cluster**: 6+ узлов (минимум 3 master + 3 replica) с automatic failover и горизонтальным масштабированием (RTO < 30 сек)
5. **Circuit Breaker Pattern**: Обязательная реализация для всех inter-service communications
6. **Local Fallback**: Кеширование конфигурации для работы при недоступности Service Discovery

### Data Consistency & Operations
7. **Consistency Protocol**: WAL → Attr File → DB Cache → Service Discovery → Commit (строго в этом порядке)
8. **Saga Coordination**: Admin Module Cluster координирует все долгосрочные операции через Saga Pattern
9. **Template Schema Evolution**: Гибкая эволюция метаданных через schema versioning без breaking changes
10. **Conflict Resolution**: Автоматическое обнаружение и разрешение конфликтов данных
11. **Attribute Files**: Always write to *.attr.json first, then update database cache
12. **Master Election**: Required for edit/rw modes using Redis Cluster coordination
13. **Service Discovery**: Ingester/Query clusters must subscribe to Redis Cluster for storage element updates
14. **Stateless Design**: All modules must be stateless
15. **Error Handling**: Insufficient storage space should return specific error message
16. **Retention Management**: Storage elements have configurable retention periods with automatic warnings

### Performance Requirements
17. **PostgreSQL Full-Text Search**: Встроенные GIN индексы для поиска по метаданным всех storage-element
18. **Multi-Level Caching**: CDN → Redis → Local → DB cache hierarchy реализация
19. **Connection Pooling**: HTTP/2 persistent connections между всеми сервисами
20. **Streaming Operations**: Chunked upload/download для файлов >10MB
21. **Background Processing**: Kafka message queue для heavy operations (compression, indexing)
22. **CDN Integration**: Автоматическая репликация файлов на CloudFlare/AWS CloudFront

## Monitoring and Logging

### Sprint 14 Implementation Status: ✅ COMPLETE

All modules now have comprehensive observability with OpenTelemetry distributed tracing, Prometheus metrics, and Grafana dashboards.

### Quick Start

```bash
# 1. Start base infrastructure (if not running)
docker-compose up -d

# 2. Start monitoring stack
docker-compose -f docker-compose.monitoring.yml up -d

# 3. Access monitoring interfaces
# Prometheus: http://localhost:9090
# Grafana: http://localhost:3000 (admin / admin123)
# AlertManager: http://localhost:9093
```

### Monitoring Stack Components

- **Prometheus** (http://localhost:9090): Metrics collection from all modules every 15 seconds
- **Grafana** (http://localhost:3000): Pre-configured dashboards for system overview
- **AlertManager** (http://localhost:9093): Alert routing and notifications
- **Node Exporter** (http://localhost:9100): Host system metrics

**Full Documentation**: See `monitoring/README.md` for comprehensive setup guide, troubleshooting, and PromQL examples.

### OpenTelemetry Integration (✅ Implemented)

All modules (admin-module, storage-element, ingester-module, query-module) implement:

- **Distributed Tracing**: Полное инструментирование всех HTTP requests, database queries, Redis operations
- **Trace Correlation**: Уникальные trace ID для корреляции across all микросервисы
- **Span Context Propagation**: Передача trace context через headers и message queues
- **Performance Profiling**: Детальное профилирование критических операций

**Implementation**: Each module has `app/core/observability.py` with `setup_observability()` function:
```python
from app.core.observability import setup_observability

setup_observability(
    app=app,
    service_name="artstore-{module-name}",
    service_version=settings.app.version,
    enable_tracing=True
)
```

### Prometheus Metrics (✅ Implemented)

All modules expose metrics at `/metrics` endpoint:

```bash
# Check metrics for each module
curl http://localhost:8000/metrics  # Admin Module
curl http://localhost:8010/metrics  # Storage Element
curl http://localhost:8020/metrics  # Ingester Module
curl http://localhost:8030/metrics  # Query Module
```

**Standard Metrics**:
- `http_requests_total` - Total HTTP requests
- `http_request_duration_seconds` - HTTP request latency
- `http_request_size_bytes` - HTTP request size
- `http_response_size_bytes` - HTTP response size
- `process_cpu_seconds_total` - CPU time
- `process_resident_memory_bytes` - Memory usage

**Custom Business Metrics** (TODO: Sprint 15):
- File Operation Metrics: Upload/download latency, success rates, error types
- Search Performance: Query response time, result relevance, cache efficiency
- Storage Utilization: Disk usage, growth rates, capacity forecasting
- Authentication Metrics: JWT validation time, key rotation frequency, security events

### Grafana Dashboards (✅ Implemented)

Pre-configured dashboard: **ArtStore - System Overview**

Access: http://localhost:3000 → Dashboards → ArtStore → System Overview

**Panels**:
1. **Services Up**: Gauge showing number of healthy services
2. **HTTP Requests Rate**: Time series of requests per second by service
3. **HTTP Response Time**: p95 and p99 latency by service
4. **HTTP Error Rate**: 5xx error percentage by service

**Custom dashboards**: Add to `monitoring/grafana/dashboards/` directory for auto-loading.

### Alert Rules (✅ Implemented)

**Critical Alerts**:
- `ServiceDown`: Service unavailable for 2+ minutes
- `HighErrorRate`: Error rate >5% for 5 minutes
- `HighResponseTime`: p95 latency >500ms for 5 minutes

**Warning Alerts**:
- `HighCPUUsage`: CPU >80% for 10 minutes
- `HighMemoryUsage`: Memory >85% for 10 minutes
- `ConnectionPoolExhausted`: <10% available connections
- `LowDiskSpace`: Disk usage >80%

**Alert Configuration**: See `monitoring/prometheus/alerts.yml` and `monitoring/alertmanager/alertmanager.yml`

### Health Checks (Baseline)

All modules implement:
- `/health/live` - Liveness probe (is service running?)
- `/health/ready` - Readiness probe (can service handle traffic?)

### Structured Logging (Mandatory)

**Production Environment** (JSON format):
```yaml
environment:
  LOG_LEVEL: "INFO"
  LOG_FORMAT: "json"  # ОБЯЗАТЕЛЬНО для production
```

**Development Environment** (text format allowed):
```yaml
environment:
  LOG_LEVEL: "DEBUG"
  LOG_FORMAT: "text"  # Только для development
```

### Third-party Analytics Integration

- **Metrics Export**: Prometheus metrics compatible with Grafana, DataDog, New Relic
- **Log Aggregation**: JSON structured logs for ELK Stack, Splunk integration
- **Trace Data**: OpenTelemetry traces exportable to Jaeger, Zipkin
- **Custom Dashboards**: Grafana provisioning API для automated dashboard deployment

## Security Considerations

### Comprehensive Security Requirements

#### Encryption Standards
- **File Storage**: Файлы хранятся в незашифрованном виде для обеспечения совместимости и простоты backup процедур
- **TLS 1.3 transit encryption**: Все межсервисные соединения должны использовать TLS 1.3
- **Secure Key Management**: JWT ключи защищены и управляются через Admin Module Cluster
- **JWT Key Rotation**: Автоматическая ротация JWT ключей каждые 24 часа
- **Perfect Forward Secrecy**: Эфемерные ключи для каждой TLS сессии

#### Identity & Access Management
- **JWT tokens expire**: 30 minutes (access) / 7 days (refresh) с automatic refresh
- **Fine-grained RBAC**: Resource-level permissions обязательны для файловых операций
- **Temporary Access Tokens**: Поддержка time-limited tokens для external integrations
- **Multi-factor Authentication**: Обязательна для административных аккаунтов
- **Password Policy**: Минимум 12 символов, bcrypt hashing, rotation каждые 90 дней

#### API Security
- **Bearer token authentication**: Обязательна для всех API endpoints кроме health checks
- **API Rate Limiting**: Adaptive limiting с автоматической блокировкой при превышении
- **Request Signing**: Цифровая подпись критических операций (upload, delete, transfer)
- **IP Whitelisting**: Configurable ограничения по IP для административных операций
- **CORS Configuration**: Строгая политика Same-Origin с explicit domain whitelisting

#### Audit & Compliance
- **Comprehensive Audit Logging**: Все операции логируются с tamper-proof signatures
- **Real-time Monitoring**: Автоматическое обнаружение и alerting suspicious activities
- **Data Retention**: Audit logs хранятся minimum 7 лет с encrypted backup
- **Compliance Reporting**: Automated генерация GDPR, SOX, HIPAA compliance reports
- **Incident Response**: Automated isolation и notification при security breaches

#### Production Security Standards
- **System admin protection**: Cannot be deleted or demoted, требует dual approval
- **Secrets Management**: Все credentials в защищенной конфигурации с encryption at rest
- **Certificate Management**: Automated renewal и validation SSL/TLS certificates
- **Vulnerability Scanning**: Weekly automated scans с mandatory patching SLA
- **Penetration Testing**: Quarterly external security assessments обязательны