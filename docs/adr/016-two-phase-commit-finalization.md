# ADR-016: Two-Phase Commit для File Finalization

## Статус

**Принято** - Реализовано в Sprint 15

## Контекст

При финализации файла из Edit SE в RW SE требуется атомарная операция:

1. Файл должен быть **скопирован** в целевой RW SE
2. Копия должна быть **верифицирована** (checksum match)
3. Только после успешной верификации - **обновление метаданных**
4. Оригинал в Edit SE должен быть **помечен для удаления**

### Риски при простом подходе

```
Простой copy-delete:

1. Copy file to RW SE
2. Delete from Edit SE          ← Failure here = DATA LOSS
3. Update metadata

Проблемы:
- Crash между шагами → inconsistent state
- Network failure → partial operation
- Нет recovery механизма
```

### Рассмотренные альтернативы

#### Simple Copy-Delete
```
Недостатки:
- Нет атомарности
- Data loss при failure
- Нет recovery
```

#### Saga Pattern
```
Каждый шаг имеет compensating action.

Недостатки:
- Сложная реализация
- Eventual consistency
- Compensating actions могут также fail
```

#### Two-Phase Commit (выбрано)
```
Prepare phase + Commit phase.

Преимущества:
- Атомарность операции
- Recovery при failure
- Explicit transaction states
- Checksum verification
```

## Решение

Реализовать **Two-Phase Commit Protocol** для финализации файлов:

### Transaction States

```python
class FinalizeTransactionStatus(str, Enum):
    """Статусы транзакции финализации"""
    PENDING = "pending"        # Транзакция создана
    COPYING = "copying"        # Phase 1: Копирование файла
    COPIED = "copied"          # Файл скопирован, ожидание verify
    VERIFYING = "verifying"    # Phase 2: Верификация checksum
    COMPLETED = "completed"    # Успешно завершено
    FAILED = "failed"          # Ошибка
    ROLLED_BACK = "rolled_back"  # Откат выполнен
```

### Two-Phase Commit Flow

```
                    Two-Phase Commit Finalization

    ┌─────────────────────────────────────────────────────────┐
    │                                                         │
    │  Client: POST /finalize/{file_id}                      │
    │                                                         │
    │      │                                                  │
    │      ▼                                                  │
    │  ┌─────────────────────────────────────────────┐       │
    │  │           PHASE 1: PREPARE                  │       │
    │  │                                             │       │
    │  │  1. Create transaction record               │       │
    │  │  2. Lock source file                        │       │
    │  │  3. Select target RW SE                     │       │
    │  │  4. Copy file to target SE                  │       │
    │  │  5. Status: COPYING → COPIED                │       │
    │  │                                             │       │
    │  └────────────────────┬────────────────────────┘       │
    │                       │                                 │
    │              Success? │                                 │
    │                       │                                 │
    │          ┌────────────┴────────────┐                   │
    │          │                         │                    │
    │        Yes                        No                   │
    │          │                         │                    │
    │          ▼                         ▼                    │
    │  ┌───────────────────┐    ┌───────────────────┐        │
    │  │   PHASE 2:        │    │    ROLLBACK       │        │
    │  │   COMMIT          │    │                   │        │
    │  │                   │    │ 1. Delete copy    │        │
    │  │ 1. Verify checksum│    │ 2. Unlock source  │        │
    │  │ 2. Update metadata│    │ 3. Mark FAILED    │        │
    │  │ 3. Queue cleanup  │    │                   │        │
    │  │ 4. Mark COMPLETED │    └───────────────────┘        │
    │  │                   │                                  │
    │  └────────┬──────────┘                                  │
    │           │                                             │
    │           ▼                                             │
    │  ┌───────────────────────────────────────────┐         │
    │  │  Cleanup Queue (24h safety margin)        │         │
    │  │  Original file in Edit SE → DELETE        │         │
    │  └───────────────────────────────────────────┘         │
    │                                                         │
    └─────────────────────────────────────────────────────────┘
```

### Phase 1: Prepare

```python
async def prepare_phase(
    self,
    file_id: UUID,
    source_se: StorageElement,
    target_se: StorageElement
) -> PrepareResult:
    """
    Phase 1: Подготовка и копирование файла.

    1. Создать запись транзакции со статусом PENDING
    2. Проверить что файл существует и является temporary
    3. Заблокировать файл (lock)
    4. Скопировать файл на target SE
    5. Обновить статус на COPIED
    """
    # Create transaction record
    tx = await self.create_transaction(file_id, source_se, target_se)

    try:
        # Lock source file
        await self.lock_file(file_id)

        # Update status to COPYING
        await self.update_status(tx.id, FinalizeTransactionStatus.COPYING)

        # Copy file to target SE
        copy_result = await self.copy_to_target(
            file_id=file_id,
            source_se=source_se,
            target_se=target_se
        )

        # Update status to COPIED
        await self.update_status(tx.id, FinalizeTransactionStatus.COPIED)

        return PrepareResult(
            transaction_id=tx.id,
            status=FinalizeTransactionStatus.COPIED,
            target_file_id=copy_result.file_id
        )

    except Exception as e:
        await self.rollback(tx.id, reason=str(e))
        raise
```

### Phase 2: Commit

```python
async def commit_phase(
    self,
    transaction_id: UUID,
    expected_checksum: str
) -> CommitResult:
    """
    Phase 2: Верификация и коммит.

    1. Получить checksum копии на target SE
    2. Сравнить с оригиналом
    3. Если match - обновить метаданные, пометить completed
    4. Если mismatch - rollback
    """
    tx = await self.get_transaction(transaction_id)

    try:
        # Update status to VERIFYING
        await self.update_status(tx.id, FinalizeTransactionStatus.VERIFYING)

        # Verify checksum on target SE
        target_checksum = await self.get_target_checksum(tx.target_file_id)

        if target_checksum != expected_checksum:
            await self.rollback(tx.id, reason="Checksum mismatch")
            raise ChecksumMismatchError(expected_checksum, target_checksum)

        # Update file registry - mark as finalized, new location
        await self.update_file_registry(
            file_id=tx.file_id,
            new_se_id=tx.target_se_id,
            retention_policy="permanent"
        )

        # Queue source file for cleanup (24h safety margin)
        await self.queue_for_cleanup(
            file_id=tx.file_id,
            source_se_id=tx.source_se_id,
            cleanup_after=datetime.utcnow() + timedelta(hours=24)
        )

        # Mark transaction as COMPLETED
        await self.update_status(tx.id, FinalizeTransactionStatus.COMPLETED)

        return CommitResult(
            transaction_id=tx.id,
            status=FinalizeTransactionStatus.COMPLETED,
            new_location=tx.target_se_id
        )

    except Exception as e:
        await self.rollback(tx.id, reason=str(e))
        raise
```

### Rollback Mechanism

```python
async def rollback(
    self,
    transaction_id: UUID,
    reason: str
) -> None:
    """
    Откат транзакции при ошибке.

    1. Удалить копию на target SE (если создана)
    2. Снять блокировку с source file
    3. Пометить транзакцию как ROLLED_BACK
    """
    tx = await self.get_transaction(transaction_id)

    # Delete copy from target if exists
    if tx.target_file_id:
        try:
            await self.delete_from_target(tx.target_file_id, tx.target_se_id)
        except Exception as e:
            logger.error(f"Failed to delete copy during rollback: {e}")

    # Unlock source file
    try:
        await self.unlock_file(tx.file_id)
    except Exception as e:
        logger.error(f"Failed to unlock source during rollback: {e}")

    # Mark as rolled back
    await self.update_status(
        tx.id,
        FinalizeTransactionStatus.ROLLED_BACK,
        error_message=reason
    )
```

### Safety Margin

После успешной финализации оригинал не удаляется сразу:

```python
SAFETY_MARGIN_HOURS = 24  # 24 часа до удаления оригинала

class FileCleanupQueue(Base):
    """Очередь на удаление после финализации"""
    __tablename__ = "file_cleanup_queue"

    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[UUID] = mapped_column(unique=True)
    se_id: Mapped[str]
    transaction_id: Mapped[UUID]
    scheduled_at: Mapped[datetime]  # Когда можно удалять
    cleanup_type: Mapped[str] = "finalized"
    created_at: Mapped[datetime]
```

### Progress Tracking

```python
class FinalizeStatus(BaseModel):
    """Статус транзакции для polling"""
    transaction_id: UUID
    status: FinalizeTransactionStatus
    progress_percent: int  # 0-100
    created_at: datetime
    updated_at: datetime
    error_message: str | None

# Progress mapping
PROGRESS_MAP = {
    FinalizeTransactionStatus.PENDING: 0,
    FinalizeTransactionStatus.COPYING: 25,
    FinalizeTransactionStatus.COPIED: 50,
    FinalizeTransactionStatus.VERIFYING: 75,
    FinalizeTransactionStatus.COMPLETED: 100,
    FinalizeTransactionStatus.FAILED: 0,
    FinalizeTransactionStatus.ROLLED_BACK: 0,
}
```

### API Endpoints

```python
@router.post("/{file_id}")
async def finalize_file(file_id: UUID) -> FinalizeResponse:
    """
    Запуск финализации temporary файла.

    Returns:
        - transaction_id для polling
        - status: "accepted"

    HTTP 202 Accepted - операция асинхронная
    """

@router.get("/{transaction_id}/status")
async def get_finalize_status(transaction_id: UUID) -> FinalizeStatus:
    """
    Получить статус транзакции финализации.

    Polling interval: 1-2 секунды рекомендуется.
    """
```

## Последствия

### Положительные

1. **Атомарность**: Операция либо полностью завершена, либо откачена
2. **Data Safety**: Checksum verification предотвращает corruption
3. **Recovery**: Явные состояния позволяют recovery при failure
4. **Audit Trail**: Полная история транзакции
5. **Safety Margin**: 24h защита от преждевременного удаления

### Отрицательные

1. **Latency**: Две фазы занимают больше времени
2. **Storage Overhead**: Временно файл существует в двух местах
3. **Complexity**: Сложнее простого copy-delete

### Митигация рисков

1. **Latency**: Асинхронное выполнение, polling для статуса
2. **Storage**: 24h safety margin приемлем для enterprise storage
3. **Complexity**: Чёткие состояния и recovery procedures

## Failure Scenarios

### Scenario 1: Failure during COPYING

```
State: COPYING
Recovery: Rollback - delete partial copy, unlock source
Result: Source file unchanged, transaction ROLLED_BACK
```

### Scenario 2: Failure during VERIFYING

```
State: VERIFYING
Recovery: Rollback - delete complete copy, unlock source
Result: Source file unchanged, transaction ROLLED_BACK
```

### Scenario 3: Checksum Mismatch

```
State: VERIFYING
Action: Automatic rollback
Result: Source file preserved, copy deleted, retry possible
```

### Scenario 4: Process Crash

```
State: Any intermediate state
Recovery: Background job scans for stuck transactions
Action: Resume from last known state or rollback
```

## Метрики

```yaml
Prometheus metrics:
  - finalize_transactions_total{status}
  - finalize_duration_seconds{phase}
  - finalize_rollbacks_total{reason}
  - finalize_checksum_mismatches_total
  - finalize_queue_size
  - cleanup_queue_size
```

## Связанные ADR

- ADR-014: Sequential Fill Strategy
- ADR-015: Retention Policy Model

## Ссылки

- `ingester-module/app/services/finalize_service.py` - FinalizeService
- `ingester-module/app/api/v1/endpoints/finalize.py` - API endpoints
- `admin-module/app/services/garbage_collector_service.py` - Cleanup queue processing
- `README.md` - раздел "Two-Phase Commit Finalization"
