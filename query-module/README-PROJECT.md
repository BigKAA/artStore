# Query Module - Поиск и получение файлов ArtStore

## Назначение модуля

**Query Module Cluster** — это высокопроизводительный отказоустойчивый сервис для поиска и получения файлов, обеспечивающий:
- **PostgreSQL Full-Text Search** для мгновенного поиска по метаданным
- **Multi-level caching** (Local → Redis → PostgreSQL) для минимизации latency
- **Optimized file download** с resumable transfers и Range requests
- **Load balancing** между Storage Elements для распределения нагрузки
- **Circuit Breaker Pattern** для graceful degradation

## Ключевые возможности

### 1. Search Capabilities

#### PostgreSQL Full-Text Search
- **GIN indexes**: Мгновенный поиск по всем метаданным
- **Multi-field search**: Поиск по filename, template, custom metadata, tags
- **Boolean operators**: AND, OR, NOT для комплексных запросов
- **Fuzzy matching**: Поиск с опечатками (Levenshtein distance)
- **Date range filters**: Поиск файлов по дате загрузки и expiration

#### Real-time Search Features
- **Auto-complete**: Предиктивный поиск на основе популярных запросов
- **Search suggestions**: Recommended queries based on search history
- **Faceted search**: Фильтры по MIME type, size ranges, upload date, Storage Element

#### Advanced Filters
```
GET /api/files/search?q=contract&size_min=1mb&size_max=10mb&mime_type=application/pdf&uploaded_after=2025-01-01
```

### 2. Caching Strategy

#### Three-Level Cache
```
Request → Local Cache (in-memory) → Redis Cluster → PostgreSQL (source of truth)
```

**Level 1: Local Cache**
- **TTL**: 60 seconds
- **Size**: 1000 наиболее популярных queries
- **Eviction**: LRU (Least Recently Used)

**Level 2: Redis Cluster**
- **TTL**: 5 minutes
- **Partitioning**: По hash query string
- **Invalidation**: При обновлении файлов

**Level 3: PostgreSQL**
- **Query cache**: Built-in PostgreSQL query cache
- **Materialized views**: Для сложных агрегаций

### 3. File Download Optimization

#### Resumable Downloads
- **Range requests**: HTTP Range header support
- **Partial content**: 206 Partial Content responses
- **Chunk download**: Configurable chunk size

#### Compression
- **Accept-Encoding**: Brotli/GZIP support
- **On-the-fly compression**: Для текстовых файлов
- **Cache compressed**: Сохранение сжатых версий

#### Connection Pooling
- **HTTP/2 persistent connections**: К Storage Elements
- **Connection reuse**: Минимизация handshake overhead
- **Adaptive pooling**: Auto-scaling based on load

### 4. Load Balancing

#### Storage Element Selection
- **Least connections**: Выбор элемента с наименьшим количеством активных соединений
- **Response time**: Приоритет быстрым Storage Elements
- **Geographic proximity**: Опциональная привязка к ближайшему ЦОД
- **Health-based**: Автоматическое исключение недоступных элементов

#### Circuit Breaker Integration
- **Per-Storage-Element tracking**: Отдельный circuit breaker для каждого элемента
- **Automatic failover**: Переключение на доступные элементы
- **Health recovery**: Gradual re-enable после восстановления

## Технологический стек

### Backend Framework
- **Python 3.12+** с async/await
- **FastAPI** для REST API
- **Uvicorn** с uvloop
- **Pydantic** для валидации
- **aiohttp** для HTTP клиента к Storage Elements

### Database & Caching
- **PostgreSQL 15+** (asyncpg) для:
  - Метаданные файлов (replicated от Storage Elements)
  - Full-text search indexes (GIN)
  - Query result caching
- **Redis 7** (sync redis-py) для:
  - Distributed caching
  - Service Discovery subscription
  - Popular query caching

### Search & Indexing
- **PostgreSQL tsvector/tsquery**: Full-text search
- **pg_trgm extension**: Fuzzy matching
- **GIN indexes**: Для быстрого поиска

### Observability
- **OpenTelemetry**: Distributed tracing
- **Prometheus client**: Metrics export
- **Structured logging**: JSON format

## API Endpoints

### Search (`/api/files/search`)

```
GET /api/files/search
Query parameters:
- q: search query (full-text search)
- mime_type: MIME type filter
- size_min, size_max: size range in bytes
- uploaded_after, uploaded_before: date range
- storage_element_id: specific Storage Element
- template: custom template filter
- tags: comma-separated tag list
- page: page number (default 1)
- page_size: results per page (default 50, max 1000)
- sort: field to sort by (uploaded_at, size, filename)
- order: asc or desc

Response:
{
  "results": [
    {
      "file_id": "uuid",
      "filename": "report.pdf",
      "size_bytes": 1048576,
      "mime_type": "application/pdf",
      "storage_element_id": "uuid",
      "uploaded_at": "2025-01-02T15:30:45Z",
      "match_score": 0.95  # relevance score
    }
  ],
  "pagination": {
    "total": 1523,
    "page": 1,
    "page_size": 50,
    "total_pages": 31
  },
  "facets": {
    "mime_types": {"application/pdf": 800, "image/jpeg": 500},
    "size_ranges": {"0-1mb": 300, "1-10mb": 800, "10mb+": 423}
  }
}
```

### Auto-complete (`/api/files/autocomplete`)

```
GET /api/files/autocomplete?q=contr

Response:
{
  "suggestions": [
    {"query": "contract", "count": 450},
    {"query": "contractor", "count": 120},
    {"query": "contribution", "count": 85}
  ]
}
```

### File Metadata (`/api/files/{file_id}`)

```
GET /api/files/{file_id}

Response:
{
  "file_id": "uuid",
  "filename": "report.pdf",
  "size_bytes": 1048576,
  "mime_type": "application/pdf",
  "storage_element_id": "uuid",
  "storage_element_url": "https://storage1.example.com",
  "md5_hash": "...",
  "sha256_hash": "...",
  "uploaded_by": "ivanov",
  "uploaded_at": "2025-01-02T15:30:45Z",
  "retention_days": 1825,
  "expires_at": "2030-01-02T15:30:45Z",
  "template": "contract",
  "custom_metadata": {...}
}
```

### File Download (`/api/files/{file_id}/download`)

```
GET /api/files/{file_id}/download
Headers:
- Range: bytes=0-1023 (optional, для resumable download)
- Accept-Encoding: br, gzip (optional, для compression)

Response 200 или 206 Partial Content:
- Content-Type: application/pdf
- Content-Length: 1048576
- Content-Encoding: br (если compressed)
- Accept-Ranges: bytes
- ETag: "sha256-hash"
- Last-Modified: Wed, 02 Jan 2025 15:30:45 GMT

Binary file data stream
```

### Health & Monitoring

```
GET /health/live
GET /health/ready
GET /metrics
```

## Внутренняя архитектура

```
query-module/
├── app/
│   ├── main.py
│   ├── core/
│   │   ├── config.py
│   │   ├── security.py
│   │   └── exceptions.py
│   ├── api/
│   │   └── v1/
│   │       └── endpoints/
│   │           ├── search.py         # Search endpoints
│   │           ├── files.py          # File metadata & download
│   │           ├── autocomplete.py   # Auto-complete
│   │           └── health.py
│   ├── schemas/
│   │   ├── search.py                 # Search request/response schemas
│   │   └── file.py
│   ├── services/
│   │   ├── search_service.py         # Full-text search logic
│   │   ├── cache_service.py          # Multi-level caching
│   │   ├── download_service.py       # File download coordination
│   │   ├── storage_client.py         # HTTP client для Storage Elements
│   │   ├── service_discovery.py      # Redis pub/sub subscription
│   │   ├── load_balancer.py          # Storage Element load balancing
│   │   └── circuit_breaker.py        # Circuit breaker per Storage Element
│   └── utils/
│       ├── query_parser.py           # Parse search queries
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

```bash
# Database
DATABASE_URL=postgresql+asyncpg://artstore:password@localhost:5432/artstore

# Redis
REDIS_URL=redis://localhost:6379/1
SERVICE_DISCOVERY_CHANNEL=artstore:storage-elements

# Caching
LOCAL_CACHE_SIZE=1000
LOCAL_CACHE_TTL_SECONDS=60
REDIS_CACHE_TTL_SECONDS=300

# Search
SEARCH_DEFAULT_PAGE_SIZE=50
SEARCH_MAX_PAGE_SIZE=1000
FUZZY_SEARCH_ENABLED=true
AUTOCOMPLETE_MIN_CHARS=3

# Download
DOWNLOAD_CHUNK_SIZE_MB=10
COMPRESSION_ENABLED=true
RANGE_REQUESTS_ENABLED=true

# Load Balancing
LOAD_BALANCE_STRATEGY=least_connections  # least_connections, round_robin, response_time
STORAGE_HEALTH_CHECK_INTERVAL_SECONDS=30

# Circuit Breaker
CIRCUIT_BREAKER_ENABLED=true
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
CIRCUIT_BREAKER_SUCCESS_THRESHOLD=2
CIRCUIT_BREAKER_TIMEOUT_SECONDS=60

# Monitoring
OPENTELEMETRY_ENABLED=true
PROMETHEUS_METRICS_ENABLED=true
```

## Тестирование

```bash
# Unit tests
pytest query-module/tests/unit/ -v --cov=app

# Integration tests
pytest query-module/tests/integration/ -v
```

## Мониторинг и метрики

### Prometheus Metrics (`/metrics`)

#### Custom Business Metrics
- `artstore_query_search_requests_total`: Количество поисковых запросов
- `artstore_query_search_duration_seconds`: Search latency
- `artstore_query_cache_hits_total`: Cache hit rate (local/redis)
- `artstore_query_downloads_total`: Количество downloads
- `artstore_query_download_duration_seconds`: Download latency
- `artstore_query_storage_response_time_seconds`: Response time от Storage Elements

### OpenTelemetry Tracing

- `artstore.query.search` - Полный поисковый запрос
- `artstore.query.cache_lookup` - Cache lookup operations
- `artstore.query.download` - File download coordination

## Troubleshooting

### Проблемы с поиском

**Проблема**: Медленный поиск
**Решение**: Проверить GIN indexes существуют. Проверить `ANALYZE` и `VACUUM` PostgreSQL.

**Проблема**: Irrelevant search results
**Решение**: Настроить relevance weighting в query parser. Добавить boost для specific fields.

### Проблемы с кешированием

**Проблема**: Low cache hit rate
**Решение**: Увеличить `LOCAL_CACHE_SIZE` и `REDIS_CACHE_TTL_SECONDS`. Analyze query patterns.

**Проблема**: Stale cache data
**Решение**: Проверить cache invalidation logic при обновлениях файлов.

## Security Considerations

### Production Checklist

- [ ] JWT validation на всех endpoints
- [ ] Query sanitization для предотвращения SQL injection
- [ ] Rate limiting для защиты от search abuse
- [ ] TLS 1.3 для соединений к Storage Elements
- [ ] Audit logging всех file downloads
- [ ] Access control на file-level (через JWT claims)

## Ссылки на документацию

- [Главная документация проекта](../README-PROJECT.md)
- [Storage Element documentation](../storage-element/README-PROJECT.md)
- [PostgreSQL Full-Text Search](https://www.postgresql.org/docs/current/textsearch.html)
