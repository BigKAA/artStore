# Storage Element - Detailed Design Specification

**Version**: 1.0
**Date**: 2025-11-08
**Status**: Draft

## Содержание

1. [Обзор архитектуры](#1-обзор-архитектуры)
2. [REST API Specification](#2-rest-api-specification)
3. [File Operations Design](#3-file-operations-design)
4. [Database Schema](#4-database-schema)
5. [Storage Modes & State Machine](#5-storage-modes--state-machine)
6. [Security & Authentication](#6-security--authentication)
7. [Monitoring & Observability](#7-monitoring--observability)
8. [Configuration Management](#8-configuration-management)

---

## 1. Обзор архитектуры

### 1.1 Компоненты системы

```
┌─────────────────────────────────────────────────────────────┐
│                     Storage Element                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  REST API    │  │ File Storage │  │  Metadata    │      │
│  │  (FastAPI)   │→ │   Engine     │→ │    Cache     │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│         ↓                  ↓                  ↓             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │     JWT      │  │ WAL + attr   │  │  PostgreSQL  │      │
│  │  Validator   │  │    .json     │  │   Cluster    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│         ↓                  ↓                  ↓             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Storage    │  │    Redis     │  │  Prometheus  │      │
│  │    Modes     │  │   Sentinel   │  │   Metrics    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 Ключевые принципы дизайна

#### 🎯 Attribute-First Storage Model
- `*.attr.json` файлы — **единственный источник истины**
- Database cache — вторичный источник для производительности
- Consistency Protocol: `WAL → attr.json → DB cache → Commit`

#### 🔐 Security-First Approach
- JWT RS256 валидация для всех API endpoints
- RBAC с проверкой на уровне операций
- Audit logging всех file operations

#### ⚡ Performance Optimization
- PostgreSQL Full-Text Search с GIN индексами
- Async I/O для file operations
- Connection pooling для DB и Redis

#### 🛡️ Fault Tolerance
- Redis Sentinel для master election (modes: edit, rw)
- Write-Ahead Log для атомарности
- Automatic reconciliation при несоответствиях

---

## 2. REST API Specification

### 2.1 API Versioning и Base Path

```yaml
Base URL: /api/v1
API Version: 1.0
Authentication: Bearer JWT (RS256)
Content-Type: application/json
```

### 2.2 Health & Status Endpoints

#### `GET /` - Service Information
**Описание**: Корневой endpoint с информацией о сервисе

**Authentication**: None

**Response** (200 OK):
```json
{
  "service": "artstore-storage-element",
  "version": "1.0.0",
  "mode": "rw",
  "status": "healthy",
  "endpoints": {
    "health": "/health",
    "api": "/api/v1",
    "admin": "/admin",
    "metrics": "/metrics"
  }
}
```

---

#### `GET /health/live` - Liveness Probe
**Описание**: Проверка работоспособности приложения

**Authentication**: None

**Response** (200 OK):
```json
{
  "status": "alive",
  "timestamp": "2025-11-08T10:30:00Z"
}
```

---

#### `GET /health/ready` - Readiness Probe
**Описание**: Проверка готовности к обработке запросов

**Authentication**: None

**Response** (200 OK):
```json
{
  "status": "ready",
  "checks": {
    "database": "ok",
    "redis": "ok",
    "storage": "ok"
  },
  "timestamp": "2025-11-08T10:30:00Z"
}
```

**Response** (503 Service Unavailable):
```json
{
  "status": "not_ready",
  "checks": {
    "database": "failed",
    "redis": "ok",
    "storage": "ok"
  },
  "errors": ["Database connection pool exhausted"],
  "timestamp": "2025-11-08T10:30:00Z"
}
```

---

#### `GET /health/status` - Detailed Status
**Описание**: Подробная информация о состоянии сервиса

**Authentication**: Required (Bearer JWT)
**Required Role**: `admin`

**Response** (200 OK):
```json
{
  "service": "artstore-storage-element",
  "version": "1.0.0",
  "mode": "rw",
  "uptime_seconds": 86400,
  "storage": {
    "type": "local",
    "total_bytes": 1073741824,
    "used_bytes": 536870912,
    "free_bytes": 536870912,
    "usage_percent": 50.0,
    "file_count": 1523
  },
  "database": {
    "status": "connected",
    "pool_size": 10,
    "pool_in_use": 3,
    "pool_available": 7,
    "cache_size": 1523
  },
  "redis": {
    "status": "connected",
    "master": "redis-1:6379",
    "is_master": true
  },
  "timestamp": "2025-11-08T10:30:00Z"
}
```

---

### 2.3 File Operations API

#### `POST /api/v1/files/upload` - Upload File
**Описание**: Загрузка файла с streaming и Saga координацией

**Authentication**: Required (Bearer JWT)
**Required Permission**: `files.upload`
**Content-Type**: `multipart/form-data`

**Request Body**:
```
POST /api/v1/files/upload
Content-Type: multipart/form-data; boundary=----WebKitFormBoundary

------WebKitFormBoundary
Content-Disposition: form-data; name="file"; filename="report.pdf"
Content-Type: application/pdf

[Binary file data]
------WebKitFormBoundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{
  "description": "Квартальный отчет Q3 2025",
  "version": 1,
  "retention_days": 365,
  "tags": ["финансы", "квартальный", "2025-Q3"]
}
------WebKitFormBoundary--
```

**Response** (201 Created):
```json
{
  "file_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "storage_filename": "report_ivanov_20251108T103045_a1b2c3d4.pdf",
  "original_filename": "report.pdf",
  "file_size": 1048576,
  "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "uploaded_at": "2025-11-08T10:30:45Z",
  "uploaded_by": "ivanov",
  "storage_path": "/2025/11/08/10/",
  "saga_id": "saga-upload-123456"
}
```

**Response** (400 Bad Request):
```json
{
  "error": "validation_error",
  "message": "Недостаточно места в хранилище",
  "details": {
    "required_bytes": 1048576,
    "available_bytes": 524288
  }
}
```

**Response** (403 Forbidden):
```json
{
  "error": "forbidden",
  "message": "Storage mode 'ro' does not allow file upload"
}
```

---

#### `GET /api/v1/files/search` - Search Files
**Описание**: Поиск файлов по метаданным через PostgreSQL Full-Text Search

**Authentication**: Required (Bearer JWT)
**Required Permission**: `files.search`

**Query Parameters**:
```
GET /api/v1/files/search?
  q=квартальный+отчет          # Full-text search query
  &tags=финансы,отчет           # Filter by tags
  &uploaded_by=ivanov           # Filter by uploader
  &date_from=2025-01-01         # Date range start
  &date_to=2025-12-31           # Date range end
  &version=1                    # File version
  &limit=50                     # Results per page (default: 50, max: 100)
  &offset=0                     # Pagination offset
  &sort_by=uploaded_at          # Sort field: uploaded_at, file_size, original_filename
  &sort_order=desc              # Sort order: asc, desc
```

**Response** (200 OK):
```json
{
  "total": 42,
  "limit": 50,
  "offset": 0,
  "results": [
    {
      "file_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "original_filename": "report.pdf",
      "storage_filename": "report_ivanov_20251108T103045_a1b2c3d4.pdf",
      "file_size": 1048576,
      "mime_type": "application/pdf",
      "uploaded_at": "2025-11-08T10:30:45Z",
      "uploaded_by": "ivanov",
      "description": "Квартальный отчет Q3 2025",
      "version": 1,
      "tags": ["финансы", "квартальный", "2025-Q3"],
      "retention_expires_at": "2026-11-08T10:30:45Z"
    }
  ]
}
```

---

#### `GET /api/v1/files/{file_id}` - Get File Metadata
**Описание**: Получение метаданных файла с caching

**Authentication**: Required (Bearer JWT)
**Required Permission**: `files.read` or `files.read.own`

**Response** (200 OK):
```json
{
  "file_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "original_filename": "report.pdf",
  "storage_filename": "report_ivanov_20251108T103045_a1b2c3d4.pdf",
  "storage_path": "/2025/11/08/10/",
  "file_size": 1048576,
  "mime_type": "application/pdf",
  "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "uploaded_at": "2025-11-08T10:30:45Z",
  "uploaded_by": "ivanov",
  "uploader_full_name": "Иван Иванов",
  "description": "Квартальный отчет Q3 2025",
  "version": 1,
  "tags": ["финансы", "квартальный", "2025-Q3"],
  "retention_days": 365,
  "retention_expires_at": "2026-11-08T10:30:45Z",
  "digital_signature": {
    "present": true,
    "signature_filename": "report_ivanov_20251108T103045_a1b2c3d4.pdf.sig",
    "algorithm": "SHA256withRSA"
  },
  "storage_element_id": "storage-01",
  "storage_mode": "rw"
}
```

**Response** (404 Not Found):
```json
{
  "error": "not_found",
  "message": "File with id 'a1b2c3d4-e5f6-7890-abcd-ef1234567890' not found"
}
```

---

#### `GET /api/v1/files/{file_id}/download` - Download File
**Описание**: Скачивание файла с resumable support

**Authentication**: Required (Bearer JWT)
**Required Permission**: `files.download` or `files.download.own`

**Request Headers**:
```
Range: bytes=0-1048575  # Optional: для resumable downloads
```

**Response** (200 OK):
```
Content-Type: application/pdf
Content-Disposition: attachment; filename="report.pdf"
Content-Length: 1048576
Accept-Ranges: bytes
ETag: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

[Binary file data]
```

**Response** (206 Partial Content):
```
Content-Type: application/pdf
Content-Range: bytes 0-524287/1048576
Content-Length: 524288
Accept-Ranges: bytes

[Partial binary file data]
```

**Response** (410 Gone) - для AR mode:
```json
{
  "error": "archived",
  "message": "Файл перенесен в долговременное хранилище, обратитесь к администратору",
  "storage_mode": "ar",
  "restore_request_endpoint": "/api/v1/files/{file_id}/restore"
}
```

---

#### `DELETE /api/v1/files/{file_id}` - Delete File
**Описание**: Удаление файла (только EDIT mode)

**Authentication**: Required (Bearer JWT)
**Required Permission**: `files.delete` or `files.delete.own` (owner only)
**Required Role**: `admin` (для rw mode)

**Response** (200 OK):
```json
{
  "message": "File deleted successfully",
  "file_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "deleted_at": "2025-11-08T10:35:00Z"
}
```

**Response** (403 Forbidden):
```json
{
  "error": "forbidden",
  "message": "File deletion not allowed in 'rw' mode. Only admins can delete files."
}
```

---

#### `PUT /api/v1/files/{file_id}/metadata` - Update Metadata
**Описание**: Обновление метаданных файла

**Authentication**: Required (Bearer JWT)
**Required Permission**: `files.update` or `files.update.own`

**Request Body**:
```json
{
  "description": "Квартальный отчет Q3 2025 (обновленная версия)",
  "tags": ["финансы", "квартальный", "2025-Q3", "обновлено"],
  "retention_days": 730
}
```

**Response** (200 OK):
```json
{
  "message": "Metadata updated successfully",
  "file_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "updated_at": "2025-11-08T10:40:00Z",
  "updated_fields": ["description", "tags", "retention_days"]
}
```

---

### 2.4 Admin API

#### `GET /admin/config` - Get Configuration
**Описание**: Получение текущей конфигурации приложения

**Authentication**: Required (Bearer JWT)
**Required Role**: `admin`

**Response** (200 OK):
```json
{
  "app": {
    "name": "storage-element",
    "version": "1.0.0",
    "mode": "rw",
    "debug": false
  },
  "storage": {
    "type": "local",
    "max_size": "1GB",
    "base_path": "/app/data/storage"
  },
  "database": {
    "host": "postgres",
    "port": 5432,
    "database": "artstore",
    "table_prefix": "storage_elem_01",
    "pool_size": 10
  },
  "redis": {
    "sentinel_hosts": [
      {"host": "redis-sentinel-1", "port": 26379}
    ],
    "master_name": "artstore-master"
  }
}
```

**Note**: Пароли и секреты возвращаются в маскированном виде: `"password": "***"`

---

#### `GET /admin/info` - System Information
**Описание**: Системная информация приложения

**Authentication**: Required (Bearer JWT)
**Required Role**: `admin`

**Response** (200 OK):
```json
{
  "system": {
    "python_version": "3.12.1",
    "platform": "Linux-6.1.0-amd64",
    "hostname": "storage-element-01",
    "pid": 1234
  },
  "storage": {
    "type": "local",
    "total_bytes": 1073741824,
    "used_bytes": 536870912,
    "free_bytes": 536870912,
    "usage_percent": 50.0,
    "file_count": 1523,
    "retention_period_days": 365,
    "expires_at": "2026-11-08T00:00:00Z",
    "warning_threshold_days": 90
  },
  "database": {
    "cache_entries": 1523,
    "last_rebuild": "2025-11-01T00:00:00Z",
    "last_verify": "2025-11-08T00:00:00Z"
  }
}
```

---

#### `POST /admin/cache/rebuild` - Rebuild Cache
**Описание**: Пересоздание кеша метаданных из attr.json файлов

**Authentication**: Required (Bearer JWT)
**Required Role**: `admin`

**Response** (202 Accepted):
```json
{
  "message": "Cache rebuild started",
  "task_id": "rebuild-20251108-103000",
  "status_endpoint": "/admin/cache/rebuild/rebuild-20251108-103000/status"
}
```

**Response** (200 OK) - status endpoint:
```json
{
  "task_id": "rebuild-20251108-103000",
  "status": "completed",
  "started_at": "2025-11-08T10:30:00Z",
  "completed_at": "2025-11-08T10:32:15Z",
  "statistics": {
    "files_scanned": 1523,
    "cache_entries_created": 1523,
    "errors": 0
  }
}
```

---

#### `POST /admin/cache/verify` - Verify Cache Integrity
**Описание**: Проверка целостности кеша метаданных

**Authentication**: Required (Bearer JWT)
**Required Role**: `admin`

**Response** (200 OK):
```json
{
  "status": "healthy",
  "checked_at": "2025-11-08T10:35:00Z",
  "statistics": {
    "total_files": 1523,
    "cache_matches": 1520,
    "cache_mismatches": 3,
    "missing_attr_files": 0,
    "orphaned_cache_entries": 0
  },
  "mismatches": [
    {
      "file_id": "xyz-123",
      "issue": "sha256_mismatch",
      "attr_value": "abc123...",
      "cache_value": "def456..."
    }
  ]
}
```

---

#### `PUT /admin/mode` - Change Storage Mode
**Описание**: Изменение режима работы storage element

**Authentication**: Required (Bearer JWT)
**Required Role**: `admin`

**Request Body**:
```json
{
  "mode": "ro",
  "reason": "Перевод в режим read-only для архивирования"
}
```

**Response** (200 OK):
```json
{
  "message": "Storage mode changed successfully",
  "previous_mode": "rw",
  "new_mode": "ro",
  "changed_at": "2025-11-08T10:40:00Z",
  "changed_by": "admin"
}
```

**Response** (400 Bad Request):
```json
{
  "error": "invalid_transition",
  "message": "Cannot transition from 'edit' to any other mode via API",
  "allowed_transitions": {
    "edit": [],
    "rw": ["ro"],
    "ro": ["ar"],
    "ar": []
  }
}
```

---

### 2.5 Coordination & Transactions API

#### `GET /api/v1/coordination/status` - Coordination Status
**Описание**: Статус системы координации (Redis Sentinel)

**Authentication**: Required (Bearer JWT)
**Required Role**: `admin`

**Response** (200 OK):
```json
{
  "coordination": {
    "enabled": true,
    "backend": "redis_sentinel",
    "master": "redis-1:6379",
    "sentinels": [
      {"host": "redis-sentinel-1", "port": 26379, "status": "ok"},
      {"host": "redis-sentinel-2", "port": 26379, "status": "ok"},
      {"host": "redis-sentinel-3", "port": 26379, "status": "ok"}
    ]
  },
  "master_election": {
    "is_master": true,
    "master_node": "storage-element-01",
    "master_since": "2025-11-08T08:00:00Z",
    "lock_ttl_seconds": 30
  }
}
```

---

#### `POST /api/v1/transactions/saga/{saga_id}/participate` - Saga Participation
**Описание**: Участие в Saga транзакции координируемой Admin Module

**Authentication**: Required (Bearer JWT - межсервисный токен)
**Required Role**: `service`

**Request Body**:
```json
{
  "saga_id": "saga-upload-123456",
  "operation": "upload",
  "step": "reserve_space",
  "payload": {
    "file_size": 1048576,
    "filename": "report.pdf"
  }
}
```

**Response** (200 OK):
```json
{
  "saga_id": "saga-upload-123456",
  "step": "reserve_space",
  "status": "completed",
  "reservation_id": "rsv-789012",
  "expires_at": "2025-11-08T10:35:00Z"
}
```

**Response** (409 Conflict):
```json
{
  "saga_id": "saga-upload-123456",
  "step": "reserve_space",
  "status": "failed",
  "error": "insufficient_storage",
  "compensation_required": true
}
```

---

#### `POST /api/v1/transactions/reconcile` - Trigger Reconciliation
**Описание**: Запуск процедуры reconciliation для устранения несоответствий

**Authentication**: Required (Bearer JWT)
**Required Role**: `admin`

**Response** (202 Accepted):
```json
{
  "message": "Reconciliation started",
  "task_id": "reconcile-20251108-104000",
  "status_endpoint": "/api/v1/transactions/reconcile/reconcile-20251108-104000/status"
}
```

---

### 2.6 Metrics & Monitoring

#### `GET /metrics` - Prometheus Metrics
**Описание**: Экспорт метрик в формате Prometheus

**Authentication**: None (обычно защищается на уровне сети)

**Response** (200 OK):
```
# HELP artstore_storage_up Service availability
# TYPE artstore_storage_up gauge
artstore_storage_up 1

# HELP artstore_storage_ready Service readiness
# TYPE artstore_storage_ready gauge
artstore_storage_ready 1

# HELP artstore_storage_mode Current storage mode
# TYPE artstore_storage_mode gauge
artstore_storage_mode{mode="rw"} 1

# HELP artstore_storage_bytes_total Total storage capacity in bytes
# TYPE artstore_storage_bytes_total gauge
artstore_storage_bytes_total 1073741824

# HELP artstore_storage_bytes_used Used storage in bytes
# TYPE artstore_storage_bytes_used gauge
artstore_storage_bytes_used 536870912

# HELP artstore_files_total Total number of files
# TYPE artstore_files_total gauge
artstore_files_total 1523

# HELP artstore_file_upload_duration_seconds File upload duration
# TYPE artstore_file_upload_duration_seconds histogram
artstore_file_upload_duration_seconds_bucket{le="1"} 450
artstore_file_upload_duration_seconds_bucket{le="5"} 980
artstore_file_upload_duration_seconds_bucket{le="10"} 1200
artstore_file_upload_duration_seconds_bucket{le="+Inf"} 1523

# HELP artstore_db_connections_active Active database connections
# TYPE artstore_db_connections_active gauge
artstore_db_connections_active 3

# HELP artstore_db_connections_total Total database connection pool size
# TYPE artstore_db_connections_total gauge
artstore_db_connections_total 10
```

---

## 3. File Operations Design

### 3.1 File Naming Utility

#### Implementation: `generate_storage_filename()`

```python
from pathlib import Path
from datetime import datetime
from uuid import uuid4

def generate_storage_filename(
    original_name: str,
    username: str,
    timestamp: datetime | None = None,
    file_uuid: str | None = None,
    max_filename_length: int = 200
) -> str:
    """
    Генерирует уникальное имя файла для хранения.

    Формат: {name}_{username}_{timestamp}_{uuid}.{ext}
    Пример: report_ivanov_20251108T103045_a1b2c3d4.pdf

    Args:
        original_name: Оригинальное имя файла
        username: Логин пользователя
        timestamp: Timestamp (default: текущее время UTC)
        file_uuid: UUID (default: генерируется автоматически)
        max_filename_length: Максимальная длина (default: 200)

    Returns:
        Storage filename с автоматическим обрезанием

    Examples:
        >>> generate_storage_filename("report.pdf", "ivanov")
        "report_ivanov_20251108T103045_a1b2c3d4.pdf"

        >>> generate_storage_filename("Very_Long_Name.pdf", "ivanov", max_filename_length=50)
        "Very_Long_N_ivanov_20251108T103045_a1b2c3d4.pdf"
    """
    # Обработка timestamp и UUID
    if timestamp is None:
        timestamp = datetime.utcnow()
    timestamp_str = timestamp.strftime("%Y%m%dT%H%M%S")

    if file_uuid is None:
        file_uuid = uuid4().hex[:8]  # Короткая форма UUID

    # Разбор оригинального имени
    name_stem = Path(original_name).stem
    name_ext = Path(original_name).suffix

    # Расчет доступной длины для name_stem
    fixed_part_length = (
        1 + len(username) +      # _username
        1 + len(timestamp_str) + # _timestamp
        1 + len(file_uuid) +     # _uuid
        len(name_ext)            # .ext
    )
    available_length = max_filename_length - fixed_part_length

    # Обрезание name_stem если необходимо
    if len(name_stem) > available_length:
        name_stem = name_stem[:available_length]

    return f"{name_stem}_{username}_{timestamp_str}_{file_uuid}{name_ext}"
```

---

### 3.2 Atomic Attr.json Write

#### Implementation: `write_attr_file_atomic()`

```python
import os
import json
from uuid import uuid4
from pathlib import Path

def write_attr_file_atomic(
    target_path: str | Path,
    attributes: dict,
    max_size_bytes: int = 4096
) -> None:
    """
    Атомарная запись файла атрибутов через WAL pattern.

    Протокол: WAL → Temp file → fsync → Atomic rename

    Args:
        target_path: Путь к целевому attr.json файлу
        attributes: Словарь атрибутов для записи
        max_size_bytes: Максимальный размер (default: 4KB)

    Raises:
        ValueError: Если размер атрибутов превышает max_size_bytes
        OSError: Если операция записи не удалась

    Examples:
        >>> attrs = {
        ...     "file_id": "a1b2c3d4",
        ...     "original_filename": "report.pdf",
        ...     "file_size": 1048576
        ... }
        >>> write_attr_file_atomic("/data/2025/11/08/10/file.attr.json", attrs)
    """
    target_path = Path(target_path)

    # Валидация размера
    attrs_json = json.dumps(attributes, indent=2, ensure_ascii=False)
    attrs_bytes = attrs_json.encode('utf-8')

    if len(attrs_bytes) > max_size_bytes:
        raise ValueError(
            f"Attributes size {len(attrs_bytes)} bytes exceeds "
            f"maximum {max_size_bytes} bytes"
        )

    # Создание директории если не существует
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Создание временного файла с уникальным именем
    temp_file = target_path.parent / f"{target_path.stem}.{uuid4()}.tmp"

    try:
        # 2. Запись в временный файл с fsync
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write(attrs_json)
            f.flush()
            os.fsync(f.fileno())  # Принудительная запись на диск

        # 3. Атомарное переименование (POSIX гарантия)
        os.rename(temp_file, target_path)

    except Exception as e:
        # Очистка временного файла при ошибке
        if temp_file.exists():
            temp_file.unlink()
        raise OSError(f"Failed to write attr.json atomically: {e}") from e
```

---

### 3.3 File Upload Flow

#### Saga-based Upload Sequence

```yaml
Saga ID: saga-upload-{uuid}
Coordinator: Admin Module Cluster
Participant: Storage Element

Steps:
  Step 1 - Reserve Space:
    Action: Storage Element reserves disk space
    Timeout: 5 seconds
    Compensation: Release reservation

  Step 2 - Upload File Data:
    Action: Stream file chunks to storage
    Timeout: Based on file size (~1MB/sec baseline)
    Compensation: Delete partially uploaded file

  Step 3 - Write Attribute File:
    Action: Atomic write *.attr.json
    Timeout: 2 seconds
    Compensation: Delete attr.json file

  Step 4 - Update DB Cache:
    Action: INSERT metadata into PostgreSQL
    Timeout: 3 seconds
    Compensation: DELETE from cache table

  Step 5 - Confirm Completion:
    Action: Return success to Admin Module
    Timeout: 2 seconds
    Compensation: Mark as failed in WAL
```

#### Pseudocode Implementation

```python
async def upload_file_saga(
    file_stream: AsyncIterable[bytes],
    metadata: dict,
    saga_id: str
) -> dict:
    """
    Saga-based file upload с компенсирующими операциями.
    """
    # Step 1: Reserve Space
    reservation = await reserve_storage_space(
        file_size=metadata['file_size'],
        saga_id=saga_id
    )

    try:
        # Step 2: Upload File Data
        storage_path = await stream_file_to_disk(
            file_stream=file_stream,
            storage_filename=metadata['storage_filename'],
            reservation_id=reservation['id']
        )

        try:
            # Step 3: Write Attr.json
            attr_path = storage_path.with_suffix('.attr.json')
            await write_attr_file_atomic(attr_path, metadata)

            try:
                # Step 4: Update DB Cache
                await db_cache_insert(metadata)

                # Step 5: Confirm Success
                await saga_complete(saga_id)
                return {"status": "success", "file_id": metadata['file_id']}

            except DBError as e:
                # Compensation: Delete attr.json
                await compensate_delete_attr(attr_path)
                raise

        except AttrWriteError as e:
            # Compensation: Delete file data
            await compensate_delete_file(storage_path)
            raise

    except UploadError as e:
        # Compensation: Release reservation
        await compensate_release_reservation(reservation['id'])
        raise
```

---

### 3.4 File Search with PostgreSQL Full-Text

#### Search Query Builder

```python
from sqlalchemy import text
from typing import List, Dict, Any

async def search_files_fulltext(
    query: str | None = None,
    tags: List[str] | None = None,
    uploaded_by: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
    offset: int = 0,
    sort_by: str = "uploaded_at",
    sort_order: str = "desc"
) -> Dict[str, Any]:
    """
    Поиск файлов через PostgreSQL Full-Text Search.

    Использует GIN индекс на tsvector для быстрого поиска.
    """
    # Построение SQL запроса с full-text search
    sql_conditions = []
    params = {}

    # Full-text search по description и original_filename
    if query:
        sql_conditions.append(
            "search_vector @@ plainto_tsquery('russian', :query)"
        )
        params['query'] = query

    # Фильтр по tags (PostgreSQL array operators)
    if tags:
        sql_conditions.append("tags && :tags")
        params['tags'] = tags

    # Фильтр по uploaded_by
    if uploaded_by:
        sql_conditions.append("uploaded_by = :uploaded_by")
        params['uploaded_by'] = uploaded_by

    # Date range фильтры
    if date_from:
        sql_conditions.append("uploaded_at >= :date_from")
        params['date_from'] = date_from

    if date_to:
        sql_conditions.append("uploaded_at <= :date_to")
        params['date_to'] = date_to

    # Формирование WHERE clause
    where_clause = " AND ".join(sql_conditions) if sql_conditions else "1=1"

    # Валидация sort параметров
    allowed_sort_fields = ['uploaded_at', 'file_size', 'original_filename']
    if sort_by not in allowed_sort_fields:
        sort_by = 'uploaded_at'

    sort_direction = 'DESC' if sort_order.lower() == 'desc' else 'ASC'

    # Выполнение запроса
    query_sql = text(f"""
        SELECT
            file_id, original_filename, storage_filename,
            file_size, mime_type, uploaded_at, uploaded_by,
            description, version, tags, retention_expires_at,
            COUNT(*) OVER() as total_count
        FROM {table_prefix}_file_metadata
        WHERE {where_clause}
        ORDER BY {sort_by} {sort_direction}
        LIMIT :limit OFFSET :offset
    """)

    params.update({'limit': limit, 'offset': offset})

    result = await db.execute(query_sql, params)
    rows = result.fetchall()

    total = rows[0]['total_count'] if rows else 0

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "results": [dict(row) for row in rows]
    }
```

---

## 4. Database Schema

### 4.1 Metadata Cache Table

```sql
-- Таблица кеша метаданных файлов
-- Префикс таблицы задается в конфигурации: {table_prefix}_file_metadata
CREATE TABLE storage_elem_01_file_metadata (
    -- Primary Key
    file_id UUID PRIMARY KEY,

    -- File Identification
    original_filename VARCHAR(500) NOT NULL,
    storage_filename VARCHAR(255) NOT NULL UNIQUE,
    storage_path VARCHAR(1000) NOT NULL,

    -- File Properties
    file_size BIGINT NOT NULL CHECK (file_size > 0),
    mime_type VARCHAR(255),
    sha256 CHAR(64) NOT NULL,

    -- Upload Information
    uploaded_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    uploaded_by VARCHAR(255) NOT NULL,
    uploader_full_name VARCHAR(500),
    uploader_uid VARCHAR(255),

    -- Metadata
    description TEXT,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    tags TEXT[], -- PostgreSQL array для tags

    -- Retention Management
    retention_days INTEGER NOT NULL CHECK (retention_days > 0),
    retention_expires_at TIMESTAMP WITH TIME ZONE NOT NULL,

    -- Digital Signature
    has_digital_signature BOOLEAN DEFAULT FALSE,
    signature_filename VARCHAR(255),
    signature_algorithm VARCHAR(100),

    -- Storage Element Info
    storage_element_id VARCHAR(100) NOT NULL,
    storage_mode VARCHAR(10) NOT NULL CHECK (storage_mode IN ('edit', 'rw', 'ro', 'ar')),

    -- Full-Text Search (tsvector для быстрого поиска)
    search_vector TSVECTOR GENERATED ALWAYS AS (
        setweight(to_tsvector('russian', coalesce(original_filename, '')), 'A') ||
        setweight(to_tsvector('russian', coalesce(description, '')), 'B') ||
        setweight(to_tsvector('russian', array_to_string(tags, ' ')), 'C')
    ) STORED,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Индексы для производительности
CREATE INDEX idx_file_metadata_uploaded_at
    ON storage_elem_01_file_metadata(uploaded_at DESC);

CREATE INDEX idx_file_metadata_uploaded_by
    ON storage_elem_01_file_metadata(uploaded_by);

CREATE INDEX idx_file_metadata_retention_expires
    ON storage_elem_01_file_metadata(retention_expires_at);

CREATE INDEX idx_file_metadata_storage_mode
    ON storage_elem_01_file_metadata(storage_mode);

-- GIN индекс для full-text search (критически важен для производительности)
CREATE INDEX idx_file_metadata_search_vector
    ON storage_elem_01_file_metadata USING GIN(search_vector);

-- GIN индекс для tags (array search)
CREATE INDEX idx_file_metadata_tags
    ON storage_elem_01_file_metadata USING GIN(tags);

-- Триггер для автоматического обновления updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_file_metadata_updated_at
BEFORE UPDATE ON storage_elem_01_file_metadata
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();
```

---

### 4.2 Storage Element Configuration Table

```sql
-- Таблица конфигурации Storage Element
CREATE TABLE storage_elem_01_config (
    -- Primary Key
    config_key VARCHAR(100) PRIMARY KEY,

    -- Configuration Value
    config_value TEXT NOT NULL,

    -- Metadata
    description TEXT,
    last_modified_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    last_modified_by VARCHAR(255)
);

-- Начальная конфигурация
INSERT INTO storage_elem_01_config (config_key, config_value, description) VALUES
    ('storage_mode', 'edit', 'Current storage mode: edit, rw, ro, ar'),
    ('storage_element_id', 'storage-01', 'Unique identifier for this storage element'),
    ('retention_period_days', '365', 'Default retention period in days'),
    ('max_storage_bytes', '1073741824', 'Maximum storage capacity in bytes'),
    ('warning_threshold_days', '90', 'Days before retention expiration to warn admin');
```

---

### 4.3 Write-Ahead Log Table

```sql
-- Таблица WAL для атомарности операций
CREATE TABLE storage_elem_01_wal (
    -- Primary Key
    wal_id BIGSERIAL PRIMARY KEY,

    -- Transaction Info
    transaction_id UUID NOT NULL,
    saga_id VARCHAR(255),

    -- Operation Details
    operation_type VARCHAR(50) NOT NULL CHECK (
        operation_type IN ('upload', 'delete', 'update_metadata', 'mode_change')
    ),
    operation_status VARCHAR(50) NOT NULL CHECK (
        operation_status IN ('pending', 'in_progress', 'committed', 'rolled_back', 'failed')
    ),

    -- Target Resource
    file_id UUID,

    -- Operation Payload
    payload JSONB NOT NULL,

    -- Compensation Data (для rollback)
    compensation_data JSONB,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    committed_at TIMESTAMP WITH TIME ZONE,

    -- Indexing
    CONSTRAINT idx_wal_transaction_id UNIQUE (transaction_id)
);

-- Индексы для WAL
CREATE INDEX idx_wal_status ON storage_elem_01_wal(operation_status);
CREATE INDEX idx_wal_created_at ON storage_elem_01_wal(created_at DESC);
CREATE INDEX idx_wal_saga_id ON storage_elem_01_wal(saga_id);
```

---

## 5. Storage Modes & State Machine

### 5.1 Mode Definitions

| Mode | Description | Allowed Operations | Master Election Required |
|------|-------------|-------------------|-------------------------|
| **edit** | Полный CRUD | Create, Read, Update, Delete | ✅ Yes |
| **rw** | Без удаления пользователями | Create, Read, Update, Delete (admin only) | ✅ Yes |
| **ro** | Только чтение | Read only | ❌ No |
| **ar** | Архивный | Read metadata only (files on cold storage) | ❌ No |

---

### 5.2 State Transition Diagram

```
┌──────────────────────────────────────────────────────────┐
│                  Storage Mode State Machine              │
└──────────────────────────────────────────────────────────┘

     ┌─────────┐
     │  EDIT   │ (Полный CRUD, нельзя изменить через API)
     └─────────┘
         │
         │ (только через config + restart)
         ↓
     ┌─────────┐
     │   RW    │ (Create, Read, Update, Delete admin-only)
     └─────────┘
         │
         │ PUT /admin/mode {"mode": "ro"}
         ↓
     ┌─────────┐
     │   RO    │ (Read-only)
     └─────────┘
         │
         │ PUT /admin/mode {"mode": "ar"}
         ↓
     ┌─────────┐
     │   AR    │ (Metadata-only, files archived)
     └─────────┘
         │
         │ (только через config + restart → any mode)
         ↓
    (можно вернуться в edit, rw, ro)
```

---

### 5.3 Mode Transition Implementation

```python
from enum import Enum
from typing import Dict, List

class StorageMode(str, Enum):
    EDIT = "edit"
    RW = "rw"
    RO = "ro"
    AR = "ar"

# Allowed transitions matrix
ALLOWED_TRANSITIONS: Dict[StorageMode, List[StorageMode]] = {
    StorageMode.EDIT: [],  # Cannot transition via API
    StorageMode.RW: [StorageMode.RO],
    StorageMode.RO: [StorageMode.AR],
    StorageMode.AR: []  # Cannot transition via API (only config + restart)
}

async def change_storage_mode(
    current_mode: StorageMode,
    target_mode: StorageMode,
    admin_username: str,
    reason: str
) -> Dict[str, any]:
    """
    Изменение режима работы Storage Element.

    Raises:
        ValueError: Если переход не разрешен
        RuntimeError: Если операция не удалась
    """
    # Валидация перехода
    if target_mode not in ALLOWED_TRANSITIONS[current_mode]:
        raise ValueError(
            f"Invalid mode transition: {current_mode} → {target_mode}. "
            f"Allowed transitions: {ALLOWED_TRANSITIONS[current_mode]}"
        )

    # Two-Phase Commit для критической операции
    transaction_id = str(uuid4())

    try:
        # Phase 1: Prepare
        await wal_log_operation(
            transaction_id=transaction_id,
            operation_type="mode_change",
            payload={
                "current_mode": current_mode.value,
                "target_mode": target_mode.value,
                "admin_username": admin_username,
                "reason": reason
            }
        )

        # Phase 2: Commit
        # 1. Update database config
        await db_update_mode(target_mode)

        # 2. Update in-memory state
        app_state.storage_mode = target_mode

        # 3. Release master lock if transitioning to ro/ar
        if target_mode in [StorageMode.RO, StorageMode.AR]:
            await redis_release_master_lock()

        # 4. Commit WAL
        await wal_commit_operation(transaction_id)

        return {
            "message": "Storage mode changed successfully",
            "previous_mode": current_mode.value,
            "new_mode": target_mode.value,
            "changed_at": datetime.utcnow().isoformat(),
            "changed_by": admin_username
        }

    except Exception as e:
        # Rollback WAL
        await wal_rollback_operation(transaction_id)
        raise RuntimeError(f"Mode transition failed: {e}") from e
```

---

## 6. Security & Authentication

### 6.1 JWT Validation

```python
import jwt
from pathlib import Path
from typing import Dict, Any

class JWTValidator:
    """
    Валидатор JWT токенов с RS256 алгоритмом.
    """
    def __init__(self, public_key_path: str):
        self.public_key = self._load_public_key(public_key_path)
        self.algorithm = "RS256"

    def _load_public_key(self, key_path: str) -> str:
        """Загрузка публичного ключа от Admin Module."""
        with open(key_path, 'r') as f:
            return f.read()

    def validate_token(self, token: str) -> Dict[str, Any]:
        """
        Валидация JWT токена.

        Args:
            token: JWT токен из Authorization header

        Returns:
            Decoded JWT claims

        Raises:
            jwt.InvalidTokenError: Если токен невалиден
            jwt.ExpiredSignatureError: Если токен истек
        """
        try:
            payload = jwt.decode(
                token,
                self.public_key,
                algorithms=[self.algorithm],
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_iat": True
                }
            )
            return payload

        except jwt.ExpiredSignatureError:
            raise jwt.InvalidTokenError("Token has expired")
        except jwt.InvalidTokenError as e:
            raise jwt.InvalidTokenError(f"Invalid token: {e}")
```

---

### 6.2 RBAC Permission Checking

```python
from typing import List
from fastapi import HTTPException, status

class PermissionChecker:
    """
    Проверка прав доступа на основе RBAC.
    """
    # Матрица разрешений
    ROLE_PERMISSIONS = {
        "admin": ["*"],  # All permissions
        "user": [
            "files.upload",
            "files.download.own",
            "files.search",
            "files.delete.own"  # Only in EDIT mode
        ],
        "auditor": [
            "files.search",
            "files.download.*",
            "audit.view",
            "audit.export"
        ],
        "readonly": [
            "files.search",
            "files.download.own"
        ]
    }

    def __init__(self, jwt_claims: Dict[str, Any]):
        self.username = jwt_claims.get("sub")
        self.roles = jwt_claims.get("roles", [])

    def has_permission(self, permission: str, resource_owner: str | None = None) -> bool:
        """
        Проверка наличия разрешения.

        Args:
            permission: Требуемое разрешение (e.g., "files.upload")
            resource_owner: Владелец ресурса для проверки .own разрешений

        Returns:
            True если разрешение есть, False иначе
        """
        for role in self.roles:
            role_perms = self.ROLE_PERMISSIONS.get(role, [])

            # Admin has all permissions
            if "*" in role_perms:
                return True

            # Check exact permission match
            if permission in role_perms:
                return True

            # Check wildcard permissions (e.g., "files.download.*")
            wildcard_perm = permission.rsplit('.', 1)[0] + ".*"
            if wildcard_perm in role_perms:
                return True

            # Check .own permissions
            if permission.endswith(".own"):
                base_perm = permission[:-4]  # Remove ".own"
                if base_perm in role_perms and resource_owner == self.username:
                    return True

        return False

    def require_permission(self, permission: str, resource_owner: str | None = None):
        """
        Требование разрешения (поднимает HTTPException если нет прав).
        """
        if not self.has_permission(permission, resource_owner):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission}' required"
            )
```

---

### 6.3 FastAPI Dependency for Auth

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()
jwt_validator = JWTValidator(public_key_path="/path/to/public_key.pem")

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict[str, Any]:
    """
    Dependency для получения текущего пользователя из JWT токена.
    """
    token = credentials.credentials

    try:
        claims = jwt_validator.validate_token(token)
        return claims
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"}
        )

async def require_admin(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Dependency для требования роли admin.
    """
    if "admin" not in current_user.get("roles", []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required"
        )
```

---

## 7. Monitoring & Observability

### 7.1 Prometheus Metrics Implementation

```python
from prometheus_client import Counter, Histogram, Gauge, Info

# Service Status Metrics
storage_up = Gauge(
    'artstore_storage_up',
    'Service availability (1 = up, 0 = down)'
)
storage_up.set(1)

storage_ready = Gauge(
    'artstore_storage_ready',
    'Service readiness (1 = ready, 0 = not ready)'
)

storage_mode = Gauge(
    'artstore_storage_mode',
    'Current storage mode',
    ['mode']
)

# Storage Metrics
storage_bytes_total = Gauge(
    'artstore_storage_bytes_total',
    'Total storage capacity in bytes'
)

storage_bytes_used = Gauge(
    'artstore_storage_bytes_used',
    'Used storage in bytes'
)

files_total = Gauge(
    'artstore_files_total',
    'Total number of files'
)

# File Operation Metrics
file_upload_duration = Histogram(
    'artstore_file_upload_duration_seconds',
    'File upload duration in seconds',
    buckets=[1, 5, 10, 30, 60, 120, 300]
)

file_download_duration = Histogram(
    'artstore_file_download_duration_seconds',
    'File download duration in seconds',
    buckets=[0.5, 1, 5, 10, 30, 60]
)

file_operations_total = Counter(
    'artstore_file_operations_total',
    'Total file operations',
    ['operation', 'status']  # operation: upload|download|delete, status: success|failure
)

# Database Metrics
db_connections_active = Gauge(
    'artstore_db_connections_active',
    'Active database connections'
)

db_connections_total = Gauge(
    'artstore_db_connections_total',
    'Total database connection pool size'
)

db_query_duration = Histogram(
    'artstore_db_query_duration_seconds',
    'Database query duration',
    ['query_type']  # query_type: select|insert|update|delete
)

# Redis Metrics
redis_master_election = Gauge(
    'artstore_redis_master_election',
    'Master election status (1 = is master, 0 = is replica)'
)

# Usage Example in FastAPI endpoint
@app.post("/api/v1/files/upload")
async def upload_file(...):
    start_time = time.time()

    try:
        # File upload logic
        result = await perform_upload(...)

        # Record success
        file_operations_total.labels(operation='upload', status='success').inc()
        file_upload_duration.observe(time.time() - start_time)
        files_total.inc()
        storage_bytes_used.inc(file_size)

        return result

    except Exception as e:
        # Record failure
        file_operations_total.labels(operation='upload', status='failure').inc()
        raise
```

---

### 7.2 Structured Logging

```python
import logging
import json
from datetime import datetime
from typing import Any, Dict

class StructuredLogger:
    """
    Structured JSON logger для операционных логов.
    """
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.logger = logging.getLogger(service_name)

    def log(
        self,
        level: str,
        message: str,
        context: Dict[str, Any] | None = None,
        **kwargs
    ):
        """
        Логирование структурированного сообщения.
        """
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "service": self.service_name,
            "level": level.upper(),
            "message": message,
            "context": context or {},
            **kwargs
        }

        # Serialize to JSON
        log_json = json.dumps(log_entry, ensure_ascii=False)

        # Output to appropriate level
        if level == "debug":
            self.logger.debug(log_json)
        elif level == "info":
            self.logger.info(log_json)
        elif level == "warning":
            self.logger.warning(log_json)
        elif level == "error":
            self.logger.error(log_json)
        elif level == "critical":
            self.logger.critical(log_json)

    def log_file_operation(
        self,
        operation: str,
        file_id: str,
        username: str,
        status: str,
        **kwargs
    ):
        """
        Специализированное логирование file operations.
        """
        self.log(
            "info",
            f"File operation: {operation}",
            context={
                "operation": operation,
                "file_id": file_id,
                "username": username,
                "status": status
            },
            **kwargs
        )

# Usage Example
logger = StructuredLogger("storage-element")

logger.log_file_operation(
    operation="upload",
    file_id="a1b2c3d4",
    username="ivanov",
    status="success",
    file_size=1048576,
    duration_ms=1234
)

# Output:
# {
#   "timestamp": "2025-11-08T10:30:45Z",
#   "service": "storage-element",
#   "level": "INFO",
#   "message": "File operation: upload",
#   "context": {
#     "operation": "upload",
#     "file_id": "a1b2c3d4",
#     "username": "ivanov",
#     "status": "success"
#   },
#   "file_size": 1048576,
#   "duration_ms": 1234
# }
```

---

## 8. Configuration Management

### 8.1 Configuration Schema (YAML)

```yaml
# storage-element/config.yaml
app:
  name: "storage-element"
  version: "1.0.0"
  debug: false
  mode: "edit"  # edit, rw, ro, ar
  rebuild_cache_on_startup: false

server:
  host: "0.0.0.0"
  port: 8010
  workers: 1

database:
  host: "postgres"
  port: 5432
  username: "artstore"
  password: "password"
  database: "artstore"
  table_prefix: "storage_elem_01"
  pool_size: 10
  max_overflow: 20
  pool_timeout: 30
  pool_recycle: 3600

redis:
  sentinel_hosts:
    - host: "redis-sentinel-1"
      port: 26379
    - host: "redis-sentinel-2"
      port: 26379
    - host: "redis-sentinel-3"
      port: 26379
  master_name: "artstore-master"
  db: 0
  password: null
  master_election:
    key_prefix: "storage_master"
    ttl: 30
    check_interval: 10

storage:
  type: "local"  # local, s3
  max_size: "1GB"
  retention_period_days: 365
  warning_threshold_days: 90
  local:
    base_path: "/app/data/storage"
  s3:
    endpoint_url: "http://minio:9000"
    access_key_id: "minioadmin"
    secret_access_key: "minioadmin"
    bucket_name: "artstore-files"
    region: "us-east-1"
    app_folder: "storage_element_01"

auth:
  mode: "local"  # local, LDAP, OAuth2
  jwt:
    public_key_path: "/app/keys/public_key.pem"
    algorithm: "RS256"

logging:
  level: "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
  format: "json"  # json, text
  handlers:
    console:
      enabled: true
    file:
      enabled: false
      path: "/app/logs/storage-element.log"
      max_bytes: 104857600  # 100MB
      backup_count: 5

metrics:
  enabled: true
  path: "/metrics"

health:
  liveness_path: "/health/live"
  readiness_path: "/health/ready"

admin:
  enabled: true
  path: "/admin"
```

---

### 8.2 Configuration Loader with Environment Variables

```python
import os
import yaml
from pathlib import Path
from typing import Any, Dict
from pydantic import BaseSettings, Field

class AppConfig(BaseSettings):
    """
    Configuration с приоритетом: Environment Variables > YAML file.
    """
    # App Settings
    app_name: str = Field(default="storage-element", env="APP_NAME")
    app_version: str = Field(default="1.0.0", env="APP_VERSION")
    app_debug: bool = Field(default=False, env="APP_DEBUG")
    app_mode: str = Field(default="edit", env="APP_MODE")

    # Server Settings
    server_host: str = Field(default="0.0.0.0", env="SERVER_HOST")
    server_port: int = Field(default=8010, env="SERVER_PORT")
    server_workers: int = Field(default=1, env="SERVER_WORKERS")

    # Database Settings
    db_host: str = Field(default="postgres", env="DB_HOST")
    db_port: int = Field(default=5432, env="DB_PORT")
    db_username: str = Field(default="artstore", env="DB_USERNAME")
    db_password: str = Field(default="password", env="DB_PASSWORD")
    db_database: str = Field(default="artstore", env="DB_DATABASE")
    db_table_prefix: str = Field(default="storage_elem_01", env="DB_TABLE_PREFIX")
    db_pool_size: int = Field(default=10, env="DB_POOL_SIZE")

    # Storage Settings
    storage_type: str = Field(default="local", env="STORAGE_TYPE")
    storage_max_size: str = Field(default="1GB", env="STORAGE_MAX_SIZE")
    storage_base_path: str = Field(default="/app/data/storage", env="STORAGE_BASE_PATH")

    # Auth Settings
    jwt_public_key_path: str = Field(default="/app/keys/public_key.pem", env="JWT_PUBLIC_KEY_PATH")

    class Config:
        env_file = ".env"
        case_sensitive = False

def load_config(config_file: str | None = None) -> Dict[str, Any]:
    """
    Загрузка конфигурации из YAML с override через environment variables.
    """
    # 1. Load from YAML file
    config = {}
    if config_file and Path(config_file).exists():
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)

    # 2. Override with environment variables through Pydantic
    app_config = AppConfig()

    # 3. Merge configurations
    final_config = {
        "app": {
            "name": app_config.app_name,
            "version": app_config.app_version,
            "debug": app_config.app_debug,
            "mode": app_config.app_mode
        },
        "server": {
            "host": app_config.server_host,
            "port": app_config.server_port,
            "workers": app_config.server_workers
        },
        "database": {
            "host": app_config.db_host,
            "port": app_config.db_port,
            "username": app_config.db_username,
            "password": app_config.db_password,
            "database": app_config.db_database,
            "table_prefix": app_config.db_table_prefix,
            "pool_size": app_config.db_pool_size
        },
        "storage": {
            "type": app_config.storage_type,
            "max_size": app_config.storage_max_size,
            "local": {
                "base_path": app_config.storage_base_path
            }
        },
        "auth": {
            "jwt": {
                "public_key_path": app_config.jwt_public_key_path
            }
        }
    }

    return final_config
```

---

## 9. Project Structure

```
storage-element/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI application entry point
│   ├── config.py                # Configuration management
│   ├── models/
│   │   ├── __init__.py
│   │   ├── file_metadata.py     # SQLAlchemy models
│   │   └── config.py            # Pydantic models for config
│   ├── api/
│   │   ├── __init__.py
│   │   ├── health.py            # Health check endpoints
│   │   ├── files.py             # File operations endpoints
│   │   ├── admin.py             # Admin endpoints
│   │   └── coordination.py     # Coordination & Saga endpoints
│   ├── core/
│   │   ├── __init__.py
│   │   ├── security.py          # JWT validation, RBAC
│   │   ├── file_operations.py  # File naming, atomic write
│   │   ├── storage.py           # Storage backend (local/S3)
│   │   ├── database.py          # Database connection, cache
│   │   ├── redis_client.py      # Redis Sentinel client
│   │   └── saga.py              # Saga participant logic
│   ├── services/
│   │   ├── __init__.py
│   │   ├── upload_service.py    # Upload workflow
│   │   ├── search_service.py    # Search implementation
│   │   └── reconcile_service.py # Reconciliation logic
│   └── utils/
│       ├── __init__.py
│       ├── logging.py           # Structured logger
│       └── metrics.py           # Prometheus metrics
├── tests/
│   ├── __init__.py
│   ├── test_file_operations.py
│   ├── test_api.py
│   └── test_security.py
├── config.yaml                  # Default configuration
├── requirements.txt             # Python dependencies
├── Dockerfile                   # Docker image
├── docker-compose.yml           # Local development
├── README.md                    # Module documentation
└── DESIGN.md                    # This file

```

---

## 10. Implementation Roadmap

### Phase 1: Core Infrastructure (Week 1)
- [x] Project structure setup
- [x] Configuration management (YAML + env vars)
- [x] Database schema creation
- [x] Health check endpoints
- [ ] Structured logging
- [ ] Prometheus metrics

### Phase 2: File Operations (Week 1-2)
- [ ] File naming utility implementation
- [ ] Atomic attr.json write
- [ ] Local filesystem storage backend
- [ ] Basic file upload (without Saga)
- [ ] File download with resumable support
- [ ] File metadata retrieval

### Phase 3: Security & Auth (Week 2)
- [ ] JWT RS256 validation
- [ ] RBAC permission checking
- [ ] FastAPI dependencies for auth
- [ ] API endpoint protection

### Phase 4: Advanced Features (Week 2-3)
- [ ] PostgreSQL Full-Text Search
- [ ] Storage modes implementation
- [ ] Mode transition state machine
- [ ] Redis Sentinel integration
- [ ] Master election logic

### Phase 5: Saga Integration (Week 3)
- [ ] Saga participant implementation
- [ ] Upload Saga workflow
- [ ] Compensating actions
- [ ] WAL logging

### Phase 6: Testing & Documentation (Week 3-4)
- [ ] Unit tests (coverage >80%)
- [ ] Integration tests
- [ ] API documentation (OpenAPI)
- [ ] Deployment guide

---

## Приложения

### A. OpenAPI Specification

Полная OpenAPI спецификация будет сгенерирована автоматически через FastAPI и доступна по адресу:
- Swagger UI: `http://localhost:8010/docs`
- ReDoc: `http://localhost:8010/redoc`
- OpenAPI JSON: `http://localhost:8010/openapi.json`

### B. Environment Variables Reference

```bash
# App Configuration
APP_NAME=storage-element
APP_VERSION=1.0.0
APP_DEBUG=false
APP_MODE=edit

# Server
SERVER_HOST=0.0.0.0
SERVER_PORT=8010
SERVER_WORKERS=1

# Database
DB_HOST=postgres
DB_PORT=5432
DB_USERNAME=artstore
DB_PASSWORD=password
DB_DATABASE=artstore
DB_TABLE_PREFIX=storage_elem_01
DB_POOL_SIZE=10

# Storage
STORAGE_TYPE=local
STORAGE_MAX_SIZE=1GB
STORAGE_BASE_PATH=/app/data/storage

# Auth
JWT_PUBLIC_KEY_PATH=/app/keys/public_key.pem

# Redis
REDIS_SENTINEL_HOSTS=redis-sentinel-1:26379,redis-sentinel-2:26379,redis-sentinel-3:26379
REDIS_MASTER_NAME=artstore-master
```

---

**Документ утвержден**: 2025-11-08
**Версия**: 1.0
**Следующий шаг**: Начать implementation Phase 1
