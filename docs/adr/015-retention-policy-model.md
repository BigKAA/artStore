# ADR-015: Retention Policy Model для File Lifecycle Management

## Статус

**Принято** - Реализовано в Sprint 14-15

## Контекст

ArtStore требует управления жизненным циклом файлов с различными требованиями к хранению:

1. **Временные файлы (drafts)** - рабочие документы, которые редактируются и могут быть удалены
2. **Постоянные файлы** - финализированные документы для долгосрочного хранения

### Проблемы существующего подхода

До Sprint 14 все файлы хранились одинаково:
- Нет разделения между рабочими и финальными документами
- Невозможно автоматически очищать старые drafts
- Все файлы занимают одинаковый "ценный" storage
- Сложность в управлении сроками хранения

### Рассмотренные альтернативы

#### Single Storage Mode
```
Все файлы в одном режиме хранения.

Недостатки:
- Нет дифференциации по важности
- Невозможна автоматическая очистка
- Всё или ничего для retention
```

#### Time-Based Tiers (Hot/Warm/Cold)
```
Автоматическое перемещение по времени.

Недостатки:
- Drafts могут быть старыми но активными
- Финальные документы нужны сразу после создания
- Не учитывает бизнес-логику
```

#### Policy-Based Model (выбрано)
```
Явная политика при загрузке.

Преимущества:
- Клиент определяет intent при загрузке
- Чёткое разделение временного и постоянного
- Возможность TTL для temporary
- Workflow: draft → finalize → permanent
```

## Решение

Реализовать **Policy-Based Retention Model** с двумя политиками:

### Retention Policies

```python
class RetentionPolicy(str, Enum):
    """
    Политика хранения определяет lifecycle файла.
    """
    TEMPORARY = "temporary"  # Рабочие файлы, Edit SE, с TTL
    PERMANENT = "permanent"  # Финальные файлы, RW SE, без TTL
```

### Mapping: Policy → Storage Mode

```
┌─────────────────────────────────────────────────────────────┐
│                   Retention Policy Mapping                   │
├─────────────────┬────────────────┬──────────────────────────┤
│ Retention Policy│ Target SE Mode │ Характеристики            │
├─────────────────┼────────────────┼──────────────────────────┤
│ TEMPORARY       │ edit           │ Full CRUD, TTL-based     │
│                 │                │ auto-cleanup, drafts     │
├─────────────────┼────────────────┼──────────────────────────┤
│ PERMANENT       │ rw             │ Read-Write, no deletion  │
│                 │                │ via API, long-term       │
└─────────────────┴────────────────┴──────────────────────────┘
```

### TTL Configuration

```yaml
TTL Parameters:
  default_ttl_days: 30        # По умолчанию для temporary
  min_ttl_days: 1             # Минимум 1 день
  max_ttl_days: 365           # Максимум 1 год

Safety Margins:
  finalization_margin: 24h    # После финализации перед удалением
  gc_scan_interval: 1h        # Интервал сканирования GC
```

### File Lifecycle Diagram

```
                    File Lifecycle with Retention Policy

    ┌────────────────────────────────────────────────────────────┐
    │                                                            │
    │  ┌─────────┐     ┌─────────┐     ┌─────────┐              │
    │  │ Upload  │────►│ Edit SE │────►│ Finalize│              │
    │  │ temp    │     │ (draft) │     │         │              │
    │  └─────────┘     └────┬────┘     └────┬────┘              │
    │                       │               │                    │
    │                       │               │                    │
    │                  TTL expires?    ┌────▼────┐              │
    │                       │          │ RW SE   │              │
    │                       ▼          │ (final) │              │
    │                  ┌─────────┐     └────┬────┘              │
    │                  │   GC    │          │                    │
    │                  │ Cleanup │          │                    │
    │                  └─────────┘          │                    │
    │                                       │                    │
    │                                  ┌────▼────┐              │
    │  ┌─────────┐                     │ Archive │              │
    │  │ Upload  │────────────────────►│ (AR SE) │              │
    │  │ perm    │                     └─────────┘              │
    │  └─────────┘                                              │
    │                                                            │
    └────────────────────────────────────────────────────────────┘
```

### Upload API с Retention Policy

```python
@router.post("/upload")
async def upload_file(
    file: UploadFile,
    retention_policy: str = "temporary",  # temporary или permanent
    ttl_days: int | None = None,          # TTL для temporary (1-365)
    description: str | None = None,
    metadata: str | None = None           # JSON метаданные
) -> UploadResponse:
    """
    Загрузка файла с указанием retention policy.

    - temporary: файл в Edit SE, TTL по умолчанию 30 дней
    - permanent: файл в RW SE, без TTL
    """
```

### Response Model

```python
class UploadResponse(BaseModel):
    file_id: UUID
    filename: str
    size_bytes: int
    retention_policy: RetentionPolicy
    ttl_expires_at: datetime | None  # Только для temporary
    storage_element_id: str
    created_at: datetime
```

### Attribute File Extension

```json
{
  "file_id": "123e4567-e89b-12d3-a456-426614174000",
  "original_filename": "document.pdf",
  "file_size": 1048576,
  "content_type": "application/pdf",
  "checksum": "sha256:abc123...",
  "retention_policy": "temporary",
  "ttl_expires_at": "2025-02-15T10:30:00Z",
  "created_at": "2025-01-15T10:30:00Z",
  "created_by": "user123",
  "metadata": {
    "project": "Project A",
    "version": "draft-1"
  }
}
```

### Garbage Collection Integration

GC обрабатывает файлы на основе retention policy:

```python
class GarbageCollectorService:
    async def process_ttl_expired(self):
        """
        Стратегия 1: TTL-expired cleanup
        Удаляет temporary файлы с истёкшим TTL.
        """
        expired_files = await self.find_expired_files()
        for file in expired_files:
            await self.queue_for_deletion(file, reason="ttl_expired")

    async def process_finalized(self):
        """
        Стратегия 2: Finalized file cleanup
        Удаляет оригиналы после successful finalization + safety margin.
        """
        finalized = await self.find_finalized_files()
        for file in finalized:
            if file.safety_margin_elapsed():
                await self.delete_from_source_se(file)
```

## Последствия

### Положительные

1. **Чёткий Lifecycle**: Каждый файл имеет определённый путь
2. **Автоматическая очистка**: TTL-based cleanup для temporary
3. **Оптимизация хранения**: Drafts не занимают permanent storage
4. **Audit Trail**: Все переходы логируются
5. **Гибкость TTL**: Клиент может указать срок хранения

### Отрицательные

1. **Дополнительная сложность**: Нужно выбирать policy при upload
2. **Необратимость**: Нельзя сменить policy без re-upload
3. **Зависимость от GC**: Требуется работающий GC для cleanup

### Митигация рисков

1. **Default Policy**: temporary по умолчанию, safer choice
2. **TTL Warnings**: Уведомления до истечения TTL
3. **Finalization API**: Явный механизм перевода в permanent
4. **Safety Margins**: Задержка удаления после finalization

## Метрики

```yaml
Prometheus metrics:
  - files_uploaded_total{retention_policy}
  - files_finalized_total
  - files_ttl_expired_total
  - files_by_retention_policy{policy}
  - ttl_remaining_seconds{file_id}  # для мониторинга
```

## API Endpoints

| Endpoint | Method | Описание |
|----------|--------|----------|
| `/upload` | POST | Загрузка с retention_policy |
| `/finalize/{file_id}` | POST | Финализация temporary → permanent |
| `/finalize/{tx_id}/status` | GET | Статус финализации |

## Связанные ADR

- ADR-014: Sequential Fill Strategy
- ADR-016: Two-Phase Commit Finalization

## Ссылки

- `ingester-module/app/schemas/upload.py` - RetentionPolicy enum
- `ingester-module/app/services/storage_selector.py` - Policy → Mode mapping
- `admin-module/app/services/garbage_collector_service.py` - TTL cleanup
- `README.md` - раздел "File Lifecycle Management"
