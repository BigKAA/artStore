# Migration Guide: STORAGE_MAX_SIZE унификация

## Обзор изменений (v1.1.0)

В версии 1.1.0 унифицированы параметры размера хранилища в единый параметр `STORAGE_MAX_SIZE`.

### Проблема

Ранее существовало дублирование параметров:
- `STORAGE_MAX_SIZE_GB` (int, гигабайты) - для local storage
- `STORAGE_S3_SOFT_CAPACITY_LIMIT` (int, байты) - для S3 storage

**Архитектурная проблема**: Два параметра для одной концепции, разные единицы измерения, путаница в конфигурации.

### Решение

Единый параметр `STORAGE_MAX_SIZE` в **байтах** для всех типов хранилищ (local, s3).

## Таблица изменений

| Старый параметр | Новый параметр | Единицы | Статус |
|-----------------|----------------|---------|--------|
| `STORAGE_MAX_SIZE_GB` | `STORAGE_MAX_SIZE` | Байты | Deprecated |
| `STORAGE_S3_SOFT_CAPACITY_LIMIT` | `STORAGE_MAX_SIZE` | Байты | Deprecated |

## Конвертация единиц

### Справочная таблица

| Размер | Значение в байтах |
|--------|-------------------|
| 1 GB | `1073741824` |
| 5 GB | `5368709120` |
| 10 GB | `10737418240` |
| 50 GB | `53687091200` |
| 100 GB | `107374182400` |
| 500 GB | `536870912000` |
| 1 TB | `1099511627776` |
| 5 TB | `5497558138880` |
| 10 TB | `10995116277760` |

### Формулы расчёта

```python
# GB → Bytes
bytes = gb_value * 1024 * 1024 * 1024
# Пример: 5 GB = 5 * 1024 * 1024 * 1024 = 5368709120 bytes

# TB → Bytes
bytes = tb_value * 1024 * 1024 * 1024 * 1024
# Пример: 1 TB = 1 * 1024^4 = 1099511627776 bytes

# Bytes → GB (для проверки)
gb = bytes / (1024 * 1024 * 1024)

# Bytes → TB (для проверки)
tb = bytes / (1024 ** 4)
```

## Автоматическая миграция

Система автоматически поддерживает legacy параметры с backward compatibility:

### Приоритет параметров

1. **STORAGE_MAX_SIZE** (высший приоритет) - если явно задан
2. **STORAGE_MAX_SIZE_GB** (legacy) - автоконвертация в байты + deprecation warning
3. **STORAGE_S3_SOFT_CAPACITY_LIMIT** для S3 (legacy) - автоконвертация + deprecation warning
4. **Default** (1 GB) - если ничего не задано

### Deprecation warnings

При использовании legacy параметров в логах появятся warnings:

```
WARNING - DEPRECATED: STORAGE_MAX_SIZE_GB=5 detected. Please migrate to STORAGE_MAX_SIZE=5368709120 (bytes)
```

```
WARNING - DEPRECATED: STORAGE_S3_SOFT_CAPACITY_LIMIT=10995116277760 detected. Please migrate to STORAGE_MAX_SIZE=10995116277760 (bytes)
```

## Действия для миграции

### 1. Development окружение (.env файл)

**Было:**
```bash
STORAGE_TYPE=local
STORAGE_MAX_SIZE_GB=1
```

**Стало:**
```bash
STORAGE_TYPE=local
STORAGE_MAX_SIZE=1073741824  # 1GB
```

### 2. S3 конфигурация (.env файл)

**Было:**
```bash
STORAGE_TYPE=s3
STORAGE_S3_SOFT_CAPACITY_LIMIT=10995116277760  # 10TB
```

**Стало:**
```bash
STORAGE_TYPE=s3
STORAGE_MAX_SIZE=10995116277760  # 10TB
```

### 3. Docker Compose

**Было:**
```yaml
storage-element-01:
  environment:
    STORAGE_TYPE: s3
    STORAGE_MAX_SIZE_GB: 1
    STORAGE_S3_SOFT_CAPACITY_LIMIT: 1073741824
```

**Стало:**
```yaml
storage-element-01:
  environment:
    STORAGE_TYPE: s3
    STORAGE_MAX_SIZE: 1073741824  # 1GB
```

### 4. Kubernetes ConfigMap/Secret

**Было:**
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: storage-element-config
data:
  STORAGE_MAX_SIZE_GB: "100"
```

**Стало:**
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: storage-element-config
data:
  STORAGE_MAX_SIZE: "107374182400"  # 100GB
```

## Проверка после миграции

### 1. Проверка логов

После перезапуска убедитесь, что нет deprecation warnings:

```bash
docker-compose logs storage-element-01 | grep -i "deprecated"
```

**Ожидаемый результат**: Пустой вывод (нет warnings)

### 2. Проверка endpoint /api/v1/info

```bash
curl -s http://localhost:8010/api/v1/info | jq '.capacity_bytes'
```

**Ожидаемый результат**: Значение соответствует `STORAGE_MAX_SIZE`

### 3. Проверка health endpoint

```bash
curl -s http://localhost:8010/health/ready | jq '.checks'
```

## Timeline удаления deprecated параметров

| Версия | Статус | Дата |
|--------|--------|------|
| v1.1.0 | Deprecated с warnings | Текущая |
| v1.x.x | Deprecated, работают | До v2.0.0 |
| v2.0.0 | **УДАЛЕНЫ** | TBD |

**Рекомендация**: Выполните миграцию до релиза v2.0.0 чтобы избежать breaking changes.

## Troubleshooting

### Проблема: Неверное значение capacity_bytes

**Симптом**: `/api/v1/info` возвращает неожиданное значение `capacity_bytes`

**Причина**: Возможно используются оба параметра (новый и legacy)

**Решение**: Удалите legacy параметры, оставьте только `STORAGE_MAX_SIZE`

### Проблема: Deprecation warning не исчезает

**Симптом**: В логах продолжает появляться warning после миграции

**Причина**: Legacy параметр всё ещё присутствует в конфигурации

**Решение**:
1. Проверьте все источники конфигурации (.env, docker-compose.yml, environment)
2. Удалите `STORAGE_MAX_SIZE_GB` и `STORAGE_S3_SOFT_CAPACITY_LIMIT`
3. Перезапустите сервис

### Проблема: Ошибка валидации max_size

**Симптом**: Ошибка `max_size must be greater than 0`

**Причина**: Неверное значение `STORAGE_MAX_SIZE`

**Решение**: Убедитесь что значение положительное число в байтах

## Дополнительные helper properties

После миграции доступны удобные properties для отображения размера:

```python
from app.core.config import settings

# Размер в байтах (основной параметр)
print(settings.storage.max_size)  # 1073741824

# Размер в GB для отображения
print(settings.storage.max_size_gb_display)  # 1.0

# Размер в TB для отображения
print(settings.storage.max_size_tb_display)  # 0.001

# Legacy property (deprecated, для совместимости)
print(settings.storage.max_size_bytes)  # 1073741824 (то же что max_size)
```

## Связанные изменения

- `storage-element/app/core/config.py` - Обновлённая модель конфигурации
- `storage-element/app/services/capacity_service.py` - Использует `max_size` напрямую
- `storage-element/app/api/v1/endpoints/info.py` - Возвращает `capacity_bytes` из `max_size`

## Версия документа

- **Версия**: 1.0
- **Дата создания**: 2025-12-05
- **Целевая версия продукта**: v1.1.0
