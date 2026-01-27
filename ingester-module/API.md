# Ingester Module - API Reference

> Версия API: v1
> Base URL: `http://{host}:8020/api/v1`

---

## Содержание

- [Аутентификация](#аутентификация)
- [Upload API](#upload-api)
  - [POST /files/upload](#post-filesupload)
  - [GET /files/](#get-files)
- [Finalize API](#finalize-api)
  - [POST /finalize/{file_id}](#post-finalizefile_id)
  - [GET /finalize/{transaction_id}/status](#get-finalizetransaction_idstatus)
- [Health API](#health-api)
  - [GET /health/live](#get-healthlive)
  - [GET /health/ready](#get-healthready)
- [Модели данных](#модели-данных)
- [Коды ошибок](#коды-ошибок)

---

## Аутентификация

Все endpoints (кроме `/health/*`) требуют JWT Bearer token.

```http
Authorization: Bearer <jwt_token>
```

Получение токена — через Admin Module OAuth 2.0:

```bash
curl -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"client_id": "...", "client_secret": "..."}'
```

---

## Upload API

### POST /files/upload

Загрузка файла в Storage Element.

**Content-Type:** `multipart/form-data`

#### Параметры формы

| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| `file` | binary | ✅ | Файл для загрузки |
| `retention_policy` | string | ❌ | `temporary` (default) или `permanent` |
| `ttl_days` | integer | ❌ | TTL в днях для temporary файлов (1-365, default: 30) |
| `description` | string | ❌ | Описание файла (max 1000 символов) |
| `compress` | boolean | ❌ | Включить сжатие (default: false) |
| `compression_algorithm` | string | ❌ | `gzip` (default) или `brotli` |
| `metadata` | string | ❌ | JSON-строка с пользовательскими метаданными |

#### Retention Policy

| Значение | Storage Element | Описание |
|----------|-----------------|----------|
| `temporary` | Edit SE | Временные файлы с автоматическим TTL. Можно финализировать через `/finalize`. |
| `permanent` | RW SE | Постоянное хранение без автоматического удаления. |

#### Пример запроса

```bash
curl -X POST http://localhost:8020/api/v1/files/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@document.pdf" \
  -F "retention_policy=temporary" \
  -F "ttl_days=30" \
  -F "description=Quarterly report draft" \
  -F 'metadata={"department": "finance", "version": "1.0"}'
```

#### Ответ 201 Created

```json
{
  "file_id": "550e8400-e29b-41d4-a716-446655440000",
  "original_filename": "document.pdf",
  "storage_filename": "document_20250127T143045_550e8400.pdf",
  "file_size": 1048576,
  "compressed": false,
  "compression_ratio": null,
  "checksum": "sha256:a1b2c3d4e5f6...",
  "uploaded_at": "2025-01-27T14:30:45Z",
  "storage_element_url": "http://se-01:8010",
  "retention_policy": "temporary",
  "ttl_expires_at": "2025-02-26T14:30:45Z",
  "storage_element_id": "se-01"
}
```

#### Ошибки

| Код | Описание |
|-----|----------|
| 400 | Невалидные параметры (JSON metadata, retention_policy) |
| 401 | Невалидный или истёкший токен |
| 503 | Storage Element недоступен |

---

### GET /files/

Получить список загруженных файлов.

> ⚠️ **Статус:** Not implemented (stub endpoint)

#### Ответ 200 OK

```json
{
  "message": "Not implemented yet",
  "user": "username"
}
```

---

## Finalize API

Two-Phase Commit процесс для переноса temporary файлов из Edit SE в RW SE.

### POST /finalize/{file_id}

Запуск финализации temporary файла.

#### Параметры пути

| Параметр | Тип | Описание |
|----------|-----|----------|
| `file_id` | UUID | ID файла для финализации |

#### Тело запроса (опционально)

```json
{
  "target_storage_element_id": "se-02",
  "description": "Updated description",
  "metadata": {"finalized_by": "user123"}
}
```

| Поле | Тип | Описание |
|------|-----|----------|
| `target_storage_element_id` | string | ID целевого RW SE (auto-select если не указан) |
| `description` | string | Обновлённое описание файла |
| `metadata` | object | Обновлённые метаданные |

#### Пример запроса

```bash
curl -X POST http://localhost:8020/api/v1/finalize/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"description": "Final version"}'
```

#### Ответ 202 Accepted

```json
{
  "transaction_id": "660e8400-e29b-41d4-a716-446655440001",
  "file_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "copying",
  "source_storage_element_id": "se-01",
  "target_storage_element_id": "se-02",
  "checksum_verified": false,
  "finalized_at": null,
  "new_storage_path": null,
  "cleanup_scheduled_at": null,
  "error_message": null
}
```

#### Ошибки

| Код | Описание |
|-----|----------|
| 400 | Файл не temporary или уже финализирован |
| 404 | Файл не найден в registry |
| 503 | Storage Element или Admin Module недоступен |

---

### GET /finalize/{transaction_id}/status

Получение статуса транзакции финализации.

#### Параметры пути

| Параметр | Тип | Описание |
|----------|-----|----------|
| `transaction_id` | UUID | ID транзакции финализации |

#### Пример запроса

```bash
curl http://localhost:8020/api/v1/finalize/660e8400-e29b-41d4-a716-446655440001/status \
  -H "Authorization: Bearer $TOKEN"
```

#### Ответ 200 OK

```json
{
  "transaction_id": "660e8400-e29b-41d4-a716-446655440001",
  "file_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "progress_percent": 100.0,
  "created_at": "2025-01-27T14:30:45Z",
  "completed_at": "2025-01-27T14:31:15Z",
  "error_message": null
}
```

#### Статусы транзакции

| Статус | Progress | Описание |
|--------|----------|----------|
| `copying` | 25% | Копирование файла на target SE |
| `copied` | 50% | Файл скопирован, ожидание верификации |
| `verifying` | 75% | Проверка checksum |
| `completed` | 100% | Успешная финализация |
| `failed` | 0% | Ошибка (см. `error_message`) |
| `rolled_back` | 0% | Транзакция откачена |

#### Ошибки

| Код | Описание |
|-----|----------|
| 404 | Транзакция не найдена |

---

## Health API

> **Base URL:** `http://{host}:8020` (без `/api/v1`)

### GET /health/live

Liveness probe — проверка что приложение запущено.

#### Ответ 200 OK

```json
{
  "status": "ok",
  "timestamp": "2025-01-27T14:30:45Z",
  "version": "0.1.0",
  "service": "artstore-ingester"
}
```

---

### GET /health/ready

Readiness probe — проверка готовности принимать трафик.

Проверяет:
- Redis (Service Discovery)
- Admin Module (fallback)
- Capacity Monitor
- Все writable Storage Elements (edit/rw)

#### Ответ 200 OK (status: ok или degraded)

```json
{
  "status": "ok",
  "timestamp": "2025-01-27T14:30:45Z",
  "checks": {
    "redis": "ok",
    "admin_module": "ok",
    "capacity_monitor": "ok",
    "storage_elements": "ok",
    "edit_storage": "ok"
  },
  "storage_elements": {
    "se-01": {
      "endpoint": "http://se-01:8010",
      "mode": "edit",
      "status": "ok"
    },
    "se-02": {
      "endpoint": "http://se-02:8010",
      "mode": "rw",
      "status": "ok"
    }
  },
  "capacity_monitor": {
    "instance_id": "ingester-1",
    "role": "leader",
    "running": true,
    "storage_elements_count": 2
  },
  "data_sources": {
    "polling_model": {
      "enabled": true,
      "description": "AdaptiveCapacityMonitor (POLLING)"
    },
    "admin_module": {
      "enabled": true,
      "description": "Admin Module Fallback API"
    },
    "fallback_chain": "POLLING → Admin Module"
  },
  "summary": {
    "total_se": 2,
    "healthy_se": 2,
    "health_percentage": 100.0
  }
}
```

#### Ответ 503 Service Unavailable (status: fail)

Возвращается когда критические компоненты недоступны.

#### Статусы

| Статус | HTTP Code | Описание |
|--------|-----------|----------|
| `ok` | 200 | Все компоненты работают |
| `degraded` | 200 | Часть SE недоступна, но работа возможна |
| `fail` | 503 | Service Discovery или все SE недоступны |

---

## Модели данных

### RetentionPolicy

```
temporary | permanent
```

### CompressionAlgorithm

```
none | gzip | brotli
```

### FinalizeTransactionStatus

```
copying | copied | verifying | completed | failed | rolled_back
```

### UploadResponse

```typescript
{
  file_id: UUID
  original_filename: string
  storage_filename: string
  file_size: integer (bytes)
  compressed: boolean
  compression_ratio: float | null
  checksum: string
  uploaded_at: datetime (ISO 8601)
  storage_element_url: string
  retention_policy: RetentionPolicy
  ttl_expires_at: datetime | null
  storage_element_id: string | null
}
```

### FinalizeResponse

```typescript
{
  transaction_id: UUID
  file_id: UUID
  status: FinalizeTransactionStatus
  source_storage_element_id: string
  target_storage_element_id: string
  checksum_verified: boolean
  finalized_at: datetime | null
  new_storage_path: string | null
  cleanup_scheduled_at: datetime | null
  error_message: string | null
}
```

### FinalizeStatus

```typescript
{
  transaction_id: UUID
  file_id: UUID
  status: FinalizeTransactionStatus
  progress_percent: float (0-100)
  created_at: datetime
  completed_at: datetime | null
  error_message: string | null
}
```

---

## Коды ошибок

| HTTP Code | Описание |
|-----------|----------|
| 200 | Успешный запрос |
| 201 | Ресурс создан (upload) |
| 202 | Запрос принят (finalize) |
| 400 | Невалидные параметры запроса |
| 401 | Требуется аутентификация |
| 404 | Ресурс не найден |
| 503 | Сервис недоступен |

### Формат ошибки

```json
{
  "detail": "Error message description"
}
```
