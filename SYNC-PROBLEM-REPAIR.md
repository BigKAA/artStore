# Query Module Sync Problem - Repair Plan

**Дата создания**: 2026-01-13
**Дата последнего обновления**: 2026-01-13
**Версия**: 2.0
**Статус**: 🚧 In Progress (PHASE 2/3 завершены, осталось PHASE 4-5)
**Приоритет**: 🔴 Критично

---

## 📋 Оглавление

- [Обзор проблемы](#обзор-проблемы)
- [Решение](#решение)
- [Архитектура sync механизма](#архитектура-sync-механизма)
- [Фазы реализации](#фазы-реализации)
- [TODO Checklist](#todo-checklist)
- [Оценка времени](#оценка-времени)

---

## Обзор проблемы

### Текущая ситуация

**Проблема**: Файлы загруженные через Ingester Module **НЕ появляются** в Query Module search results.

**Root Cause**: Нет автоматической синхронизации между Storage Element cache и Query Module cache.

### Последовательность событий

```
1. Ingester Module → POST /api/v1/files/upload
2. Ingester → Admin Module → Saga coordination
3. Admin Module → Storage Element → File stored
4. Storage Element → PostgreSQL cache update (file_metadata)
5. ❌ Query Module cache НЕ обновлён
6. ❌ Query Module search → File NOT FOUND
```

### Архитектура

```
┌──────────────────────────┐
│   Ingester Module        │
│   POST /upload           │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│   Admin Module (Saga)    │
│   - Coordination         │
│   - Service Discovery    │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│   Storage Element        │
│   ┌────────────────────┐ │
│   │ PostgreSQL cache   │ │ ← Обновляется ✅
│   │ file_metadata      │ │
│   └────────────────────┘ │
└──────────────────────────┘
           │
           │ ❌ NO SYNC
           ▼
┌──────────────────────────┐
│   Query Module           │
│   ┌────────────────────┐ │
│   │ PostgreSQL cache   │ │ ← НЕ обновляется ❌
│   │ file_metadata_cache│ │
│   └────────────────────┘ │
│   GET /search → ❌       │
└──────────────────────────┘
```

---

## Решение

### Option A: Event-Driven Sync через Redis Pub/Sub

**Архитектура**:

```
┌──────────────────────────────────────────┐
│         Admin Module (Event Publisher)    │
│   После успешного Saga:                  │
│   1. File stored в Storage Element        │
│   2. Publish event в Redis                │
│      redis.publish("file:created", {...}) │
└──────────────┬───────────────────────────┘
               │
               │ Redis Pub/Sub
               ▼
       ┌───────────────┐
       │     Redis     │
       │  Channel:     │
       │ file:created  │
       └───────┬───────┘
               │
               │ Subscribe
               ▼
┌──────────────────────────────────────────┐
│      Query Module (Event Subscriber)      │
│   1. Subscribe to "file:created"          │
│   2. Receive event with file metadata     │
│   3. Insert into local cache              │
│      (file_metadata_cache table)          │
│   4. File available in search ✅          │
└──────────────────────────────────────────┘
```

### Ключевые компоненты

#### 1. Admin Module: Event Publisher

**Responsibility**: Публикация events после успешного Saga

**Implementation**:
- После успешного file upload через Saga
- Publish event `file:created` в Redis channel
- Event payload: полные метаданные файла

**Event Format**:
```json
{
  "event_type": "file:created",
  "timestamp": "2026-01-13T10:00:00Z",
  "file_id": "uuid",
  "storage_element_id": "se-01",
  "metadata": {
    "original_filename": "document.pdf",
    "storage_filename": "document_user_20260113_uuid.pdf",
    "file_size": 1048576,
    "mime_type": "application/pdf",
    "created_at": "2026-01-13T10:00:00Z",
    "created_by_username": "ivanov",
    "created_by_fullname": "Иван Иванов",
    "description": "Contract document",
    "version": "1.0",
    "tags": ["urgent", "contract"],
    "storage_path": "files/active",
    "checksum": "sha256:a1b2c3d4...",
    "retention_expires_at": "2027-01-13T10:00:00Z"
  }
}
```

#### 2. Query Module: Event Subscriber

**Responsibility**: Подписка на events и обновление local cache

**Implementation**:
- Background task (asyncio) подписывается на Redis channel
- Получает events с метаданными
- Вставляет в `file_metadata_cache` таблицу
- Graceful degradation при ошибках

**Process**:
```python
async def sync_subscriber():
    redis = await get_redis_client()
    pubsub = redis.pubsub()
    await pubsub.subscribe("file:created", "file:updated", "file:deleted")

    async for message in pubsub.listen():
        if message["type"] == "message":
            await handle_file_event(message["data"])
```

#### 3. Event Handlers

**file:created**:
- INSERT new record в file_metadata_cache
- Handle duplicate (ON CONFLICT DO UPDATE)

**file:updated**:
- UPDATE existing record в file_metadata_cache
- Handle not found (warning log)

**file:deleted**:
- DELETE record из file_metadata_cache
- Soft delete (set deleted flag)

### Преимущества решения

✅ **Real-time sync**: События обрабатываются мгновенно
✅ **Decoupled**: Admin Module и Query Module не зависят друг от друга
✅ **Reliable**: Redis Pub/Sub надёжный механизм
✅ **Scalable**: Множество Query Module instances могут подписаться
✅ **Event-driven**: Современный архитектурный паттерн
✅ **Graceful degradation**: При ошибке Redis - система продолжает работу

### Trade-offs

⚠️ **Eventual consistency**: Небольшая задержка (миллисекунды) между publish и subscribe
⚠️ **Redis dependency**: Требуется работающий Redis
⚠️ **Event loss**: Если Query Module offline во время event - потеря sync (mitigation: periodic full sync)

---

## Архитектура sync механизма

### Component Diagram

```
┌─────────────────────────────────────────────────┐
│              Admin Module                        │
│  ┌────────────────────────────────────────────┐ │
│  │  Saga Coordinator                          │ │
│  │  - File upload workflow                    │ │
│  │  - Saga success → Publish event            │ │
│  └────────────────┬───────────────────────────┘ │
│                   │                              │
│  ┌────────────────▼───────────────────────────┐ │
│  │  Event Publisher Service                   │ │
│  │  - Redis client                            │ │
│  │  - Publish to "file:created"               │ │
│  │  - Publish to "file:updated"               │ │
│  │  - Publish to "file:deleted"               │ │
│  └────────────────┬───────────────────────────┘ │
└───────────────────┼──────────────────────────────┘
                    │
                    │ Redis Pub/Sub
                    ▼
            ┌───────────────┐
            │     Redis     │
            │   Channels:   │
            │ - file:created│
            │ - file:updated│
            │ - file:deleted│
            └───────┬───────┘
                    │
                    │ Subscribe
                    ▼
┌─────────────────────────────────────────────────┐
│             Query Module                         │
│  ┌────────────────────────────────────────────┐ │
│  │  Event Subscriber Service                  │ │
│  │  - Background asyncio task                 │ │
│  │  - Subscribe to Redis channels             │ │
│  │  - Handle events                           │ │
│  └────────────────┬───────────────────────────┘ │
│                   │                              │
│  ┌────────────────▼───────────────────────────┐ │
│  │  Cache Sync Service                        │ │
│  │  - Insert file metadata                    │ │
│  │  - Update file metadata                    │ │
│  │  - Delete file metadata                    │ │
│  │  - Handle duplicates (ON CONFLICT)         │ │
│  └────────────────┬───────────────────────────┘ │
│                   │                              │
│  ┌────────────────▼───────────────────────────┐ │
│  │  PostgreSQL (artstore_query)               │ │
│  │  - file_metadata_cache table               │ │
│  │  - Full-text search (GIN indexes)          │ │
│  └────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

### Sequence Diagram: File Upload Flow

```
Ingester  Admin Module  Storage Element  Redis  Query Module
   │           │              │            │         │
   │──upload──>│              │            │         │
   │           │              │            │         │
   │           │──Saga────────>│           │         │
   │           │              │            │         │
   │           │<─success─────│            │         │
   │           │              │            │         │
   │           │──publish event────────────>│        │
   │           │   (file:created)           │        │
   │           │              │            │         │
   │           │              │            │<─listen─│
   │           │              │            │         │
   │           │              │            │─event──>│
   │           │              │            │         │
   │           │              │            │         │──INSERT cache
   │           │              │            │         │
   │<─success──│              │            │         │
   │           │              │            │         │
   │           │              │            │         │<─cache updated
   │           │              │            │         │
   User────────────────────────────────────────────>│
   │        GET /search                              │
   │                                                 │
   │<──────────────────────results (file found)─────│
```

---

## Фазы реализации

План разбит на **5 фаз** для управления размером контекста и постепенной реализации.

### PHASE 1: Admin Module - Event Publisher (2-3 дня) - ✅ ЗАВЕРШЕНА

**Цель**: Добавить публикацию events в Admin Module после успешного Saga

**Задачи**:
1. ✅ Создать `EventPublisher` service
2. ✅ Интегрировать с Saga coordinator
3. ✅ Publish `file:created` event после успешного upload
4. ✅ Publish `file:updated` event
5. ✅ Publish `file:deleted` event
6. ✅ Unit tests для EventPublisher
7. ✅ Integration tests с Redis

**Файлы**:
- ✅ `admin-module/app/services/event_publisher.py` - СОЗДАН
- ✅ `admin-module/app/saga/coordinator.py` - ИЗМЕНЕН
- ✅ `admin-module/tests/test_event_publisher.py` - СОЗДАН

**Deliverables**:
- ✅ EventPublisher service реализован
- ✅ Integration с Saga coordinator
- ✅ Events публикуются в Redis
- ✅ Tests проходят

**Дата завершения**: 2026-01-13

### PHASE 2: Query Module - Event Subscriber (2-3 дня) - ✅ ЗАВЕРШЕНА

**Цель**: Добавить подписку на events в Query Module

**Задачи**:
1. ✅ Создать `EventSubscriber` service
2. ✅ Background asyncio task для subscription
3. ✅ Subscribe к Redis channels (file:created, file:updated, file:deleted)
4. ✅ Event parsing и validation через Pydantic schemas
5. ✅ Graceful degradation при Redis unavailable
6. ✅ Logging и monitoring
7. ✅ Unit tests для EventSubscriber
8. ✅ Integration tests с Redis mock
9. ✅ Создать `CacheSyncService` для обновления cache
10. ✅ Integration EventSubscriber с CacheSyncService

**Файлы**:
- ✅ `query-module/app/services/event_subscriber.py` - СОЗДАН
- ✅ `query-module/app/services/cache_sync.py` - СОЗДАН
- ✅ `query-module/app/schemas/events.py` - СОЗДАН
- ✅ `query-module/app/core/redis.py` - СОЗДАН
- ✅ `query-module/app/main.py` - ИЗМЕНЕН (lifespan startup/shutdown)
- ✅ `query-module/tests/services/test_event_subscriber.py` - СОЗДАН
- ✅ `query-module/tests/services/test_cache_sync.py` - СОЗДАН

**Deliverables**:
- ✅ EventSubscriber service реализован с reconnection logic
- ✅ Background task запускается при startup и gracefully stops при shutdown
- ✅ Events принимаются из Redis и обрабатываются
- ✅ CacheSyncService обновляет file_metadata_cache таблицу
- ✅ Unit tests проходят (EventSubscriber + CacheSyncService)
- ✅ Idempotent operations (ON CONFLICT DO UPDATE)

**Дата завершения**: 2026-01-13

**Особенности реализации**:
- Reconnection logic с exponential backoff
- Graceful shutdown с cancel background task
- Automatic fallback: file:updated → file:created если запись не найдена
- Hard delete для file:deleted (Query Module не нуждается в soft delete)
- Storage Element URL генерируется временно (будет заменен Service Discovery)

### PHASE 3: Query Module - Cache Sync Service (1-2 дня) - ✅ ЗАВЕРШЕНА (совмещена с PHASE 2)

**Цель**: Реализовать обработку events и обновление cache

**Задачи**:
1. ✅ Создать `CacheSyncService`
2. ✅ Handle `file:created` event → INSERT cache (with ON CONFLICT DO UPDATE)
3. ✅ Handle `file:updated` event → UPDATE cache (with fallback to INSERT)
4. ✅ Handle `file:deleted` event → DELETE cache (hard delete)
5. ✅ Handle duplicates (ON CONFLICT DO UPDATE)
6. ✅ Error handling и logging
7. ✅ Unit tests для CacheSyncService
8. ✅ Integration tests с PostgreSQL mock

**Файлы**:
- ✅ `query-module/app/services/cache_sync.py` - СОЗДАН
- ✅ `query-module/app/services/event_subscriber.py` - ИНТЕГРИРОВАН
- ✅ `query-module/tests/services/test_cache_sync.py` - СОЗДАН

**Deliverables**:
- ✅ CacheSyncService реализован с idempotent operations
- ✅ Events корректно обновляют cache через PostgreSQL asyncpg
- ✅ Duplicate handling работает (ON CONFLICT DO UPDATE)
- ✅ Tests проходят

**Дата завершения**: 2026-01-13 (совмещена с PHASE 2)

**Особенности реализации**:
- PostgreSQL INSERT ... ON CONFLICT DO UPDATE для idempotency
- Automatic recovery: UPDATE не нашел запись → вызывается INSERT
- Hard delete для file:deleted (Query Module cache не требует soft delete)
- AsyncSession context management через async generator

### PHASE 4: End-to-End Integration Testing (1 день)

**Цель**: Тестирование полного flow от upload до search

**Задачи**:
1. E2E test: upload file → verify Query Module cache
2. E2E test: search file → verify results
3. Performance testing (latency measurements)
4. Load testing (multiple concurrent uploads)
5. Failure scenarios testing (Redis down, Query Module offline)
6. Recovery testing (reconnection после failure)

**Файлы**:
- `tests/integration/test_sync_e2e.py` - NEW
- `claudedocs/sync-repair/e2e-test-results.md` - NEW

**Deliverables**:
- ✅ E2E tests проходят
- ✅ Performance metrics задокументированы
- ✅ Failure scenarios handled gracefully

### PHASE 5: Documentation & Deployment (1 день)

**Цель**: Документация, deployment guide, мониторинг

**Задачи**:
1. Обновить README.md модулей
2. Создать deployment guide
3. Обновить .env.example
4. Создать monitoring dashboard (Grafana)
5. Создать alerts для sync failures
6. Обновить архитектурную документацию
7. Migration guide для production

**Файлы**:
- `admin-module/README.md` - UPDATE
- `query-module/README.md` - UPDATE
- `claudedocs/sync-repair/deployment-guide.md` - NEW
- `claudedocs/sync-repair/monitoring-guide.md` - NEW

**Deliverables**:
- ✅ Документация обновлена
- ✅ Deployment guide создан
- ✅ Monitoring настроен
- ✅ Production ready

---

## TODO Checklist

### ☐ PHASE 1: Admin Module - Event Publisher

- [ ] 1.1 Создать EventPublisher service
  - [ ] Redis client integration
  - [ ] Publish method для events
  - [ ] Event serialization (JSON)
- [ ] 1.2 Интегрировать с Saga coordinator
  - [ ] После успешного upload → publish file:created
  - [ ] Error handling для publish failures
- [ ] 1.3 Event formats
  - [ ] Define file:created event schema
  - [ ] Define file:updated event schema
  - [ ] Define file:deleted event schema
- [ ] 1.4 Testing
  - [ ] Unit tests для EventPublisher
  - [ ] Integration tests с Redis
  - [ ] Mock Saga coordinator для testing
- [ ] 1.5 Configuration
  - [ ] Redis URL configuration
  - [ ] Channel names configuration
  - [ ] Event TTL configuration

**Estimated Time**: 2-3 дня

---

### ☐ PHASE 2: Query Module - Event Subscriber

- [ ] 2.1 Создать EventSubscriber service
  - [ ] Redis Pub/Sub client
  - [ ] Subscribe to channels
  - [ ] Event listener (async loop)
- [ ] 2.2 Background task integration
  - [ ] Startup в lifespan
  - [ ] Graceful shutdown
  - [ ] Reconnection logic
- [ ] 2.3 Event parsing
  - [ ] JSON deserialization
  - [ ] Schema validation
  - [ ] Error handling для invalid events
- [ ] 2.4 Graceful degradation
  - [ ] Continue operation if Redis unavailable
  - [ ] Logging warnings
  - [ ] Metrics для connection failures
- [ ] 2.5 Testing
  - [ ] Unit tests для EventSubscriber
  - [ ] Integration tests с Redis mock
  - [ ] Reconnection testing

**Estimated Time**: 2-3 дня

---

### ☐ PHASE 3: Query Module - Cache Sync Service

- [ ] 3.1 Создать CacheSyncService
  - [ ] INSERT method для file:created
  - [ ] UPDATE method для file:updated
  - [ ] DELETE method для file:deleted
- [ ] 3.2 Database operations
  - [ ] ON CONFLICT DO UPDATE для duplicates
  - [ ] Batch operations для performance
  - [ ] Transaction management
- [ ] 3.3 Error handling
  - [ ] Database connection failures
  - [ ] Constraint violations
  - [ ] Retry logic с exponential backoff
- [ ] 3.4 Integration with EventSubscriber
  - [ ] Call CacheSyncService от EventSubscriber
  - [ ] Error propagation
  - [ ] Logging и metrics
- [ ] 3.5 Testing
  - [ ] Unit tests для CacheSyncService
  - [ ] Integration tests с PostgreSQL
  - [ ] Duplicate handling tests

**Estimated Time**: 1-2 дня

---

### ☐ PHASE 4: End-to-End Integration Testing

- [ ] 4.1 E2E test setup
  - [ ] Docker compose для всех сервисов
  - [ ] Test data generation
  - [ ] Test utilities
- [ ] 4.2 Upload → Search flow test
  - [ ] Upload file через Ingester
  - [ ] Wait для event processing
  - [ ] Search file в Query Module
  - [ ] Verify file found
- [ ] 4.3 Performance testing
  - [ ] Measure event latency (publish → subscribe)
  - [ ] Measure cache update latency
  - [ ] Measure search latency after sync
- [ ] 4.4 Load testing
  - [ ] 100 concurrent uploads
  - [ ] Verify all files synced
  - [ ] Check for race conditions
- [ ] 4.5 Failure scenarios
  - [ ] Redis unavailable during publish
  - [ ] Query Module offline during event
  - [ ] Database unavailable during sync
- [ ] 4.6 Recovery testing
  - [ ] Redis reconnection after failure
  - [ ] Query Module reconnection
  - [ ] Cache consistency после recovery

**Estimated Time**: 1 день

---

### ☐ PHASE 5: Documentation & Deployment

- [ ] 5.1 Code documentation
  - [ ] Docstrings для всех public methods
  - [ ] Type hints для всех functions
  - [ ] Inline comments для complex logic
- [ ] 5.2 Module documentation
  - [ ] Update admin-module/README.md
  - [ ] Update query-module/README.md
  - [ ] Add sync architecture diagram
- [ ] 5.3 Deployment documentation
  - [ ] Deployment guide (step-by-step)
  - [ ] Configuration guide (.env parameters)
  - [ ] Migration guide (production upgrade)
- [ ] 5.4 Monitoring setup
  - [ ] Prometheus metrics для events
  - [ ] Grafana dashboard для sync monitoring
  - [ ] Alerts для sync failures
- [ ] 5.5 Operations documentation
  - [ ] Troubleshooting guide
  - [ ] Health check procedures
  - [ ] Rollback procedures

**Estimated Time**: 1 день

---

## Оценка времени

### По фазам

| Фаза | Описание | Оценка |
|------|----------|--------|
| **PHASE 1** | Admin Module - Event Publisher | 2-3 дня |
| **PHASE 2** | Query Module - Event Subscriber | 2-3 дня |
| **PHASE 3** | Query Module - Cache Sync Service | 1-2 дня |
| **PHASE 4** | E2E Integration Testing | 1 день |
| **PHASE 5** | Documentation & Deployment | 1 день |

**Общая оценка**: **7-10 дней**

### Критический путь

```
PHASE 1 (3 дня)
  ↓
PHASE 2 (3 дня)
  ↓
PHASE 3 (2 дня)
  ↓
PHASE 4 (1 день)
  ↓
PHASE 5 (1 день)
────────────────
Total: 10 дней (максимум)
```

### Оптимистичный сценарий

- PHASE 1: 2 дня (если EventPublisher простой)
- PHASE 2: 2 дня (если EventSubscriber без сложностей)
- PHASE 3: 1 день (если database operations straightforward)
- PHASE 4: 1 день
- PHASE 5: 1 день

**Total**: 7 дней

---

## Конфигурация

### Admin Module (.env)

```bash
# Redis для event publishing
REDIS_URL=redis://redis:6379/0

# Event configuration
EVENT_PUBLISH_ENABLED=true
EVENT_CHANNEL_FILE_CREATED=file:created
EVENT_CHANNEL_FILE_UPDATED=file:updated
EVENT_CHANNEL_FILE_DELETED=file:deleted
EVENT_PUBLISH_TIMEOUT=5  # seconds
```

### Query Module (.env)

```bash
# Redis для event subscription
REDIS_URL=redis://redis:6379/0

# Event configuration
EVENT_SUBSCRIBE_ENABLED=true
EVENT_CHANNEL_FILE_CREATED=file:created
EVENT_CHANNEL_FILE_UPDATED=file:updated
EVENT_CHANNEL_FILE_DELETED=file:deleted
EVENT_RECONNECT_DELAY=5  # seconds
EVENT_MAX_RECONNECT_ATTEMPTS=10

# Cache sync configuration
CACHE_SYNC_BATCH_SIZE=100
CACHE_SYNC_RETRY_ATTEMPTS=3
CACHE_SYNC_RETRY_DELAY=1  # seconds
```

---

## Мониторинг

### Prometheus Metrics

**Admin Module**:
```python
artstore_admin_events_published_total{event_type="file:created"}
artstore_admin_events_publish_failures_total{event_type="file:created"}
artstore_admin_events_publish_duration_seconds{event_type="file:created"}
```

**Query Module**:
```python
artstore_query_events_received_total{event_type="file:created"}
artstore_query_events_processing_failures_total{event_type="file:created"}
artstore_query_cache_sync_duration_seconds{event_type="file:created"}
artstore_query_redis_connection_status{status="connected|disconnected"}
```

### Grafana Alerts

**Critical**:
- Redis connection down > 5 minutes
- Event processing failure rate > 10%
- Cache sync lag > 1 minute

**Warning**:
- Redis connection flapping
- Event processing slow (> 1 second)
- Cache sync errors increasing

---

## Безопасность

### Event Security

1. **Event Integrity**:
   - Events не содержат sensitive data (только metadata)
   - File content никогда не передаётся через events

2. **Access Control**:
   - Redis Pub/Sub channels не требуют authentication (internal network)
   - Query Module validates event schema перед processing

3. **Audit**:
   - Все events логируются
   - Event processing failures логируются с context

---

## Риски и Митигации

### Риск 1: Event Loss

**Scenario**: Query Module offline во время event → event потерян

**Mitigation**:
- Periodic full sync job (hourly/daily)
- Compare Storage Element cache vs Query Module cache
- Resync missing files

### Риск 2: Redis Unavailable

**Scenario**: Redis down → events не доставляются

**Mitigation**:
- Graceful degradation (system continues operation)
- Warning logs и alerts
- Periodic full sync как fallback

### Риск 3: Event Processing Failure

**Scenario**: Database error during cache sync

**Mitigation**:
- Retry logic с exponential backoff
- Dead letter queue для failed events
- Manual intervention tools

### Риск 4: Race Conditions

**Scenario**: Concurrent events для same file

**Mitigation**:
- ON CONFLICT DO UPDATE в database
- Event ordering через timestamp
- Idempotent event handlers

---

## Rollback Plan

### Если sync не работает

1. **Disable Event Publishing**:
   ```bash
   # Admin Module .env
   EVENT_PUBLISH_ENABLED=false
   ```

2. **Disable Event Subscription**:
   ```bash
   # Query Module .env
   EVENT_SUBSCRIBE_ENABLED=false
   ```

3. **Revert Code**:
   ```bash
   git revert <commit-hash>
   docker-compose build admin-module query-module
   docker-compose up -d
   ```

4. **Manual Sync** (если нужно):
   ```bash
   # Run periodic full sync job
   curl -X POST http://localhost:8030/api/v1/admin/sync/full
   ```

---

## Начало работы

### Текущий статус

```yaml
STATUS: 🚧 In Progress
COMPLETED_PHASES:
  - PHASE 1: ✅ Admin Module - Event Publisher (2026-01-13)
  - PHASE 2: ✅ Query Module - Event Subscriber (2026-01-13)
  - PHASE 3: ✅ Query Module - Cache Sync Service (2026-01-13, совмещена с PHASE 2)

NEXT_PHASE: PHASE 4 (E2E Integration Testing)
ESTIMATED_TIME: 1 день для PHASE 4
REMAINING_TIME: 2 дня (PHASE 4-5)

PROGRESS: 60% (3/5 фаз завершено)
```

### Команды для начала

```bash
# 1. Создать feature branch
git checkout -b feature/query-module-sync-repair

# 2. Начать PHASE 1
cd admin-module

# 3. Создать EventPublisher service
mkdir -p app/services
touch app/services/event_publisher.py

# 4. Прочитать детальный план PHASE 1
cat ../claudedocs/sync-repair/phase1-event-publisher.md  # Будет создан
```

---

## Контакты и вопросы

**Документация проекта**: [README.md](README.md)
**Git Workflow**: [GIT-WORKFLOW-RULES.md](GIT-WORKFLOW-RULES.md)
**Development Guide**: [DEVELOPMENT-GUIDE.md](DEVELOPMENT-GUIDE.md)

**Для вопросов**: Создать issue или обсудить с командой разработки.

---

**Дата создания плана**: 2026-01-13
**Версия плана**: 1.0
**Автор**: Claude Code + Development Team
**Статус**: ✅ Ready to start PHASE 1
