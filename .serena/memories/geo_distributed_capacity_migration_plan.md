# План миграции: Geo-Distributed Capacity Management с Leader Election

**Создан:** 2025-12-04
**Обновлён:** 2025-12-05
**Статус:** Phase 4 Cutover COMPLETE ✅

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

## 🏗️ Целевая архитектура (FINAL - Phase 4)

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
│  - capacity:{mode}:available (sorted set)             │
│                                                         │
│  Fallback Chain: POLLING → Admin Module                │
│  (Legacy PUSH model REMOVED)                           │
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
- [x] **CapacityService Unit Tests** (19 tests)

#### ✅ COMPLETED - Integration Tests
- [x] **Leader Election Failover** (12 tests)
- [x] **Adaptive Polling** (13 tests)

#### 📊 Test Summary Phase 2
| Module | Test Type | Tests | Status |
|--------|-----------|-------|--------|
| Ingester | Unit (Capacity Monitor) | 44 | ✅ PASSED |
| Storage Element | Unit (CapacityService) | 19 | ✅ PASSED |
| Ingester | Integration (Failover) | 12 | ✅ PASSED |
| Ingester | Integration (Polling) | 13 | ✅ PASSED |
| **TOTAL** | | **88** | ✅ **ALL PASSED** |

### Phase 3: Parallel Run (Sprint 18) ✅ COMPLETE

#### ✅ COMPLETED - Fallback Chain Implementation
- [x] **Task 1**: Инициализация SE endpoints в main.py
- [x] **Task 2**: Метод выбора из AdaptiveCapacityMonitor
- [x] **Task 3**: Fallback chain в select_storage_element()
- [x] **Task 4**: Конфигурационные флаги
- [x] **Task 5**: Sorted set в AdaptiveCapacityMonitor
- [x] **Task 6**: Метрики источника выбора
- [x] **Task 7**: Health check обновление
- [x] **Task 8**: Интеграционные тесты

#### ✅ Phase 3 Git Commit
- [x] Commit: `b6083d3` feat(ingester): Add parallel run fallback chain POLLING → PUSH → Admin
- [x] Branch: `feature/ingester-parallel-run-fallback-chain` merged to main

### Phase 4: Cutover (Sprint 19) ✅ COMPLETE

#### ✅ COMPLETED - Full Removal of Legacy PUSH Model

**Task 1: Remove HealthReporter from Storage Element**
- [x] Удалён файл `storage-element/app/services/health_reporter.py`
- [x] Удалена интеграция HealthReporter из `storage-element/app/main.py`
- [x] Redis используется только для внутреннего кеширования

**Task 2: Remove Legacy Redis PUSH Fallback from Ingester**
- [x] Удалён `_select_from_redis()` метод из StorageSelector
- [x] Удалены `_redis_client`, `_cache`, `_cache_timestamp`, `_cache_ttl_seconds` атрибуты
- [x] Упрощён `__init__` и `initialize()` - redis_client больше не требуется
- [x] Fallback chain: POLLING → Admin Module (без PUSH step)

**Task 3: Remove Configuration Option**
- [x] Удалён `fallback_to_push` из `CapacityMonitorSettings`
- [x] Обновлён field_validator для boolean parsing

**Task 4: Update Health Endpoints**
- [x] Обновлён `data_sources` в health.py - push_model удалён
- [x] Fallback chain отражает POLLING → Admin Module

**Task 5: Add Cleanup Script**
- [x] Создан `scripts/cleanup_legacy_redis_keys.py`
- [x] Поддержка `--dry-run` и `--execute` режимов
- [x] Удаляет: `storage:elements:*`, `storage:rw:by_priority`, `storage:edit:by_priority`

**Task 6: Add Production Alerting**
- [x] Создан `monitoring/prometheus/alerts.yml` с alert groups:
  - `leader_election` - NoCapacityMonitorLeader, MultipleCapacityMonitorLeaders, FrequentLeaderTransitions
  - `capacity_polling` - HighPollingFailureRate, AllStorageElementsUnreachable
  - `storage_selection` - StorageSelectionFailures, AdminModuleFallbackActive
  - `cache_health` - LowCacheHitRate
  - `redis_capacity_monitor` - RedisUnavailableForLeaderElection
- [x] Создан `monitoring/prometheus/prometheus.yml`

**Task 7: Create Cutover Runbook**
- [x] Создан `claudedocs/PHASE4_CUTOVER_RUNBOOK.md`
- [x] Pre-Cutover Checklist
- [x] Step-by-step Cutover Procedure
- [x] Rollback Procedure (Quick + Full)
- [x] Monitoring During Cutover
- [x] Troubleshooting Guide
- [x] Success Criteria

**Task 8: Update Tests**
- [x] Обновлён `test_parallel_run.py` для POLLING-only mode
- [x] Удалены тесты для `fallback_to_push`
- [x] Удалены тесты для `_select_from_redis`
- [x] Добавлены тесты для отсутствия legacy атрибутов

#### 📊 Phase 4 Files Changed
| Файл | Изменения |
|------|-----------|
| `storage-element/app/services/health_reporter.py` | DELETED |
| `storage-element/app/main.py` | MODIFIED - removed HealthReporter |
| `ingester-module/app/services/storage_selector.py` | MODIFIED - removed PUSH fallback |
| `ingester-module/app/core/config.py` | MODIFIED - removed fallback_to_push |
| `ingester-module/app/api/v1/endpoints/health.py` | MODIFIED - updated data_sources |
| `scripts/cleanup_legacy_redis_keys.py` | NEW - Redis cleanup script |
| `monitoring/prometheus/alerts.yml` | NEW - alerting rules |
| `monitoring/prometheus/prometheus.yml` | NEW - Prometheus config |
| `claudedocs/PHASE4_CUTOVER_RUNBOOK.md` | NEW - cutover runbook |
| `ingester-module/tests/integration/test_parallel_run.py` | MODIFIED - updated for POLLING-only |

#### ✅ Phase 4 Git Branch
- [x] Branch: `feature/phase4-cutover-remove-legacy-push`
- [ ] Pending: Merge to main after review

## 🔧 Технические детали (Final Architecture)

### Redis Cache Structure (Phase 4 - POLLING Only)

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

# Sorted Sets для Sequential Fill
capacity:edit:available = sorted_set { se_id: priority }
capacity:rw:available = sorted_set { se_id: priority }
TTL: 600s

# DELETED Legacy Keys (Phase 4)
# storage:elements:{se_id}     - REMOVED
# storage:rw:by_priority       - REMOVED
# storage:edit:by_priority     - REMOVED
```

### Fallback Chain (Phase 4 - Final)

```python
async def select_storage_element(...):
    # 1. POLLING модель (AdaptiveCapacityMonitor)
    se = await self._select_from_adaptive_monitor(...)
    if se:
        return se  # source = "adaptive_monitor"

    # 2. Admin Module API - единственный fallback
    se = await self._select_from_admin_module(...)
    return se  # source = "admin_module" or None

    # REMOVED: _select_from_redis() - legacy PUSH model
```

### Configuration Parameters (Phase 4 - Final)

```bash
# Ingester Capacity Monitor
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

# Phase 4: POLLING-only mode
CAPACITY_MONITOR_USE_FOR_SELECTION=on      # Use POLLING model in StorageSelector
# REMOVED: CAPACITY_MONITOR_FALLBACK_TO_PUSH - no longer exists
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

### Selection Source (Phase 4)
- `storage_selection_source_total{source, status}` - adaptive_monitor/admin_module/none
  - REMOVED: `redis` source label - legacy PUSH model removed

## 🔄 Rollback Plan (Phase 4)

### Quick Rollback (< 5 minutes)
```bash
# 1. Откатить к предыдущему коммиту
git checkout main~1

# 2. Пересобрать и перезапустить
docker-compose build
docker-compose up -d

# 3. Legacy ключи восстановятся автоматически при старте SE
```

### Full Rollback
```bash
# 1. Восстановить Redis backup
redis-cli --rdb /backup/redis-backup-YYYYMMDD.rdb

# 2. Checkout конкретный коммит
git checkout $(cat /backup/last-commit.txt)

# 3. Full rebuild
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

## ✅ Success Criteria

### Phase 1 (Implementation) ✅ ACHIEVED
- [x] Storage Element /capacity endpoint working
- [x] AdaptiveCapacityMonitor with Leader Election implemented
- [x] All Prometheus metrics defined
- [x] Configuration classes created

### Phase 2 (Testing) ✅ ACHIEVED
- [x] 88 tests written and passing
- [x] Unit + Integration test coverage complete

### Phase 3 (Parallel Run) ✅ ACHIEVED
- [x] AdaptiveCapacityMonitor получает endpoints при старте
- [x] StorageSelector использует fallback chain (POLLING → PUSH → Admin)
- [x] Метрики показывают распределение по источникам
- [x] Тесты проходят для всех сценариев fallback
- [x] Zero downtime - legacy функциональность работает
- [x] Sorted set для Sequential Fill

### Phase 4 (Cutover) ✅ ACHIEVED
- [x] HealthReporter полностью удалён из Storage Element
- [x] Legacy Redis PUSH fallback удалён из Ingester
- [x] Fallback chain упрощён: POLLING → Admin Module
- [x] fallback_to_push конфигурация удалена
- [x] Cleanup script для legacy Redis keys создан
- [x] Production alerting rules настроены
- [x] Cutover runbook документирован
- [x] Тесты обновлены для POLLING-only mode

## 📝 Git Commits (All Phases)

### Phase 1
1. `dc45fbf` - feat(storage-element): Add /capacity endpoint for geo-distributed polling
2. `6149077` - feat(ingester): Add AdaptiveCapacityMonitor with Redis Leader Election
3. `e97a765` - feat(ingester): Add retry logic, lazy update, and capacity health checks
4. `f0dddde` - Merge branch 'feature/ingester-adaptive-capacity-monitor'

### Phase 2
5. `da9af5a` - test(capacity): Add comprehensive unit and integration tests
6. `4a0c6c7` - Merge branch 'test/capacity-monitoring-comprehensive-tests'

### Phase 3
7. `b6083d3` - feat(ingester): Add parallel run fallback chain POLLING → PUSH → Admin

### Phase 4
8. `TBD` - feat(phase4): Remove legacy PUSH model, cutover to POLLING-only mode
   - Branch: `feature/phase4-cutover-remove-legacy-push`
