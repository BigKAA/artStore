# Критически важные концепции ArtStore

## 🔴 Абсолютные требования

### 1. Docker Compose ТОЛЬКО из корня проекта

**ОБЯЗАТЕЛЬНОЕ ПРАВИЛО №1:**
```bash
# ✅ ВСЕГДА делать так:
cd /home/artur/Projects/artStore
docker-compose up -d <module-name>

# ❌ НИКОГДА не делать:
cd admin-module
docker-compose up -d  # НЕ ДЕЛАТЬ ТАК!
```

**Почему критично:**
- Корневой docker-compose.yml управляет всей системой
- Модули зависят от общих сервисов (PostgreSQL, Redis, MinIO)
- Неправильный запуск приведет к ошибкам сети и зависимостей

### 2. Attribute-First Storage Model

**Файлы `*.attr.json` - единственный источник истины для метаданных**

**Consistency Protocol (порядок СТРОГО обязателен):**
1. Write-Ahead Log (WAL) - запись намерения
2. Временный файл создается
3. `fsync` для гарантии записи
4. Atomic rename в `*.attr.json`
5. Database cache обновляется
6. Service Discovery уведомляется
7. Commit WAL

**Rollback при любом сбое!**

**Пример attr.json:**
```json
{
  "file_id": "uuid",
  "filename": "document.pdf",
  "content_type": "application/pdf",
  "size_bytes": 1024,
  "checksum": "sha256-hash",
  "storage_element_id": "se-001",
  "created_at": "2024-01-01T00:00:00Z"
}
```

### 3. JWT RS256 Authentication

**ТОЛЬКО асимметричная криптография:**
- Admin Module генерирует токены приватным ключом (RS256)
- Другие модули проверяют токены публичным ключом
- Automatic key rotation каждые 24 часа
- Grace period 1 час для плавного перехода

**Никогда не использовать HS256 (симметричная)!**

### 4. Redis ASYNC Mode для Service Discovery и кеширования

**🔴 КРИТИЧЕСКИ ВАЖНО: Redis используется АСИНХРОННО (redis.asyncio)**

```python
# ✅ Правильно - асинхронный redis.asyncio
import redis.asyncio as aioredis
from redis.asyncio import Redis

async def get_redis() -> Redis:
    client = await aioredis.from_url(
        settings.redis.url,
        max_connections=settings.redis.pool_size,
        decode_responses=True
    )
    return client

# Использование в FastAPI endpoints
@app.get("/cache")
async def get_cache():
    redis_client = await get_redis()
    value = await redis_client.get("key")  # await обязателен!
    return {"value": value}

# ❌ Неправильно - синхронный redis-py
import redis
redis_client = redis.Redis(host='redis', port=6379)
redis_client.set('key', 'value')  # Блокирует event loop!
```

**Почему ASYNC:**
- Неблокирующая работа с event loop FastAPI
- Высокая производительность при concurrent requests
- Корректная интеграция с asyncpg и другими async компонентами
- Избежание blocking I/O в async контексте

**Эталонная реализация:** `admin-module/app/core/redis.py`

### 5. PostgreSQL ASYNC через asyncpg

**Все database операции асинхронные:**

```python
# ✅ Правильно
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

engine = create_async_engine("postgresql+asyncpg://...")

async with AsyncSession(engine) as session:
    result = await session.execute(query)

# ❌ Неправильно - синхронный код
from sqlalchemy import create_engine, Session

engine = create_engine("postgresql://...")
session = Session(engine)
result = session.query(Model).all()  # Blocking!
```

### 6. Storage Element Modes

**Режимы работы Storage Element:**

| Режим | Операции | Изменение режима |
|-------|----------|------------------|
| `edit` | Full CRUD (Create, Read, Update, Delete) | Не меняется через API |
| `rw` | Read + Write (без Delete) | → `ro` через API |
| `ro` | Read Only | → `ar` через API |
| `ar` | Archive (только чтение, холодное хранение) | Только через конфиг + restart |

**Важно:**
- Режим `edit` → `rw` ТОЛЬКО через конфигурацию + restart (не через API)
- Режим `ar` (archive) необратим без ручного вмешательства
- Переход `rw` → `ro` → `ar` - односторонний для защиты данных

### 7. Saga Pattern для распределенных транзакций

**Координация через Admin Module:**

**Upload Saga пример:**
1. **Ingester**: Начало загрузки (compensate: удалить temp файл)
2. **Storage**: Запись файла (compensate: удалить файл)
3. **Storage**: Создать attr.json (compensate: удалить attr.json)
4. **Admin**: Обновить DB cache (compensate: удалить запись)
5. **Admin**: Service Discovery publish (compensate: отменить publish)
6. **Commit** - все успешно

**При сбое на любом шаге:**
- Запускаются compensating actions в обратном порядке
- Система возвращается к согласованному состоянию
- Идемпотентность операций для безопасного retry

### 8. Circuit Breaker Pattern

**Graceful degradation при недоступности зависимостей:**

```python
from circuitbreaker import circuit

@circuit(failure_threshold=5, recovery_timeout=60)
async def fetch_from_storage(file_id: str):
    """Circuit breaker защищает от каскадных сбоев."""
    return await storage_client.get(file_id)

# При 5 ошибках подряд -> circuit OPEN (60 секунд)
# Запросы сразу возвращают ошибку, не нагружая Storage
```

**Fallback strategies:**
- Кеш данные если Storage недоступен
- Degraded mode (только чтение из cache)
- Queue запросы для retry когда service восстановится

### 9. Service Discovery Protocol

**Publish-Subscribe через Redis (ASYNC):**

```python
# Admin Module публикует конфигурацию (async)
redis_client = await get_redis()
await redis_client.publish(
    'storage-elements:config',
    json.dumps(storage_elements_list)
)

# Ingester/Query подписываются на обновления (async)
pubsub = redis_client.pubsub()
await pubsub.subscribe('storage-elements:config')

async for message in pubsub.listen():
    if message['type'] == 'message':
        config = json.loads(message['data'])
        await update_local_config(config)
```

**Fallback:** Локальная конфигурация при недоступности Redis

### 10. Stateless Design

**Все сервисы должны быть stateless:**
- ❌ Нет локального state на диске (кроме temp файлов)
- ✅ Все состояние в PostgreSQL или Redis
- ✅ Horizontal scaling без проблем
- ✅ Любой инстанс может обработать любой запрос

**Исключения:**
- Storage Element: хранит файлы физически (но metadata в DB)
- WAL файлы: temporary state для атомарности

## Security Framework

### 1. OAuth 2.0 Client Credentials Flow

**ТОЛЬКО machine-to-machine authentication:**

```bash
# 1. Получить access token
curl -X POST http://localhost:8000/api/auth/token \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "service-name",
    "client_secret": "secret-value"
  }'

# Response:
{
  "access_token": "eyJ...",
  "token_type": "Bearer",
  "expires_in": 1800
}

# 2. Использовать token для API запросов
curl -X GET http://localhost:8000/api/service-accounts \
  -H "Authorization: Bearer eyJ..."
```

**Service Account роли:**
- `ADMIN`: Full access ко всем endpoints
- `USER`: Standard file operations
- `AUDITOR`: Read-only для audit logs
- `READONLY`: Read-only для всех данных

### 2. JWT Token Structure

**Формат JWT payload:**
```json
{
  "sub": "service-account-id",
  "client_id": "service-name",
  "role": "USER",
  "permissions": ["files:read", "files:write"],
  "iat": 1640000000,
  "exp": 1640001800,
  "iss": "artstore-admin",
  "aud": ["storage", "ingester", "query"]
}
```

### 3. Rate Limiting

**Адаптивный rate limiting:**
- Default: 100 req/min per service account
- Burst: 150 req/min кратковременно
- Auto-throttling при high load
- IP-based blocking для abuse

### 4. Audit Logging

**Все критические операции логируются:**
```json
{
  "timestamp": "2024-01-01T00:00:00Z",
  "service": "storage-element",
  "action": "file:delete",
  "user_id": "service-account-id",
  "resource": "file-id",
  "result": "success",
  "metadata": {
    "file_size": 1024,
    "storage_element": "se-001"
  },
  "signature": "tamper-proof-signature"
}
```

## Monitoring & Observability

### 1. Health Checks (обязательны!)

**Каждый модуль должен предоставлять:**

```bash
# Liveness - контейнер живой?
GET /health/live
# Response: 200 OK (всегда, если процесс работает)

# Readiness - готов обрабатывать запросы?
GET /health/ready
# Response:
# 200 OK - все зависимости доступны
# 503 Service Unavailable - ждет PostgreSQL/Redis
```

### 2. Prometheus Metrics

**Endpoint на каждом модуле:**
```
GET /metrics

# Основные метрики:
- http_requests_total
- http_request_duration_seconds
- database_connections_active
- redis_operations_total
- file_operations_total
- storage_space_used_bytes
```

### 3. OpenTelemetry Tracing

**Distributed tracing для всех операций:**
- Trace ID передается через все сервисы
- Span для каждой операции
- Context propagation через HTTP headers
- Export в Jaeger/Zipkin

## Performance Considerations

### 1. Multi-Level Caching

**Query Module:**
1. Local in-memory cache (TTL 5 min)
2. Redis cache (TTL 1 hour) - **ASYNC**
3. PostgreSQL cache table (TTL 24 hours)
4. attr.json файлы (источник истины)

### 2. Database Connection Pooling

```python
# SQLAlchemy async pool
engine = create_async_engine(
    database_url,
    pool_size=20,          # Max connections
    max_overflow=10,       # Additional connections под нагрузкой
    pool_pre_ping=True,    # Проверка соединений
    pool_recycle=3600      # Recycle каждый час
)
```

### 3. Streaming для больших файлов

**Ingester Module:**
```python
@router.post("/upload")
async def upload_file(file: UploadFile):
    """Streaming upload without loading entire file into memory."""
    async with storage.write_stream(file.filename) as stream:
        async for chunk in file.stream():
            await stream.write(chunk)
```

## Production Checklist

Перед deployment в production:

- [ ] ⚠️ Все secrets в environment variables, не в коде
- [ ] ⚠️ LOG_FORMAT=json для structured logging
- [ ] ⚠️ JWT RS256 с автоматической ротацией ключей
- [ ] ⚠️ Rate limiting настроен и протестирован
- [ ] ⚠️ Health checks работают на всех модулях
- [ ] ⚠️ Prometheus metrics экспортируются
- [ ] ⚠️ Database backups настроены
- [ ] ⚠️ Circuit breakers протестированы
- [ ] ⚠️ CORS политики настроены корректно
- [ ] ⚠️ Redis ASYNC mode используется везде (не sync)
