# План миграции: Geo-Distributed Capacity Management с Leader Election

**Создан:** 2025-12-04
**Обновлён:** 2025-12-04
**Статус:** Phase 2 Testing COMPLETE ✅

## 🎯 Цели миграции

1. Переход от Redis-based push модели к HTTP polling модели
2. Поддержка Storage Elements в удаленных ЦОД (без доступа к Redis)
3. Горизонтальное масштабирование Ingester с Leader Election
4. Снижение сетевого трафика на 75%

## 📋 Проблемы, которые решаем

### Первичная: Storage Elements в удаленных ЦОД
- Не имеют доступа к центральному Redis
- Не могут инициировать подключение через reverse proxy/PTF/WAF
- Текущая архитектура (Storage → Redis ← Ingester) не работает

### Вторичная: Горизонтальное масштабирование Ingester
- Без coordination: 4 Ingester × 100 SE = 1,152,000 requests/day
- Дублирование polling, waste resources
- С Leader Election: 288,000 requests/day (75% reduction)

## 🏗️ Целевая архитектура

```
┌──────────────────── Control Plane ────────────────────┐
│  N × Ingester (Leader Election via Redis)             │
│  - 1 LEADER: Polling Storage Elements                 │
│  - N-1 FOLLOWERS: Reading from shared Redis cache     │
│                                                         │
│  Redis (Shared):                                       │
│  - capacity_monitor:leader_lock (TTL=30s)             │
│  - capacity:{se_id} (TTL=600s)                        │
│  - health:{se_id} (TTL=600s)                          │
└─────────────────────┬───────────────────────────────────┘
                      │
          ┌───────────┴───────────┐
          │ ТОЛЬКО Leader polls   │
          ↓                        ↓
    Reverse Proxy / PTF / WAF
          │
          ↓
    Storage Elements (DC1-5)
    GET /api/v1/capacity
```

## 📅 Migration Phases

### Phase 1: Implementation (Sprint 17) ✅ COMPLETE

#### ✅ COMPLETED - Storage Element
- [x] `/api/v1/capacity` endpoint
- [x] `CapacityService` (Local FS + S3 support)
- [x] Configuration fields (datacenter_location, s3_soft_capacity_limit)
- [x] Router registration
- [x] Commit: `dc45fbf` merged to main

#### ✅ COMPLETED - Ingester Module
- [x] `AdaptiveCapacityMonitor` service с Leader Election
- [x] Leader Election logic (Redis SET NX EX)
- [x] Leader/Follower modes с automatic failover
- [x] HTTP polling с exponential backoff (2s, 4s, 8s)
- [x] Redis cache для capacity данных (TTL=600s)
- [x] Lazy update trigger для 507 errors
- [x] `CapacityMonitorConfig` configuration class
- [x] `CapacityMonitorSettings` в config.py
- [x] Integration в main.py lifespan
- [x] Commit: `6149077` feat(ingester): Add AdaptiveCapacityMonitor with Redis Leader Election

#### ✅ COMPLETED - Prometheus Metrics
- [x] `capacity_monitor_leader_state` - Leader/Follower status
- [x] `capacity_monitor_leader_transitions_total` - acquired/lost/renewed
- [x] `leader_lock_acquisition_duration_seconds` - lock latency
- [x] `capacity_poll_duration_seconds` - polling latency per SE
- [x] `capacity_poll_failures_total` - failures by error type
- [x] `lazy_update_triggers_total` - lazy update events
- [x] `storage_elements_available` - available SE by mode
- [x] `capacity_cache_hits_total` - cache hit/miss rate

#### ✅ COMPLETED - UploadService Integration
- [x] `InsufficientStorageException` for HTTP 507 handling
- [x] `UploadService` retry logic (3 attempts max)
- [x] `excluded_se_ids` parameter in StorageSelector
- [x] Lazy update integration via `set_capacity_monitor()`
- [x] Health checks (Capacity Monitor status, edit-mode SE count)
- [x] Commit: `e97a765` feat(ingester): Add retry logic, lazy update, and capacity health checks

#### ✅ MERGED TO MAIN
- [x] Merge commit: `f0dddde` Merge branch 'feature/ingester-adaptive-capacity-monitor'
- [x] Feature branch deleted

### Phase 2: Testing (Sprint 17, Week 2) ✅ COMPLETE

#### ✅ COMPLETED - Unit Tests
- [x] **AdaptiveCapacityMonitor Unit Tests** (44 tests)
  - StorageCapacityInfo serialization (3 tests)
  - Leader Election logic (10 tests)
  - Capacity Polling (7 tests)
  - Cache Operations (5 tests)
  - Lazy Update mechanism (3 tests)
  - Monitor Lifecycle (5 tests)
  - Status & Metrics (3 tests)
  - Global Singleton (2 tests)
  - Adaptive Polling State (2 tests)
  - **File:** `ingester-module/tests/unit/test_capacity_monitor.py`

- [x] **CapacityService Unit Tests** (19 tests)
  - Local filesystem capacity (6 tests)
  - S3 capacity calculation (5 tests)
  - get_capacity_info dispatcher (5 tests)
  - FastAPI dependency (1 test)
  - Precision calculations (2 tests)
  - **File:** `storage-element/tests/unit/test_capacity_service.py`

#### ✅ COMPLETED - Integration Tests
- [x] **Leader Election Failover** (12 tests)
  - Single instance becomes Leader
  - Second instance becomes Follower
  - Follower promotion after TTL expiry
  - Leader renews lock periodically
  - Graceful leadership release
  - Rapid Leader succession
  - Brief Redis hiccup tolerance
  - Cache survives Leader change
  - Lazy update for Follower
  - Concurrent access (only one Leader)
  - **File:** `ingester-module/tests/integration/test_capacity_monitor_failover.py`

- [x] **Adaptive Polling** (13 tests)
  - Initial interval is base_interval
  - Failure count increments on poll failure
  - Success resets failure count
  - Leader executes polling loop
  - Multiple Storage Elements polled
  - Polling updates Redis cache
  - get_capacity returns cached data
  - HTTP timeout handling
  - HTTP error response handling
  - Parallel polling multiple SE
  - Follower reads from cache
  - Status includes polling info
  - Health status reflects polling state
  - **File:** `ingester-module/tests/integration/test_adaptive_polling.py`

#### 📊 Test Summary
| Module | Test Type | Tests | Status |
|--------|-----------|-------|--------|
| Ingester | Unit (Capacity Monitor) | 44 | ✅ PASSED |
| Storage Element | Unit (CapacityService) | 19 | ✅ PASSED |
| Ingester | Integration (Failover) | 12 | ✅ PASSED |
| Ingester | Integration (Polling) | 13 | ✅ PASSED |
| **TOTAL** | | **88** | ✅ **ALL PASSED** |

### Phase 3: Parallel Run (Sprint 18)

- [ ] Deploy AdaptiveCapacityMonitor (parallel с текущей Redis write логикой)
- [ ] Storage Elements продолжают писать в Redis (compatibility)
- [ ] Monitoring: Leader transitions, poll metrics, cache consistency
- [ ] Validation: сравнение данных из двух источников
- [ ] Duration: 1 week minimum

### Phase 4: Cutover (Sprint 19)

- [ ] Verify Leader Election stability (>99.9% uptime)
- [ ] Ingester читает ТОЛЬКО из capacity cache
- [ ] Удалить Redis write logic из Storage Elements
- [ ] Cleanup старых Redis keys
- [ ] Full production monitoring
- [ ] Rollback plan validation

## 🔧 Технические детали

### Созданные файлы (Phase 1 + Phase 2)

```
storage-element/
├── app/api/v1/endpoints/capacity.py      # NEW - /capacity endpoint
├── app/services/capacity_service.py      # NEW - CapacityService
├── app/api/v1/router.py                  # MODIFIED - router registration
├── app/core/config.py                    # MODIFIED - datacenter_location, s3_soft_limit
└── tests/unit/test_capacity_service.py   # NEW - 19 unit tests

ingester-module/
├── app/services/capacity_monitor.py      # NEW - AdaptiveCapacityMonitor (~1000 lines)
├── app/core/config.py                    # MODIFIED - CapacityMonitorSettings
├── app/core/metrics.py                   # MODIFIED - Leader Election metrics (8 new)
├── app/core/exceptions.py                # MODIFIED - InsufficientStorageException
├── app/services/upload_service.py        # MODIFIED - retry logic, lazy update
├── app/services/storage_selector.py      # MODIFIED - excluded_se_ids support
├── app/api/v1/endpoints/health.py        # MODIFIED - capacity monitor health checks
├── app/main.py                           # MODIFIED - lifespan integration
├── tests/unit/test_capacity_monitor.py   # NEW - 44 unit tests
├── tests/integration/test_capacity_monitor_failover.py  # NEW - 12 integration tests
└── tests/integration/test_adaptive_polling.py           # NEW - 13 integration tests
```

### Redis Cache Structure

```redis
# Leader Election
capacity_monitor:leader_lock = "ingester-instance-uuid"
TTL: 30s

# Capacity Data (обновляется Leader)
capacity:{se_id} = {
  "storage_id": "se-dc2-01",
  "mode": "rw",
  "total": "...",
  "used": "...",
  "available": "...",
  "percent_used": "...",
  "health": "healthy",
  "backend": "local",
  "location": "dc2",
  "last_update": "ISO8601",
  "last_poll": "ISO8601",
  "endpoint": "https://..."
}
TTL: 600s

# Health Status
health:{se_id} = "healthy" | "unhealthy: <reason>"
TTL: 600s
```

### Leader Election Logic

```python
# Atomic leadership acquisition
acquired = await redis.set(
    "capacity_monitor:leader_lock",
    instance_id,
    nx=True,  # SET only if NOT exists
    ex=30,    # Expire after 30s
)

# Leadership renewal (Leader only)
if is_leader:
    await redis.expire("capacity_monitor:leader_lock", 30)
```

### Retry Logic with Lazy Update

```python
# UploadService retry pattern
excluded_se_ids = set()
for attempt in range(max_retries):
    se = await storage_selector.select_storage_element(
        file_size=size,
        excluded_se_ids=excluded_se_ids
    )
    try:
        return await _upload_to_storage_element(se, ...)
    except InsufficientStorageException as e:
        excluded_se_ids.add(e.storage_element_id)
        if capacity_monitor:
            await capacity_monitor.trigger_lazy_update(e.storage_element_id)
```

### Automatic Failover Timeline

```
T=0s:   Ingester-01 LEADER (TTL=30s)
T=15s:  Ingester-01 crashes
T=30s:  Lock expires
T=31s:  Ingester-02 acquires lock → becomes LEADER
        
Max failover time: 30s
Cache remains valid: 600s (TTL)
```

### Configuration Parameters

```bash
# Storage Element
STORAGE_ELEMENT_ID=se-dc2-01
STORAGE_DATACENTER_LOCATION=dc2
STORAGE_TYPE=local|s3
STORAGE_EXTERNAL_ENDPOINT=https://se-dc2-01.example.com
STORAGE_S3_SOFT_CAPACITY_LIMIT=10995116277760  # 10TB

# Ingester (NEW - Sprint 17)
CAPACITY_MONITOR_ENABLED=on
CAPACITY_MONITOR_LEADER_TTL=30
CAPACITY_MONITOR_LEADER_RENEWAL_INTERVAL=10
CAPACITY_MONITOR_BASE_INTERVAL=30
CAPACITY_MONITOR_MAX_INTERVAL=300
CAPACITY_MONITOR_HTTP_TIMEOUT=15
CAPACITY_MONITOR_HTTP_RETRIES=3
CAPACITY_MONITOR_RETRY_BASE_DELAY=2.0
CAPACITY_MONITOR_CACHE_TTL=600
CAPACITY_MONITOR_HEALTH_TTL=600
CAPACITY_MONITOR_FAILURE_THRESHOLD=3
CAPACITY_MONITOR_RECOVERY_THRESHOLD=2
```

## 📊 Prometheus Metrics

### Leader Election
- `capacity_monitor_leader_state{instance_id}` - 1=leader, 0=follower
- `capacity_monitor_leader_transitions_total{instance_id, transition_type}` - acquired/lost/renewed
- `leader_lock_acquisition_duration_seconds{result}` - latency

### Capacity Polling
- `capacity_poll_duration_seconds{storage_id, status}` - poll latency
- `capacity_poll_failures_total{storage_id, error_type}` - failures
- `lazy_update_triggers_total{storage_id, reason}` - stale cache events
- `storage_elements_available{mode}` - available SE count
- `capacity_cache_hits_total{result}` - cache hit/miss

## ⚠️ Known Limitations

1. **Leader Failover Window:** Max 30s без polling
   - Mitigation: Cache TTL=600s, lazy update

2. **Redis Dependency:** Redis down = no Leader Election
   - Mitigation: Redis HA (Sentinel), followers use stale cache

3. **Eventual Consistency:** 30s-5min capacity staleness
   - Mitigation: Lazy update на 507 errors

## 🔄 Rollback Plan

### Phase 3 Rollback (Parallel Run)
1. Stop AdaptiveCapacityMonitor на всех Ingester
2. Storage Elements продолжают Redis write (unchanged)
3. Ingester читает из старого Redis source
4. Zero downtime rollback

### Phase 4 Rollback (After Cutover)
1. Re-enable Redis write на Storage Elements
2. Restart Storage Elements
3. Switch Ingester back to old Redis source
4. Stop AdaptiveCapacityMonitor
5. Expected downtime: 5-10 minutes

## 📚 Ссылки

- **Documentation:** `claudedocs/geo-distributed-capacity-management-solution.md`
- **Storage Element endpoint:** `storage-element/app/api/v1/endpoints/capacity.py`
- **Capacity Service:** `storage-element/app/services/capacity_service.py`
- **Capacity Monitor:** `ingester-module/app/services/capacity_monitor.py`
- **Configuration:** `ingester-module/app/core/config.py`
- **Metrics:** `ingester-module/app/core/metrics.py`
- **Exceptions:** `ingester-module/app/core/exceptions.py`
- **Upload Service:** `ingester-module/app/services/upload_service.py`
- **Health Checks:** `ingester-module/app/api/v1/endpoints/health.py`
- **Unit Tests (Monitor):** `ingester-module/tests/unit/test_capacity_monitor.py`
- **Unit Tests (Service):** `storage-element/tests/unit/test_capacity_service.py`
- **Integration Tests (Failover):** `ingester-module/tests/integration/test_capacity_monitor_failover.py`
- **Integration Tests (Polling):** `ingester-module/tests/integration/test_adaptive_polling.py`

## ✅ Success Criteria

### Phase 1 (Implementation) ✅ ACHIEVED
- [x] Storage Element /capacity endpoint working
- [x] AdaptiveCapacityMonitor with Leader Election implemented
- [x] All Prometheus metrics defined
- [x] Configuration classes created
- [x] Integration in main.py lifespan
- [x] UploadService retry logic with excluded_se_ids
- [x] Lazy update integration
- [x] Health checks for capacity monitor

### Phase 2 (Testing) ✅ ACHIEVED
- [x] 88 tests written and passing
- [x] Unit test coverage for Leader Election, Polling, Cache, Lazy Update
- [x] Unit test coverage for CapacityService (Local FS + S3)
- [x] Integration tests for failover scenarios (12 tests)
- [x] Integration tests for adaptive polling (13 tests)
- [x] Failover time validated in tests

### Phase 3 (Parallel Run)
- [ ] Leader Election uptime > 99.9%
- [ ] Cache consistency > 99%
- [ ] No impact on upload latency
- [ ] Traffic reduction visible in metrics

### Phase 4 (Cutover)
- [ ] Zero downtime migration
- [ ] 75% traffic reduction confirmed
- [ ] All alerts configured and tested
- [ ] Runbook documented and validated

## 📝 Git Commits

1. `dc45fbf` - feat(storage-element): Add /capacity endpoint for geo-distributed polling
2. `6149077` - feat(ingester): Add AdaptiveCapacityMonitor with Redis Leader Election
3. `e97a765` - feat(ingester): Add retry logic, lazy update, and capacity health checks
4. `f0dddde` - Merge branch 'feature/ingester-adaptive-capacity-monitor'
5. _(pending)_ - test: Add comprehensive unit and integration tests for capacity monitoring
