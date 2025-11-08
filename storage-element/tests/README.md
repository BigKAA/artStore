# Storage Element Tests

Комплексные тесты для Storage Element микросервиса.

## Структура Тестов

- `test_file_upload.py` - Тесты загрузки файлов с streaming и WAL integration
- `test_file_search.py` - Тесты PostgreSQL full-text search с advanced filtering
- `test_file_download.py` - Тесты HTTP Range requests (RFC 7233) и streaming download

## Требования

### Общие Требования
```bash
pip install -r requirements.txt
```

### Специфичные Требования для Тестов Поиска

**test_file_search.py** требует PostgreSQL базу данных:
- UUID тип данных
- TSVECTOR для full-text search
- JSONB для advanced tag queries
- PostgreSQL функции (ts_rank, plainto_tsquery)

SQLite НЕ поддерживает эти возможности.

## Запуск Тестов

### Вариант 1: С PostgreSQL (Полная Функциональность)

1. **Запустите PostgreSQL**:
   ```bash
   cd /home/artur/Projects/artStore
   docker-compose up -d postgres
   ```

2. **Примените миграции**:
   ```bash
   cd storage-element
   alembic upgrade head
   ```

3. **Установите переменную окружения**:
   ```bash
   export APP__DATABASE__HOST=localhost
   ```

4. **Запустите тесты**:
   ```bash
   python -m pytest tests/test_file_search.py -v
   ```

### Вариант 2: Без PostgreSQL (Тесты Пропускаются)

Если PostgreSQL недоступен, тесты автоматически пропускаются:

```bash
python -m pytest tests/test_file_search.py -v
# Все тесты будут SKIPPED
```

### Запуск Всех Тестов

```bash
# Запустить все тесты
python -m pytest tests/ -v

# С покрытием кода
python -m pytest tests/ --cov=app --cov-report=html

# Только быстрые тесты (пропустить PostgreSQL-зависимые)
python -m pytest tests/ -v -m "not slow"
```

## Docker Testing

Для изолированного тестирования в Docker:

```bash
# В контейнере без PostgreSQL (тесты пропускаются)
docker run --rm -v "$(pwd)":/app -w /app python:3.11-slim \
  bash -c "pip install -q -r requirements.txt && python -m pytest tests/test_file_search.py -v"

# С PostgreSQL (требует docker network настройку)
docker-compose -f docker-compose-test.yml up --abort-on-container-exit
```

## Конфигурация Тестовой Базы Данных

Тесты используют следующие параметры подключения из конфигурации:

```yaml
database:
  host: localhost  # или postgres для Docker
  port: 5432
  username: artstore
  password: password
  database: artstore
  table_prefix: storage_elem_01
```

## Важные Замечания

### PostgreSQL Full-Text Search
- Тесты `test_file_search.py` проверяют **реальную** PostgreSQL функциональность
- Mock'и и in-memory SQLite **НЕ** могут эмулировать PostgreSQL FTS
- Для полного тестирования необходима настоящая PostgreSQL база

### WAL и Атомарные Операции
- Тесты `test_file_upload.py` требуют файловую систему для WAL журнала
- Используется временная директория для изоляции тестов
- Автоматическая очистка после завершения тестов

### HTTP Range Requests
- Тесты `test_file_download.py` проверяют RFC 7233 compliance
- Все тесты работают без PostgreSQL (используют локальную файловую систему)
- Integration tests помечены как skipped (требуют полный upload-download цикл)

### Тестовые Данные
- Все тесты создают и удаляют свои данные
- Используется отдельный table_prefix для изоляции
- Cleanup гарантирован через pytest fixtures

## Покрытие Тестов

Текущее покрытие:

- **File Upload**: 15 тест-кейсов
  - Успешная загрузка
  - Validation (filename, retention, username)
  - Streaming больших файлов
  - Unicode имена файлов
  - Tags обработка
  - SHA256 calculation
  - WAL integration
  - Error handling

- **File Search**: 21 тест-кейс
  - Full-text search с ranking
  - Filtering (uploader, size, date, tags, retention)
  - Комбинированные фильтры
  - Pagination
  - Edge cases
  - JSONB tag queries
  - Similar files suggestions
  - Error handling

- **File Download**: 16 тест-кейсов (passed) + 8 integration (skipped)
  - Path traversal protection
  - ETag generation
  - Range parsing (single, multiple, suffix, open-ended)
  - Range validation
  - File streaming (full, partial, middle, single byte)
  - Multipart ranges
  - Integration tests (требуют PostgreSQL + full stack)

## CI/CD Integration

Для CI/CD pipeline:

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: password
          POSTGRES_DB: artstore
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt

      - name: Run migrations
        run: |
          alembic upgrade head
        env:
          APP__DATABASE__HOST: postgres

      - name: Run tests
        run: |
          pytest tests/ -v --cov=app
        env:
          APP__DATABASE__HOST: postgres
```

## Troubleshooting

### Тесты Пропускаются
Если видите "SKIPPED" для test_file_search.py:
- Проверьте, что PostgreSQL запущен
- Проверьте переменную окружения APP__DATABASE__HOST
- Убедитесь, что миграции применены

### Connection Errors
Если тесты падают с connection errors:
- Проверьте docker-compose ps
- Проверьте порт 5432 доступен
- Проверьте credentials в конфигурации

### SQLAlchemy Type Errors
Если видите "can't render element of type UUID":
- Это нормально для SQLite - тесты должны быть SKIPPED
- Запустите с PostgreSQL для полной функциональности
