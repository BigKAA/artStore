# Storage Element API Reference

**Base URL**: Все API endpoints доступны по префиксу `/api/v1/`

## File Operations (`/api/v1/files/*`)

```
POST /api/v1/files/upload
  - Chunked upload с streaming
  - Input: multipart/form-data (file + metadata JSON)
  - Output: {"file_id": "uuid", "storage_filename": "...", "size_bytes": 123}
  - Режимы: edit, rw

GET /api/v1/files/{file_id}
  - Метаданные файла
  - Output: Полный attr.json content
  - Режимы: edit, rw, ro, ar

GET /api/v1/files/{file_id}/download
  - Скачивание файла
  - Resumable download (Range requests RFC 7233)
  - Output: File stream
  - Режимы: edit, rw, ro (ar требует restore)

PATCH /api/v1/files/{file_id}
  - Обновление метаданных файла
  - Input: {"description": "...", "tags": [...]}
  - Режимы: edit, rw

DELETE /api/v1/files/{file_id}
  - Удаление файла
  - Режимы: только edit

GET /api/v1/files/
  - Поиск и листинг файлов
  - Query params: search_query, uploaded_by, min_size, max_size,
                  uploaded_after, uploaded_before, tags, limit, offset
  - Режимы: все
```

## System Information (`/api/v1/info`)

```
GET /api/v1/info
  - Полная информация о Storage Element для auto-discovery
  - Используется Admin Module для автоматической регистрации и синхронизации
  - Output: {
      "name": "storage-element",
      "display_name": "Storage Element 01",
      "version": "1.0.0",
      "mode": "edit",
      "storage_type": "local",
      "base_path": "/data/storage",
      "capacity_bytes": 1099511627776,
      "used_bytes": 549755813888,
      "file_count": 1234,
      "status": "operational"
    }
  - Не требует авторизации
```

## Capacity Information (`/api/v1/capacity`)

```
GET /api/v1/capacity
  - Информация о емкости для adaptive polling (Ingester Module)
  - Output: {
      "element_id": "se-01",
      "mode": "rw",
      "capacity_total": 1099511627776,
      "capacity_used": 549755813888,
      "capacity_free": 549755813888,
      "capacity_percent": 50.0,
      "status": "ok"
    }
  - Не требует авторизации
```

## Garbage Collector Operations (`/api/v1/gc/*`)

Endpoints для системного Garbage Collector (только Service Accounts):

```
DELETE /api/v1/gc/{file_id}
  - Физическое удаление файла из хранилища
  - Используется GC после подтверждения удаления из всех систем
  - Требует: Service Account с ролью ADMIN

GET /api/v1/gc/{file_id}/exists
  - Проверка существования файла
  - Output: {"exists": true/false, "file_id": "..."}
  - Требует: Service Account
```

## Cache Management (`/api/v1/cache/*`)

Endpoints для управления кешем метаданных (см. раздел [Cache Synchronization](README.md#cache-synchronization-v120) в README):

```
POST /api/v1/cache/rebuild
  - Полная пересборка кеша из attr.json файлов
  - Требует: Service Account с ролью ADMIN

POST /api/v1/cache/rebuild/incremental
  - Инкрементальная пересборка (только новые файлы)
  - Требует: Service Account с ролью ADMIN

GET /api/v1/cache/consistency
  - Проверка консистентности кеша (dry-run)
  - Требует: Service Account с ролью ADMIN

POST /api/v1/cache/cleanup-expired
  - Очистка expired записей кеша
  - Требует: Service Account с ролью ADMIN
```

## Health & Monitoring

```
GET /health/live
  - Liveness probe (Kubernetes)
  - Output: {"status": "ok", "timestamp": "...", "checks": {"process": "running"}}

GET /health/ready
  - Readiness probe
  - Проверяет: storage accessibility (S3 bucket/local filesystem)
  - Output: {"status": "ready/not_ready", "timestamp": "...", "checks": {...}}
  - HTTP 200 если готов, HTTP 503 если не готов

GET /metrics
  - Prometheus metrics
```

## Важные замечания

**Mode определяется ТОЛЬКО конфигурацией** storage element при запуске.
Admin Module использует endpoint `/api/v1/info` для получения актуальной информации,
но **НЕ МОЖЕТ изменять mode** через API.

## Аутентификация

Все protected endpoints требуют Bearer token в заголовке:

```bash
Authorization: Bearer <JWT_TOKEN>
```

Подробнее см. [Аутентификация и RBAC](README.md#аутентификация-и-rbac) в README.
