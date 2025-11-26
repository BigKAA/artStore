# Storage Element - Физическое хранилище файлов ArtStore

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
max_size_gb: 100
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
max_size_gb: 1000
retention_years: 5
fill_threshold_percent: 95  # Переход на другой RW элемент при 95% заполнении
```

**Переход**: `POST /api/admin/change-mode` (RW → RO)

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

**Переход**: `POST /api/admin/change-mode` (RO → AR)

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

### File Operations (`/api/files/*`)

```
POST /api/files/upload
  - Chunked upload с streaming
  - Input: multipart/form-data (file + metadata JSON)
  - Output: {"file_id": "uuid", "storage_filename": "...", "size_bytes": 123}
  - Режимы: edit, rw

GET /api/files/{file_id}
  - Метаданные файла
  - Output: Полный attr.json content
  - Режимы: edit, rw, ro, ar

GET /api/files/{file_id}/download
  - Скачивание файла
  - Resumable download (Range requests support)
  - Output: File stream
  - Режимы: edit, rw, ro (ar требует restore)

PATCH /api/files/{file_id}/metadata
  - Обновление custom metadata
  - Input: {"template": "...", "tags": [...]}
  - Режимы: edit

DELETE /api/files/{file_id}
  - Удаление файла
  - Режимы: только edit

POST /api/files/{file_id}/restore
  - Запрос восстановления из AR режима
  - Output: {"restore_id": "uuid", "status": "queued", "estimated_time": "2-7 days"}
  - Режимы: только ar
```

### Admin Operations (`/api/admin/*`)

```
POST /api/admin/change-mode
  - Смена режима работы Storage Element
  - Input: {"new_mode": "ro"}  # rw→ro or ro→ar
  - Two-Phase Commit для консистентности

POST /api/admin/reconcile
  - Ручной запуск reconciliation между attr.json и DB cache
  - Output: {"reconciled": 150, "conflicts": 2, "errors": 0}

GET /api/admin/stats
  - Статистика Storage Element
  - Output: {
      "total_files": 10000,
      "total_size_gb": 500,
      "used_percent": 50,
      "mode": "rw",
      "oldest_file": "2020-01-01",
      "newest_file": "2025-01-02"
    }

GET /api/admin/health
  - Детальный health check
  - Проверяет: filesystem space, database connectivity, WAL status
```

### Health & Monitoring

```
GET /health/live
  - Liveness probe

GET /health/ready
  - Readiness probe
  - Проверяет: filesystem accessible, database connected, sufficient disk space

GET /metrics
  - Prometheus metrics
```

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
STORAGE_MODE=rw  # edit, rw, ro, ar
STORAGE_TYPE=local  # local или s3
STORAGE_MAX_SIZE_GB=1000
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

# Reconciliation
RECONCILE_SCHEDULE_HOURS=24
RECONCILE_AUTO_FIX=true

# AR Mode Restore
AR_RESTORE_STORAGE_ELEMENT_ID=  # UUID Restore Storage Element
AR_RESTORE_TTL_DAYS=30
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
**Решение**: Запустить `POST /api/admin/reconcile` для автоматического исправления.

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

## Ссылки на документацию

- [Главная документация проекта](../README.md)
- [Write-Ahead Logging](https://www.postgresql.org/docs/current/wal-intro.html)
- [Atomic File Operations](https://lwn.net/Articles/457667/)
- [Two-Phase Commit Protocol](https://en.wikipedia.org/wiki/Two-phase_commit_protocol)
