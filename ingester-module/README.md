# Ingester Module - Прием и управление файлами ArtStore

## Назначение модуля

**Ingester Module Cluster** — это высокопроизводительный отказоустойчивый сервис для приема и управления файлами, обеспечивающий:
- **Streaming upload** с chunked передачей и resumable uploads
- **Автоматическое распределение** файлов между Storage Elements
- **Валидацию и обработку** загружаемых файлов
- **Участие в Saga транзакциях** координируемых Admin Module
- **Circuit Breaker Pattern** для graceful degradation при недоступности Storage Elements

## Ключевые возможности

### 1. File Upload Management

#### Streaming Upload
- **Chunked transfer**: Поддержка загрузки больших файлов по частям
- **Progress tracking**: Real-time прогресс загрузки
- **Resumable uploads**: Возможность продолжить прерванную загрузку
- **Parallel uploads**: Одновременная загрузка множественных файлов

#### File Validation
- **Size limits**: Настраиваемые ограничения размера (default: 1GB)
- **MIME type validation**: Проверка типа файла
- **Virus scanning**: Интеграция с ClamAV (опционально)
- **Content validation**: Проверка целостности (MD5, SHA256)

#### Compression On-the-fly
- **Brotli compression**: Для текстовых документов (PDF, DOCX, TXT)
- **GZIP fallback**: Если Brotli не поддерживается клиентом
- **Selective compression**: Только для файлов >10MB

### 2. Storage Element Selection (StorageSelector Service)

#### Sequential Fill Algorithm

Сервис `StorageSelector` (`app/services/storage_selector.py`) реализует интеллектуальный выбор Storage Element для загрузки файлов:

```
┌─────────────────────────────────────────────────────────────────┐
│                   StorageSelector Flow                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. select_storage_element(file_size, retention_policy)         │
│     │                                                            │
│     ▼                                                            │
│  2. Determine required_mode:                                     │
│     TEMPORARY → edit | PERMANENT → rw                           │
│     │                                                            │
│     ▼                                                            │
│  3. Try Redis Registry (primary source)                         │
│     │  ZRANGE storage:{mode}:by_priority 0 -1                   │
│     │  For each SE in priority order:                           │
│     │    - Check capacity_status != FULL                        │
│     │    - Check can_accept_file(file_size)                     │
│     │  Return first matching SE                                 │
│     │                                                            │
│     ├──[Redis OK]──► Return StorageElementInfo                  │
│     │                                                            │
│     └──[Redis fail]──► Try Admin Module API (fallback)          │
│                        GET /api/v1/internal/storage-elements/available   │
│                        Return StorageElementInfo or raise error │
│                                                                  │
│  NOTE: Sprint 16 - Static STORAGE_ELEMENT_BASE_URL removed.     │
│  Service Discovery (Redis/Admin Module) is now MANDATORY.       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

#### Retention Policy Mapping

| Retention Policy | Target Mode | Use Case |
|-----------------|-------------|----------|
| `TEMPORARY` | `edit` | Документы в работе, TTL-based cleanup |
| `PERMANENT` | `rw` | Долгосрочное архивное хранение |

#### StorageElementInfo Data Class

Информация о Storage Element получается из Redis Hash и включает:

```python
@dataclass
class StorageElementInfo:
    element_id: str      # Уникальный ID SE
    mode: str            # edit, rw, ro, ar
    endpoint: str        # HTTP URL для API вызовов
    priority: int        # Порядок выбора (ascending)
    capacity_total: int  # Общая ёмкость (bytes)
    capacity_used: int   # Использовано (bytes)
    capacity_free: int   # Свободно (bytes)
    capacity_percent: float  # % использования
    capacity_status: CapacityStatus  # OK, WARNING, CRITICAL, FULL
    health_status: str   # healthy, degraded, unavailable
    last_updated: datetime  # Timestamp последнего health report
```

#### Capacity Status Levels

```python
class CapacityStatus(str, Enum):
    OK = "ok"           # Нормальная работа
    WARNING = "warning" # Alert админам, запись продолжается
    CRITICAL = "critical"  # Срочный alert, запись продолжается
    FULL = "full"       # SE исключён из выбора
```

#### Local Cache

- **TTL**: 5 секунд (настраивается)
- **Назначение**: Уменьшение нагрузки на Redis при частых запросах
- **Инвалидация**: Автоматическая по TTL или вручную через `invalidate_cache()`

#### Fallback Chain (Sprint 16)

```
Redis Registry → Admin Module API → Error
     │                  │               │
     │ Real-time        │ Cached data   │ No fallback!
     │ health data      │ from DB       │ Service Discovery
     ▼                  ▼               │ is MANDATORY
   Primary           Secondary          ▼
                                      503 Error
```

**Important (Sprint 16):** Static `STORAGE_ELEMENT_BASE_URL` configuration has been
removed. At least one of Redis or Admin Module must be available for file operations.
If both are unavailable, upload/finalize operations will fail with 503 Service Unavailable.

#### Integration

```python
# Инициализация при startup
from app.services.storage_selector import init_storage_selector

storage_selector = await init_storage_selector(
    redis_client=redis,
    admin_client=admin_http_client
)

# Использование при upload
se = await storage_selector.select_storage_element(
    file_size=file.size,
    retention_policy=RetentionPolicy.TEMPORARY
)

if se:
    await upload_to_storage_element(se.endpoint, file)
else:
    raise NoAvailableStorageError()

# Shutdown
await close_storage_selector()
```

#### Prometheus Metrics

Сервис записывает метрики через `record_storage_selection()`:

| Metric | Labels | Description |
|--------|--------|-------------|
| `storage_selection_total` | retention_policy, status, source | Количество выборов SE |
| `storage_selection_duration_seconds` | retention_policy | Время выбора SE |

#### Service Discovery Integration (Sprint 16)

- **Redis Pub/Sub**: Подписка на обновления конфигурации Storage Elements (primary)
- **Admin Module API**: Fallback на HTTP API при недоступности Redis
- **Local cache**: Кеширование SE информации на 5 секунд для снижения нагрузки
- **Automatic refresh**: Обновление списка Storage Elements в real-time
- **No static fallback**: `STORAGE_ELEMENT_BASE_URL` удалён, Service Discovery обязателен

### 3. File Operations

#### Upload
```
POST /api/files/upload
- Multipart/form-data streaming
- Automatic Storage Element selection
- Saga transaction coordination
- Webhook notifications on completion
```

#### Delete
```
DELETE /api/files/{file_id}
- Только для файлов в edit mode Storage Elements
- Saga-coordinated deletion (file + attr.json + DB cache cleanup)
- Audit logging
```

#### Transfer
```
POST /api/files/{file_id}/transfer
- Перенос файла между Storage Elements
- Two-Phase Commit protocol
- Verification после переноса
- Rollback при сбоях
```

#### Batch Operations
```
POST /api/files/batch/upload
- Загрузка до 100 файлов / 1GB за один запрос
- Parallel processing
- Partial success support (some succeed, some fail)
- Detailed response для каждого файла
```

### 4. Saga Transaction Participation

Ingester Module участвует в распределенных транзакциях координируемых Admin Module:

#### Upload Saga
```
1. Validate file → Ingester
2. Select Storage Element → Ingester
3. Upload to Storage → Storage Element
4. Update attr.json → Storage Element
5. Update DB cache → Storage Element
6. Publish to Service Discovery → Admin Module
7. Send webhook → Admin Module
```

#### Delete Saga
```
1. Check permissions → Admin Module
2. Delete file → Storage Element
3. Delete attr.json → Storage Element
4. Cleanup DB cache → Storage Element
5. Audit log → Admin Module
```

#### Transfer Saga
```
1. Validate source & destination → Ingester
2. Copy to destination → Two-Phase Commit
3. Verify copy → Storage Elements
4. Delete from source → Storage Element (только после успешной верификации)
5. Update Service Discovery → Admin Module
```

### 5. High Availability Features

#### Circuit Breaker Pattern
- **Automatic detection** недоступных Storage Elements
- **Graceful degradation**: Переключение на доступные элементы
- **Exponential backoff**: Retry с экспоненциальной задержкой
- **Health recovery**: Автоматическое включение после восстановления

#### Load Balanced Cluster
- **Multiple Ingester nodes** за Load Balancer
- **Stateless design**: Любой узел может обработать любой запрос
- **Session affinity** (опционально): Для resumable uploads

## Технологический стек

### Backend Framework
- **Python 3.12+** с async/await
- **FastAPI** для REST API
- **Uvicorn** с uvloop
- **Pydantic** для валидации
- **aiohttp** для HTTP клиента к Storage Elements

### Integration
- **Redis** (sync redis-py) для Service Discovery подписки
- **PostgreSQL** (опционально) для tracking upload state (resumable uploads)

### File Processing
- **aiofiles** для async file I/O
- **hashlib** для MD5/SHA256
- **brotli/gzip** для compression
- **python-magic** для MIME type detection

### Observability
- **OpenTelemetry** для distributed tracing
- **Prometheus client** для метрик
- **Structured logging** (JSON)

## API Endpoints

### File Upload (`/api/files/upload`)

```
POST /api/files/upload
Content-Type: multipart/form-data

Form fields:
- file: binary file data
- metadata: JSON string (optional custom metadata)

Headers:
- Authorization: Bearer <JWT_token>
- X-Upload-Session-ID: <uuid> (optional, для resumable uploads)

Response 201:
{
  "file_id": "uuid",
  "storage_element_id": "uuid",
  "storage_filename": "report_ivanov_20250102T153045_uuid.pdf",
  "size_bytes": 1048576,
  "md5_hash": "...",
  "sha256_hash": "...",
  "uploaded_at": "2025-01-02T15:30:45Z"
}

Response 202 (resumable upload in progress):
{
  "upload_session_id": "uuid",
  "bytes_uploaded": 524288,
  "bytes_total": 1048576,
  "percent_complete": 50
}
```

### Resumable Upload Status

```
GET /api/files/upload/session/{session_id}

Response:
{
  "session_id": "uuid",
  "status": "in_progress",  # in_progress, completed, failed
  "bytes_uploaded": 524288,
  "bytes_total": 1048576,
  "created_at": "2025-01-02T15:30:00Z",
  "last_activity_at": "2025-01-02T15:30:45Z",
  "expires_at": "2025-01-02T17:30:00Z"  # 2 часа TTL
}
```

### File Delete

```
DELETE /api/files/{file_id}
Authorization: Bearer <JWT_token>

Response 204: No Content (успешное удаление)

Response 400:
{
  "error": "file_in_readonly_storage",
  "message": "Cannot delete file from read-only Storage Element"
}
```

### File Transfer

```
POST /api/files/{file_id}/transfer
Authorization: Bearer <JWT_token>
Content-Type: application/json

{
  "destination_storage_element_id": "uuid",
  "delete_source": true,  # false для copy, true для move
  "verify_checksum": true
}

Response 202:
{
  "transfer_id": "uuid",
  "status": "in_progress",
  "estimated_time_seconds": 120
}

GET /api/files/transfer/{transfer_id}

Response:
{
  "transfer_id": "uuid",
  "status": "completed",  # queued, in_progress, verifying, completed, failed
  "source_storage_element_id": "uuid",
  "destination_storage_element_id": "uuid",
  "bytes_transferred": 1048576,
  "transfer_rate_mbps": 10.5,
  "started_at": "2025-01-02T15:30:00Z",
  "completed_at": "2025-01-02T15:32:00Z"
}
```

### Batch Upload

```
POST /api/files/batch/upload
Content-Type: multipart/form-data

Limits:
- Max files: 100
- Max total size: 1GB

Response 207 Multi-Status:
{
  "results": [
    {
      "filename": "file1.pdf",
      "status": "success",
      "file_id": "uuid",
      "size_bytes": 1048576
    },
    {
      "filename": "file2.docx",
      "status": "failed",
      "error": "file_too_large",
      "message": "File exceeds maximum size limit"
    }
  ],
  "summary": {
    "total": 2,
    "succeeded": 1,
    "failed": 1
  }
}
```

### Health & Monitoring

```
GET /health/live
GET /health/ready
GET /metrics
```

## Внутренняя архитектура

```
ingester-module/
├── app/
│   ├── main.py                    # FastAPI entry point
│   ├── core/
│   │   ├── config.py              # Configuration
│   │   ├── security.py            # JWT validation
│   │   └── exceptions.py
│   ├── api/
│   │   └── v1/
│   │       └── endpoints/
│   │           ├── upload.py      # File upload endpoints
│   │           ├── delete.py      # File delete endpoints
│   │           ├── transfer.py    # File transfer endpoints
│   │           └── health.py
│   ├── schemas/
│   │   ├── upload.py              # Upload schemas
│   │   ├── transfer.py            # Transfer schemas
│   │   └── batch.py               # Batch operation schemas
│   ├── services/
│   │   ├── upload_service.py      # Upload business logic
│   │   ├── storage_client.py      # HTTP client для Storage Element
│   │   ├── storage_selector.py    # Storage Element selection logic
│   │   ├── service_discovery.py   # Redis pub/sub subscription
│   │   ├── validation_service.py  # File validation (size, MIME, virus scan)
│   │   ├── compression_service.py # On-the-fly compression
│   │   ├── transfer_service.py    # File transfer coordination
│   │   ├── saga_participant.py    # Saga transaction participation
│   │   └── circuit_breaker.py     # Circuit breaker implementation
│   └── utils/
│       ├── file_utils.py          # File utilities
│       ├── hash_utils.py          # MD5/SHA256 calculation
│       └── metrics.py
├── tests/
│   ├── unit/
│   │   ├── test_upload_service.py
│   │   ├── test_storage_selector.py
│   │   └── test_circuit_breaker.py
│   └── integration/
│       ├── test_upload_api.py
│       └── test_transfer_api.py
├── Dockerfile
├── requirements.txt
└── .env.example
```

## Конфигурация

### Environment Variables

```bash
# ==========================================
# Application Settings
# ==========================================
APP_NAME=artstore-ingester
APP_VERSION=0.1.0
APP_DEBUG=off
APP_HOST=0.0.0.0
APP_PORT=8020

# ==========================================
# Authentication Settings
# ==========================================
AUTH_ENABLED=on
AUTH_PUBLIC_KEY_PATH=/app/keys/public_key.pem
AUTH_ALGORITHM=RS256
AUTH_ADMIN_MODULE_URL=http://admin-module:8000  # Sprint 16: используется для fallback

# ==========================================
# Storage Element HTTP Client Settings (Sprint 16)
# ==========================================
# IMPORTANT: STORAGE_ELEMENT_BASE_URL удалён в Sprint 16!
# Endpoints выбираются динамически через Service Discovery:
# - Primary: Redis Service Discovery
# - Fallback: Admin Module API (/api/v1/internal/storage-elements/available)
STORAGE_ELEMENT_TIMEOUT=30
STORAGE_ELEMENT_MAX_RETRIES=3
STORAGE_ELEMENT_CONNECTION_POOL_SIZE=100

# ==========================================
# Redis Settings (Service Discovery - MANDATORY)
# ==========================================
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=
REDIS_MAX_CONNECTIONS=50

# ==========================================
# Compression Settings
# ==========================================
COMPRESSION_ENABLED=on
COMPRESSION_ALGORITHM=gzip  # gzip или brotli
COMPRESSION_LEVEL=6  # 1-9 для gzip, 0-11 для brotli
COMPRESSION_MIN_SIZE=1024  # Минимальный размер файла для сжатия (bytes)

# ==========================================
# Logging Settings
# ==========================================
LOG_LEVEL=INFO
LOG_FORMAT=json  # json (production) или text (development)

# ==========================================
# Upload Limits (Future)
# ==========================================
# MAX_FILE_SIZE_MB=1024  # 1GB
# MAX_BATCH_FILES=100
# MAX_BATCH_SIZE_MB=1024
# CHUNK_SIZE_MB=10

# ==========================================
# Resumable Uploads (Future)
# ==========================================
# RESUMABLE_UPLOADS_ENABLED=true
# UPLOAD_SESSION_TTL_HOURS=2
# UPLOAD_SESSION_CLEANUP_INTERVAL_HOURS=1

# ==========================================
# Circuit Breaker (Future)
# ==========================================
# CIRCUIT_BREAKER_ENABLED=true
# CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
# CIRCUIT_BREAKER_SUCCESS_THRESHOLD=2
# CIRCUIT_BREAKER_TIMEOUT_SECONDS=60

# ==========================================
# Saga Coordination (Future)
# ==========================================
# SAGA_ENABLED=true
# SAGA_TIMEOUT_SECONDS=300
# SAGA_RETRY_MAX_ATTEMPTS=3

# ==========================================
# Validation (Future)
# ==========================================
# VIRUS_SCAN_ENABLED=false  # Требует ClamAV integration
# MIME_TYPE_VALIDATION=true
# ALLOWED_MIME_TYPES=application/pdf,application/msword,image/*

# ==========================================
# Monitoring
# ==========================================
# OPENTELEMETRY_ENABLED=true
# PROMETHEUS_METRICS_ENABLED=true
```

## Architecture Changes (Sprint 16)

### Service Discovery стал обязательным

**Что изменилось:**
- Удалена статическая конфигурация `STORAGE_ELEMENT_BASE_URL`
- Endpoints Storage Elements получаются ТОЛЬКО через Service Discovery
- Fallback chain: Redis → Admin Module API → Error (no static fallback)

**Почему:**
- Единственный источник истины для конфигурации SE
- Динамическое обновление endpoints без перезапуска
- Консистентность данных о capacity и health статусах
- Упрощение конфигурации (меньше env variables)

**Миграция:**
1. Удалить `STORAGE_ELEMENT_BASE_URL` из `.env` файлов
2. Убедиться что Redis доступен ИЛИ Admin Module API настроен
3. Проверить что SE зарегистрированы через Admin Module

### Health Check endpoints стандартизированы

**Было:** `/api/v1/health/live`, `/api/v1/health/ready`
**Стало:** `/health/live`, `/health/ready`

Теперь соответствует стандарту других модулей (Admin, Storage, Query).

### Readiness Check проверяет все writable SE

Health check `/health/ready` теперь:
1. Проверяет Redis (Service Discovery)
2. Проверяет Admin Module (fallback)
3. Получает ВСЕ writable SE (режимы `edit`/`rw`)
4. Проверяет каждый SE на `/health/live`
5. Возвращает агрегированный статус:
   - `ok`: все компоненты healthy
   - `degraded`: частично healthy
   - `fail`: критические компоненты недоступны

## Тестирование

### Unit Tests

```bash
pytest ingester-module/tests/unit/ -v --cov=app
```

### Integration Tests

```bash
# Requires running Storage Element mock
pytest ingester-module/tests/integration/ -v
```

### Тестовые сценарии

- **Simple upload**: Single файл < 100MB
- **Large file upload**: Streaming upload > 100MB с chunking
- **Resumable upload**: Прерывание и продолжение загрузки
- **Batch upload**: 10 файлов одновременно
- **Storage Element failure**: Circuit breaker activation
- **Saga rollback**: Сбой на этапе upload → compensating actions

## Мониторинг и метрики

### Prometheus Metrics (`/metrics`)

#### Custom Business Metrics
- `artstore_ingester_uploads_total`: Количество загрузок (success/failure)
- `artstore_ingester_upload_duration_seconds`: Latency загрузки
- `artstore_ingester_upload_size_bytes`: Размер загружаемых файлов (histogram)
- `artstore_ingester_storage_selection_duration_seconds`: Время выбора Storage Element
- `artstore_ingester_compression_ratio`: Коэффициент сжатия
- `artstore_ingester_circuit_breaker_state`: Состояние circuit breaker (open/closed/half-open)
- `artstore_ingester_saga_transactions_total`: Количество Saga транзакций
- `artstore_ingester_saga_compensations_total`: Количество compensating actions

### OpenTelemetry Tracing

- `artstore.ingester.upload` - Полный цикл загрузки
- `artstore.ingester.validation` - Валидация файла
- `artstore.ingester.compression` - Сжатие файла
- `artstore.ingester.storage_selection` - Выбор Storage Element
- `artstore.ingester.transfer` - Перенос файла между Storage Elements

## Troubleshooting

### Проблемы с Service Discovery (Sprint 16)

**Проблема**: `503 Service Unavailable` - No available Storage Elements
**Причина**: Service Discovery не может найти доступные SE
**Решение**:
1. Проверить что Redis запущен: `redis-cli ping`
2. Проверить что Admin Module доступен: `curl http://admin-module:8000/health/live`
3. Проверить что SE зарегистрированы в Redis: `redis-cli KEYS "storage:*"`
4. Проверить логи Ingester на ошибки подключения

**Проблема**: `RuntimeError: StorageSelector is required`
**Причина**: StorageSelector не инициализирован (Redis и Admin Module недоступны)
**Решение**:
1. Убедиться что `AUTH_ADMIN_MODULE_URL` настроен правильно
2. Проверить сетевую связность между модулями
3. Проверить что Admin Module полностью запустился (health/ready)

### Проблемы с загрузкой

**Проблема**: Upload timeout
**Решение**: Увеличить `SAGA_TIMEOUT_SECONDS`. Проверить network latency к Storage Element.

**Проблема**: Circuit breaker open для всех Storage Elements
**Решение**: Проверить доступность Storage Elements. Проверить логи на ошибки соединения.

### Проблемы с производительностью

**Проблема**: Медленная загрузка файлов
**Решение**: Увеличить `CHUNK_SIZE_MB` для больших файлов. Проверить compression overhead (отключить если не нужно).

**Проблема**: High memory usage
**Решение**: Уменьшить `MAX_BATCH_FILES` и `MAX_BATCH_SIZE_MB`. Проверить streaming upload implementation.

## Security Considerations

### Production Checklist

- [ ] JWT validation на всех endpoints
- [ ] File size limits строго настроены
- [ ] Virus scanning включен (ClamAV integration)
- [ ] MIME type validation включена
- [ ] TLS 1.3 для соединений к Storage Elements
- [ ] Rate limiting для защиты от DoS
- [ ] Audit logging всех file operations

### Best Practices

1. **Virus scanning** обязателен для production
2. **File size limits** должны соответствовать Storage Element capacity
3. **Circuit breaker** thresholds настроить based on SLA Storage Elements
4. **Resumable uploads** включить для файлов >100MB
5. **Compression** использовать selectively (не для уже сжатых файлов)

## Ссылки на документацию

- [Главная документация проекта](../README.md)
- [Admin Module documentation](../admin-module/README.md)
- [Storage Element documentation](../storage-element/README.md)
- [Circuit Breaker Pattern](https://martinfowler.com/bliki/CircuitBreaker.html)
- [Saga Pattern](https://microservices.io/patterns/data/saga.html)
