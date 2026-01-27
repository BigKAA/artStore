# Storage Element - Физическое хранилище файлов ArtStore

## Оглавление

- [Назначение модуля](#назначение-модуля)
- [Ключевые концепции](#ключевые-концепции)
- [Режимы работы Storage Element](#режимы-работы-storage-element)
- [Технологический стек](#технологический-стек)
- [API Endpoints](API.md)
- [Внутренняя архитектура](#внутренняя-архитектура)
- [Конфигурация](#конфигурация)
- [S3 Storage Requirements](#s3-storage-requirements)
- [Тестирование](#тестирование)
- [Health Reporting Service](#health-reporting-service-sprint-14)
- [Мониторинг и метрики](#мониторинг-и-метрики)
- [Troubleshooting](#troubleshooting)
- [Аутентификация и RBAC](#аутентификация-и-rbac)
- [Security Considerations](#security-considerations)
- [Интеграция с Admin Module](#интеграция-с-admin-module)
- [Cache Synchronization](#cache-synchronization-v120)
- [Migration Notes](#migration-notes-v110)
- [Ссылки на документацию](#ссылки-на-документацию)

---

## Назначение модуля

**Storage Element** — это модуль физического хранения файлов с кешированием метаданных, обеспечивающий:
- **Четыре режима работы**: edit (полный CRUD), rw (чтение-запись), ro (только чтение), ar (архив)
- **Attribute-first storage**: `*.attr.json` как единственный источник истины для метаданных
- **Write-Ahead Log (WAL)**: Атомарность всех файловых операций
- **Automatic Reconciliation**: Восстановление консистентности между attr.json и DB cache
- **Flexible storage backends**: Local filesystem или S3/MinIO

## Ключевые концепции

### Attribute-First Storage Model

**Критически важно**: Файлы атрибутов (`*.attr.json`) являются **единственным источником истины** для метаданных файлов.

**Почему это важно**:
- Backup элемента хранения = простое копирование файлов без dump БД
- Восстановление = копирование файлов обратно, database cache пересоздается автоматически
- Простота миграции между Storage Elements

**Протокол записи**:
```
1. Write-Ahead Log entry → журнал транзакций
2. Write attr.json (atomic rename) → источник истины
3. Update database cache → для производительности поиска
4. Publish to Service Discovery → уведомление других модулей
5. WAL commit → завершение транзакции
```

**Протокол чтения**:
```
Предпочтительный порядок:
1. Database cache (быстро, но может быть устаревшим)
2. Attr.json file (медленнее, но всегда актуально)
3. Automatic reconciliation при несоответствии
```

### File Naming Convention

**Format**: `{original_name}_{username}_{timestamp}_{uuid}.{ext}`

**Пример**: `report_ivanov_20250102T153045_a1b2c3d4-e5f6-7890-abcd-ef1234567890.pdf`

**Компоненты**:
- `original_name`: Оригинальное имя файла (обрезается до 200 символов)
- `username`: Имя пользователя загрузившего файл
- `timestamp`: ISO 8601 format (YYYYMMDDTHHMMSS)
- `uuid`: UUID4 для гарантии уникальности
- `ext`: Оригинальное расширение файла

**Преимущества**:
- Original filename первым → human-readable при сортировке
- Уникальность при одновременной загрузке файлов с одинаковыми именами
- Полное оригинальное имя сохранено в attr.json

### Directory Structure

**Pattern**: `/storage/{year}/{month}/{day}/{hour}/`

**Пример**:
```
.data/storage/
└── 2025/
    └── 01/
        └── 02/
            └── 15/
                ├── report_ivanov_20250102T153045_a1b2c3d4.pdf
                ├── report_ivanov_20250102T153045_a1b2c3d4.pdf.attr.json
                ├── document_petrov_20250102T154512_e5f6g7h8.docx
                └── document_petrov_20250102T154512_e5f6g7h8.docx.attr.json
```

**Преимущества**:
- Удобство резервного копирования по периодам (hourly, daily, monthly backups)
- Простая навигация по файлам
- Эффективное удаление старых данных
- Ограничение количества файлов в одной директории

### Attribute File Format (*.attr.json)

**Максимальный размер**: 4KB (гарантия атомарности записи filesystem)

**Обязательные поля**:
```json
{
  "file_id": "uuid",
  "original_filename": "Длинное оригинальное имя файла.pdf",
  "storage_filename": "report_ivanov_20250102T153045_a1b2c3d4.pdf",
  "size_bytes": 1048576,
  "mime_type": "application/pdf",
  "md5_hash": "d41d8cd98f00b204e9800998ecf8427e",
  "sha256_hash": "e3b0c44298fc1c149afbf4c8996fb924...",
  "uploaded_by": "ivanov",
  "uploaded_at": "2025-01-02T15:30:45Z",
  "retention_days": 365,
  "expires_at": "2026-01-02T15:30:45Z",
  "version": 1,
  "schema_version": "1.0"
}
```

**Опциональные поля (custom metadata)**:
```json
{
  "template": "contract",
  "department": "legal",
  "contract_number": "2025-001",
  "parties": ["Company A", "Company B"],
  "tags": ["urgent", "confidential"]
}
```

## Режимы работы Storage Element

### EDIT (Редактирование)

**Возможности**:
- ✅ Создание файлов (upload)
- ✅ Чтение файлов (download)
- ✅ Изменение метаданных
- ✅ Удаление файлов

**Использование**:
- Оперативное хранилище для документов в работе
- Staging area перед переносом в долгосрочное хранилище

**Конфигурация**:
```yaml
mode: edit
max_size: 107374182400  # 100 GB в байтах
retention_days: 90  # Автоматическая очистка через 90 дней
auto_cleanup: true
```

**Ограничения**:
- Невозможно изменить режим через API (fixed mode)
- Требует настроенного auto_cleanup для предотвращения переполнения

### RW (Read-Write, без удаления)

**Возможности**:
- ✅ Создание файлов (upload)
- ✅ Чтение файлов (download)
- ❌ Удаление файлов (запрещено)

**Использование**:
- Долгосрочное архивное хранилище с определенным сроком
- Защита от случайного удаления документов

**Lifecycle**:
```
RW (активное заполнение) → RW (заполнен, read-only фактически) → RO (explicit transition)
```

**Конфигурация**:
```yaml
mode: rw
max_size: 1099511627776  # 1 TB в байтах
retention_years: 5
fill_threshold_percent: 95  # Переход на другой RW элемент при 95% заполнении
```

**Переход в RO**: Изменить `STORAGE_MODE=ro` в конфигурации и перезапустить сервис.

### RO (Read-Only)

**Возможности**:
- ✅ Чтение файлов (download)
- ❌ Создание файлов
- ❌ Изменение метаданных
- ❌ Удаление файлов

**Использование**:
- Долгосрочное архивное хранение
- Полная защита от изменений

**Конфигурация**:
```yaml
mode: ro
retention_years: 10
```

**Переход в AR**: Изменить `STORAGE_MODE=ar` в конфигурации и перезапустить сервис.

### AR (Archive, холодное хранение)

**Возможности**:
- ✅ Чтение метаданных (из attr.json)
- ❌ Прямое чтение файлов (требуется восстановление)

**Использование**:
- Холодное хранение на съемных носителях (магнитные ленты, offline storage)
- Минимизация затрат на хранение редко используемых файлов

**Физическое хранение**:
- **Локально**: Только `*.attr.json` файлы (< 4KB каждый)
- **Offline**: Фактические файлы на магнитных лентах или внешних дисках

**Процесс восстановления**:
```
1. Запрос файла → 202 Accepted (queued for restoration)
2. Администратор восстанавливает файлы из ленты на Restore Storage Element (режим EDIT)
3. Webhook notification → пользователь уведомлен
4. Пользователь скачивает файл (TTL 30 дней)
5. Auto-cleanup через 30 дней
```

**Конфигурация**:
```yaml
mode: ar
retention_years: 70
restore_storage_element_id: "uuid"  # Куда восстанавливать файлы
restore_ttl_days: 30
```

## Технологический стек

### Backend Framework
- **Python 3.12+** с async/await
- **FastAPI** для REST API
- **Uvicorn** с uvloop
- **Pydantic** для валидации

### Storage Backends

#### Local Filesystem
- **aiofiles** для async file I/O
- **Directory structure**: `/year/month/day/hour/`
- **Atomic operations**: Temporary file → fsync → atomic rename

#### S3/MinIO
- **aioboto3** для async S3 operations
- **Bucket structure**: Аналогичная директорной структуре
- **Multipart uploads**: Для файлов > 100MB

### Database
- **PostgreSQL 15+** (asyncpg) для кеша метаданных
- **Alembic** для миграций
- **GIN indexes** для full-text search по метаданным

### Write-Ahead Log
- **Custom WAL implementation** в PostgreSQL
- **Transaction log table**: Все операции логируются до выполнения
- **Automatic cleanup**: Старые WAL записи удаляются после commit

### Observability
- **OpenTelemetry** для tracing
- **Prometheus client** для метрик
- **Structured logging** (JSON)

## API Endpoints

Полное описание API см. в **[API.md](API.md)**.

**Краткий обзор доступных endpoints**:

| Группа | Prefix | Описание |
|--------|--------|----------|
| File Operations | `/api/v1/files/*` | Upload, download, metadata, delete |
| System Info | `/api/v1/info` | Auto-discovery информация |
| Capacity | `/api/v1/capacity` | Информация о ёмкости |
| Garbage Collector | `/api/v1/gc/*` | Системное удаление файлов |
| Cache Management | `/api/v1/cache/*` | Управление кешем метаданных |
| Health | `/health/*` | Liveness и readiness probes |
| Metrics | `/metrics` | Prometheus метрики |

**ВАЖНО**: Mode определяется ТОЛЬКО конфигурацией storage element при запуске.
Admin Module использует endpoint `/api/v1/info` для получения актуальной информации,
но НЕ МОЖЕТ изменять mode через API.

## Внутренняя архитектура

```
storage-element/
├── app/
│   ├── main.py                    # FastAPI entry point
│   ├── core/
│   │   ├── config.py              # Configuration
│   │   ├── security.py            # JWT validation
│   │   └── exceptions.py
│   ├── api/
│   │   └── v1/
│   │       └── endpoints/
│   │           ├── files.py       # File operations
│   │           ├── admin.py       # Admin operations
│   │           ├── info.py        # System info for auto-discovery
│   │           └── health.py
│   ├── models/
│   │   ├── file.py                # File metadata (cache)
│   │   └── wal_entry.py           # WAL transaction log
│   ├── schemas/
│   │   ├── file.py                # File schemas
│   │   └── admin.py
│   ├── services/
│   │   ├── file_service.py        # File business logic
│   │   ├── storage_service.py     # Local FS / S3 abstraction
│   │   ├── wal_service.py         # Write-Ahead Log
│   │   ├── cache_service.py       # DB cache management
│   │   ├── reconcile_service.py   # Reconciliation между attr.json и DB
│   │   └── master_election.py     # Redis-based master election
│   ├── db/
│   │   ├── session.py
│   │   └── base.py
│   └── utils/
│       ├── file_utils.py          # File utilities
│       ├── attr_utils.py          # Attr.json helpers
│       └── metrics.py
├── tests/
│   ├── unit/
│   └── integration/
├── Dockerfile
├── requirements.txt
└── .env.example
```

## Конфигурация

### Environment Variables

#### Application Settings

```bash
# Application Configuration
APP_DEBUG=false              # Debug режим (дополнительное логирование)
APP_SWAGGER_ENABLED=false    # Swagger UI и ReDoc документация
```

**Swagger/OpenAPI Documentation**:
- `APP_SWAGGER_ENABLED=true` - включает Swagger UI (`/docs`) и ReDoc (`/redoc`)
- **Production**: По умолчанию выключено для безопасности
- **Development**: Рекомендуется включить для удобства разработки
- Независим от `APP_DEBUG` режима

```bash
# Storage Configuration
STORAGE_MODE=rw           # edit, rw, ro, ar - ВАЖНО: определяется ТОЛЬКО здесь, не через API
STORAGE_TYPE=local        # local или s3
DISPLAY_NAME="Storage Element 01"  # Читаемое название для UI (используется при auto-discovery)

# Максимальный размер хранилища (единый параметр для local и s3)
# Значение в БАЙТАХ:
#   1 GB  = 1073741824
#   10 GB = 10737418240
#   100 GB = 107374182400
#   1 TB  = 1099511627776
#   10 TB = 10995116277760
STORAGE_MAX_SIZE=1099511627776  # 1TB

STORAGE_RETENTION_DAYS=1825  # 5 лет

# Local Filesystem
STORAGE_LOCAL_BASE_PATH=./.data/storage

# S3/MinIO
STORAGE_S3_ENDPOINT_URL=http://localhost:9000
STORAGE_S3_BUCKET_NAME=artstore-files
STORAGE_S3_ACCESS_KEY_ID=minioadmin
STORAGE_S3_SECRET_ACCESS_KEY=minioadmin

# Database
DATABASE_URL=postgresql+asyncpg://artstore:password@localhost:5432/artstore
DB_TABLE_PREFIX=storage_elem_01  # Для уникальности в shared DB

# PostgreSQL SSL (опционально, для production)
DB_SSL_ENABLED=false                    # Включить SSL для PostgreSQL
DB_SSL_MODE=require                     # SSL режим: disable, require, verify-ca, verify-full
# DB_SSL_CA_CERT=/app/ssl-certs/ca-cert.pem      # CA certificate (для verify-ca/verify-full)
# DB_SSL_CLIENT_CERT=/app/ssl-certs/client-cert.pem  # Client certificate (опционально)
# DB_SSL_CLIENT_KEY=/app/ssl-certs/client-key.pem    # Client key (опционально)

# WAL Configuration
WAL_ENABLED=true
WAL_RETENTION_HOURS=24

# Redis (для master election в edit/rw режимах)
REDIS_URL=redis://localhost:6379/0
REDIS_MASTER_ELECTION_ENABLED=false  # true для edit/rw clusters

# Health Reporting (Sprint 14)
STORAGE_ELEMENT_ID=se-01              # Уникальный ID для registry
STORAGE_EXTERNAL_ENDPOINT=http://localhost:8010  # URL для Ingester Module
STORAGE_PRIORITY=1                    # Priority для Sequential Fill (lower = higher priority)
STORAGE_HEALTH_REPORT_INTERVAL=30     # Секунд между reports
STORAGE_HEALTH_REPORT_TTL=90          # TTL для Redis ключей (interval * 3)

# Reconciliation
RECONCILE_SCHEDULE_HOURS=24
RECONCILE_AUTO_FIX=true

# AR Mode Restore
AR_RESTORE_STORAGE_ELEMENT_ID=  # UUID Restore Storage Element
AR_RESTORE_TTL_DAYS=30
```

## S3 Storage Requirements

При использовании S3-совместимого хранилища (MinIO, AWS S3) требуется выполнение следующих условий:

### Bucket Configuration

1. **Bucket должен существовать**: Сервис **НЕ создает** bucket автоматически
   - Имя задается через `STORAGE_S3_BUCKET_NAME` (по умолчанию: `artstore-files`)
   - Администратор должен создать bucket **перед запуском** сервиса

2. **App Folder**: Директория внутри bucket для данного Storage Element
   - Имя задается через `STORAGE_S3_APP_FOLDER` (по умолчанию: `storage_element_01`)
   - Сервис **попытается создать** директорию при старте (placeholder `.keep`)
   - Если создание не удалось - логируется ошибка, readiness возвращает 503

### Health Check поведение

**При старте приложения (lifespan)**:
- Проверяется существование bucket
- Проверяется/создается app_folder
- Ошибки логируются, но **НЕ блокируют запуск** (graceful degradation)
- Readiness probe будет возвращать 503 до исправления проблемы

**Readiness Probe (`/health/ready`)**:

| Состояние | HTTP Code | Response |
|-----------|-----------|----------|
| Bucket недоступен | 503 | `{"status": "not_ready", "s3_error": "S3 bucket 'X' is not accessible at 'Y'"}` |
| App folder недоступен | 503 | `{"status": "not_ready", "s3_error": "Directory 'X' in bucket 'Y' is not accessible..."}` |
| Всё OK | 200 | `{"status": "ready", "s3_bucket": "accessible", "s3_app_folder": "accessible"}` |

### Пример успешного ответа Readiness

```json
{
  "status": "ready",
  "timestamp": "2025-11-30T12:00:00.000000+00:00",
  "checks": {
    "s3_bucket": "accessible",
    "s3_app_folder": "accessible",
    "s3_endpoint": "http://localhost:9000",
    "s3_bucket_name": "artstore-files",
    "s3_app_folder_name": "storage_element_01",
    "storage_type": "s3",
    "storage_mode": "rw"
  }
}
```

### Пример ответа при недоступном bucket

```json
{
  "status": "not_ready",
  "timestamp": "2025-11-30T12:00:00.000000+00:00",
  "checks": {
    "s3_bucket": "not_accessible",
    "s3_app_folder": "not_accessible",
    "s3_error": "S3 bucket 'artstore-files' is not accessible at 'http://localhost:9000'",
    "s3_endpoint": "http://localhost:9000",
    "s3_bucket_name": "artstore-files",
    "s3_app_folder_name": "storage_element_01",
    "storage_type": "s3",
    "storage_mode": "rw"
  }
}
```

### Troubleshooting S3

**Bucket недоступен**:
```bash
# Создать bucket в MinIO CLI (mc)
mc mb myminio/artstore-files

# Или через AWS CLI
aws --endpoint-url http://localhost:9000 s3 mb s3://artstore-files

# Проверить доступность
aws --endpoint-url http://localhost:9000 s3 ls
```

**App folder недоступен**:
```bash
# Создать директорию через MinIO CLI
mc cp /dev/null myminio/artstore-files/storage_element_01/.keep

# Или через AWS CLI
aws --endpoint-url http://localhost:9000 s3api put-object \
    --bucket artstore-files \
    --key storage_element_01/.keep \
    --body /dev/null
```

**Проверка прав доступа**:
```bash
# Убедиться что access key имеет права на bucket
mc admin user info myminio minioadmin

# Или проверить policy
mc admin policy info myminio readwrite
```

## Тестирование

### Unit Tests

```bash
# Тестирование бизнес-логики
pytest storage-element/tests/unit/ -v

# Покрытие
pytest storage-element/tests/unit/ --cov=app --cov-report=html
```

### Integration Tests

```bash
# Полный тестовый цикл с реальными зависимостями
pytest storage-element/tests/integration/ -v

# Docker-based (рекомендуется)
docker-compose -f docker-compose.test.yml up --abort-on-container-exit storage-element-test
```

### Тестовые сценарии

- **Upload flow**: WAL → attr.json → DB cache → verification
- **Download flow**: Cache hit → DB lookup → attr.json fallback
- **Reconciliation**: Detect conflicts → auto-fix → audit log
- **Mode transition**: rw → ro с Two-Phase Commit
- **AR restore**: Queue request → webhook notification → TTL cleanup

## Health Reporting Service (Sprint 14)

### HealthReporter (`app/services/health_reporter.py`)

Сервис периодической публикации статуса Storage Element в Redis Registry для Sequential Fill алгоритма Ingester Module.

#### Архитектура

```
┌─────────────────────────────────────────────────────────────────┐
│                    Health Reporting Flow                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Storage Element                     Redis Registry            │
│   ┌─────────────┐                    ┌─────────────┐            │
│   │ SE #1       │ ──────────────────►│ Hash        │            │
│   │             │   Every 30 sec     │ storage:    │            │
│   │ Capacity:   │   (configurable)   │ elements:   │            │
│   │  - total    │                    │ {se_id}     │            │
│   │  - used     │                    │             │            │
│   │  - free     │                    │ TTL: 90s    │            │
│   │  - status   │                    └─────────────┘            │
│   │             │                                                │
│   │ Health:     │                    ┌─────────────┐            │
│   │  - healthy  │ ──────────────────►│ Sorted Set  │            │
│   │             │   ZADD/ZREM        │ storage:    │            │
│   └─────────────┘                    │ {mode}:     │            │
│                                      │ by_priority │            │
│                                      └─────────────┘            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

#### Redis Schema

| Key Pattern | Type | Description |
|-------------|------|-------------|
| `storage:elements:{se_id}` | Hash | Полные метаданные SE (TTL = report_ttl) |
| `storage:{mode}:by_priority` | Sorted Set | SE IDs отсортированные по priority |

#### Hash Fields (`storage:elements:{se_id}`)

```redis
HGETALL storage:elements:se-01
{
  "id": "se-01",
  "mode": "rw",
  "capacity_total": "1099511627776",      # 1TB в байтах
  "capacity_used": "549755813888",         # 512GB
  "capacity_free": "549755813888",         # 512GB
  "capacity_percent": "50.00",
  "endpoint": "http://storage-01:8010",
  "priority": "1",
  "last_updated": "2025-01-02T15:30:45+00:00",
  "health_status": "healthy",
  "capacity_status": "ok",                  # ok, warning, critical, full
  "threshold_warning": "85.00",
  "threshold_critical": "92.00",
  "threshold_full": "98.00"
}
```

#### Adaptive Capacity Thresholds

Пороги рассчитываются динамически на основе размера SE:

```python
def calculate_adaptive_threshold(total_capacity_bytes: int, mode: str) -> dict:
    total_gb = total_capacity_bytes / (1024**3)

    if mode == "rw":
        warning_free_gb = max(total_gb * 0.15, 150)   # 15% или 150GB
        critical_free_gb = max(total_gb * 0.08, 80)   # 8% или 80GB
        full_free_gb = max(total_gb * 0.02, 20)       # 2% или 20GB
    elif mode == "edit":
        warning_free_gb = max(total_gb * 0.10, 100)   # 10% или 100GB
        critical_free_gb = max(total_gb * 0.05, 50)   # 5% или 50GB
        full_free_gb = max(total_gb * 0.01, 10)       # 1% или 10GB
```

**Примеры для RW Storage:**

| SE Size | Warning | Critical | Full | Waste |
|---------|---------|----------|------|-------|
| 1TB | 85% | 92% | 98% | 2% |
| 10TB | 98.5% | 99.2% | 99.8% | 0.2% |
| 100TB | 98.5% | 99.2% | 99.8% | 0.2% |

#### Capacity Status Levels

| Status | Description | Action |
|--------|-------------|--------|
| `OK` | Нормальная работа | Приём файлов продолжается |
| `WARNING` | Приближение к порогу | Alert админам, приём продолжается |
| `CRITICAL` | Срочное предупреждение | Urgent alert, приём продолжается |
| `FULL` | SE заполнен | SE удаляется из Sorted Set, переключение на другой SE |

#### Graceful Shutdown Behavior

При shutdown SE автоматически удаляется из Redis:
1. Удаляет Hash `storage:elements:{se_id}`
2. Удаляет из Sorted Set `storage:rw:by_priority`
3. Удаляет из Sorted Set `storage:edit:by_priority`

#### Circuit Breaker Integration

- При недоступности Redis используется Circuit Breaker
- Report пропускается если circuit открыт
- Автоматический recovery при восстановлении Redis

#### Configuration

```bash
STORAGE_ELEMENT_ID=se-01              # Уникальный ID в registry
STORAGE_EXTERNAL_ENDPOINT=http://localhost:8010  # URL для API calls
STORAGE_PRIORITY=1                    # Sequential Fill priority (lower = higher)
STORAGE_HEALTH_REPORT_INTERVAL=30     # Секунд между reports
STORAGE_HEALTH_REPORT_TTL=90          # TTL для Redis ключей
```

#### Prometheus Metrics (Sprint 14)

| Metric | Labels | Description |
|--------|--------|-------------|
| `storage_capacity_total_bytes` | element_id, mode | Общая ёмкость |
| `storage_capacity_used_bytes` | element_id, mode | Использовано |
| `storage_capacity_free_bytes` | element_id, mode | Свободно |
| `storage_capacity_percent` | element_id, mode | Процент использования |
| `storage_capacity_status` | element_id, status | Текущий статус (0=ok,1=warning,2=critical,3=full) |
| `storage_redis_publish_total` | element_id, status | Количество publishes в Redis |
| `storage_redis_publish_duration_seconds` | element_id | Время публикации |

#### Usage

```python
# Инициализация при startup
from app.services.health_reporter import init_health_reporter

health_reporter = await init_health_reporter(redis_client)

# Shutdown
await stop_health_reporter()
```

## Мониторинг и метрики

### Prometheus Metrics (`/metrics`)

#### Custom Business Metrics
- `artstore_storage_files_total`: Количество файлов по mode
- `artstore_storage_size_bytes`: Размер хранилища в байтах
- `artstore_storage_used_percent`: Процент заполнения
- `artstore_file_upload_duration_seconds`: Latency загрузки файлов
- `artstore_file_download_duration_seconds`: Latency скачивания файлов
- `artstore_reconciliation_conflicts_total`: Количество конфликтов
- `artstore_wal_entries_total`: WAL записи (pending/committed/rolled_back)
- `artstore_attr_file_size_bytes`: Размер attr.json файлов (histogram)

### OpenTelemetry Tracing

Все операции трассируются:
- `artstore.storage.upload` - Полный цикл загрузки файла
- `artstore.storage.download` - Скачивание файла
- `artstore.storage.reconcile` - Процесс reconciliation
- `artstore.storage.wal` - WAL операции

## Troubleshooting

### Проблемы с консистентностью

**Проблема**: DB cache не соответствует attr.json
**Решение**: Использовать Cache Management API:
1. `GET /api/v1/cache/consistency` - проверить расхождения
2. `POST /api/v1/cache/rebuild/incremental` - добавить недостающие записи
3. `POST /api/v1/cache/rebuild` - полная пересборка (при критических расхождениях)

**Проблема**: WAL entries stuck in pending state
**Решение**: Проверить логи на ошибки filesystem. Перезапустить storage element для auto-recovery.

### Проблемы с производительностью

**Проблема**: Медленная загрузка файлов
**Решение**: Проверить disk I/O performance. Для S3 проверить network latency и S3 endpoint accessibility.

**Проблема**: DB cache queries slow
**Решение**: Проверить наличие GIN indexes. Увеличить DB connection pool если нужно.

### Проблемы с disk space

**Проблема**: Disk full
**Решение**:
1. Проверить `auto_cleanup` settings для edit режима
2. Перенести старые файлы на другой Storage Element (rw → ro)
3. Перевести ro элементы в ar режим

## Аутентификация и RBAC

### JWT RS256 Authentication

Storage Element использует **JWT токены с RS256** для distributed authentication:
- **Публичный ключ** загружается из Admin Module
- **Autonomous validation** - проверка токенов без обращения к Admin Module
- **Bearer token** обязателен для всех protected API endpoints

**JWT Token Payload**:
```json
{
  "sub": "user_id_123",
  "username": "ivanov",
  "roles": ["user", "operator"],
  "exp": 1735777200,
  "iat": 1735775400
}
```

### Роли и Разрешения (RBAC)

| Роль | Описание | File Operations | Admin Operations |
|------|----------|-----------------|------------------|
| **ADMIN** | Полный доступ | create, read, update, delete | Все |
| **OPERATOR** | Управление storage | read | Mode transitions, storage admin |
| **USER** | Стандартный пользователь | create, read, update, delete | - |
| **READONLY** | Только чтение | read | - |

**Матрица разрешений**:

| Permission | ADMIN | OPERATOR | USER | READONLY |
|-----------|-------|----------|------|----------|
| `file:create` | ✅ | ❌ | ✅ | ❌ |
| `file:read` | ✅ | ✅ | ✅ | ✅ |
| `file:update` | ✅ | ❌ | ✅ | ❌ |
| `file:delete` | ✅ | ❌ | ✅ | ❌ |
| `mode:transition` | ✅ | ✅ | ❌ | ❌ |
| `admin:storage` | ✅ | ✅ | ❌ | ❌ |

### Конфигурация

```bash
# JWT public key для валидации токенов
AUTH__JWT_PUBLIC_KEY_PATH=./keys/public_key.pem
AUTH__JWT_ALGORITHM=RS256
```

**Важно**: В production публичный ключ получается из Admin Module автоматически.

## Security Considerations

### Production Checklist

- [ ] TLS 1.3 для всех соединений
- [ ] JWT validation на всех endpoints
- [ ] File upload size limits настроены
- [ ] Virus scanning интеграция (ClamAV или аналог)
- [ ] Access control на filesystem level (strict permissions)
- [ ] Audit logging всех file operations
- [ ] Regular reconciliation schedule (каждые 24 часа)
- [ ] WAL retention и cleanup настроены
- [ ] Disk space monitoring и alerting

### Best Practices

1. **Никогда не удаляйте** attr.json без удаления файла
2. **Никогда не редактируйте** attr.json вручную, только через API
3. **Backup strategy**: Копируйте директории storage целиком, не только БД
4. **Reconciliation**: Запускайте регулярно для обнаружения drift
5. **Mode transitions**: Тестируйте на staging перед production

## Интеграция с Admin Module

### Автоматическая синхронизация состояния

Admin Module периодически опрашивает все зарегистрированные Storage Elements для синхронизации информации о текущем состоянии. Это обеспечивает актуальность данных в системе без необходимости ручного обновления.

#### Механизм синхронизации

1. **Periodic Health Check**: Admin Module выполняет запрос к `/api/v1/info` каждого Storage Element
2. **Сравнение состояния**: Полученные данные сравниваются с информацией в базе данных
3. **Автоматическое обновление**: При обнаружении изменений данные обновляются в PostgreSQL
4. **Service Discovery**: Изменения публикуются в Redis для уведомления других модулей (Ingester, Query)

#### Синхронизируемые поля

| Поле | Описание | Источник |
|------|----------|----------|
| `mode` | Текущий режим работы (edit/rw/ro/ar) | `/api/v1/info` → `mode` |
| `status` | Статус (operational/degraded/offline) | `/api/v1/info` → `status` |
| `capacity_bytes` | Общая емкость хранилища | `/api/v1/info` → `capacity_bytes` |
| `used_bytes` | Использованное пространство | `/api/v1/info` → `used_bytes` |
| `file_count` | Количество файлов | `/api/v1/info` → `file_count` |

#### Конфигурация в Admin Module

```bash
# Включить/выключить периодическую проверку
SCHEDULER_STORAGE_HEALTH_CHECK_ENABLED=true

# Интервал проверки в секундах (10-3600, по умолчанию 60)
SCHEDULER_STORAGE_HEALTH_CHECK_INTERVAL_SECONDS=60
```

#### Поведение при изменении режима

**Важно**: Режим Storage Element (`mode`) определяется **ТОЛЬКО** конфигурацией при запуске модуля (переменная `STORAGE_MODE` или `APP_MODE`).

Admin Module **НЕ МОЖЕТ** изменить режим через API, но отслеживает его изменение:

```
Сценарий: Администратор переводит Storage Element из RW в RO

1. Администратор изменяет конфигурацию: APP_MODE=ro
2. Администратор перезапускает контейнер Storage Element
3. Storage Element стартует в режиме RO
4. Admin Module при очередном health check обнаруживает mode=ro
5. Admin Module обновляет информацию в БД
6. Admin Module публикует изменения в Redis
7. Ingester получает уведомление и перестает направлять uploads на этот элемент
8. Query получает уведомление и продолжает использовать элемент для downloads
```

#### Обнаружение недоступных элементов

Если Storage Element недоступен (сеть, рестарт, сбой):

1. Health check завершается с ошибкой (timeout/connection refused)
2. Admin Module устанавливает `status = offline`
3. Изменение публикуется в Redis
4. Ingester/Query прекращают использование этого элемента
5. При восстановлении доступности статус автоматически обновляется на `operational`

#### Логирование событий синхронизации

Admin Module логирует важные события:

```
INFO  - Storage health check completed: 5 synced, 0 failed, 2 changes detected
INFO  - Storage element 'storage-01' mode changed: rw -> ro
WARN  - Storage element 'storage-02' is offline (connection refused)
INFO  - Storage element 'storage-02' is back online
```

### Удаление Storage Element

Storage Element можно удалить из Admin Module при соблюдении условий:

1. **Требование**: `file_count == 0` (элемент пуст)
2. **Требование роли**: SUPER_ADMIN
3. **Режим**: Любой (edit, rw, ro, ar) - ограничение по режиму отсутствует

**Важно**: Удаление из Admin Module не удаляет сам сервис Storage Element, а только его регистрацию в системе. Физически сервис продолжит работу до остановки администратором.

### Admin UI Auto-Refresh

Веб-интерфейс Admin UI автоматически обновляет список Storage Elements:

- **Интервал**: 60 секунд (по умолчанию)
- **Управление**: Переключатель "Auto-refresh" в заголовке страницы
- **Поведение**: При отключении обновление происходит только при ручном нажатии "Sync All"

## Cache Synchronization (v1.2.0)

### Hybrid Cache Synchronization Overview

Начиная с версии 1.2.0, Storage Element поддерживает **автоматическую синхронизацию** PostgreSQL кеша с `*.attr.json` файлами через:

- **TTL-based Lazy Rebuild**: Автоматическая пересборка expired cache entries при запросах
- **Manual Rebuild APIs**: Явные endpoint'ы для администратора (full/incremental rebuild)
- **Consistency Check**: Dry-run проверка расхождений между cache и attr.json
- **Priority-Based Locking**: Ручные операции блокируют автоматические

**Зачем нужна синхронизация?**

- **Восстановление после сбоев**: Если database cache был утерян или повреждён
- **Миграция данных**: При переносе файлов между Storage Elements
- **Обнаружение orphans**: Файлы в cache без attr.json или наоборот
- **Expired cache cleanup**: Удаление устаревших cache entries

### Cache TTL Configuration

Каждая запись в cache имеет **TTL (Time-To-Live)**, после которого требуется обновление из attr.json.

**TTL по режимам Storage Element:**

| Режим | TTL | Обоснование |
|-------|-----|-------------|
| `edit` | 24 часа | Частые изменения файлов |
| `rw` | 24 часа | Активная запись файлов |
| `ro` | 168 часов (7 дней) | Редкие изменения |
| `ar` | 168 часов (7 дней) | Архивное хранение |

**Переменные окружения:**

```bash
# Управление TTL через env variables (опционально)
CACHE_TTL_HOURS_EDIT=24
CACHE_TTL_HOURS_RW=24
CACHE_TTL_HOURS_RO=168
CACHE_TTL_HOURS_AR=168
```

### Lazy Rebuild (Автоматический режим)

**Когда срабатывает:**
- При `GET /api/v1/files/{file_id}` запросе метаданных
- Если `cache_expired = True` (cache_updated_at + cache_ttl_hours < now)

**Поведение:**
```python
# 1. Проверка TTL
if metadata.cache_expired:
    # 2. Try to rebuild from attr.json (non-blocking)
    try:
        await _rebuild_entry_from_attr(file_id)
    except Exception:
        # 3. Graceful degradation: вернуть stale cache
        return metadata  # Stale but still usable

# 4. Вернуть свежий cache
return metadata
```

**Важно**: Lazy rebuild использует **низкоприоритетный lock** и пропускается если идёт Manual Rebuild.

### Manual Cache Rebuild APIs

#### 1. Full Rebuild (Полная пересборка)

**Endpoint**: `POST /api/v1/cache/rebuild`

**Описание**: TRUNCATE cache таблицы и полная пересборка из всех attr.json файлов.

**Когда использовать:**
- После восстановления из backup
- При критическом расхождении cache и attr.json
- После миграции данных

**Пример запроса:**

```bash
# Получить токен
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"client_id":"admin-service","client_secret":"YourSecret"}' \
  | jq -r '.access_token')

# Full rebuild
curl -X POST http://localhost:8010/api/v1/cache/rebuild \
  -H "Authorization: Bearer $TOKEN"
```

**Response:**

```json
{
  "operation_type": "full",
  "started_at": "2026-01-10T18:00:00Z",
  "completed_at": "2026-01-10T18:05:30Z",
  "duration_seconds": 330.5,
  "statistics": {
    "attr_files_scanned": 10000,
    "cache_entries_before": 9500,
    "cache_entries_after": 10000,
    "entries_created": 10000,
    "entries_updated": 0,
    "entries_deleted": 0
  },
  "errors": []
}
```

#### 2. Incremental Rebuild (Инкрементальная пересборка)

**Endpoint**: `POST /api/v1/cache/rebuild/incremental`

**Описание**: Добавляет только отсутствующие в cache attr.json файлы. НЕ удаляет orphan cache entries.

**Когда использовать:**
- После добавления новых файлов через filesystem (обход API)
- Для периодической синхронизации без full rebuild

**Пример запроса:**

```bash
curl -X POST http://localhost:8010/api/v1/cache/rebuild/incremental \
  -H "Authorization: Bearer $TOKEN"
```

**Response:**

```json
{
  "operation_type": "incremental",
  "statistics": {
    "attr_files_scanned": 10000,
    "cache_entries_before": 9500,
    "cache_entries_after": 10000,
    "entries_created": 500,
    "entries_updated": 0
  }
}
```

#### 3. Consistency Check (Проверка консистентности)

**Endpoint**: `GET /api/v1/cache/consistency`

**Описание**: Dry-run проверка расхождений между cache и attr.json (НЕ изменяет данные).

**Пример запроса:**

```bash
curl -X GET http://localhost:8010/api/v1/cache/consistency \
  -H "Authorization: Bearer $TOKEN"
```

**Response:**

```json
{
  "total_attr_files": 10000,
  "total_cache_entries": 9980,
  "orphan_cache_count": 5,
  "orphan_attr_count": 25,
  "expired_cache_count": 150,
  "is_consistent": false,
  "inconsistency_percentage": 0.3,
  "details": {
    "orphan_cache_entries": ["file-id-1", "file-id-2"],
    "orphan_attr_files": ["file-id-3", "file-id-4"],
    "expired_cache_entries": ["file-id-5"]
  }
}
```

**Интерпретация:**
- `orphan_cache_entries`: Записи в cache без соответствующих attr.json (удалить?)
- `orphan_attr_files`: Attr.json файлы без записей в cache (добавить?)
- `expired_cache_entries`: Cache entries с истёкшим TTL (обновить?)

#### 4. Cleanup Expired Entries (Очистка expired)

**Endpoint**: `POST /api/v1/cache/cleanup-expired`

**Описание**: Удаляет cache entries с истёкшим TTL.

**Когда использовать:**
- Для освобождения места в БД
- Периодическая cleanup задача (опционально)

**Пример запроса:**

```bash
curl -X POST http://localhost:8010/api/v1/cache/cleanup-expired \
  -H "Authorization: Bearer $TOKEN"
```

**Response:**

```json
{
  "operation_type": "cleanup_expired",
  "statistics": {
    "entries_deleted": 150
  },
  "duration_seconds": 2.5
}
```

### Priority-Based Locking

Система использует **Redis distributed locks** для координации операций синхронизации.

**Приоритеты операций** (от высшего к низшему):

1. **MANUAL_REBUILD** (Priority 1) - API-triggered full/incremental rebuild
2. **MANUAL_CHECK** (Priority 2) - API-triggered consistency check
3. **LAZY_REBUILD** (Priority 3) - On-demand expired entry rebuild
4. **BACKGROUND_CLEANUP** (Priority 4) - Optional cleanup job

**Правила блокировок:**
- MANUAL_REBUILD блокирует все остальные операции
- LAZY_REBUILD пропускается если идёт MANUAL_REBUILD (graceful degradation)
- При конфликте низкоприоритетная операция ждёт или пропускается

**Пример конфликта:**

```bash
# Terminal 1: Start manual rebuild (занимает lock на 30 минут)
curl -X POST http://localhost:8010/api/v1/cache/rebuild \
  -H "Authorization: Bearer $TOKEN"

# Terminal 2: Try to start incremental rebuild
curl -X POST http://localhost:8010/api/v1/cache/rebuild/incremental \
  -H "Authorization: Bearer $TOKEN"

# Response: HTTP 409 Conflict
{
  "detail": "Cannot acquire lock: rebuild already in progress"
}
```

### Storage Backend Abstraction

Cache synchronization работает с двумя типами storage backends:

**Local Filesystem:**
```bash
STORAGE_TYPE=local
STORAGE_LOCAL_BASE_PATH=/data/storage
```

**S3/MinIO:**
```bash
STORAGE_TYPE=s3
STORAGE_S3_ENDPOINT_URL=http://minio:9000
STORAGE_S3_BUCKET_NAME=artstore
STORAGE_S3_APP_FOLDER=storage-elem-01
```

Система автоматически определяет backend через `settings.storage.type` и использует соответствующий драйвер для чтения attr.json.

### Best Practices

**Production рекомендации:**

1. **Периодическая consistency check** (раз в неделю):
   ```bash
   # Cron job: каждый понедельник в 02:00
   0 2 * * 1 curl -X GET http://localhost:8010/api/v1/cache/consistency \
     -H "Authorization: Bearer $TOKEN" | mail -s "Cache Consistency Report" admin@example.com
   ```

2. **Incremental rebuild** после добавления файлов вручную:
   ```bash
   # После копирования attr.json через filesystem
   curl -X POST http://localhost:8010/api/v1/cache/rebuild/incremental \
     -H "Authorization: Bearer $TOKEN"
   ```

3. **Full rebuild** только в исключительных случаях:
   - Восстановление из backup
   - Критическое расхождение (>10% orphans)
   - После миграции данных

4. **Cleanup expired entries** (опционально):
   ```bash
   # Cron job: каждый день в 03:00
   0 3 * * * curl -X POST http://localhost:8010/api/v1/cache/cleanup-expired \
     -H "Authorization: Bearer $TOKEN"
   ```

**Development рекомендации:**

- Используйте `GET /api/v1/cache/consistency` перед manual rebuild
- Тестируйте lazy rebuild через expired entries
- Проверяйте logs на наличие cache rebuild warnings

### Troubleshooting

**Проблема**: Cache entries устаревают быстрее чем TTL

**Решение**: Проверить настройки TTL для текущего режима Storage Element:

```python
# Проверка в logs
logger.info(f"Cache TTL: {metadata.cache_ttl_hours} hours for mode {settings.app.mode}")
```

**Проблема**: Manual rebuild timeout (>30 минут)

**Решение**: Для больших хранилищ (>100K файлов) увеличить timeout в коде:

```python
# app/api/v1/endpoints/cache.py
result = await service.rebuild_cache_full()  # Default timeout: 1800s (30 min)
```

**Проблема**: Orphan attr files обнаружены

**Решение**: Проверить доступность attr.json файлов и запустить incremental rebuild:

```bash
# 1. Check consistency
curl -X GET http://localhost:8010/api/v1/cache/consistency -H "Authorization: Bearer $TOKEN"

# 2. Incremental rebuild для добавления orphan attr files
curl -X POST http://localhost:8010/api/v1/cache/rebuild/incremental -H "Authorization: Bearer $TOKEN"
```

## Migration Notes (v1.1.0)

### STORAGE_MAX_SIZE унификация

В версии 1.1.0 унифицированы параметры размера хранилища в единый `STORAGE_MAX_SIZE`.

#### Что изменилось

| Старый параметр | Новый параметр | Единицы |
|-----------------|----------------|---------|
| `STORAGE_MAX_SIZE_GB` | `STORAGE_MAX_SIZE` | Байты |
| `STORAGE_S3_SOFT_CAPACITY_LIMIT` | `STORAGE_MAX_SIZE` | Байты |

#### Автоматическая миграция

Система автоматически мигрирует legacy параметры с deprecation warning в логах:
- `STORAGE_MAX_SIZE_GB=5` → `STORAGE_MAX_SIZE=5368709120` (5GB в байтах)
- `STORAGE_S3_SOFT_CAPACITY_LIMIT=10995116277760` → `STORAGE_MAX_SIZE=10995116277760`

#### Конвертация единиц

```python
# GB → Bytes
1 GB = 1 * 1024 * 1024 * 1024 = 1073741824 bytes

# TB → Bytes
1 TB = 1 * 1024 * 1024 * 1024 * 1024 = 1099511627776 bytes
```

#### Действия для миграции

1. **Development окружение** (`.env`):
   ```bash
   # Было:
   STORAGE_MAX_SIZE_GB=1

   # Стало:
   STORAGE_MAX_SIZE=1073741824  # 1GB
   ```

2. **Docker Compose**:
   ```yaml
   environment:
     STORAGE_MAX_SIZE: 1073741824  # 1GB
   ```

**Deprecated параметры** будут удалены в v2.0.0. До этого они продолжают работать с warning в логах.

## Ссылки на документацию

- [Главная документация проекта](../README.md)
- [Write-Ahead Logging](https://www.postgresql.org/docs/current/wal-intro.html)
- [Atomic File Operations](https://lwn.net/Articles/457667/)
- [Two-Phase Commit Protocol](https://en.wikipedia.org/wiki/Two-phase_commit_protocol)
