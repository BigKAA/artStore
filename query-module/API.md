# Query Module - API Reference

> Версия API: v1
> Base URL: `http://{host}:8030`

---

## Содержание

- [Аутентификация](#аутентификация)
- [Search API](#search-api)
  - [POST /api/search](#post-apisearch)
  - [GET /api/search/{file_id}](#get-apisearchfile_id)
- [Download API](#download-api)
  - [GET /api/download/{file_id}](#get-apidownloadfile_id)
  - [GET /api/download/{file_id}/metadata](#get-apidownloadfile_idmetadata)
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

## Search API

### POST /api/search

Поиск файлов с Full-Text Search и фильтрацией.

**Content-Type:** `application/json`

#### Тело запроса (SearchRequest)

| Поле | Тип | Обязательный | Описание |
|------|-----|--------------|----------|
| `query` | string | ❌ | Поисковый запрос (filename, tags, description) |
| `filename` | string | ❌ | Имя файла для поиска |
| `file_extension` | string | ❌ | Расширение файла (.pdf, .jpg и т.д.) |
| `tags` | string[] | ❌ | Список тегов для поиска (max 50) |
| `username` | string | ❌ | Фильтр по имени пользователя |
| `min_size` | integer | ❌ | Минимальный размер файла (bytes) |
| `max_size` | integer | ❌ | Максимальный размер файла (bytes) |
| `created_after` | datetime | ❌ | Файлы созданные после указанной даты |
| `created_before` | datetime | ❌ | Файлы созданные до указанной даты |
| `mode` | string | ❌ | Режим поиска: `exact`, `partial`, `fulltext` (default: `partial`) |
| `limit` | integer | ❌ | Максимум результатов (1-1000, default: 100) |
| `offset` | integer | ❌ | Смещение для пагинации (default: 0) |
| `sort_by` | string | ❌ | Поле сортировки: `created_at`, `updated_at`, `file_size`, `filename`, `relevance` |
| `sort_order` | string | ❌ | Порядок: `asc`, `desc` (default: `desc`) |

#### Режимы поиска (mode)

| Режим | Описание |
|-------|----------|
| `exact` | Точное совпадение |
| `partial` | Частичное совпадение (LIKE queries) |
| `fulltext` | Full-Text Search (PostgreSQL GIN) |

#### Пример запроса

```bash
curl -X POST http://localhost:8030/api/search \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "contract",
    "mode": "partial",
    "tags": ["important"],
    "min_size": 1024,
    "limit": 50,
    "sort_by": "created_at",
    "sort_order": "desc"
  }'
```

#### Ответ 200 OK (SearchResponse)

```json
{
  "results": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "filename": "contract_2025.pdf",
      "storage_filename": "contract_2025_550e8400.pdf",
      "file_size": 1048576,
      "mime_type": "application/pdf",
      "sha256_hash": "a1b2c3d4e5f6...",
      "username": "user123",
      "tags": ["important", "legal"],
      "description": "Annual contract",
      "created_at": "2025-01-27T14:30:45Z",
      "updated_at": "2025-01-27T14:30:45Z",
      "storage_element_id": "se-01",
      "relevance_score": 0.95
    }
  ],
  "total_count": 150,
  "limit": 50,
  "offset": 0,
  "has_more": true
}
```

#### Ошибки

| Код | Описание |
|-----|----------|
| 400 | Невалидные параметры поиска |
| 401 | Не авторизован |
| 504 | Таймаут поиска |
| 500 | Внутренняя ошибка сервера |

---

### GET /api/search/{file_id}

Получение метаданных файла по ID.

#### Параметры пути

| Параметр | Тип | Описание |
|----------|-----|----------|
| `file_id` | UUID | ID файла |

#### Пример запроса

```bash
curl http://localhost:8030/api/search/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer $TOKEN"
```

#### Ответ 200 OK (FileMetadataResponse)

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "contract_2025.pdf",
  "storage_filename": "contract_2025_550e8400.pdf",
  "file_size": 1048576,
  "mime_type": "application/pdf",
  "sha256_hash": "a1b2c3d4e5f6...",
  "username": "user123",
  "tags": ["important", "legal"],
  "description": "Annual contract",
  "created_at": "2025-01-27T14:30:45Z",
  "updated_at": "2025-01-27T14:30:45Z",
  "storage_element_id": "se-01",
  "relevance_score": null
}
```

#### Ошибки

| Код | Описание |
|-----|----------|
| 401 | Не авторизован |
| 404 | Файл не найден |
| 500 | Внутренняя ошибка сервера |

---

## Download API

### GET /api/download/{file_id}

Скачивание файла с поддержкой resumable downloads.

#### Параметры пути

| Параметр | Тип | Описание |
|----------|-----|----------|
| `file_id` | UUID | ID файла |

#### HTTP Headers (опционально)

| Header | Описание |
|--------|----------|
| `Range` | HTTP Range для resumable download (format: `bytes=start-end`) |

#### Пример запроса

```bash
# Полное скачивание
curl -O http://localhost:8030/api/download/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer $TOKEN"

# Resumable download (с 1MB)
curl -O http://localhost:8030/api/download/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Range: bytes=1048576-"
```

#### Ответ 200 OK / 206 Partial Content

**Headers:**
```http
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="contract_2025.pdf"
Accept-Ranges: bytes
```

**Body:** Binary file stream

#### Ошибки

| Код | Описание |
|-----|----------|
| 401 | Не авторизован |
| 404 | Файл не найден |
| 416 | Range not satisfiable |
| 503 | Storage Element недоступен |
| 500 | Ошибка скачивания |

---

### GET /api/download/{file_id}/metadata

Получение метаданных файла для скачивания.

#### Параметры пути

| Параметр | Тип | Описание |
|----------|-----|----------|
| `file_id` | UUID | ID файла |

#### Пример запроса

```bash
curl http://localhost:8030/api/download/550e8400-e29b-41d4-a716-446655440000/metadata \
  -H "Authorization: Bearer $TOKEN"
```

#### Ответ 200 OK (DownloadMetadata)

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "contract_2025.pdf",
  "file_size": 1048576,
  "mime_type": "application/pdf",
  "sha256_hash": "a1b2c3d4e5f6...",
  "created_at": "2025-01-27T14:30:45Z",
  "storage_element_id": "se-01",
  "storage_element_url": "http://se-01:8010",
  "download_url": null,
  "supports_range_requests": true
}
```

#### Ошибки

| Код | Описание |
|-----|----------|
| 401 | Не авторизован |
| 404 | Файл не найден |
| 503 | Storage Element недоступен |

---

## Health API

> **Base URL:** `http://{host}:8030` (без `/api`)

### GET /health/live

Liveness probe — проверка что приложение запущено.

#### Ответ 200 OK

```json
{
  "status": "alive"
}
```

---

### GET /health/ready

Readiness probe — проверка готовности принимать трафик.

Проверяет:
- PostgreSQL database
- Redis cache (non-critical)

#### Ответ 200 OK

```json
{
  "status": "ready",
  "database": "healthy",
  "cache": "healthy"
}
```

#### Ответ 200 OK (degraded)

```json
{
  "status": "ready",
  "database": "healthy",
  "cache": "degraded"
}
```

#### Ответ 503 Service Unavailable

```json
{
  "status": "not_ready",
  "database": "unhealthy",
  "cache": "healthy"
}
```

---

## Модели данных

### SearchMode

```
exact | partial | fulltext
```

### SortField

```
created_at | updated_at | file_size | filename | relevance
```

### SortOrder

```
asc | desc
```

### SearchRequest

```typescript
{
  query?: string              // max 500 chars
  filename?: string           // max 255 chars
  file_extension?: string     // max 10 chars
  tags?: string[]             // max 50 tags
  username?: string
  min_size?: integer          // bytes, >= 0
  max_size?: integer          // bytes, >= 0
  created_after?: datetime
  created_before?: datetime
  mode?: SearchMode           // default: partial
  limit?: integer             // 1-1000, default: 100
  offset?: integer            // default: 0
  sort_by?: SortField         // default: created_at
  sort_order?: SortOrder      // default: desc
}
```

### FileMetadataResponse

```typescript
{
  id: string                  // UUID
  filename: string
  storage_filename: string
  file_size: integer          // bytes
  mime_type?: string
  sha256_hash: string
  username: string
  tags?: string[]
  description?: string
  created_at: datetime
  updated_at: datetime
  storage_element_id: string
  relevance_score?: float     // 0.0-1.0
}
```

### SearchResponse

```typescript
{
  results: FileMetadataResponse[]
  total_count: integer
  limit: integer
  offset: integer
  has_more: boolean
}
```

### DownloadMetadata

```typescript
{
  id: string                    // UUID
  filename: string
  file_size: integer            // bytes
  mime_type?: string
  sha256_hash: string
  created_at: datetime
  storage_element_id: string
  storage_element_url: string
  download_url?: string
  supports_range_requests: boolean
}
```

### RangeRequest

```typescript
{
  start: integer              // >= 0
  end?: integer               // >= 0, optional
}
```

---

## Коды ошибок

| HTTP Code | Описание |
|-----------|----------|
| 200 | Успешный запрос |
| 206 | Partial Content (Range request) |
| 400 | Невалидные параметры запроса |
| 401 | Требуется аутентификация |
| 404 | Ресурс не найден |
| 416 | Range not satisfiable |
| 500 | Внутренняя ошибка сервера |
| 503 | Сервис недоступен |
| 504 | Gateway timeout |

### Формат ошибки

```json
{
  "detail": "Error message description"
}
```
