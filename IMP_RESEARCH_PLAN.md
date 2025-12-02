# Implementation Plan: Storage Selection & Lifecycle Management

## Обзор

Этот документ описывает детальный план реализации системы выбора Storage Elements и управления жизненным циклом документов в ArtStore.

**Дата создания**: 2025-12-01
**Статус**: Phase 3 (Sprint 16) - COMPLETED ✅
**Приоритет**: High
**Последнее обновление**: 2025-12-02

**Sprint 16 Progress**:
- ✅ Task 3.1: GarbageCollector Background Job - DONE
- ✅ Task 3.2: Storage Element Delete API - DONE

---

## Проблемы для решения

### Проблема 1: Выбор RW Storage Element при множественных доступных модулях

**Контекст**: В системе может быть несколько Storage Elements в режиме `rw` (read-write). Необходимо определить алгоритм выбора целевого SE для записи новых файлов.

**Требования**:
- Sequential Fill стратегия — заполнение SE последовательно до достижения capacity threshold
- Graceful degradation при недоступности Redis (fallback на Admin Module)
- Alert + Reject поведение при отсутствии доступных SE
- Автоматическое обновление статуса SE в реальном времени

### Проблема 2: Разделение Edit vs RW Storage и жизненный цикл документов

**Контекст**: Система поддерживает два типа хранения:
- **Edit SE** — документы "в работе" (draft, work-in-progress)
- **RW SE** — финализированные документы (accepted, permanent)

**Требования**:
- Explicit указание retention policy при upload
- API для финализации (перемещения temporary → permanent)
- Two-Phase Commit для надёжного перемещения файлов
- Автоматическая garbage collection для Edit SE

---

## Архитектурные решения

### 1. Sequential Fill через Redis Registry

**Почему этот подход?**

✅ **Преимущества**:
- **Децентрализация**: Ingester самостоятельно выбирает SE без координации с Admin Module
- **Масштабируемость**: Несколько Ingester могут работать параллельно без блокировок
- **Гибкость**: Порядок SE легко изменяется через priority в Redis
- **Производительность**: O(log N) complexity для выбора SE через Sorted Set

❌ **Альтернативы, которые были отклонены**:
- **Hardcoded порядок SE** — негибкость при добавлении новых SE
- **Admin Module как coordinator** — создаёт bottleneck и single point of failure
- **Round Robin балансировка** — не соответствует требованию Sequential Fill

**Почему Redis, а не PostgreSQL?**

✅ **Redis**:
- Низкая latency (~1ms) для критического пути upload
- Pub/Sub для real-time updates статуса SE
- Sorted Set для efficient ordering по priority
- Atomic operations для consistency

❌ **PostgreSQL**:
- Более высокая latency (~5-10ms) для каждого запроса
- Нет native Pub/Sub для real-time updates
- Сложнее реализовать efficient priority-based querying

**Redis Schema Design**:

```redis
# Метаданные каждого Storage Element
Key: storage:elements:{se_id}
Type: Hash
Fields:
  - id: se_id (уникальный идентификатор)
  - mode: rw | ro | ar | edit
  - capacity_total: bytes (общая capacity)
  - capacity_used: bytes (использованная capacity)
  - capacity_percent: float 0-100 (% заполненности)
  - endpoint: http://se-host:port (URL для доступа)
  - priority: int (меньше = выше приоритет)
  - last_updated: timestamp (время последнего обновления)
  - health_status: healthy | degraded | unavailable

# Sorted Set для RW Storage Elements
Key: storage:rw:by_priority
Type: Sorted Set
Score: priority (меньше = выше приоритет)
Member: se_id

# Sorted Set для Edit Storage Elements
Key: storage:edit:by_priority
Type: Sorted Set
Score: priority
Member: se_id
```

**Почему разделение на два Sorted Set (rw и edit)?**

✅ **Преимущества**:
- Быстрый фильтр по режиму без дополнительных проверок
- Разные capacity thresholds для RW (95%) и Edit (90%)
- Независимое управление priority для разных типов storage
- Упрощённая логика выбора в Ingester

### 2. Health Reporting от Storage Elements

**Почему Storage Element сам публикует статус?**

✅ **Преимущества**:
- **Decoupling**: SE не зависит от Admin Module для обновления статуса
- **Real-time updates**: Изменения capacity видны немедленно
- **Autonomy**: SE сам знает свою capacity лучше всех
- **Fault tolerance**: SE может продолжать работать даже если Admin недоступен

❌ **Альтернатива: Admin Module периодически опрашивает SE**:
- Увеличивает нагрузку на Admin Module
- Задержка в обновлении статуса (polling interval)
- Admin становится critical path для updates

**Параметры Health Reporting**:

| Параметр | Значение | Обоснование |
|----------|----------|-------------|
| **Report interval** | 30 секунд | Баланс между актуальностью и нагрузкой на Redis |
| **Staleness threshold** | 2 минуты | 4x report interval для учёта сетевых задержек |
| **Retry interval при ошибке** | 5 секунд | Быстрое восстановление после временных сбоев |

**Почему 30 секунд для report interval?**

✅ **30 секунд**:
- Достаточно частое обновление для capacity monitoring
- Низкая нагрузка на Redis (~2 writes/min на SE)
- Приемлемая задержка для Sequential Fill (новый SE активируется через 30 сек)

❌ **Альтернативы**:
- **5-10 секунд**: Избыточная нагрузка на Redis без реальной пользы
- **60+ секунд**: Слишком медленная реакция на изменения capacity

### 3. Adaptive Capacity Thresholds

**Проблема с фиксированными thresholds**:

Фиксированный процентный threshold не масштабируется для Storage Elements разного размера:

| SE Size | Fixed 95% | Free Space | Assessment |
|---------|-----------|------------|------------|
| 1TB | 95% | 50GB | ✅ Acceptable |
| 10TB | 95% | 500GB | ⚠️ Moderate waste |
| 100TB | 95% | 5TB | ❌ Significant waste |
| 1PB | 95% | 50TB | ❌ **CRITICAL waste** |

**Решение: Adaptive Threshold Strategy**

Вместо фиксированного процента используем **адаптивный расчёт** на основе абсолютного минимального free space:

```python
def calculate_adaptive_threshold(total_capacity_bytes: int, mode: str) -> dict:
    """
    Рассчитать adaptive threshold на основе размера SE.

    Для RW:
    - Минимум 50GB или 2% от capacity (что больше)
    - Warning: 15% или 150GB free
    - Critical: 8% или 80GB free
    - Full: 2% или 20GB free

    Для Edit (более aggressive):
    - Минимум 30GB или 1% от capacity
    - Warning: 10% или 100GB free
    - Critical: 5% или 50GB free
    - Full: 1% или 10GB free
    """
    total_gb = total_capacity_bytes / (1024**3)

    if mode == "rw":
        warning_free_gb = max(total_gb * 0.15, 150)
        critical_free_gb = max(total_gb * 0.08, 80)
        full_free_gb = max(total_gb * 0.02, 20)
    elif mode == "edit":
        warning_free_gb = max(total_gb * 0.10, 100)
        critical_free_gb = max(total_gb * 0.05, 50)
        full_free_gb = max(total_gb * 0.01, 10)

    return {
        "warning_threshold": (total_gb - warning_free_gb) / total_gb * 100,
        "critical_threshold": (total_gb - critical_free_gb) / total_gb * 100,
        "full_threshold": (total_gb - full_free_gb) / total_gb * 100,
        "warning_free_gb": warning_free_gb,
        "critical_free_gb": critical_free_gb,
        "full_free_gb": full_free_gb
    }
```

**Примеры адаптивных thresholds для RW Storage**:

| SE Size | Warning | Critical | Full | Free @ Full | Waste % |
|---------|---------|----------|------|-------------|---------|
| 1TB | 85% (150GB) | 92% (80GB) | 98% (20GB) | 20GB | 2% |
| 10TB | 98.5% (150GB) | 99.2% (80GB) | 99.8% (20GB) | 20GB | 0.2% |
| 100TB | 98.5% (1.5TB) | 99.2% (800GB) | 99.8% (200GB) | 200GB | 0.2% |
| 1PB | 98.5% (15TB) | 99.2% (8TB) | 99.8% (2TB) | 2TB | 0.2% |

**Примеры для Edit Storage** (более aggressive):

| SE Size | Warning | Critical | Full | Free @ Full | Waste % |
|---------|---------|----------|------|-------------|---------|
| 1TB | 90% (100GB) | 95% (50GB) | 99% (10GB) | 10GB | 1% |
| 10TB | 99% (100GB) | 99.5% (50GB) | 99.9% (10GB) | 10GB | 0.1% |
| 100TB | 99% (1TB) | 99.5% (500GB) | 99.9% (100GB) | 100GB | 0.1% |

**Почему этот подход?**

✅ **Преимущества**:
- **Масштабируемость**: Автоматически адаптируется к любому размеру SE
- **Efficiency**: Минимизирует waste space на больших SE (98%+ utilization)
- **Safety**: Защищает малые SE (минимум 50GB/30GB free)
- **Predictability**: Абсолютные значения понятнее для администраторов
- **No configuration**: Не требует manual tuning для каждого SE

❌ **Фиксированный процент**:
- Не масштабируется для больших SE
- Waste растёт линейно с размером
- Требует manual adjustment для разных размеров

### 3.1. Multi-Level Capacity Status

Вместо бинарного "ok/reject" используем **graduated response** с четырьмя статусами:

```python
class CapacityStatus(Enum):
    OK = "ok"              # Normal operation
    WARNING = "warning"    # Approaching threshold, alert admin
    CRITICAL = "critical"  # Very close to full, urgent action needed
    FULL = "full"          # Reject new writes, switch to next SE
```

**Поведение системы по статусам**:

| Status | Capacity | Ingester Behaviour | Alerting | Logging | Admin UI |
|--------|----------|-------------------|----------|---------|----------|
| **OK** | < warning | ✅ Accept writes | — | INFO | 🟢 Green |
| **WARNING** | ≥ warning | ✅ Accept writes | ⚠️ Low priority | WARNING | 🟡 Yellow |
| **CRITICAL** | ≥ critical | ✅ Accept writes | 🚨 High priority | ERROR | 🟠 Orange |
| **FULL** | ≥ full | ❌ Skip SE, try next | 🚨 Critical page | CRITICAL | 🔴 Red |

**Ключевое отличие**:
- WARNING и CRITICAL продолжают принимать записи, только алертят
- FULL — единственный статус, когда SE исключается из Sequential Fill
- Это даёт администратору время для реакции без impact на availability

**Почему graduated response?**

✅ **Преимущества**:
- **Proactive alerting**: Администратор узнаёт о проблеме заранее
- **No downtime**: Система продолжает работать при warning/critical
- **Time to react**: Достаточно времени для добавления capacity
- **Better visibility**: Чёткая градация severity

❌ **Binary ok/reject**:
- Администратор узнаёт о проблеме слишком поздно
- Внезапный reject без предупреждения
- Нет времени для плановых действий

### 3.2. Intelligent File Size Handling

**Проблема**: При streaming upload размер файла часто неизвестен до завершения передачи.

**Сценарий проблемы**:
```
Client → Ingester: POST /upload (chunked transfer encoding)
Ingester → Storage Element: streaming upload
Storage Element: disk full при 90% upload → error
Result: Wasted bandwidth + time + partial file cleanup
```

**Решение: Pre-flight Check + Optimistic Retry**

```python
async def upload_with_intelligent_fallback(
    file: UploadFile,
    retention_policy: str,
    storage_selector: StorageSelector
) -> str:
    """Upload с intelligent fallback при insufficient space."""

    # 1. Попробовать получить размер файла
    file_size = None
    if hasattr(file, 'size'):
        file_size = file.size
    elif 'Content-Length' in request.headers:
        file_size = int(request.headers['Content-Length'])

    # 2. Выбрать SE с pre-flight check (если размер известен)
    attempts = 0
    max_attempts = 3  # До 3 попыток на разных SE

    while attempts < max_attempts:
        target_se = await storage_selector.select_storage_element(
            retention_policy=retention_policy,
            required_free_space=file_size  # Pre-flight check
        )

        if not target_se:
            raise HTTPException(503, "No available storage")

        try:
            # 3. Попробовать upload
            file_id = await storage_client.upload_file(
                storage_element=target_se,
                file=file,
                retention_policy=retention_policy
            )

            # Success!
            return file_id

        except InsufficientSpaceError as e:
            # 4. Disk full → retry на следующем SE
            logger.warning(
                f"Upload failed on {target_se['id']}, retrying",
                extra={
                    "se_id": target_se["id"],
                    "attempt": attempts + 1,
                    "file_size": file_size
                }
            )

            # Временно пометить SE как full
            await storage_selector.mark_se_temporarily_full(target_se["id"])

            attempts += 1
            continue

    # Все попытки исчерпаны
    raise HTTPException(503, "Failed to upload after multiple attempts")
```

**Логика Pre-flight Check в StorageSelector**:

```python
async def select_storage_element(
    self,
    retention_policy: str,
    required_free_space: Optional[int] = None
) -> Optional[dict]:
    """
    Выбрать SE с учётом required_free_space.

    Args:
        required_free_space: Минимальное free space в bytes (если известно)
    """
    # ... (получение списка SE по priority)

    for se_id in se_ids:
        se_data = await self.redis.hgetall(f"storage:elements:{se_id}")

        # Skip SE в статусе FULL
        if se_data.get("capacity_status") == "full":
            continue

        # Pre-flight check: достаточно ли места?
        if required_free_space:
            free_bytes = (
                int(se_data["capacity_total"]) -
                int(se_data["capacity_used"])
            )

            if free_bytes < required_free_space:
                logger.debug(f"SE {se_id} skipped: insufficient space")
                continue  # Попробовать следующий SE

        # SE подходит
        return se_data

    return None  # Нет подходящих SE
```

**Почему этот подход?**

✅ **Pre-flight check** (если Content-Length известен):
- Избегает wasted bandwidth при upload в заполненный SE
- Немедленное переключение на подходящий SE
- Оптимизация для случаев когда размер известен

✅ **Optimistic retry** (если размер неизвестен):
- Не блокирует upload при неизвестном размере
- Automatic fallback при "disk full" ошибке
- До 3 попыток перед окончательным reject

✅ **Graceful degradation**:
- Система продолжает работать даже если первый SE заполнен
- Sequential Fill автоматически продолжается на следующем SE
- Минимальный impact на user experience

### 4. Fallback на Admin Module

**Почему нужен fallback?**

✅ **Resilience**: Система продолжает работать при недоступности Redis
✅ **Consistency**: Admin Module — single source of truth для конфигурации SE
✅ **Bootstrap**: При старте Ingester может получить начальную конфигурацию

**Fallback алгоритм**:

```python
try:
    # Primary: Redis
    se = await select_from_redis(retention_policy)
except RedisError:
    # Fallback: Admin Module HTTP API
    logger.warning("Redis unavailable, falling back to Admin Module")
    se = await admin_client.get_available_storage(retention_policy)
```

**Почему HTTP API, а не прямое обращение к PostgreSQL?**

✅ **HTTP API**:
- Соблюдение микросервисной архитектуры
- Admin Module может применять бизнес-логику
- Authentication через JWT токены
- Audit trail для всех запросов

❌ **Прямой доступ к DB**:
- Нарушение boundary между сервисами
- Невозможность применить security policies
- Coupling между схемой DB и Ingester

**Admin Module Fallback Endpoint**:

```
GET /api/v1/storage-elements?mode={rw|edit}&available=true&order_by=priority
Authorization: Bearer {service_account_token}

Response:
[
  {
    "id": "se-1",
    "mode": "rw",
    "capacity_percent": 60.0,
    "endpoint": "http://se-1:8010",
    "priority": 1
  },
  ...
]
```

### 5. Alert + Reject при отсутствии доступных SE

**Почему Reject, а не Queue?**

✅ **Reject с 503 Service Unavailable**:
- **Honest feedback**: Клиент знает что запрос не выполнен
- **Fast fail**: Немедленная индикация проблемы
- **No hidden complexity**: Нет необходимости управлять очередью
- **Backpressure**: Клиент может реализовать retry logic

❌ **Queue (отложенная обработка)**:
- Усложнение архитектуры (нужна persistent queue)
- Неопределённость для клиента (когда файл будет загружен?)
- Риск переполнения queue при длительной unavailability
- Сложность управления приоритетами в queue

**Alert механизм**:

1. **Structured logging**:
   ```python
   logger.critical(
       "No available storage elements",
       extra={
           "alert": "storage_unavailable",
           "severity": "critical",
           "retention_policy": retention_policy
       }
   )
   ```

2. **Prometheus metric**:
   ```python
   storage_unavailable_counter.labels(
       retention_policy=retention_policy
   ).inc()
   ```

3. **AlertManager rule** (в будущем):
   ```yaml
   - alert: StorageUnavailable
     expr: rate(storage_unavailable_total[5m]) > 0
     for: 1m
     severity: critical
   ```

**Почему критический алерт?**

✅ **Critical severity**:
- Прямое влияние на доступность системы (uploads не работают)
- Требуется немедленная реакция администратора
- Риск потери данных при повторных попытках клиента

---

## Жизненный цикл документов: Edit vs RW

### 6. Retention Policy вместо Document Status

**Почему Retention Policy?**

✅ **Преимущества**:
- **Бизнес-ориентированная терминология**: "temporary" / "permanent" понятнее чем "draft" / "final"
- **Соответствие индустрии**: AWS S3 Lifecycle, Google Cloud Storage используют retention policies
- **Расширяемость**: Легко добавить новые политики (e.g., "archive", "compliance")
- **Separation of concerns**: Retention policy отделена от бизнес-статуса документа

❌ **Альтернативы**:
- **Document status (draft/final)**: Смешивает бизнес-логику и storage concerns
- **Workflow states**: Слишком сложно для simple use cases
- **Implicit (по типу файла)**: Нет гибкости для пользователя

**API Design**:

```json
POST /api/v1/upload
{
  "file": "<binary>",
  "retention_policy": "temporary",  // или "permanent"
  "ttl_days": 30,                   // только для temporary
  "metadata": {
    "document_type": "invoice",
    "business_status": "draft"      // опциональная бизнес-логика
  }
}
```

**Почему TTL только для temporary?**

✅ **TTL для temporary**:
- Автоматическая очистка забытых draft'ов
- Защита от переполнения Edit SE
- Соответствие концепции "временного" хранения

❌ **TTL для permanent**:
- Противоречит концепции "permanent" storage
- RW SE предназначен для long-term retention
- Lifecycle RW → RO → AR управляется админом, не TTL

**Default TTL = 30 дней**:

✅ **Обоснование**:
- Достаточно времени для завершения работы над документом
- Баланс между гибкостью и защитой от мусора
- Соответствие типичным workflow циклам (sprint, month, etc.)

### 7. Explicit Finalize API

**Почему отдельный endpoint для финализации?**

✅ **Преимущества**:
- **Explicit action**: Финализация — явное и осознанное действие
- **Audit trail**: Чёткая запись когда и кто финализировал документ
- **Validation point**: Возможность проверок перед финализацией
- **Rollback point**: Можно отменить финализацию до commit

❌ **Альтернатива: Автоматическая финализация**:
- Время-based: Непредсказуемо, может финализировать незавершённый документ
- Metadata-based: Сложность определения "readiness" для финализации
- Отсутствие explicit control для пользователя

**API Design**:

```json
POST /api/v1/files/{file_id}/finalize
{
  "target_retention_policy": "permanent"
}

Response:
{
  "file_id": "uuid",
  "status": "finalized",
  "transaction_id": "uuid",
  "new_storage_element": "se-rw-1",
  "finalized_at": "2025-12-01T10:00:00Z"
}
```

### 8. Two-Phase Commit для надёжной финализации

**Почему Two-Phase Commit?**

✅ **Преимущества**:
- **Atomicity**: Либо полная успешная финализация, либо rollback
- **Data integrity**: Checksum verification предотвращает corruption
- **Audit trail**: Все шаги записаны в transaction log
- **Recoverability**: Можно восстановить прерванные транзакции

❌ **Альтернативы**:
- **Simple Move**: Риск потери данных при сбое во время перемещения
- **Copy-Only**: Дублирование файлов без cleanup
- **Async без tracking**: Невозможно определить статус операции

**Two-Phase Commit процесс**:

```
Phase 1: COPY
├─ Download file from source Edit SE
├─ Calculate checksum_source (SHA-256)
├─ Upload file to target RW SE
├─ Record transaction: status="copying"
└─ Update transaction: status="copied", checksum_source

Phase 2: VERIFY & COMMIT
├─ Request checksum from target RW SE
├─ Compare checksum_source == checksum_target
├─ If match:
│  ├─ Update file metadata: storage_element → target_se
│  ├─ Update file metadata: retention_policy → "permanent"
│  ├─ Update transaction: status="completed"
│  └─ Schedule cleanup: delete from source Edit SE after 24h
└─ If mismatch:
   ├─ Delete file from target RW SE
   ├─ Update transaction: status="failed"
   └─ Raise IntegrityError
```

**Почему SHA-256 для checksum?**

✅ **SHA-256**:
- Industry standard для file integrity verification
- Cryptographically secure (collision resistance)
- Доступен в стандартной библиотеке Python (hashlib)
- Баланс между security и performance

❌ **Альтернативы**:
- **MD5**: Считается weak для security purposes
- **SHA-512**: Overkill для file integrity, медленнее
- **CRC32**: Недостаточно надёжен для критичных данных

**Почему 24 часа safety margin перед delete?**

✅ **24 часа**:
- Достаточно времени для обнаружения проблем с финализацией
- Возможность rollback при необходимости
- Минимальное impact на capacity Edit SE
- Соответствие операционным SLA (рабочий день для реакции)

❌ **Альтернативы**:
- **Немедленное удаление**: Риск потери данных при ошибке metadata update
- **7+ дней**: Избыточное хранение дубликатов, waste of space

### 9. Database Schema для Transaction Log

**Почему нужен отдельный transaction log?**

✅ **Преимущества**:
- **Auditability**: Полная история всех финализаций
- **Debugging**: Возможность trace failure причин
- **Recovery**: Восстановление прерванных транзакций
- **Monitoring**: Метрики успешности финализаций

**Schema Design**:

```sql
-- Transaction log для финализаций
CREATE TABLE file_finalize_transactions (
    transaction_id UUID PRIMARY KEY,
    file_id UUID NOT NULL REFERENCES files(file_id),
    source_se VARCHAR(255) NOT NULL,       -- Edit SE id
    target_se VARCHAR(255) NOT NULL,       -- RW SE id
    status VARCHAR(50) NOT NULL,           -- copying | copied | completed | failed
    checksum_source VARCHAR(64),           -- SHA-256 checksum от source
    checksum_target VARCHAR(64),           -- SHA-256 checksum от target
    error_message TEXT,                    -- При status=failed
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP
);

CREATE INDEX idx_file_finalize_tx_file_id ON file_finalize_transactions(file_id);
CREATE INDEX idx_file_finalize_tx_status ON file_finalize_transactions(status);
CREATE INDEX idx_file_finalize_tx_created ON file_finalize_transactions(created_at);

-- Cleanup queue для отложенного удаления
CREATE TABLE file_cleanup_queue (
    id SERIAL PRIMARY KEY,
    file_id UUID NOT NULL,
    storage_element_id VARCHAR(255) NOT NULL,
    scheduled_at TIMESTAMP NOT NULL,       -- Когда удалять (created + 24h)
    processed_at TIMESTAMP,                -- Когда обработано
    error_message TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_cleanup_queue_scheduled ON file_cleanup_queue(scheduled_at)
WHERE processed_at IS NULL;
```

**Почему отдельная таблица cleanup_queue?**

✅ **Преимущества**:
- **Decoupling**: Cleanup не блокирует finalize transaction
- **Retry logic**: Можно переобработать failed cleanup
- **Batch processing**: GC job обрабатывает cleanup батчами
- **Monitoring**: Отдельные метрики для cleanup операций

### 10. Garbage Collection Background Job

**Почему background job, а не event-driven cleanup?**

✅ **Background job (periodic)**:
- **Simplicity**: Простая реализация без event bus
- **Batch efficiency**: Обработка нескольких файлов за раз
- **Resource control**: Можно ограничить CPU/IO usage
- **Predictability**: Чёткое расписание для операций

❌ **Event-driven (immediate)**:
- Сложность координации между сервисами
- Возможные race conditions
- Непредсказуемая нагрузка на Storage Elements

**GC Job стратегии**:

| Стратегия | Описание | Frequency | Обоснование |
|-----------|----------|-----------|-------------|
| **TTL-based cleanup** | Удаление temporary файлов с истекшим TTL | Every 6h | Регулярная очистка forgotten drafts |
| **Finalized files cleanup** | Удаление из Edit SE после finalize (safety margin 24h) | Every 6h | Завершение Two-Phase Commit |
| **Orphaned files cleanup** | Удаление файлов без записей в DB (age > 7 days) | Every 6h | Защита от data inconsistency |

**Почему 6 часов для run interval?**

✅ **6 часов**:
- Достаточно частое для своевременной очистки
- Низкая нагрузка на систему (4 runs/day)
- Предсказуемое время выполнения для мониторинга
- Баланс между актуальностью и resource usage

❌ **Альтернативы**:
- **1 час**: Избыточная частота, лишняя нагрузка
- **24 часа**: Слишком медленная реакция, риск переполнения Edit SE

**Почему 7 дней для orphaned files?**

✅ **7 дней safety margin**:
- Достаточно времени для обнаружения и исправления data inconsistency
- Защита от случайного удаления "забытых" файлов
- Соответствие retention policies для temporary storage

**GC Job implementation details**:

```python
# admin-module/app/services/garbage_collector.py

class GarbageCollector:
    async def start(self):
        """Запуск periodic GC job"""
        while True:
            await self._run_cleanup_cycle()
            await asyncio.sleep(6 * 3600)  # 6 hours

    async def _run_cleanup_cycle(self):
        """Полный цикл очистки"""
        # 1. TTL-based cleanup
        ttl_cleaned = await self._cleanup_expired_ttl()

        # 2. Finalized files cleanup
        finalized_cleaned = await self._cleanup_finalized_files()

        # 3. Orphaned files cleanup
        orphaned_cleaned = await self._cleanup_orphaned_files()

        # Metrics
        gc_cleanup_total.labels(type="ttl").inc(ttl_cleaned)
        gc_cleanup_total.labels(type="finalized").inc(finalized_cleaned)
        gc_cleanup_total.labels(type="orphaned").inc(orphaned_cleaned)
```

---

## Comprehensive Monitoring & Alerting

### 1. Enhanced Prometheus Metrics

**Capacity Metrics** (real-time monitoring):

```python
# storage-element/app/core/metrics.py

from prometheus_client import Gauge, Counter, Histogram

# Capacity в bytes (для точности на больших SE)
storage_capacity_total_bytes = Gauge(
    "storage_capacity_total_bytes",
    "Total storage capacity in bytes",
    ["se_id", "mode"]
)

storage_capacity_used_bytes = Gauge(
    "storage_capacity_used_bytes",
    "Used storage capacity in bytes",
    ["se_id", "mode"]
)

storage_capacity_free_bytes = Gauge(
    "storage_capacity_free_bytes",
    "Free storage capacity in bytes",
    ["se_id", "mode"]
)

# Capacity status (0=ok, 1=warning, 2=critical, 3=full)
storage_capacity_status = Gauge(
    "storage_capacity_status",
    "Current capacity status",
    ["se_id", "mode"]
)

# Capacity forecast (predictive analytics)
storage_capacity_forecast_days = Gauge(
    "storage_capacity_forecast_days",
    "Forecast: days until threshold at current fill rate",
    ["se_id", "threshold"]  # threshold: warning|critical|full
)

# Upload rejections
storage_upload_rejected_total = Counter(
    "storage_upload_rejected_total",
    "Total uploads rejected due to capacity",
    ["se_id", "reason"]  # reason: full|no_space_for_file
)

# Automatic SE switching
storage_element_switch_total = Counter(
    "storage_element_switch_total",
    "Total automatic SE switches",
    ["from_se", "to_se", "reason"]  # reason: full|insufficient_space
)

# Selection performance
storage_selection_duration_seconds = Histogram(
    "storage_selection_duration_seconds",
    "Duration of SE selection",
    ["retention_policy"]
)

storage_selection_total = Counter(
    "storage_selection_total",
    "Total SE selections",
    ["retention_policy", "status"]  # status: success|fallback|failed
)
```

### 2. Capacity Forecasting

**Predictive Analytics для proactive management**:

```python
# storage-element/app/services/capacity_forecaster.py

from datetime import datetime, timedelta
from typing import Optional

class CapacityForecaster:
    """Прогнозирование заполнения Storage Element."""

    def __init__(self, redis_client):
        self.redis = redis_client
        self.history_key_prefix = "storage:history:"
        self.history_retention_days = 30

    async def record_capacity_snapshot(self, se_id: str, used_bytes: int):
        """Записать capacity snapshot для forecasting."""
        timestamp = int(datetime.utcnow().timestamp())

        # Redis time series (sorted set)
        await self.redis.zadd(
            f"{self.history_key_prefix}{se_id}",
            {f"{timestamp}:{used_bytes}": timestamp}
        )

        # Cleanup старых записей (> 30 дней)
        cutoff = timestamp - (self.history_retention_days * 86400)
        await self.redis.zremrangebyscore(
            f"{self.history_key_prefix}{se_id}",
            0,
            cutoff
        )

    async def forecast_days_until_full(
        self,
        se_id: str,
        total_capacity: int,
        threshold_bytes: int
    ) -> Optional[float]:
        """
        Прогноз: за сколько дней SE заполнится до threshold.

        Returns:
            Количество дней или None если недостаточно данных
        """
        # Получить historical data (последние 7 дней)
        history_key = f"{self.history_key_prefix}{se_id}"
        now = int(datetime.utcnow().timestamp())
        week_ago = now - (7 * 86400)

        history = await self.redis.zrangebyscore(
            history_key,
            week_ago,
            now,
            withscores=True
        )

        if len(history) < 2:
            return None  # Недостаточно данных

        # Linear regression для rate of fill
        data_points = []
        for entry, timestamp in history:
            _, used_bytes_str = entry.split(":")
            data_points.append({
                "timestamp": timestamp,
                "used_bytes": int(used_bytes_str)
            })

        first = data_points[0]
        last = data_points[-1]

        time_delta_seconds = last["timestamp"] - first["timestamp"]
        bytes_delta = last["used_bytes"] - first["used_bytes"]

        if time_delta_seconds == 0 or bytes_delta <= 0:
            return None  # Нет роста

        # Rate of fill (bytes/second)
        fill_rate = bytes_delta / time_delta_seconds

        # Remaining bytes до threshold
        remaining_bytes = threshold_bytes - last["used_bytes"]

        if remaining_bytes <= 0:
            return 0  # Уже за threshold

        # Days until threshold
        seconds_until = remaining_bytes / fill_rate
        days_until = seconds_until / 86400

        return days_until
```

**Интеграция в HealthReporter**:

```python
async def _report_status(self):
    """Report с forecasting."""
    # ... existing capacity calculation

    # Record snapshot для forecasting
    await capacity_forecaster.record_capacity_snapshot(
        self.se_id,
        storage_stats["used"]
    )

    # Forecast для каждого threshold
    thresholds = calculate_adaptive_threshold(
        storage_stats["total"],
        settings.storage_mode
    )

    for threshold_name in ["warning", "critical", "full"]:
        threshold_bytes = (
            storage_stats["total"] -
            int(thresholds[f"{threshold_name}_free_gb"] * 1024**3)
        )

        forecast_days = await capacity_forecaster.forecast_days_until_full(
            self.se_id,
            storage_stats["total"],
            threshold_bytes
        )

        if forecast_days is not None:
            # Update Prometheus metric
            storage_capacity_forecast_days.labels(
                se_id=self.se_id,
                threshold=threshold_name
            ).set(forecast_days)

            # Log если forecast < 30 дней
            if forecast_days < 30:
                logger.warning(
                    f"SE {self.se_id} forecasted to reach {threshold_name} "
                    f"in {forecast_days:.1f} days",
                    extra={
                        "se_id": self.se_id,
                        "threshold": threshold_name,
                        "forecast_days": forecast_days
                    }
                )
```

### 3. Prometheus AlertManager Rules

```yaml
# monitoring/prometheus/alerts/storage_capacity.yml

groups:
  - name: storage_capacity
    interval: 30s
    rules:
      # Multi-level capacity alerts
      - alert: StorageCapacityWarning
        expr: storage_capacity_status{status="warning"} == 1
        for: 5m
        labels:
          severity: warning
          component: storage
        annotations:
          summary: "Storage {{ $labels.se_id }} capacity warning"
          description: |
            Storage Element {{ $labels.se_id }} has reached warning threshold.
            Free space: {{ query "storage_capacity_free_bytes{se_id='$labels.se_id'} / 1024^3" | first | value | humanize }}GB
            Forecast (full): {{ query "storage_capacity_forecast_days{se_id='$labels.se_id',threshold='full'}" | first | value | humanize }} days

      - alert: StorageCapacityCritical
        expr: storage_capacity_status{status="critical"} == 2
        for: 2m
        labels:
          severity: critical
          component: storage
        annotations:
          summary: "Storage {{ $labels.se_id }} capacity CRITICAL"
          description: |
            URGENT: Storage Element {{ $labels.se_id }} critically low on space.
            Free space: {{ query "storage_capacity_free_bytes{se_id='$labels.se_id'} / 1024^3" | first | value | humanize }}GB
            Forecast (full): {{ query "storage_capacity_forecast_days{se_id='$labels.se_id',threshold='full'}" | first | value | humanize }} days
            ACTION REQUIRED: Add capacity immediately.

      - alert: StorageCapacityFull
        expr: storage_capacity_status{status="full"} == 3
        for: 1m
        labels:
          severity: page
          component: storage
        annotations:
          summary: "Storage {{ $labels.se_id }} is FULL"
          description: |
            CRITICAL: Storage Element {{ $labels.se_id }} is full and rejecting writes.
            System automatically switching to next SE.
            IMMEDIATE ACTION: Expand capacity or migrate data.

      # Predictive alert (7+ days forecast)
      - alert: StorageCapacityPredictiveFull
        expr: storage_capacity_forecast_days{threshold="full"} < 7 and storage_capacity_forecast_days{threshold="full"} > 0
        for: 1h
        labels:
          severity: warning
          component: storage
        annotations:
          summary: "Storage {{ $labels.se_id }} will be full in < 7 days"
          description: |
            Storage Element {{ $labels.se_id }} forecasted to reach capacity in {{ $value | humanize }} days.
            Current fill rate indicates proactive action needed.
            Consider expanding capacity or implementing lifecycle policies.

      # Upload rejection alert
      - alert: StorageUploadRejections
        expr: rate(storage_upload_rejected_total[5m]) > 0.1
        for: 2m
        labels:
          severity: critical
          component: storage
        annotations:
          summary: "High upload rejection rate on {{ $labels.se_id }}"
          description: |
            Storage Element {{ $labels.se_id }} rejecting uploads.
            Rejection rate: {{ $value | humanizePercentage }}
            May indicate insufficient capacity across all SE.

      # Automatic SE switching (может указывать на проблемы)
      - alert: FrequentStorageSwitching
        expr: rate(storage_element_switch_total[10m]) > 0.5
        for: 5m
        labels:
          severity: warning
          component: storage
        annotations:
          summary: "Frequent automatic SE switching detected"
          description: |
            System frequently switching between Storage Elements.
            Switch rate: {{ $value }} switches/second
            This may indicate capacity issues or misconfiguration.
```

### 4. Structured Logging

**Capacity Status Logging**:

```python
# storage-element/app/services/health_reporter.py

async def _report_status(self):
    """Report с comprehensive logging."""
    storage_stats = await self._get_storage_stats()
    thresholds = calculate_adaptive_threshold(
        storage_stats["total"],
        settings.storage_mode
    )
    status = get_capacity_status(
        storage_stats["used"],
        storage_stats["total"],
        thresholds
    )

    # Структурированный лог
    log_data = {
        "event": "storage_capacity_status",
        "se_id": self.se_id,
        "mode": settings.storage_mode,
        "capacity": {
            "total_gb": storage_stats["total"] / (1024**3),
            "used_gb": storage_stats["used"] / (1024**3),
            "free_gb": (storage_stats["total"] - storage_stats["used"]) / (1024**3),
            "percent": storage_stats["percent"]
        },
        "status": status.value,
        "thresholds": {
            "warning_pct": thresholds["warning_threshold"],
            "critical_pct": thresholds["critical_threshold"],
            "full_pct": thresholds["full_threshold"],
            "warning_free_gb": thresholds["warning_free_gb"],
            "critical_free_gb": thresholds["critical_free_gb"],
            "full_free_gb": thresholds["full_free_gb"]
        }
    }

    # Log level на основе status
    if status == CapacityStatus.FULL:
        logger.critical("Storage capacity FULL", extra=log_data)
    elif status == CapacityStatus.CRITICAL:
        logger.error("Storage capacity CRITICAL", extra=log_data)
    elif status == CapacityStatus.WARNING:
        logger.warning("Storage capacity WARNING", extra=log_data)
    else:
        logger.info("Storage capacity OK", extra=log_data)
```

**Upload Rejection Logging**:

```python
# ingester-module/app/api/v1/endpoints/upload.py

if not target_se:
    logger.critical(
        "No available storage for upload",
        extra={
            "event": "storage_unavailable",
            "retention_policy": retention_policy,
            "file_size": file_size,
            "available_se_count": await storage_selector.count_available_se(retention_policy),
            "alert": "critical"
        }
    )

    # Prometheus metric
    storage_unavailable_counter.labels(
        retention_policy=retention_policy
    ).inc()

    raise HTTPException(503, "No available storage")
```

### 5. Admin UI Visualization

**Dashboard Components**:

```typescript
// admin-ui/src/app/components/storage-capacity-dashboard/

interface StorageElementStatus {
  id: string;
  mode: 'rw' | 'ro' | 'ar' | 'edit';
  capacityTotal: number;  // bytes
  capacityUsed: number;
  capacityFree: number;
  capacityPercent: number;
  status: 'ok' | 'warning' | 'critical' | 'full';
  thresholds: {
    warning: { percent: number; freeGb: number };
    critical: { percent: number; freeGb: number };
    full: { percent: number; freeGb: number };
  };
  forecast: {
    warningDays: number | null;
    criticalDays: number | null;
    fullDays: number | null;
  };
}
```

**Capacity Gauge Component**:

```html
<div class="capacity-gauge" [ngClass]="status">
  <!-- Progress bar -->
  <div class="gauge-fill" [style.width.%]="capacityPercent"></div>

  <!-- Threshold markers -->
  <div class="threshold-marker warning" [style.left.%]="thresholds.warning.percent"></div>
  <div class="threshold-marker critical" [style.left.%]="thresholds.critical.percent"></div>
  <div class="threshold-marker full" [style.left.%]="thresholds.full.percent"></div>

  <!-- Label -->
  <div class="gauge-label">
    {{ capacityUsed | fileSize }} / {{ capacityTotal | fileSize }}
    ({{ capacityPercent | number:'1.1-1' }}%)
  </div>
</div>

<!-- Forecast widget -->
<div class="forecast-widget" *ngIf="forecast.fullDays !== null">
  <mat-icon [ngClass]="getForecastSeverity(forecast.fullDays)">
    schedule
  </mat-icon>
  <span>
    Full in {{ forecast.fullDays | number:'1.0-0' }} days
  </span>
</div>

<!-- Capacity trend chart -->
<canvas baseChart
  [datasets]="capacityChartData"
  [labels]="capacityChartLabels"
  [options]="capacityChartOptions"
  [type]="'line'">
</canvas>
```

**Color Coding (CSS)**:

```css
.capacity-gauge.ok {
  border-color: #4caf50;  /* Green */
}

.capacity-gauge.warning {
  border-color: #ff9800;  /* Orange */
}

.capacity-gauge.critical {
  border-color: #f44336;  /* Red */
}

.capacity-gauge.full {
  border-color: #9c27b0;  /* Purple */
}

.forecast-widget .mat-icon.safe {
  color: #4caf50;  /* > 30 days */
}

.forecast-widget .mat-icon.warning {
  color: #ff9800;  /* 7-30 days */
}

.forecast-widget .mat-icon.urgent {
  color: #f44336;  /* < 7 days */
}
```

---

## Актуализированная итоговая стратегия

### Ключевые изменения от оригинального плана

| Аспект | Было | Стало |
|--------|------|-------|
| **Capacity Threshold** | Фиксированный 95% | Adaptive: MAX(2%, 50GB free) для RW, MAX(1%, 30GB) для Edit |
| **Alerting** | Бинарный (ok/reject) | Multi-level (ok → warning → critical → full) |
| **File Size Handling** | Игнорировался | Pre-flight check (Content-Length) + optimistic retry |
| **Monitoring** | Basic capacity metrics | Comprehensive: bytes metrics + status + forecast + rejections |
| **Forecasting** | Отсутствовало | Predictive analytics с 7-30 дневными прогнозами |
| **Logging** | Simple logs | Structured JSON logs с event types и severity |
| **Admin UI** | Отсутствовало | Real-time dashboard с gauges, trends, forecast widgets |

### Преимущества актуализированной стратегии

✅ **Efficiency**: 98%+ utilization на больших SE вместо 95%
✅ **Safety**: Защита малых SE (минимум 50GB/30GB free)
✅ **Proactive**: Multi-level alerting даёт время для реакции (warning → critical → full)
✅ **Resilience**: Intelligent fallback при insufficient space (до 3 retry)
✅ **Visibility**: Comprehensive monitoring на всех уровнях (metrics + logs + UI + forecast)
✅ **Predictive**: Forecasting за 7-30 дней для proactive capacity management
✅ **Scalable**: Автоматическая адаптация к любому размеру SE без configuration

---

## Implementation Tasks

### Phase 1: Redis Storage Registry (Sprint 14)

#### Task 1.1: Redis Schema & Health Reporting

**Цель**: Реализовать Redis registry для Storage Elements с автоматическим health reporting.

**Модули**: `storage-element`, `admin-module`

**Subtasks**:

1. **Обновить Storage Element config**:
   ```python
   # storage-element/app/core/config.py

   class StorageElementSettings(BaseSettings):
       # ... existing fields

       # New fields для health reporting
       storage_element_id: str = Field(..., env="STORAGE_ELEMENT_ID")
       priority: int = Field(default=100, env="STORAGE_PRIORITY")
       external_endpoint: str = Field(..., env="STORAGE_EXTERNAL_ENDPOINT")
       health_report_interval: int = Field(default=30, env="HEALTH_REPORT_INTERVAL")
   ```

2. **Создать HealthReporter service**:
   ```bash
   storage-element/app/services/health_reporter.py
   ```
   - Periodic background task (async)
   - Публикация в Redis: `storage:elements:{se_id}` и `storage:{mode}:by_priority`
   - Расчёт capacity statistics (statvfs для local, boto3 для S3)
   - Error handling с retry logic

3. **Интегрировать HealthReporter в main.py**:
   ```python
   # storage-element/app/main.py

   @app.on_event("startup")
   async def startup_event():
       # ... existing

       # Start health reporting
       health_reporter = HealthReporter(redis_client)
       asyncio.create_task(health_reporter.start_reporting())
   ```

4. **Unit тесты для HealthReporter**:
   ```bash
   storage-element/tests/unit/test_health_reporter.py
   ```
   - Mock Redis operations
   - Test capacity calculation
   - Test error recovery

**Acceptance Criteria**:
- [x] Storage Element публикует статус в Redis каждые 30 секунд
- [x] Redis содержит актуальную capacity информацию
- [x] Sorted Set `storage:rw:by_priority` и `storage:edit:by_priority` обновляются
- [x] Prometheus metrics для capacity monitoring (Sprint 14 addition)
- [ ] Unit тесты покрывают ≥90% кода (TODO: написать тесты)

**Estimated Effort**: 6 hours

**Реализованные файлы**:
- `storage-element/app/core/config.py` - Добавлены настройки: element_id, priority, external_endpoint, health_report_interval, health_report_ttl
- `storage-element/app/core/capacity_calculator.py` - Adaptive threshold calculator с CapacityStatus enum
- `storage-element/app/core/capacity_metrics.py` - **NEW** Prometheus metrics: capacity gauges, status gauges, thresholds, file operations, Redis publish metrics
- `storage-element/app/services/health_reporter.py` - **NEW** HealthReporter service с periodic background task
- `storage-element/app/main.py` - Интеграция HealthReporter в lifespan

---

#### Task 1.2: Storage Selector в Ingester Module

**Цель**: Реализовать Sequential Fill алгоритм выбора Storage Element.

**Модули**: `ingester-module`

**Subtasks**:

1. **Создать StorageSelector service**:
   ```bash
   ingester-module/app/services/storage_selector.py
   ```
   - Метод `select_storage_element(retention_policy)`
   - Sequential Fill через Redis Sorted Set
   - Capacity threshold checks (95% RW, 90% Edit)
   - Fallback на Admin Module HTTP API

2. **Создать Admin Module fallback client**:
   ```bash
   ingester-module/app/clients/admin_client.py
   ```
   - HTTP client для `/api/v1/storage-elements`
   - Authentication через service account JWT
   - Error handling и retry logic

3. **Интегрировать StorageSelector в upload endpoint**:
   ```python
   # ingester-module/app/api/v1/endpoints/upload.py

   @router.post("/upload")
   async def upload_file(
       file: UploadFile,
       retention_policy: RetentionPolicy = RetentionPolicy.PERMANENT,
       storage_selector: StorageSelector = Depends(get_storage_selector)
   ):
       target_se = await storage_selector.select_storage_element(retention_policy)

       if not target_se:
           # Alert + Reject
           raise HTTPException(503, "No available storage")

       # ... continue upload
   ```

4. **Unit и integration тесты**:
   ```bash
   ingester-module/tests/unit/test_storage_selector.py
   ingester-module/tests/integration/test_upload_with_selection.py
   ```
   - Mock Redis responses
   - Test fallback к Admin Module
   - Test capacity threshold logic
   - Test 503 error при unavailability

**Acceptance Criteria**:
- [x] Ingester корректно выбирает SE по Sequential Fill алгоритму
- [x] Fallback на Admin Module работает при недоступности Redis (через admin_client.py)
- [x] 503 error при отсутствии доступных SE (NoAvailableStorageException)
- [x] Prometheus metrics для selection failures (реализованы базовые метрики)
- [x] Upload endpoint интегрирован с StorageSelector
- [ ] Unit тесты покрывают ≥90% кода (TODO: написать тесты)

**Estimated Effort**: 8 hours

**Реализованные файлы**:
- `ingester-module/app/services/storage_selector.py` - **NEW** StorageSelector с Sequential Fill, Redis + fallback на Admin Module + fallback на local config
- `ingester-module/app/clients/admin_client.py` - **NEW** HTTP client для Admin Module fallback API
- `ingester-module/app/services/upload_service.py` - Интеграция StorageSelector, dynamic SE endpoint selection, HTTP client caching
- `ingester-module/app/core/exceptions.py` - Добавлен NoAvailableStorageException
- `ingester-module/app/core/redis.py` - Redis async client для Ingester
- `ingester-module/app/main.py` - Инициализация Redis и StorageSelector в lifespan

**Особенности реализации**:
- Маппинг storage_mode → retention_policy: edit=TEMPORARY, rw=PERMANENT
- HTTP client кеширование для multiple SE endpoints
- Graceful degradation: Redis → Admin Module → Local config

---

#### Task 1.3: Admin Module Storage Elements API

**Цель**: Создать REST API для fallback запросов от Ingester.

**Модули**: `admin-module`

**Subtasks**:

1. **Создать endpoint `/api/v1/storage-elements`**:
   ```bash
   admin-module/app/api/v1/endpoints/storage_elements.py
   ```
   - GET endpoint с query parameters: `mode`, `available`, `order_by`
   - Фильтрация по capacity threshold
   - Сортировка по priority
   - Authentication через JWT

2. **Создать StorageElementService**:
   ```bash
   admin-module/app/services/storage_element_service.py
   ```
   - Получение SE из Redis
   - Fallback на database при недоступности Redis
   - Применение filters и sorting

3. **Integration тесты**:
   ```bash
   admin-module/tests/integration/test_storage_elements_api.py
   ```
   - Test GET endpoint
   - Test authentication
   - Test query parameters filtering

**Acceptance Criteria**:
- [x] GET `/api/internal/storage-elements/available` возвращает отсортированный список SE
- [x] Endpoint требует JWT authentication (service account)
- [x] API фильтрует по mode и capacity_status
- [ ] Integration тесты покрывают все query parameters (TODO: написать тесты)
- [x] API документация в Swagger UI (internal tag)

**Estimated Effort**: 4 hours

**Реализованные файлы**:
- `admin-module/app/api/v1/endpoints/internal.py` - **NEW** Internal endpoint для fallback запросов от Ingester
- `admin-module/app/api/v1/router.py` - Регистрация internal router
- `admin-module/app/models/storage_element.py` - SQLAlchemy модель (использует существующую)

**Особенности реализации**:
- Endpoint: `GET /api/v1/internal/storage-elements/available?mode={rw|edit}`
- Внутренний API (internal tag в Swagger), не предназначен для внешнего использования
- Фильтрация: mode, capacity_status != full
- Сортировка: по priority (ascending)

---

## Implementation Status Summary - Phase 1 (Sprint 14) ✅

| Task | Status | Notes |
|------|--------|-------|
| **Task 1.1**: Redis Schema & Health Reporting | ✅ DONE | HealthReporter + Prometheus metrics |
| **Task 1.2**: Storage Selector в Ingester | ✅ DONE | Sequential Fill + triple fallback |
| **Task 1.3**: Admin Module Internal API | ✅ DONE | Fallback endpoint |
| **Unit Tests** | ⏳ TODO | Требуется написать тесты |

---

### Phase 2: Retention Policy & Lifecycle (Sprint 15) - ✅ IMPLEMENTED

**Status**: COMPLETED (2024-12-02)

**Summary**:
- Database migrations applied successfully
- Upload API supports retention_policy and ttl_days parameters
- Finalize API endpoint implemented with Two-Phase Commit
- Models created: File, FileFinalizeTransaction, FileCleanupQueue
- Integration tests pending (Sprint 16)

#### Task 2.1: Database Schema для Retention Policy

**Цель**: Обновить database schema для поддержки retention policies и transaction logging.

**Модули**: `admin-module`, `storage-element`, `ingester-module`, `query-module`

**Subtasks**:

1. **Создать Alembic migration для files table**:
   ```bash
   admin-module/alembic/versions/xxx_add_retention_policy.py
   ```
   ```sql
   ALTER TABLE files
   ADD COLUMN retention_policy VARCHAR(20) NOT NULL DEFAULT 'permanent',
   ADD COLUMN ttl_expires_at TIMESTAMP,
   ADD COLUMN finalized_at TIMESTAMP;

   CREATE INDEX idx_files_retention_policy ON files(retention_policy);
   CREATE INDEX idx_files_ttl_expires ON files(ttl_expires_at)
   WHERE retention_policy = 'temporary';
   ```

2. **Создать file_finalize_transactions table**:
   ```sql
   CREATE TABLE file_finalize_transactions (
       transaction_id UUID PRIMARY KEY,
       file_id UUID NOT NULL REFERENCES files(file_id),
       source_se VARCHAR(255) NOT NULL,
       target_se VARCHAR(255) NOT NULL,
       status VARCHAR(50) NOT NULL,
       checksum_source VARCHAR(64),
       checksum_target VARCHAR(64),
       error_message TEXT,
       created_at TIMESTAMP NOT NULL DEFAULT NOW(),
       updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
       completed_at TIMESTAMP
   );
   ```

3. **Создать file_cleanup_queue table**:
   ```sql
   CREATE TABLE file_cleanup_queue (
       id SERIAL PRIMARY KEY,
       file_id UUID NOT NULL,
       storage_element_id VARCHAR(255) NOT NULL,
       scheduled_at TIMESTAMP NOT NULL,
       processed_at TIMESTAMP,
       error_message TEXT,
       created_at TIMESTAMP NOT NULL DEFAULT NOW()
   );
   ```

4. **Обновить SQLAlchemy models**:
   ```bash
   admin-module/app/models/file.py
   admin-module/app/models/finalize_transaction.py
   admin-module/app/models/cleanup_queue.py
   ```

5. **Тестовая миграция на dev environment**:
   ```bash
   docker-compose exec admin-module alembic upgrade head
   ```

**Acceptance Criteria**:
- [x] Alembic migrations применяются без ошибок
- [x] Все indexes созданы корректно
- [x] SQLAlchemy models синхронизированы с schema
- [x] Rollback миграций работает корректно

**Estimated Effort**: 4 hours

**Реализованные файлы** (Sprint 15):
- `admin-module/alembic/versions/20251201_0002_add_retention_policy_and_lifecycle.py` - **NEW** Миграция для files, file_finalize_transactions, file_cleanup_queue
- `admin-module/app/models/file.py` - **NEW** File model с retention_policy, ttl_expires_at, user_metadata
- `admin-module/app/models/finalize_transaction.py` - **NEW** FileFinalizeTransaction model для Two-Phase Commit
- `admin-module/app/models/cleanup_queue.py` - **NEW** FileCleanupQueue model для GC
- `admin-module/app/models/__init__.py` - Обновлён с импортом новых моделей

**Исправленные проблемы**:
- `metadata` → `user_metadata` (reserved name в SQLAlchemy)
- `create_type=True` для PostgreSQL ENUM типов (retention_policy_enum, finalize_transaction_status_enum)
- `admin-module/app/api/dependencies/auth.py` - Исправлен импорт несуществующего User model → ServiceAccount

---

#### Task 2.2: Retention Policy в Upload API

**Цель**: Добавить поддержку retention_policy в upload endpoint.

**Модули**: `ingester-module`

**Subtasks**:

1. **Обновить UploadRequest schema**:
   ```python
   # ingester-module/app/schemas/upload.py

   from enum import Enum

   class RetentionPolicy(str, Enum):
       TEMPORARY = "temporary"
       PERMANENT = "permanent"

   class UploadRequest(BaseModel):
       retention_policy: RetentionPolicy = RetentionPolicy.PERMANENT
       ttl_days: Optional[int] = Field(default=30, ge=1, le=365)
       metadata: dict = Field(default_factory=dict)
   ```

2. **Обновить upload endpoint**:
   ```python
   # ingester-module/app/api/v1/endpoints/upload.py

   @router.post("/upload")
   async def upload_file(
       file: UploadFile,
       request: UploadRequest,
       storage_selector: StorageSelector = Depends(get_storage_selector)
   ):
       # Select SE based on retention_policy
       target_se = await storage_selector.select_storage_element(
           retention_policy=request.retention_policy.value
       )

       # Calculate TTL expiration
       ttl_expires_at = None
       if request.retention_policy == RetentionPolicy.TEMPORARY:
           ttl_expires_at = datetime.utcnow() + timedelta(days=request.ttl_days)

       # Upload to Storage Element
       file_id = await file_service.upload_to_storage(
           file=file,
           storage_element=target_se,
           retention_policy=request.retention_policy,
           ttl_expires_at=ttl_expires_at,
           metadata=request.metadata
       )

       return {"file_id": file_id, "retention_policy": request.retention_policy}
   ```

3. **Integration тесты**:
   ```bash
   ingester-module/tests/integration/test_upload_retention_policy.py
   ```
   - Test upload с temporary retention
   - Test upload с permanent retention
   - Test TTL calculation
   - Test validation (ttl_days range)

**Acceptance Criteria**:
- [x] Upload API принимает retention_policy parameter
- [x] TTL корректно рассчитывается для temporary files
- [x] Files записываются в соответствующие SE (edit или rw)
- [ ] Integration тесты проходят успешно (TODO: написать тесты)
- [x] API documentation обновлена (Swagger UI)

**Estimated Effort**: 4 hours

**Реализованные файлы** (Sprint 15):
- `ingester-module/app/schemas/upload.py` - **UPDATED** RetentionPolicy enum, UploadRequest с retention_policy и ttl_days
- `ingester-module/app/api/v1/endpoints/upload.py` - **UPDATED** Upload endpoint с retention_policy support
- `ingester-module/app/services/upload_service.py` - **UPDATED** Интеграция retention_policy в upload flow

**Особенности реализации**:
- Default retention_policy = "temporary" (для Edit SE)
- ttl_days диапазон: 1-365 дней, default 30
- storage_mode deprecated в пользу retention_policy
- Маппинг: temporary → edit SE, permanent → rw SE

---

#### Task 2.3: Finalize API Endpoint

**Цель**: Реализовать API для финализации temporary → permanent.

**Модули**: `ingester-module` или `admin-module` (TBD)

**Subtasks**:

1. **Создать FinalizeRequest/Response schemas**:
   ```bash
   ingester-module/app/schemas/finalize.py
   ```

2. **Создать FileFinalizationService**:
   ```bash
   ingester-module/app/services/file_finalization_service.py
   ```
   - `start_finalize_transaction()`
   - `copy_to_target()` - Phase 1
   - `verify_and_commit()` - Phase 2
   - `schedule_cleanup()`
   - `rollback_finalize()`

3. **Создать endpoint `/api/v1/files/{file_id}/finalize`**:
   ```python
   @router.post("/files/{file_id}/finalize")
   async def finalize_file(
       file_id: str,
       request: FinalizeRequest,
       file_service: FileFinalizationService = Depends(...)
   ):
       # Validation
       file_meta = await file_service.get_file_metadata(file_id)
       if file_meta.retention_policy == RetentionPolicy.PERMANENT:
           raise HTTPException(400, "File is already finalized")

       # Two-Phase Commit
       transaction_id = await file_service.start_finalize_transaction(...)

       try:
           await file_service.copy_to_target(...)
           await file_service.verify_and_commit(...)
           await file_service.schedule_cleanup(...)

           return {"status": "finalized", "transaction_id": transaction_id}
       except Exception as e:
           await file_service.rollback_finalize(transaction_id)
           raise HTTPException(500, f"Finalization failed: {e}")
   ```

4. **Integration тесты**:
   ```bash
   ingester-module/tests/integration/test_finalize_api.py
   ```
   - Test successful finalization
   - Test rollback при checksum mismatch
   - Test идемпотентность (повторный finalize)
   - Test cleanup scheduling

**Acceptance Criteria**:
- [x] POST `/api/v1/finalize/{file_id}` работает корректно ✅
- [x] Two-Phase Commit обеспечивает atomicity ✅
- [x] Checksum verification предотвращает corruption ✅
- [x] Cleanup корректно добавляется в queue ✅
- [ ] Integration тесты покрывают все сценарии (Sprint 16)
- [x] Transaction log записывается в DB ✅

**Estimated Effort**: 12 hours

**Реализованные файлы** (Sprint 15):
- `ingester-module/app/api/v1/endpoints/finalize.py` - **NEW** Finalize API endpoints
- `ingester-module/app/services/finalize_service.py` - **NEW** FinalizeService с Two-Phase Commit
- `ingester-module/app/schemas/upload.py` - **UPDATED** FinalizeRequest, FinalizeResponse, FinalizeStatus schemas
- `admin-module/app/models/finalize_transaction.py` - **NEW** FileFinalizeTransaction model
- `admin-module/app/models/cleanup_queue.py` - **NEW** FileCleanupQueue model

**Особенности реализации**:
- **Endpoint изменён**: `/api/v1/finalize/{file_id}` (вместо `/api/v1/files/{file_id}/finalize`)
- **Async Two-Phase Commit**: HTTP 202 Accepted с transaction_id для асинхронного отслеживания
- **Status polling**: GET `/api/v1/finalize/{transaction_id}/status` для отслеживания прогресса
- **Status progression**: COPYING (25%) → COPIED (50%) → VERIFYING (75%) → COMPLETED (100%)
- **Safety margin**: 24 часа перед удалением из source SE
- **TODO**: Integration с Admin Module file registry (MVP использует placeholder данные)

---

### Phase 3: Garbage Collection (Sprint 16)

#### Task 3.1: GarbageCollector Background Job

**Цель**: Реализовать периодический GC job для очистки Edit Storage Elements.

**Модули**: `admin-module`

**Subtasks**:

1. **Создать GarbageCollector service**:
   ```bash
   admin-module/app/services/garbage_collector.py
   ```
   - `start()` - periodic execution (every 6h)
   - `_run_cleanup_cycle()` - main orchestrator
   - `_cleanup_expired_ttl()` - TTL-based cleanup
   - `_cleanup_finalized_files()` - cleanup после finalize
   - `_cleanup_orphaned_files()` - orphaned files cleanup

2. **Интегрировать GC job в main.py**:
   ```python
   # admin-module/app/main.py

   @app.on_event("startup")
   async def startup_event():
       # ... existing

       # Start Garbage Collector
       gc = GarbageCollector(db, redis_client)
       asyncio.create_task(gc.start())
   ```

3. **Prometheus metrics для GC**:
   ```python
   gc_cleanup_total = Counter(
       "gc_cleanup_total",
       "Total files cleaned by GC",
       ["type"]  # ttl | finalized | orphaned
   )

   gc_cleanup_duration = Histogram(
       "gc_cleanup_duration_seconds",
       "Duration of GC cleanup cycle"
   )
   ```

4. **Unit тесты**:
   ```bash
   admin-module/tests/unit/test_garbage_collector.py
   ```
   - Mock DB operations
   - Test TTL expiration logic
   - Test orphaned files detection
   - Test cleanup scheduling

5. **Integration тесты**:
   ```bash
   admin-module/tests/integration/test_gc_full_cycle.py
   ```
   - End-to-end test полного GC цикла
   - Test взаимодействие с Storage Elements
   - Test cleanup queue processing

**Acceptance Criteria**:
- [x] GC job запускается каждые 6 часов ✅
- [x] TTL-based cleanup удаляет expired files ✅
- [x] Finalized files cleanup обрабатывает cleanup queue ✅
- [x] Orphaned files cleanup удаляет files без DB records ✅
- [x] Prometheus metrics записываются корректно ✅
- [x] Unit тесты проходят успешно (19/19 passed) ✅
- [ ] Integration тесты (TODO: Sprint 17)

**Estimated Effort**: 10 hours

**Реализованные файлы** (Sprint 16):
- `admin-module/app/services/garbage_collector_service.py` - **NEW** GarbageCollectorService с тремя стратегиями очистки
- `admin-module/app/core/config.py` - **UPDATED** Добавлены GC settings в SchedulerSettings
- `admin-module/app/core/scheduler.py` - **UPDATED** Интеграция GC job в APScheduler
- `admin-module/tests/unit/test_garbage_collector.py` - **NEW** Unit тесты (19 тестов)

**Особенности реализации**:
- **Три стратегии очистки**: TTL-based, Finalized files (+24h safety margin), Orphaned files (>7 days grace)
- **Prometheus metrics**: gc_files_cleaned_total, gc_files_failed_total, gc_run_duration_seconds, gc_last_run_timestamp, gc_queue_pending_size
- **Configurable settings**: SCHEDULER_GC_ENABLED, SCHEDULER_GC_INTERVAL_HOURS (default 6), SCHEDULER_GC_BATCH_SIZE (default 100), SCHEDULER_GC_SAFETY_MARGIN_HOURS (default 24), SCHEDULER_GC_ORPHAN_GRACE_DAYS (default 7)
- **HTTP client**: Использует httpx.AsyncClient для удаления файлов на Storage Elements
- **Retry logic**: max_retry_count=3 для обработки transient failures

---

#### Task 3.2: Storage Element Delete API

**Цель**: Реализовать API для удаления файлов на Storage Element (используется GC job).

**Модули**: `storage-element`

**Subtasks**:

1. **Создать DELETE endpoint**:
   ```bash
   storage-element/app/api/v1/endpoints/files.py
   ```
   ```python
   @router.delete("/files/{file_id}")
   async def delete_file(
       file_id: str,
       current_user: dict = Depends(get_current_user)
   ):
       # Authorization check (только service accounts)
       if current_user["type"] != "service_account":
           raise HTTPException(403, "Only service accounts can delete files")

       # Delete physical file
       await file_service.delete_file(file_id)

       # Delete attr.json
       await file_service.delete_attr_file(file_id)

       # Update DB cache (mark as deleted)
       await db.execute(
           "UPDATE file_metadata SET deleted_at = NOW() WHERE file_id = $1",
           file_id
       )

       return {"status": "deleted", "file_id": file_id}
   ```

2. **Audit logging для delete operations**:
   ```python
   await audit_service.log_event(
       action="file_delete",
       resource_id=file_id,
       user_id=current_user["id"],
       details={"reason": "gc_cleanup"}
   )
   ```

3. **Integration тесты**:
   ```bash
   storage-element/tests/integration/test_delete_api.py
   ```
   - Test successful delete
   - Test authorization (только service accounts)
   - Test audit logging
   - Test idempotency (delete уже удалённого файла)

**Acceptance Criteria**:
- [x] DELETE `/api/v1/gc/{file_id}` работает корректно ✅
- [x] Physical file и attr.json удаляются (через FileService.delete_file) ✅
- [x] DB cache удаляется полностью ✅
- [x] Audit log записывается для каждого delete (structured logging) ✅
- [x] Только service accounts могут удалять файлы ✅
- [x] Unit тесты проходят успешно (12/12 passed) ✅
- [ ] Integration тесты (Sprint 17)

**Estimated Effort**: 4 hours

**Реализованные файлы** (Sprint 16):
- `storage-element/app/api/deps/auth.py` - **UPDATED** Добавлен `require_service_account` dependency
- `storage-element/app/api/deps/__init__.py` - **UPDATED** Экспорт ServiceAccount
- `storage-element/app/api/v1/endpoints/gc.py` - **NEW** GC API endpoints (DELETE, GET /exists)
- `storage-element/app/api/v1/router.py` - **UPDATED** Подключение GC router
- `storage-element/tests/unit/test_gc_api.py` - **NEW** Unit тесты (12 тестов)
- `storage-element/tests/integration/test_gc_delete_api.py` - **NEW** Integration тесты

**Implementation Notes**:
- **Endpoint**: `DELETE /api/v1/gc/{file_id}` (отдельный от основного `/files/{file_id}`)
- **Authorization**: Только Service Accounts через `require_service_account` dependency
- **Idempotency**: Повторное удаление возвращает `status="already_deleted"` (200 OK)
- **Audit logging**: Structured JSON logs с `audit=True` marker
- **Cleanup types**: Поддерживает `ttl_expired`, `finalized`, `orphaned`
- **Существующий FileService**: Использует `FileService.delete_file` для WAL protocol

---

### Phase 4: Monitoring & Documentation (Sprint 17)

#### Task 4.1: Prometheus Metrics

**Цель**: Добавить comprehensive metrics для monitoring новой функциональности.

**Модули**: Все модули

**Metrics**:

```python
# Ingester Module
storage_selection_duration = Histogram(
    "storage_selection_duration_seconds",
    "Duration of storage element selection"
)

storage_selection_total = Counter(
    "storage_selection_total",
    "Total storage selections",
    ["retention_policy", "status"]  # status: success | fallback | failed
)

storage_unavailable_total = Counter(
    "storage_unavailable_total",
    "Total times no storage was available",
    ["retention_policy"]
)

# File Finalization
file_finalize_duration = Histogram(
    "file_finalize_duration_seconds",
    "Duration of file finalization"
)

file_finalize_total = Counter(
    "file_finalize_total",
    "Total file finalizations",
    ["status"]  # status: success | failed | rollback
)

# Garbage Collector
gc_cleanup_total = Counter(
    "gc_cleanup_total",
    "Total files cleaned by GC",
    ["type"]  # ttl | finalized | orphaned
)

gc_cleanup_duration = Histogram(
    "gc_cleanup_duration_seconds",
    "Duration of GC cleanup cycle"
)

# Storage Element Health
storage_element_capacity_percent = Gauge(
    "storage_element_capacity_percent",
    "Storage element capacity usage percentage",
    ["se_id", "mode"]
)

storage_element_health_status = Gauge(
    "storage_element_health_status",
    "Storage element health status (1=healthy, 0=unhealthy)",
    ["se_id"]
)
```

**Acceptance Criteria**:
- [ ] Все metrics экспортируются на `/metrics` endpoint
- [ ] Metrics доступны в Prometheus
- [ ] Grafana dashboard создан для визуализации

**Estimated Effort**: 4 hours

---

#### Task 4.2: Grafana Dashboard

**Цель**: Создать Grafana dashboard для monitoring storage lifecycle.

**Subtasks**:

1. **Создать dashboard JSON**:
   ```bash
   monitoring/grafana/dashboards/storage-lifecycle.json
   ```

2. **Панели**:
   - Storage Element Capacity (по SE)
   - Storage Selection Success Rate
   - Finalization Success Rate
   - GC Cleanup Statistics
   - Storage Unavailability Alerts
   - Two-Phase Commit Transaction Status

3. **Import dashboard в Grafana**:
   ```bash
   # Via provisioning
   monitoring/grafana/provisioning/dashboards/storage-lifecycle.yaml
   ```

**Acceptance Criteria**:
- [ ] Dashboard отображает все key metrics
- [ ] Панели обновляются в real-time
- [ ] Dashboard автоматически импортируется при запуске Grafana

**Estimated Effort**: 3 hours

---

#### Task 4.3: Documentation Updates

**Цель**: Обновить документацию для новой функциональности.

**Subtasks**:

1. **Обновить README.md**:
   - Секция "Storage Element Selection Strategy"
   - Секция "File Lifecycle Management"
   - Диаграммы Sequential Fill и Two-Phase Commit

2. **Обновить модульные README.md**:
   - `ingester-module/README.md` - Storage Selector
   - `storage-element/README.md` - Health Reporting
   - `admin-module/README.md` - GC Job

3. **Обновить API documentation**:
   - Swagger UI descriptions для новых endpoints
   - Examples для retention_policy параметров

4. **Создать Architecture Decision Records (ADR)**:
   ```bash
   docs/adr/014-sequential-fill-strategy.md
   docs/adr/015-retention-policy-model.md
   docs/adr/016-two-phase-commit-finalization.md
   ```

**Acceptance Criteria**:
- [ ] README.md обновлён с новыми секциями
- [ ] API documentation актуальна
- [ ] ADR документируют key architectural decisions
- [ ] Диаграммы включены в документацию

**Estimated Effort**: 6 hours

---

## Testing Strategy

### Unit Tests

| Module | Test Coverage Target | Key Areas |
|--------|---------------------|-----------|
| Storage Element | ≥90% | HealthReporter, capacity calculation |
| Ingester Module | ≥90% | StorageSelector, fallback logic |
| Admin Module | ≥90% | GarbageCollector, finalization service |

### Integration Tests

| Scenario | Description | Success Criteria |
|----------|-------------|------------------|
| **Sequential Fill** | Upload несколько файлов, verify SE selection order | Файлы записываются в SE по priority |
| **Fallback** | Redis unavailable, verify fallback to Admin Module | Upload успешен через Admin API |
| **Finalization** | Upload temporary file, finalize to permanent | Two-Phase Commit успешен, cleanup scheduled |
| **GC Cleanup** | Expire temporary file, wait for GC cycle | File удалён из Edit SE |
| **Capacity Threshold** | Fill SE до 95%, verify new SE selection | Ingester переключается на следующий SE |

### End-to-End Tests

| Workflow | Description | Validation |
|----------|-------------|------------|
| **Full Lifecycle** | Upload temporary → Finalize → GC cleanup | File проходит через все этапы без ошибок |
| **Concurrent Uploads** | Несколько Ingester пишут параллельно | Sequential Fill работает корректно |
| **SE Failure** | Отключить SE, verify system resilience | Система переключается на backup SE |

---

## Rollout Plan

### Sprint 14: Redis Registry & Selection (Week 1-2) ✅ COMPLETED

**Deliverables**:
- [x] HealthReporter в Storage Element
- [x] StorageSelector в Ingester Module
- [x] Admin Module fallback API
- [x] Prometheus metrics для capacity monitoring (bonus)
- [ ] Unit и integration тесты (TODO)

**Deployment**:
1. Deploy updated Storage Element (backward compatible)
2. Deploy Admin Module с fallback API
3. Deploy Ingester Module с StorageSelector
4. Monitor Redis registry population
5. Verify Sequential Fill behaviour

**Rollback Plan**:
- Ingester fallback на hardcoded SE list
- Admin Module rollback к previous version

---

### Sprint 15: Retention Policy & Lifecycle (Week 3-4) - ✅ COMPLETED

**Deliverables**:
- [x] Database migrations для retention_policy ✅
- [x] Upload API с retention_policy support ✅
- [x] Finalize API endpoint ✅
- [x] Two-Phase Commit implementation ✅
- [ ] Integration тесты (перенесены в Sprint 16)

**Implemented Files**:
- `admin-module/alembic/versions/20251201_0002_add_retention_policy_and_lifecycle.py`
- `admin-module/app/models/file.py`, `finalize_transaction.py`, `cleanup_queue.py`
- `ingester-module/app/api/v1/endpoints/finalize.py`
- `ingester-module/app/services/finalize_service.py`
- `ingester-module/app/schemas/upload.py` (updated)

**Deployment** (COMPLETED 2024-12-02):
1. ✅ Applied database migrations (backward compatible)
2. ✅ Deployed Ingester Module с retention_policy API
3. ✅ Deployed Admin Module с finalization models
4. ⏳ Monitor finalization success rate (pending integration tests)
5. ⏳ Verify cleanup queue population (pending GC implementation)

**Rollback Plan**:
- Retention policy defaults to "permanent"
- Finalize API disabled via feature flag

---

### Sprint 16: Garbage Collection (Week 5-6) - ✅ COMPLETED

**Deliverables**:
- [x] GarbageCollector background job ✅ (Task 3.1 DONE)
- [x] Storage Element delete API (Task 3.2 DONE)
- [x] Cleanup queue processing ✅ (included in Task 3.1)
- [x] Unit тесты ✅ (19/19 passed)
- [ ] Integration тесты (Sprint 17)

**Deployment**:
1. Deploy Storage Element с delete API
2. Deploy Admin Module с GC job
3. Monitor GC cleanup metrics
4. Verify no data loss during cleanup

**Rollback Plan**:
- Disable GC job via config flag
- Manual cleanup через Admin API

---

### Sprint 17: Monitoring & Documentation (Week 7)

**Deliverables**:
- [ ] Prometheus metrics
- [ ] Grafana dashboard
- [ ] Updated documentation
- [ ] ADR documents

**Deployment**:
1. Deploy metrics to all modules
2. Import Grafana dashboard
3. Publish updated documentation
4. Conduct team training session

---

## Success Metrics

### Performance Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Storage Selection Latency** | < 50ms (p95) | Prometheus histogram |
| **Finalization Duration** | < 30s for 1GB file (p95) | Prometheus histogram |
| **GC Cleanup Throughput** | ≥ 1000 files/hour | Prometheus counter |
| **Storage Unavailability Rate** | < 0.1% | Prometheus counter / total uploads |

### Reliability Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Sequential Fill Correctness** | 100% | Manual verification + integration tests |
| **Finalization Success Rate** | ≥ 99.9% | Prometheus counter (success / total) |
| **Data Integrity (checksum match)** | 100% | Transaction log analysis |
| **GC False Positive Rate** | 0% | Audit log review |

### Operational Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Redis Availability** | ≥ 99.9% | Uptime monitoring |
| **Fallback Frequency** | < 1% | Prometheus counter (fallback / total) |
| **Edit SE Capacity Utilization** | 70-90% | Prometheus gauge |
| **RW SE Capacity Utilization** | 80-95% | Prometheus gauge |

---

## Risk Assessment

### High Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Data loss при finalization** | High | Two-Phase Commit с checksum verification, 24h safety margin |
| **GC удаляет активные файлы** | High | 7-day grace period для orphaned files, audit logging |
| **Sequential Fill не работает** | Medium | Fallback на Admin Module, comprehensive testing |

### Medium Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Redis unavailability** | Medium | Fallback на Admin Module HTTP API |
| **Storage Element capacity exhausted** | Medium | Alert + Reject, 95% threshold для early warning |
| **Performance degradation при GC** | Low | Batch processing, 6-hour interval |

### Low Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Clock skew влияет на TTL** | Low | Use UTC timestamps, reasonable TTL margins (30 days) |
| **Race condition в Sequential Fill** | Low | Acceptable behaviour, capacity monitoring fixes drift |

---

## Maintenance & Operations

### Monitoring Alerts

```yaml
# Prometheus AlertManager rules

- alert: StorageUnavailable
  expr: rate(storage_unavailable_total[5m]) > 0
  for: 1m
  severity: critical
  annotations:
    summary: "No available storage for uploads"

- alert: FinalizationFailureRate
  expr: |
    rate(file_finalize_total{status="failed"}[10m]) /
    rate(file_finalize_total[10m]) > 0.01
  for: 5m
  severity: warning
  annotations:
    summary: "Finalization failure rate > 1%"

- alert: GCCleanupStuck
  expr: |
    time() - gc_cleanup_last_success_timestamp > 7200
  for: 10m
  severity: warning
  annotations:
    summary: "GC cleanup hasn't run successfully in 2 hours"

- alert: StorageElementCapacityHigh
  expr: storage_element_capacity_percent > 90
  for: 15m
  severity: warning
  annotations:
    summary: "Storage Element {{ $labels.se_id }} capacity > 90%"
```

### Operational Runbooks

#### Runbook 1: Storage Unavailable Alert

**Symptoms**: Upload requests failing with 503 errors

**Investigation**:
1. Check Prometheus: `storage_unavailable_total` counter
2. Check Redis: `redis-cli ZRANGE storage:rw:by_priority 0 -1`
3. Check Storage Element capacity: `storage_element_capacity_percent` gauge

**Resolution**:
1. If capacity exhausted: Add new Storage Element or expand existing
2. If Redis unavailable: Restart Redis, verify fallback to Admin Module
3. If all SE unhealthy: Investigate SE health issues

---

#### Runbook 2: Finalization Failures

**Symptoms**: High rate of finalization failures

**Investigation**:
1. Check transaction log: `SELECT * FROM file_finalize_transactions WHERE status = 'failed' ORDER BY created_at DESC LIMIT 10`
2. Check error messages: `error_message` column
3. Check network connectivity between Edit SE and RW SE

**Resolution**:
1. If checksum mismatch: Investigate storage corruption, retry finalization
2. If network issues: Check SE health status, verify endpoints
3. Manual intervention: Use Admin API to retry failed transactions

---

#### Runbook 3: GC Not Running

**Symptoms**: `GCCleanupStuck` alert firing

**Investigation**:
1. Check Admin Module logs: `docker-compose logs -f admin-module | grep "GC"`
2. Check GC metrics: `gc_cleanup_duration_seconds`, `gc_cleanup_total`
3. Check DB connectivity and Redis health

**Resolution**:
1. If Admin Module crashed: Restart container
2. If DB locked: Check for long-running transactions
3. Manual cleanup: Use `/api/v1/admin/cleanup/trigger` endpoint

---

## Appendix

### A. Redis Commands for Debugging

```bash
# Проверить статус Storage Elements
redis-cli HGETALL storage:elements:se-1

# Проверить RW priority queue
redis-cli ZRANGE storage:rw:by_priority 0 -1 WITHSCORES

# Проверить Edit priority queue
redis-cli ZRANGE storage:edit:by_priority 0 -1 WITHSCORES

# Удалить устаревший SE
redis-cli ZREM storage:rw:by_priority se-1
redis-cli DEL storage:elements:se-1
```

### B. Database Queries for Debugging

```sql
-- Проверить pending finalization transactions
SELECT * FROM file_finalize_transactions
WHERE status IN ('copying', 'copied')
ORDER BY created_at DESC;

-- Проверить cleanup queue
SELECT * FROM file_cleanup_queue
WHERE processed_at IS NULL AND scheduled_at < NOW()
ORDER BY scheduled_at ASC;

-- Проверить expired TTL files
SELECT file_id, created_at, ttl_expires_at
FROM files
WHERE retention_policy = 'temporary'
  AND ttl_expires_at < NOW()
  AND deleted_at IS NULL;

-- Статистика по retention policies
SELECT retention_policy, COUNT(*) as count,
       AVG(EXTRACT(EPOCH FROM (NOW() - created_at))/86400) as avg_age_days
FROM files
WHERE deleted_at IS NULL
GROUP BY retention_policy;
```

### C. API Examples

```bash
# Upload temporary file
curl -X POST http://localhost:8020/api/v1/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@document.pdf" \
  -F "retention_policy=temporary" \
  -F "ttl_days=30"

# Upload permanent file
curl -X POST http://localhost:8020/api/v1/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@document.pdf" \
  -F "retention_policy=permanent"

# Finalize temporary file
curl -X POST http://localhost:8020/api/v1/files/{file_id}/finalize \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"target_retention_policy": "permanent"}'

# Get Storage Elements (Admin fallback API)
curl -X GET "http://localhost:8000/api/v1/storage-elements?mode=rw&available=true&order_by=priority" \
  -H "Authorization: Bearer $TOKEN"

# Trigger manual GC cleanup (Admin API)
curl -X POST http://localhost:8000/api/v1/admin/cleanup/trigger \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"cleanup_type": "ttl"}'
```

---

## Changelog

| Date | Version | Changes | Author |
|------|---------|---------|--------|
| 2025-12-01 | 1.0 | Initial version | Claude + User |
| 2025-12-01 | 1.1 | Актуализация: Adaptive capacity thresholds, multi-level alerting, intelligent file size handling, comprehensive monitoring & forecasting | Claude + User |
| 2025-12-01 | 1.2 | **Sprint 14 IMPLEMENTED**: HealthReporter, StorageSelector, Admin Module internal API, Prometheus metrics. Updated acceptance criteria, added implementation notes | Claude + User |
| 2025-12-02 | 1.3 | **Sprint 16 Task 3.1 IMPLEMENTED**: GarbageCollectorService с тремя стратегиями очистки (TTL, Finalized, Orphaned), Prometheus metrics, APScheduler integration, 19 unit tests passed | Claude + User |
| 2025-12-02 | 1.4 | **Sprint 16 Task 3.2 IMPLEMENTED**: Storage Element GC Delete API (`DELETE /api/v1/gc/{file_id}`), require_service_account dependency, idempotent delete, audit logging, 12 unit tests passed | Claude + User |

---

## Sign-off

**Prepared by**: Claude Code (AI Assistant)
**Reviewed by**: [To be filled]
**Approved by**: [To be filled]
**Date**: 2025-12-01
