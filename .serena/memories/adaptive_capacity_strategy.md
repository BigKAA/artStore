# Adaptive Capacity Management Strategy

**Документ**: IMP_RESEARCH_PLAN.md версия 1.1
**Дата**: 2025-12-01

## Ключевая проблема

Фиксированные capacity thresholds (95%) не масштабируются для Storage Elements разного размера:
- SE 1TB: 50GB unused = acceptable
- SE 100TB: 5TB unused = significant waste
- SE 1PB: 50TB unused = CRITICAL waste

## Решение: Adaptive Thresholds

### Формула

```python
def calculate_adaptive_threshold(total_capacity_bytes: int, mode: str) -> dict:
    total_gb = total_capacity_bytes / (1024**3)
    
    if mode == "rw":
        warning_free_gb = max(total_gb * 0.15, 150)   # 15% или 150GB
        critical_free_gb = max(total_gb * 0.08, 80)    # 8% или 80GB
        full_free_gb = max(total_gb * 0.02, 20)        # 2% или 20GB
    elif mode == "edit":
        warning_free_gb = max(total_gb * 0.10, 100)   # 10% или 100GB
        critical_free_gb = max(total_gb * 0.05, 50)    # 5% или 50GB
        full_free_gb = max(total_gb * 0.01, 10)        # 1% или 10GB
    
    return {
        "warning_threshold": (total_gb - warning_free_gb) / total_gb * 100,
        "critical_threshold": (total_gb - critical_free_gb) / total_gb * 100,
        "full_threshold": (total_gb - full_free_gb) / total_gb * 100,
        "warning_free_gb": warning_free_gb,
        "critical_free_gb": critical_free_gb,
        "full_free_gb": full_free_gb
    }
```

### Примеры RW Storage

| SE Size | Warning | Critical | Full | Waste % |
|---------|---------|----------|------|---------|
| 1TB | 85% | 92% | 98% | 2% |
| 10TB | 98.5% | 99.2% | 99.8% | 0.2% |
| 100TB | 98.5% | 99.2% | 99.8% | 0.2% |
| 1PB | 98.5% | 99.2% | 99.8% | 0.2% |

### Multi-Level Status

```python
class CapacityStatus(Enum):
    OK = "ok"              # Normal operation
    WARNING = "warning"    # Alert admin, continue writes
    CRITICAL = "critical"  # Urgent alert, continue writes
    FULL = "full"          # Reject writes, switch to next SE
```

## Intelligent File Size Handling

### Pre-flight Check + Optimistic Retry

```python
async def upload_with_intelligent_fallback(file, retention_policy):
    # 1. Получить размер если доступен (Content-Length)
    file_size = get_file_size(file)
    
    # 2. До 3 попыток на разных SE
    attempts = 0
    while attempts < 3:
        target_se = await storage_selector.select_storage_element(
            retention_policy=retention_policy,
            required_free_space=file_size  # Pre-flight check
        )
        
        try:
            return await upload_file(target_se, file)
        except InsufficientSpaceError:
            # Retry на следующем SE
            attempts += 1
            continue
    
    raise HTTPException(503, "No available storage")
```

## Comprehensive Monitoring

### Prometheus Metrics

- `storage_capacity_total_bytes` - Total capacity
- `storage_capacity_used_bytes` - Used capacity
- `storage_capacity_free_bytes` - Free capacity
- `storage_capacity_status` - Current status (0=ok, 1=warning, 2=critical, 3=full)
- `storage_capacity_forecast_days` - Days until threshold (predictive)
- `storage_upload_rejected_total` - Upload rejections counter
- `storage_element_switch_total` - Automatic SE switches

### Capacity Forecasting

```python
class CapacityForecaster:
    async def forecast_days_until_full(se_id, total_capacity, threshold_bytes):
        """
        Linear regression на historical data (последние 7 дней)
        для прогнозирования заполнения SE.
        
        Returns: days until threshold или None
        """
        # Получить history из Redis time series
        history = await redis.zrangebyscore(f"storage:history:{se_id}", ...)
        
        # Linear regression: rate_of_fill = bytes_delta / time_delta
        fill_rate = calculate_fill_rate(history)
        
        # Forecast
        remaining_bytes = threshold_bytes - current_used
        days_until = (remaining_bytes / fill_rate) / 86400
        
        return days_until
```

### AlertManager Rules

1. **StorageCapacityWarning** - 5min delay, warning severity
2. **StorageCapacityCritical** - 2min delay, critical severity
3. **StorageCapacityFull** - 1min delay, page severity
4. **StorageCapacityPredictiveFull** - forecast < 7 days, warning
5. **StorageUploadRejections** - rate > 0.1, critical
6. **FrequentStorageSwitching** - rate > 0.5, warning

### Admin UI

- Real-time capacity gauges с color coding (green/yellow/orange/red/purple)
- Threshold markers на progress bar
- Forecast widgets (days until warning/critical/full)
- Capacity trend charts (historical data)

## Преимущества

✅ **Efficiency**: 98%+ utilization на больших SE (vs 95%)
✅ **Safety**: Минимум 50GB/30GB free для малых SE
✅ **Proactive**: Multi-level alerting даёт время для реакции
✅ **Resilience**: Intelligent fallback с 3 retry attempts
✅ **Visibility**: Comprehensive monitoring (metrics + logs + UI + forecast)
✅ **Predictive**: Forecasting за 7-30 дней для proactive management
✅ **Scalable**: Автоматическая адаптация без manual configuration

## Implementation

См. `/home/artur/Projects/artStore/IMP_RESEARCH_PLAN.md` версия 1.1 для детальных tasks.

**Phase 1** (Sprint 14): Redis Registry + Health Reporting + Adaptive Thresholds
**Phase 2** (Sprint 15): Retention Policy + Lifecycle
**Phase 3** (Sprint 16): Garbage Collection
**Phase 4** (Sprint 17): Monitoring + Forecasting + Admin UI
