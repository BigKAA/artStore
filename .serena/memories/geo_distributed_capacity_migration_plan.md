# План миграции: Geo-Distributed Capacity Management с Leader Election

**Создан:** 2025-12-04
**Статус:** Architecture Complete, Implementation Pending

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

### Phase 1: Implementation (Sprint N+1) ← ТЕКУЩАЯ ФАЗА

#### ✅ COMPLETED
- [x] Storage Element: `/api/v1/capacity` endpoint
- [x] `CapacityService` (Local FS + S3 support)
- [x] Configuration fields (datacenter_location, s3_soft_capacity_limit)
- [x] Router registration
- [x] Comprehensive documentation

#### 🚧 TO DO
- [ ] `AdaptiveCapacityMonitor` service с Leader Election
- [ ] Leader Election logic (Redis SET NX EX)
- [ ] Leader/Follower modes
- [ ] `UploadService` retry logic + lazy update
- [ ] Health checks (minimum 1 edit Storage)
- [ ] Prometheus metrics (Leader + Polling)

### Phase 2: Testing (Sprint N+1, Week 2)

- [ ] Unit tests для Leader Election logic
- [ ] Unit tests для CapacityService
- [ ] Integration tests для adaptive polling
- [ ] Integration tests для failover scenarios
- [ ] Load tests (4 Ingester × 100 SE)
- [ ] Chaos testing (kill Leader, Redis failures)

### Phase 3: Parallel Run (Sprint N+2)

- [ ] Deploy AdaptiveCapacityMonitor (parallel с текущей Redis write логикой)
- [ ] Storage Elements продолжают писать в Redis (compatibility)
- [ ] Monitoring: Leader transitions, poll metrics, cache consistency
- [ ] Validation: сравнение данных из двух источников
- [ ] Duration: 1 week minimum

### Phase 4: Cutover (Sprint N+3)

- [ ] Verify Leader Election stability (>99.9% uptime)
- [ ] Ingester читает ТОЛЬКО из capacity cache
- [ ] Удалить Redis write logic из Storage Elements
- [ ] Cleanup старых Redis keys
- [ ] Full production monitoring
- [ ] Rollback plan validation

## 🔧 Технические детали

### Redis Cache Structure

```redis
# Leader Election
capacity_monitor:leader_lock = "ingester-instance-uuid"
TTL: 30s

# Capacity Data (обновляется Leader)
capacity:{se_id} = {
  "storage_id": "se-dc2-01",
  "mode": "rw",
  "capacity": {"total": ..., "used": ..., "available": ...},
  "health": "healthy",
  "last_update": "ISO8601"
}
TTL: 600s

# Health Status
health:{se_id} = "healthy" | "unhealthy: <reason>"
TTL: 600s

# Polling Metadata
capacity:{se_id}:last_poll = "ISO8601"
capacity:{se_id}:prev = {...}  # Для adaptive logic
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

# Ingester (NEW)
CAPACITY_MONITOR_LEADER_TTL=30
CAPACITY_MONITOR_BASE_INTERVAL=30
CAPACITY_MONITOR_MAX_INTERVAL=300
CAPACITY_MONITOR_HTTP_TIMEOUT=15
```

## 📊 Prometheus Metrics

### Leader Election
- `capacity_monitor_leader_state{instance_id}` - 1=leader, 0=follower
- `capacity_monitor_leader_transitions_total{transition_type}` - acquired/lost/renewed
- `leader_lock_acquisition_duration_seconds` - latency

### Capacity Polling
- `capacity_poll_duration_seconds{storage_id, status}` - poll latency
- `capacity_poll_failures_total{storage_id, error_type}` - failures
- `lazy_update_triggers_total{storage_id, reason}` - stale cache events
- `storage_elements_available{mode}` - available SE count

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
- **Configuration:** `storage-element/app/core/config.py`

## ✅ Success Criteria

### Phase 2 (Testing)
- [ ] 100% unit test coverage для Leader Election
- [ ] Failover time < 35s в интеграционных тестах
- [ ] Zero data loss при failover
- [ ] 100 SE polling в < 60s

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
