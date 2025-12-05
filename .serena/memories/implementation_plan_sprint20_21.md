# План исправлений по результатам тестирования Storage Element Selection

**Дата**: 2025-12-05
**Основание**: TEST-RESULTS-2025-12-05.md (70% pass rate)
**Стратегия**: Immediate Fixes (Sprint 20) + Admin Standalone Mode (Sprint 21) + Roadmap Future Improvements

---

## ЧАСТЬ 1: IMMEDIATE FIXES (Sprint 20) - 2 часа

### Fix 1: Admin Module Fallback URL ⚠️ CRITICAL (15 мин)

**Проблема**: Ingester использует `/api/auth/token` вместо `/api/v1/auth/token`
**Файл**: `ingester-module/app/services/admin_client.py:117`
**Изменение**: `/api/auth/token` → `/api/v1/auth/token`

### Fix 2: Checksum Verification (Defense in Depth) ⚠️ HIGH (50 мин)

**Проблема**: GET `/api/v1/files/{file_id}/metadata` возвращает 404 после копирования

**Option A** (15 мин): `storage-element/app/api/v1/endpoints/files.py:92`
- Добавить `await db.commit()` после upload

**Option B** (35 мин): `ingester-module/app/services/finalize_service.py:464-476`
- Заменить `_verify_checksum()` на версию с retry logic (3 попытки, 0.5s delay)

### Fix 3: Error Response Code ⚠️ MEDIUM (20 мин)

**Проблема**: NoAvailableStorageException → 500 вместо 503
**Файл**: `ingester-module/app/main.py:360`
**Добавить**: `@app.exception_handler(NoAvailableStorageException)` → HTTP 503

---

## ЧАСТЬ 2: ADMIN STANDALONE MODE (Sprint 21) - 6 часов

### Цель: Устранить зависимость Admin Module от Redis

**Принцип**: Redis = Cache, PostgreSQL = Source of Truth

#### Компонент 1: JWT Keys Filesystem Storage (1.5 часа)

**Файлы**:
- `admin-module/app/services/token_service.py` - Dual storage (Redis cache + Filesystem)
- `admin-module/app/core/config.py` - Add `JWT_KEYS_DIR = /var/artstore/jwt-keys`

**Логика**: Redis (fast path) → Filesystem fallback (always available)

#### Компонент 2: Service Discovery Database Fallback (1.5 часа)

**Файлы**:
- `admin-module/app/services/storage_element_publish_service.py`
- `admin-module/app/api/v1/endpoints/storage_elements.py`

**Логика**: Redis (primary) → PostgreSQL fallback (if Redis unavailable)

#### Компонент 3: Authentication without Redis (1 час)

**Файлы**:
- `admin-module/app/api/v1/endpoints/auth.py` - Optional rate limiting
- `admin-module/app/middleware/rate_limit.py` - `redis_available()` check

**Поведение**: Rate limiting только если Redis доступен, иначе degraded mode

#### Компонент 4: Health Check Degraded Mode (0.5 часа)

**Файл**: `admin-module/app/api/v1/endpoints/health.py`

**Response**: `{"status": "degraded", "checks": {"database": "healthy", "redis": "unavailable", "degraded": true}}`

---

## ЧАСТЬ 3: FUTURE IMPROVEMENTS ROADMAP (Sprint 22-23) - 5 часов

### Improvement 5: Pre-Upload Capacity Reservation (Sprint 22, 4 часа)

**Цель**: Предотвратить overflow SE >100%

**Компоненты**:
- `ingester-module/app/services/capacity_reservation.py` (NEW)
- `ingester-module/app/services/upload_service.py` (reserve/release)
- `ingester-module/app/services/storage_selector.py` (учитывать reservations)

**Redis**: `storage:reservations:{se_id}` (hash), TTL 10 минут

### Improvement 6: Capacity Prediction (Sprint 23, 2 часа)

**Цель**: Ранний reject больших файлов

**Компоненты**:
- `ingester-module/app/api/v1/endpoints/upload.py` (Extract Content-Length)
- `ingester-module/app/services/upload_service.py` (predict_capacity method)

**Эффект**: HTTP 507 BEFORE file transfer (~100ms), экономия bandwidth

---

## КРИТИЧЕСКИЕ ФАЙЛЫ ДЛЯ ИЗМЕНЕНИЯ

### Sprint 20 (Immediate Fixes)
1. `ingester-module/app/services/admin_client.py:117`
2. `storage-element/app/api/v1/endpoints/files.py:92`
3. `ingester-module/app/services/finalize_service.py:464-476`
4. `ingester-module/app/main.py:360`

### Sprint 21 (Admin Standalone)
1. `admin-module/app/services/token_service.py`
2. `admin-module/app/services/storage_element_publish_service.py`
3. `admin-module/app/api/v1/endpoints/auth.py`
4. `admin-module/app/api/v1/endpoints/health.py`
5. `admin-module/app/core/config.py`
6. `admin-module/app/middleware/rate_limit.py`

---

## МЕТРИКИ УСПЕХА

### Sprint 20
- ✅ T8 (Redis Fallback): FAILED → PASSED
- ✅ T9 (Admin API Fallback): PARTIAL → PASSED
- ✅ T6 (Finalization): PARTIAL → PASSED
- ✅ T10 (Error Code): 500 → 503
- ✅ Pass Rate: 70% → 100%

### Sprint 21
- ✅ Admin Module работает без Redis
- ✅ Ingester fallback chain полностью функционален
- ✅ Health check показывает degraded mode
- ✅ Performance: <200ms overhead для database fallback

### Sprint 22-23
- ✅ SE capacity никогда не превышает 100%
- ✅ Early rejection файлов <100ms
- ✅ Bandwidth savings: ~30% для rejected uploads

---

## ИТОГОВАЯ СЛОЖНОСТЬ

| Компонент | Время | Риск |
|-----------|-------|------|
| Immediate Fixes | 2 часа | Низкий-Средний |
| Admin Standalone | 6 часов | Высокий |
| Future Improvements | 5 часов | Средний |
| **ИТОГО** | **13 часов** | **Средний** |

---

**Следующий шаг**: Приступить к реализации Fix 1 (Admin Fallback URL) как критический blocker.
