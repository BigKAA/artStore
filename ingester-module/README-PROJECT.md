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

### 2. Storage Element Selection

#### Intelligent Distribution
- **Load balancing**: Распределение по заполненности Storage Elements
- **Mode awareness**: Только edit и rw элементы для загрузки
- **Geographic preference**: Опциональная привязка к ЦОД
- **Health checking**: Автоматическое исключение недоступных элементов

#### Service Discovery Integration
- **Redis Pub/Sub**: Подписка на обновления конфигурации Storage Elements
- **Local cache**: Fallback на локальную конфигурацию при недоступности Redis
- **Automatic refresh**: Обновление списка Storage Elements в real-time

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
# Upload Limits
MAX_FILE_SIZE_MB=1024  # 1GB
MAX_BATCH_FILES=100
MAX_BATCH_SIZE_MB=1024
CHUNK_SIZE_MB=10

# Compression
COMPRESSION_ENABLED=true
COMPRESSION_MIN_SIZE_MB=10
COMPRESSION_ALGORITHM=brotli  # brotli или gzip

# Storage Element Selection
STORAGE_SELECTION_STRATEGY=least_used  # least_used, round_robin, random
STORAGE_HEALTH_CHECK_INTERVAL_SECONDS=30

# Service Discovery
REDIS_URL=redis://localhost:6379/0
SERVICE_DISCOVERY_CHANNEL=artstore:storage-elements
SERVICE_DISCOVERY_FALLBACK_CONFIG=/config/storage-elements.json

# Resumable Uploads
RESUMABLE_UPLOADS_ENABLED=true
UPLOAD_SESSION_TTL_HOURS=2
UPLOAD_SESSION_CLEANUP_INTERVAL_HOURS=1

# Circuit Breaker
CIRCUIT_BREAKER_ENABLED=true
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
CIRCUIT_BREAKER_SUCCESS_THRESHOLD=2
CIRCUIT_BREAKER_TIMEOUT_SECONDS=60

# Saga Coordination
SAGA_ENABLED=true
SAGA_TIMEOUT_SECONDS=300
SAGA_RETRY_MAX_ATTEMPTS=3

# Validation
VIRUS_SCAN_ENABLED=false  # Требует ClamAV integration
MIME_TYPE_VALIDATION=true
ALLOWED_MIME_TYPES=application/pdf,application/msword,image/*

# Monitoring
OPENTELEMETRY_ENABLED=true
PROMETHEUS_METRICS_ENABLED=true
```

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

- [Главная документация проекта](../README-PROJECT.md)
- [Admin Module documentation](../admin-module/README-PROJECT.md)
- [Storage Element documentation](../storage-element/README-PROJECT.md)
- [Circuit Breaker Pattern](https://martinfowler.com/bliki/CircuitBreaker.html)
- [Saga Pattern](https://microservices.io/patterns/data/saga.html)
