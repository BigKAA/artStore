# Cache Synchronization API - Примеры использования

**Дата создания**: 2026-01-10
**Версия**: 1.0
**Storage Element версия**: 1.2.0

---

## 📋 Содержание

1. [Аутентификация](#аутентификация)
2. [Full Rebuild](#full-rebuild-полная-пересборка)
3. [Incremental Rebuild](#incremental-rebuild-инкрементальная-пересборка)
4. [Consistency Check](#consistency-check-проверка-консистентности)
5. [Cleanup Expired Entries](#cleanup-expired-entries-очистка-expired)
6. [Production Automation](#production-automation)
7. [Troubleshooting Scenarios](#troubleshooting-scenarios)

---

## Аутентификация

Все cache API endpoints требуют JWT аутентификации с **ADMIN** ролью.

### Получение токена

```bash
# Способ 1: Универсальный (автоматическое получение client_id)
CLIENT_ID=$(docker exec artstore_postgres psql -U artstore -d artstore_admin -t -c \
  "SELECT client_id FROM service_accounts WHERE name='admin-service';" | xargs)

TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d "{\"client_id\":\"$CLIENT_ID\",\"client_secret\":\"Test-Password123\"}" \
  | jq -r '.access_token')

echo "Token: $TOKEN"

# Способ 2: Если client_id уже известен
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"client_id":"sa_prod_admin_service_abc12345","client_secret":"Test-Password123"}' \
  | jq -r '.access_token')
```

### Проверка токена

```bash
# Decode JWT для проверки содержимого
echo $TOKEN | cut -d'.' -f2 | base64 -d 2>/dev/null | jq

# Ожидаемый payload:
# {
#   "sub": "service-account-id",
#   "client_id": "sa_prod_admin_service_abc12345",
#   "role": "ADMIN",
#   "exp": 1234567890,
#   ...
# }
```

---

## Full Rebuild (Полная пересборка)

### Scenario 1: Восстановление после backup

```bash
# 1. Проверить текущее состояние
curl -X GET "http://localhost:8010/api/v1/cache/consistency" \
  -H "Authorization: Bearer $TOKEN" \
  | jq

# Пример output:
# {
#   "is_consistent": false,
#   "total_attr_files": 5000,
#   "total_cache_entries": 0,  # Cache пуст после restore
#   "orphan_attr_count": 5000
# }

# 2. Запустить full rebuild
curl -X POST "http://localhost:8010/api/v1/cache/rebuild" \
  -H "Authorization: Bearer $TOKEN" \
  | jq

# 3. Проверить результат
# {
#   "operation_type": "full",
#   "duration_seconds": 125.5,
#   "statistics": {
#     "attr_files_scanned": 5000,
#     "cache_entries_before": 0,
#     "cache_entries_after": 5000,
#     "entries_created": 5000
#   },
#   "errors": []
# }
```

### Scenario 2: Критическое расхождение cache

```bash
# Если consistency check показал >10% inconsistency

# 1. Check consistency first
REPORT=$(curl -s -X GET "http://localhost:8010/api/v1/cache/consistency" \
  -H "Authorization: Bearer $TOKEN")

INCONSISTENCY=$(echo $REPORT | jq -r '.inconsistency_percentage')

echo "Inconsistency: $INCONSISTENCY%"

# 2. If inconsistency > 10% → Full rebuild
if (( $(echo "$INCONSISTENCY > 10" | bc -l) )); then
  echo "Critical inconsistency detected. Starting full rebuild..."

  curl -X POST "http://localhost:8010/api/v1/cache/rebuild" \
    -H "Authorization: Bearer $TOKEN" \
    | jq
else
  echo "Inconsistency acceptable. Consider incremental rebuild."
fi
```

### Scenario 3: Monitoring rebuild progress

```bash
# Full rebuild может занять время для больших хранилищ
# Мониторинг через logs

# Terminal 1: Start rebuild
curl -X POST "http://localhost:8010/api/v1/cache/rebuild" \
  -H "Authorization: Bearer $TOKEN" \
  | jq &

# Terminal 2: Monitor logs
docker logs -f storage-element-01 | grep "cache_rebuild"

# Expected log messages:
# INFO: Starting full cache rebuild | element_id=storage-elem-01
# INFO: Truncated cache table: storage_elem_01_files
# INFO: Processed 100 entries...
# INFO: Processed 500 entries...
# INFO: Full cache rebuild completed | duration_seconds=125.5
```

---

## Incremental Rebuild (Инкрементальная пересборка)

### Scenario 1: После добавления файлов через filesystem

```bash
# Если файлы были добавлены напрямую в storage (обход API)

# 1. Copy attr.json files manually to storage
# (Например, восстановление отдельных файлов из backup)

# 2. Run incremental rebuild
curl -X POST "http://localhost:8010/api/v1/cache/rebuild/incremental" \
  -H "Authorization: Bearer $TOKEN" \
  | jq

# 3. Result
# {
#   "operation_type": "incremental",
#   "statistics": {
#     "attr_files_scanned": 5000,
#     "cache_entries_before": 4950,
#     "cache_entries_after": 5000,
#     "entries_created": 50  # Только новые файлы добавлены
#   }
# }
```

### Scenario 2: Периодическая синхронизация

```bash
# Cron job для daily incremental sync
# /etc/cron.d/artstore-cache-sync

#!/bin/bash
# Daily incremental cache rebuild for storage-element-01

# Get auth token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"client_id":"sa_prod_admin_service_abc12345","client_secret":"PRODUCTION_SECRET"}' \
  | jq -r '.access_token')

# Run incremental rebuild
RESULT=$(curl -s -X POST "http://localhost:8010/api/v1/cache/rebuild/incremental" \
  -H "Authorization: Bearer $TOKEN")

# Log result
echo "[$(date)] Incremental rebuild completed: $RESULT" >> /var/log/artstore/cache-sync.log

# Send notification if errors
ERRORS=$(echo $RESULT | jq '.errors | length')
if [ "$ERRORS" -gt 0 ]; then
  echo "$RESULT" | mail -s "ArtStore Cache Rebuild Errors" admin@example.com
fi
```

---

## Consistency Check (Проверка консистентности)

### Scenario 1: Weekly consistency report

```bash
# Проверка консистентности без изменения данных (dry-run)

# 1. Run consistency check
CONSISTENCY_REPORT=$(curl -s -X GET "http://localhost:8010/api/v1/cache/consistency" \
  -H "Authorization: Bearer $TOKEN")

echo "$CONSISTENCY_REPORT" | jq

# 2. Parse key metrics
IS_CONSISTENT=$(echo "$CONSISTENCY_REPORT" | jq -r '.is_consistent')
INCONSISTENCY_PCT=$(echo "$CONSISTENCY_REPORT" | jq -r '.inconsistency_percentage')
ORPHAN_CACHE=$(echo "$CONSISTENCY_REPORT" | jq -r '.orphan_cache_count')
ORPHAN_ATTR=$(echo "$CONSISTENCY_REPORT" | jq -r '.orphan_attr_count')
EXPIRED=$(echo "$CONSISTENCY_REPORT" | jq -r '.expired_cache_count')

# 3. Generate report
cat <<EOF
=== Cache Consistency Report ===
Date: $(date)
Storage Element: storage-elem-01

Status: $([ "$IS_CONSISTENT" == "true" ] && echo "✅ CONSISTENT" || echo "⚠️ INCONSISTENT")
Inconsistency: $INCONSISTENCY_PCT%

Details:
- Orphan cache entries: $ORPHAN_CACHE
- Orphan attr.json files: $ORPHAN_ATTR
- Expired cache entries: $EXPIRED

Recommendations:
$(if [ "$INCONSISTENCY_PCT" == "0.0" ]; then
  echo "✅ No action required. Cache is fully consistent."
elif (( $(echo "$INCONSISTENCY_PCT < 5" | bc -l) )); then
  echo "ℹ️  Minor inconsistency. Consider incremental rebuild."
else
  echo "⚠️  Significant inconsistency. Full rebuild recommended."
fi)
===============================
EOF
```

### Scenario 2: Pre-rebuild validation

```bash
# Всегда проверяйте консистентность перед manual rebuild

# Function to check and recommend action
check_and_recommend() {
  local REPORT=$(curl -s -X GET "http://localhost:8010/api/v1/cache/consistency" \
    -H "Authorization: Bearer $TOKEN")

  local INCONSISTENCY=$(echo "$REPORT" | jq -r '.inconsistency_percentage')
  local ORPHAN_CACHE=$(echo "$REPORT" | jq -r '.orphan_cache_count')
  local ORPHAN_ATTR=$(echo "$REPORT" | jq -r '.orphan_attr_count')

  echo "Consistency Check Results:"
  echo "  Inconsistency: $INCONSISTENCY%"
  echo "  Orphan cache entries: $ORPHAN_CACHE"
  echo "  Orphan attr files: $ORPHAN_ATTR"
  echo ""

  # Recommendation logic
  if (( $(echo "$INCONSISTENCY > 10" | bc -l) )); then
    echo "Recommendation: FULL REBUILD (high inconsistency)"
  elif [ "$ORPHAN_ATTR" -gt 0 ]; then
    echo "Recommendation: INCREMENTAL REBUILD (missing cache entries)"
  elif [ "$ORPHAN_CACHE" -gt 0 ]; then
    echo "Recommendation: INVESTIGATE orphan cache entries (manual cleanup may be needed)"
  else
    echo "Recommendation: NO ACTION REQUIRED (cache is consistent)"
  fi
}

# Run check
check_and_recommend
```

---

## Cleanup Expired Entries (Очистка expired)

### Scenario 1: Daily cleanup job

```bash
# Автоматическая очистка expired entries

#!/bin/bash
# /usr/local/bin/artstore-cleanup-expired.sh

# Configuration
API_BASE_URL="http://localhost:8010/api/v1"
AUTH_ENDPOINT="http://localhost:8000/api/v1/auth/token"
CLIENT_ID="sa_prod_admin_service_abc12345"
CLIENT_SECRET="PRODUCTION_SECRET"
LOG_FILE="/var/log/artstore/cache-cleanup.log"

# Get auth token
TOKEN=$(curl -s -X POST "$AUTH_ENDPOINT" \
  -H "Content-Type: application/json" \
  -d "{\"client_id\":\"$CLIENT_ID\",\"client_secret\":\"$CLIENT_SECRET\"}" \
  | jq -r '.access_token')

if [ -z "$TOKEN" ] || [ "$TOKEN" == "null" ]; then
  echo "[ERROR] Failed to get auth token" >> "$LOG_FILE"
  exit 1
fi

# Run cleanup
RESULT=$(curl -s -X POST "$API_BASE_URL/cache/cleanup-expired" \
  -H "Authorization: Bearer $TOKEN")

# Log result
DELETED=$(echo "$RESULT" | jq -r '.statistics.entries_deleted')
DURATION=$(echo "$RESULT" | jq -r '.duration_seconds')

echo "[$(date)] Cleanup completed: $DELETED entries deleted in ${DURATION}s" >> "$LOG_FILE"

# Email notification if significant cleanup
if [ "$DELETED" -gt 100 ]; then
  echo "Large cleanup: $DELETED expired entries deleted" | \
    mail -s "ArtStore Cache Cleanup Alert" admin@example.com
fi

exit 0
```

### Scenario 2: On-demand cleanup

```bash
# Manual cleanup when needed

# 1. Check expired count first
CONSISTENCY=$(curl -s -X GET "http://localhost:8010/api/v1/cache/consistency" \
  -H "Authorization: Bearer $TOKEN")

EXPIRED_COUNT=$(echo "$CONSISTENCY" | jq -r '.expired_cache_count')

echo "Expired cache entries: $EXPIRED_COUNT"

# 2. Run cleanup if needed
if [ "$EXPIRED_COUNT" -gt 0 ]; then
  echo "Running cleanup..."

  CLEANUP_RESULT=$(curl -s -X POST "http://localhost:8010/api/v1/cache/cleanup-expired" \
    -H "Authorization: Bearer $TOKEN")

  echo "$CLEANUP_RESULT" | jq
else
  echo "No expired entries to clean up."
fi
```

---

## Production Automation

### Complete cache management cron setup

```bash
# /etc/cron.d/artstore-cache-management

# Daily incremental rebuild at 02:00
0 2 * * * artstore /usr/local/bin/artstore-incremental-rebuild.sh

# Weekly consistency check (Monday 03:00)
0 3 * * 1 artstore /usr/local/bin/artstore-consistency-check.sh

# Daily expired cleanup at 04:00
0 4 * * * artstore /usr/local/bin/artstore-cleanup-expired.sh
```

### Monitoring script example

```bash
#!/bin/bash
# /usr/local/bin/artstore-cache-health-check.sh
#
# Comprehensive cache health monitoring

API_BASE="http://localhost:8010/api/v1"
AUTH_ENDPOINT="http://localhost:8000/api/v1/auth/token"

# Get token
TOKEN=$(curl -s -X POST "$AUTH_ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{"client_id":"admin-service","client_secret":"SECRET"}' \
  | jq -r '.access_token')

# Get consistency report
REPORT=$(curl -s -X GET "$API_BASE/cache/consistency" \
  -H "Authorization: Bearer $TOKEN")

# Parse metrics
IS_CONSISTENT=$(echo "$REPORT" | jq -r '.is_consistent')
INCONSISTENCY=$(echo "$REPORT" | jq -r '.inconsistency_percentage')
TOTAL_ATTR=$(echo "$REPORT" | jq -r '.total_attr_files')
TOTAL_CACHE=$(echo "$REPORT" | jq -r '.total_cache_entries')
EXPIRED=$(echo "$REPORT" | jq -r '.expired_cache_count')

# Health status evaluation
HEALTH_STATUS="OK"
ALERTS=()

# Check consistency
if [ "$IS_CONSISTENT" != "true" ]; then
  if (( $(echo "$INCONSISTENCY > 10" | bc -l) )); then
    HEALTH_STATUS="CRITICAL"
    ALERTS+=("High inconsistency: ${INCONSISTENCY}% - Full rebuild required")
  elif (( $(echo "$INCONSISTENCY > 5" | bc -l) )); then
    HEALTH_STATUS="WARNING"
    ALERTS+=("Moderate inconsistency: ${INCONSISTENCY}% - Incremental rebuild recommended")
  fi
fi

# Check expired entries
EXPIRED_PCT=$(echo "scale=2; $EXPIRED * 100 / $TOTAL_CACHE" | bc)
if (( $(echo "$EXPIRED_PCT > 10" | bc -l) )); then
  HEALTH_STATUS="WARNING"
  ALERTS+=("High expired cache: ${EXPIRED_PCT}% - Cleanup recommended")
fi

# Output results
cat <<EOF
{
  "timestamp": "$(date -Iseconds)",
  "health_status": "$HEALTH_STATUS",
  "metrics": {
    "total_attr_files": $TOTAL_ATTR,
    "total_cache_entries": $TOTAL_CACHE,
    "inconsistency_percentage": $INCONSISTENCY,
    "expired_count": $EXPIRED,
    "expired_percentage": $EXPIRED_PCT
  },
  "alerts": $(printf '%s\n' "${ALERTS[@]}" | jq -R . | jq -s .)
}
EOF

# Send alert if not OK
if [ "$HEALTH_STATUS" != "OK" ]; then
  echo "Cache Health Alert: $HEALTH_STATUS" | \
    mail -s "ArtStore Cache Health Alert" admin@example.com
fi
```

---

## Troubleshooting Scenarios

### Scenario 1: Lock timeout при rebuild

```bash
# Problem: Manual rebuild застрял (lock занят)

# 1. Check Redis locks
docker exec -it artstore_redis redis-cli keys "cache_lock:*"

# Output example:
# 1) "cache_lock:storage-elem-01:manual_rebuild"

# 2. Check lock TTL
docker exec -it artstore_redis redis-cli TTL "cache_lock:storage-elem-01:manual_rebuild"

# Output: 1200 (20 minutes remaining)

# 3. Option A: Wait for lock to expire (safer)
# Option B: Force release lock (DANGEROUS - use only if rebuild crashed)

# Force release (only if rebuild process is confirmed dead):
docker exec -it artstore_redis redis-cli DEL "cache_lock:storage-elem-01:manual_rebuild"

# 4. Retry rebuild
curl -X POST "http://localhost:8010/api/v1/cache/rebuild" \
  -H "Authorization: Bearer $TOKEN"
```

### Scenario 2: Большое количество orphan cache entries

```bash
# Problem: Consistency check показал много orphan cache entries

# 1. Get consistency report
REPORT=$(curl -s -X GET "http://localhost:8010/api/v1/cache/consistency" \
  -H "Authorization: Bearer $TOKEN")

ORPHAN_CACHE_IDS=$(echo "$REPORT" | jq -r '.details.orphan_cache_entries[]')

echo "Orphan cache entries:"
echo "$ORPHAN_CACHE_IDS"

# 2. Investigate: Check if attr.json files were deleted
# (Manual inspection через filesystem или S3 bucket)

# 3. Decision:
# - If attr.json files exist but not detected → Incremental rebuild
# - If attr.json files truly deleted → Full rebuild recommended

# Full rebuild will remove orphan cache entries
curl -X POST "http://localhost:8010/api/v1/cache/rebuild" \
  -H "Authorization: Bearer $TOKEN"
```

### Scenario 3: Performance issues при rebuild

```bash
# Problem: Rebuild занимает слишком много времени (>30 min)

# 1. Check attr.json file count
ATTR_COUNT=$(find /data/storage -name "*.attr.json" | wc -l)
echo "Total attr.json files: $ATTR_COUNT"

# 2. Estimate rebuild time
# Примерно 1000 files/second для local FS
# Примерно 100-500 files/second для S3 (зависит от latency)
ESTIMATED_SECONDS=$(echo "$ATTR_COUNT / 500" | bc)
echo "Estimated rebuild time: ${ESTIMATED_SECONDS}s ($(($ESTIMATED_SECONDS / 60)) minutes)"

# 3. For large storage (>100K files), consider:
# - Incremental rebuild instead of full
# - Increase rebuild timeout in code
# - Run during maintenance window

# Check current rebuild progress via logs
docker logs -f storage-element-01 | grep "Processed.*entries"
```

---

## Appendix: Complete Example Script

```bash
#!/bin/bash
# artstore-cache-complete-workflow.sh
#
# Complete cache management workflow example

set -e  # Exit on error

# Configuration
API_BASE="http://localhost:8010/api/v1"
AUTH_ENDPOINT="http://localhost:8000/api/v1/auth/token"
CLIENT_ID="sa_prod_admin_service_abc12345"
CLIENT_SECRET="Test-Password123"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Step 1: Authentication
echo -e "${GREEN}[1/5] Authenticating...${NC}"
TOKEN=$(curl -s -X POST "$AUTH_ENDPOINT" \
  -H "Content-Type: application/json" \
  -d "{\"client_id\":\"$CLIENT_ID\",\"client_secret\":\"$CLIENT_SECRET\"}" \
  | jq -r '.access_token')

if [ -z "$TOKEN" ] || [ "$TOKEN" == "null" ]; then
  echo -e "${RED}[ERROR] Authentication failed${NC}"
  exit 1
fi
echo -e "${GREEN}✓ Authenticated${NC}"

# Step 2: Consistency Check
echo -e "${GREEN}[2/5] Checking cache consistency...${NC}"
CONSISTENCY=$(curl -s -X GET "$API_BASE/cache/consistency" \
  -H "Authorization: Bearer $TOKEN")

IS_CONSISTENT=$(echo "$CONSISTENCY" | jq -r '.is_consistent')
INCONSISTENCY=$(echo "$CONSISTENCY" | jq -r '.inconsistency_percentage')

echo "$CONSISTENCY" | jq

# Step 3: Decide action based on consistency
if [ "$IS_CONSISTENT" == "true" ]; then
  echo -e "${GREEN}✓ Cache is consistent. No action needed.${NC}"
  exit 0
fi

echo -e "${YELLOW}⚠ Inconsistency detected: ${INCONSISTENCY}%${NC}"

# Step 4: Execute appropriate rebuild
if (( $(echo "$INCONSISTENCY > 10" | bc -l) )); then
  echo -e "${YELLOW}[3/5] Running FULL rebuild (high inconsistency)...${NC}"
  REBUILD_RESULT=$(curl -s -X POST "$API_BASE/cache/rebuild" \
    -H "Authorization: Bearer $TOKEN")
else
  echo -e "${GREEN}[3/5] Running INCREMENTAL rebuild (low inconsistency)...${NC}"
  REBUILD_RESULT=$(curl -s -X POST "$API_BASE/cache/rebuild/incremental" \
    -H "Authorization: Bearer $TOKEN")
fi

echo "$REBUILD_RESULT" | jq
echo -e "${GREEN}✓ Rebuild completed${NC}"

# Step 5: Cleanup expired entries
echo -e "${GREEN}[4/5] Cleaning up expired entries...${NC}"
CLEANUP_RESULT=$(curl -s -X POST "$API_BASE/cache/cleanup-expired" \
  -H "Authorization: Bearer $TOKEN")

DELETED=$(echo "$CLEANUP_RESULT" | jq -r '.statistics.entries_deleted')
echo -e "${GREEN}✓ Deleted $DELETED expired entries${NC}"

# Step 6: Final consistency verification
echo -e "${GREEN}[5/5] Verifying final consistency...${NC}"
FINAL_CONSISTENCY=$(curl -s -X GET "$API_BASE/cache/consistency" \
  -H "Authorization: Bearer $TOKEN")

FINAL_IS_CONSISTENT=$(echo "$FINAL_CONSISTENCY" | jq -r '.is_consistent')

if [ "$FINAL_IS_CONSISTENT" == "true" ]; then
  echo -e "${GREEN}✅ SUCCESS: Cache is now fully consistent${NC}"
else
  echo -e "${RED}❌ WARNING: Cache still has inconsistencies${NC}"
  echo "$FINAL_CONSISTENCY" | jq
  exit 1
fi

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Cache management workflow completed${NC}"
echo -e "${GREEN}========================================${NC}"
```

**Usage:**

```bash
chmod +x artstore-cache-complete-workflow.sh
./artstore-cache-complete-workflow.sh
```

---

## Ссылки

- [Storage Element README.md](../storage-element/README.md)
- [Cache Synchronization Implementation Plan](./CACHE_SYNC_IMPLEMENTATION_PLAN.md)
- [Authentication Quick Start](../admin-module/README.md#authentication)
