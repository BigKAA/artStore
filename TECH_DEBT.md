# Technical Debt - ArtStore Project

Файл для отслеживания технического долга и отложенных задач.

---

## Отложенные задачи (DEFERRED)

### TD-001: Grafana Dashboard для Storage Lifecycle

**Источник**: Sprint 17, Task 4.2
**Приоритет**: Medium
**Estimated Effort**: 3 hours
**Дата отложения**: 2025-12-02

**Описание**:
Создать Grafana dashboard для визуализации storage lifecycle metrics.

**Требования**:

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

**Связанные метрики** (уже реализованы в Task 4.1):
- `ingester-module/app/core/metrics.py` - Storage Selection & Finalization metrics
- `storage-element/app/core/capacity_metrics.py` - Storage capacity metrics
- `admin-module/app/services/garbage_collector_service.py` - GC metrics

---

## Известные проблемы (KNOWN ISSUES)

### KI-001: Failing Tests in test_security.py и test_upload_service.py

**Приоритет**: Low
**Количество**: ~18 тестов
**Причина**: API изменения в предыдущих спринтах без обновления тестов

**Затронутые файлы**:
- `ingester-module/tests/unit/test_security.py`
- `ingester-module/tests/unit/test_upload_service.py`

**Статус**: Требует ревью и исправления тестов под актуальный API

---

## Формат записей

```markdown
### TD-XXX: Краткое название

**Источник**: Sprint N, Task X.Y
**Приоритет**: High/Medium/Low
**Estimated Effort**: X hours
**Дата отложения**: YYYY-MM-DD

**Описание**: ...

**Acceptance Criteria**:
- [ ] Критерий 1
- [ ] Критерий 2
```

---

*Последнее обновление: 2025-12-02*
