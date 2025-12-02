# ADR-014: Sequential Fill Strategy для Storage Element Selection

## Статус

**Принято** - Реализовано в Sprint 14-15

## Контекст

ArtStore - распределенная система файлового хранилища с несколькими Storage Elements (SE).
При загрузке файлов необходимо выбирать целевой SE на основе:

1. **Retention Policy** - файл должен попасть в SE с нужным режимом:
   - `temporary` → Edit SE (режим `edit`)
   - `permanent` → RW SE (режим `rw`)

2. **Доступная ёмкость** - SE должен иметь достаточно места для файла

3. **Приоритет** - при наличии нескольких подходящих SE нужен детерминированный выбор

### Рассмотренные альтернативы

#### Round Robin
```
Преимущества:
- Равномерное распределение нагрузки
- Простая реализация

Недостатки:
- Фрагментация данных по всем SE
- Сложность в управлении заполненностью
- Затрудняет дедупликацию
- Непредсказуемое размещение
```

#### Consistent Hashing
```
Преимущества:
- Детерминированное размещение
- Минимальное перераспределение при добавлении SE

Недостатки:
- Сложная реализация
- Неравномерное заполнение при разных размерах SE
- Требует ребалансировки
```

#### Random Selection
```
Преимущества:
- Максимальная простота

Недостатки:
- Недетерминированность
- Невозможно предсказать размещение
- Сложности с тестированием
```

#### Sequential Fill (выбрано)
```
Преимущества:
- Предсказуемое размещение
- Максимальная утилизация каждого SE
- Простота резервного копирования (один SE = один backup unit)
- Детерминированный выбор
- Удобство для миграции в archive

Недостатки:
- Неравномерная нагрузка на активный SE
- Требует мониторинга заполненности
```

## Решение

Реализовать **Sequential Fill Strategy** со следующими характеристиками:

### Алгоритм выбора SE

```
                    ┌─────────────────────┐
                    │   Upload Request    │
                    │  retention_policy   │
                    │     file_size       │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │  Filter by Mode     │
                    │  temporary → edit   │
                    │  permanent → rw     │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │  Sort by Priority   │
                    │  (ascending order)  │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
        ┌─────▼─────┐    ┌─────▼─────┐    ┌─────▼─────┐
        │  SE-01    │    │  SE-02    │    │  SE-03    │
        │ priority=1│    │ priority=2│    │ priority=3│
        │ cap=70%   │    │ cap=30%   │    │ cap=10%   │
        └─────┬─────┘    └───────────┘    └───────────┘
              │
    ┌─────────▼─────────┐
    │  Check Capacity   │
    │  status != FULL   │
    │  has space for    │
    │  file_size        │
    └─────────┬─────────┘
              │
              ├── OK ──────► Return SE-01
              │
              └── FULL ────► Try SE-02 (next priority)
```

### Adaptive Capacity Thresholds

Вместо фиксированного 95% порога используются адаптивные пороги на основе размера SE:

```python
def calculate_thresholds(capacity_bytes: int) -> dict:
    """
    Адаптивные пороги учитывают размер SE.
    Для маленьких SE (< 1GB) - более агрессивные пороги.
    """
    if capacity_bytes < 1_073_741_824:  # < 1GB
        return {
            "warning": 0.80,   # 80%
            "critical": 0.90,  # 90%
            "full": 0.95       # 95%
        }
    elif capacity_bytes < 107_374_182_400:  # < 100GB
        return {
            "warning": 0.85,   # 85%
            "critical": 0.92,  # 92%
            "full": 0.97       # 97%
        }
    else:  # >= 100GB
        return {
            "warning": 0.90,   # 90%
            "critical": 0.95,  # 95%
            "full": 0.98       # 98%
        }
```

### Capacity Status Levels

```
┌──────────────────────────────────────────────────────────┐
│                    Storage Capacity                       │
├───────────┬───────────┬────────────┬────────────┬────────┤
│    OK     │  WARNING  │  CRITICAL  │    FULL    │ Action │
├───────────┼───────────┼────────────┼────────────┼────────┤
│  0-85%    │  85-92%   │  92-97%    │   >97%     │        │
│   ✅      │    ⚠️     │    🔴      │    ⛔      │        │
├───────────┼───────────┼────────────┼────────────┼────────┤
│ Accept    │ Accept    │ Small      │ Reject     │        │
│ all       │ all       │ files only │ all        │        │
└───────────┴───────────┴────────────┴────────────┴────────┘
```

### Intelligent File Size Handling

При CRITICAL статусе система пытается разместить файл более интеллектуально:

1. **Проверка свободного места** с запасом (1.5x размера файла)
2. **Маленькие файлы** (< 10MB) могут быть приняты даже в CRITICAL
3. **Fallback** на SE с большим свободным местом при переполнении

### Data Classes

```python
@dataclass
class StorageElementInfo:
    """Информация о Storage Element для селекции"""
    id: str
    endpoint: str
    mode: str  # edit, rw, ro, ar
    priority: int
    capacity_bytes: int
    used_bytes: int
    available_bytes: int
    utilization_percent: float
    status: CapacityStatus  # OK, WARNING, CRITICAL, FULL
    last_health_check: datetime
    is_healthy: bool
```

```python
class CapacityStatus(str, Enum):
    """Статус заполненности SE"""
    OK = "ok"           # Принимает все файлы
    WARNING = "warning" # Принимает, но приближается к лимиту
    CRITICAL = "critical"  # Только маленькие файлы
    FULL = "full"       # Не принимает новые файлы
```

## Последствия

### Положительные

1. **Предсказуемость**: Файлы размещаются детерминированно по приоритету SE
2. **Утилизация**: Каждый SE заполняется максимально перед переходом к следующему
3. **Backup-friendly**: Заполненный SE - готовый backup unit
4. **Простота миграции**: Заполненный SE можно перевести в RO/AR режим
5. **Прозрачность**: Легко понять, где находится файл

### Отрицательные

1. **Hot Spot**: Активный SE получает всю нагрузку
2. **Single Point of Failure**: При недоступности активного SE - деградация
3. **Неравномерный износ**: Первые SE изнашиваются быстрее

### Митигация рисков

1. **Hot Spot**: Мониторинг IOPS, горизонтальное масштабирование через несколько Edit SE
2. **SPOF**: Fallback на следующий SE по приоритету, Health Check каждые 30с
3. **Износ**: Ротация приоритетов, использование SSD для активных SE

## Метрики

```yaml
Prometheus metrics:
  - storage_selector_selections_total{mode, status}
  - storage_selector_fallbacks_total{reason}
  - storage_selector_no_capacity_total{retention_policy}
  - storage_element_capacity_status{se_id}
  - storage_element_utilization_percent{se_id}
```

## Связанные ADR

- ADR-015: Retention Policy Model
- ADR-016: Two-Phase Commit Finalization

## Ссылки

- `ingester-module/app/services/storage_selector.py` - реализация StorageSelector
- `storage-element/app/services/health_reporter.py` - Health Reporting для SE
- `README.md` - раздел "Storage Element Selection Strategy"
