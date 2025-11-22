# Integration Tests для Storage Element

## Обзор

Integration tests тестируют Storage Element в реальном окружении с:
- PostgreSQL database (с migrations)
- Redis coordination
- HTTP API endpoints
- Реальной JWT аутентификацией (RS256)

## Быстрый старт

### Автоматический запуск (Рекомендуется)

```bash
# Запуск всех integration tests в Docker окружении
cd storage-element
./scripts/run_integration_tests.sh
```

Скрипт автоматически:
1. ✅ Очищает предыдущее тестовое окружение
2. ✅ Запускает PostgreSQL и Redis в Docker
3. ✅ Применяет Alembic migrations
4. ✅ Запускает Storage Element в тестовом режиме
5. ✅ Выполняет все integration tests
6. ✅ Предлагает оставить окружение для debugging

### Ручной запуск

```bash
# 1. Запустить тестовую инфраструктуру
docker-compose -f docker-compose.test.yml up -d

# 2. Дождаться готовности сервисов
docker-compose -f docker-compose.test.yml ps

# 3. Применить migrations
source ../.venv/bin/activate
export DB_HOST=localhost DB_PORT=5433 DB_USERNAME=artstore_test \
       DB_PASSWORD=test_password DB_DATABASE=artstore_test \
       DB_TABLE_PREFIX=test_storage
alembic upgrade head

# 4. Запустить tests
export JWT_PUBLIC_KEY_PATH="../admin-module/.keys/public_key.pem"
pytest tests/integration/ -v

# 5. Cleanup
docker-compose -f docker-compose.test.yml down -v
```

## Структура тестов

```
tests/integration/
├── README.md                           # Этот файл
├── conftest.py                         # Pytest fixtures для integration tests
├── test_file_operations.py             # API endpoint tests (upload, download, delete)
├── test_storage_service.py             # Storage service direct tests
└── test_template_schema_integration.py # Template schema filesystem tests
```

## Pytest Fixtures

### Authentication

```python
@pytest.fixture(scope="function")
def auth_headers():
    """JWT токен для каждого теста (избегаем expiration)"""
    return {"Authorization": "Bearer <valid_jwt_token>"}
```

### HTTP Client

```python
@pytest.fixture(scope="function")
async def async_client():
    """AsyncClient для HTTP API testing через real HTTP requests"""
    # Real HTTP requests к Docker test container на localhost:8011
    base_url = os.environ.get("STORAGE_API_URL", "http://localhost:8011")
    async with AsyncClient(
        base_url=base_url,
        timeout=30.0
    ) as client:
        yield client
```

### Test Data

```python
@pytest.fixture(scope="session")
def test_file_content():
    """Тестовое содержимое файла"""
    return b"Test file content..."

@pytest.fixture(scope="session")
def test_file_metadata():
    """Метаданные для тестового файла"""
    return {"document_type": "test", "tags": ["test"]}
```

### Cleanup

```python
@pytest.fixture(scope="function")
async def cleanup_test_files(async_client, auth_headers):
    """Автоматическая очистка файлов после tests"""
    files_to_cleanup = []
    yield files_to_cleanup
    # Cleanup logic...
```

## Конфигурация окружения

### Docker Test Environment

**docker-compose.test.yml** создает изолированное тестовое окружение:

```yaml
services:
  postgres-test:      # Port 5433 (отдельный от production)
  redis-test:         # Port 6380 (отдельный от production)
  storage-element-test: # Port 8011 (отдельный от production)
```

**Важно**: Тестовое окружение полностью изолировано от production.

### Environment Variables

```bash
# Database
DB_HOST=localhost
DB_PORT=5433
DB_USERNAME=artstore_test
DB_PASSWORD=test_password
DB_DATABASE=artstore_test
DB_TABLE_PREFIX=test_storage

# Redis
REDIS_HOST=localhost
REDIS_PORT=6380

# JWT
JWT_PUBLIC_KEY_PATH=../admin-module/.keys/public_key.pem

# API
STORAGE_API_URL=http://localhost:8011
```

## Запуск отдельных тестов

```bash
# Все integration tests
pytest tests/integration/ -v

# Конкретный файл
pytest tests/integration/test_file_operations.py -v

# Конкретный тест
pytest tests/integration/test_file_operations.py::TestFileUpload::test_upload_file_success -v

# С coverage
pytest tests/integration/ -v --cov=app --cov-report=html

# С markers
pytest tests/integration/ -v -m "api"
pytest tests/integration/ -v -m "requires_db"
```

## Test Markers

```python
@pytest.mark.integration  # Integration test
@pytest.mark.api          # API endpoint test
@pytest.mark.storage      # Storage backend test
@pytest.mark.auth         # Authentication test
@pytest.mark.slow         # Slow-running test
@pytest.mark.requires_db  # Requires database
@pytest.mark.requires_redis # Requires Redis
```

## Debugging

### Просмотр логов

```bash
# Storage Element logs
docker logs artstore_storage_element_test -f

# PostgreSQL logs
docker logs artstore_storage_postgres_test -f

# Redis logs
docker logs artstore_storage_redis_test -f
```

### Подключение к тестовой БД

```bash
docker exec -it artstore_storage_postgres_test psql -U artstore_test -d artstore_test

# Проверка таблиц
\dt test_storage.*

# Проверка данных
SELECT * FROM test_storage.files LIMIT 10;
```

### Подключение к тестовому Redis

```bash
docker exec -it artstore_storage_redis_test redis-cli

# Проверка ключей
KEYS *

# Проверка значений
GET storage_master:test
```

### HTTP запросы к тестовому API

```bash
# Health check
curl http://localhost:8011/health/live

# Metrics
curl http://localhost:8011/metrics

# OpenAPI docs
open http://localhost:8011/docs
```

## Troubleshooting

### JWT Public Key Not Found

```bash
# Проверка что ключ существует
ls -la ../admin-module/.keys/public_key.pem

# Если не существует - сгенерировать
cd ../admin-module
python scripts/generate_jwt_keys.py
```

### Database Connection Failed

```bash
# Проверка что PostgreSQL запущен
docker ps | grep postgres_test

# Проверка health
docker exec artstore_storage_postgres_test pg_isready -U artstore_test

# Перезапуск PostgreSQL
docker-compose -f docker-compose.test.yml restart postgres-test
```

### Migrations Failed

```bash
# Проверка текущей версии
alembic current

# Откат всех migrations
alembic downgrade base

# Повторное применение
alembic upgrade head

# Проверка истории
alembic history
```

### Storage Element Not Starting

```bash
# Проверка логов
docker logs artstore_storage_element_test --tail 100

# Проверка health checks
docker inspect artstore_storage_element_test | jq '.[0].State.Health'

# Перезапуск
docker-compose -f docker-compose.test.yml restart storage-element-test
```

### Tests Hanging or Timing Out

```bash
# Увеличить timeout в pytest
pytest tests/integration/ -v --timeout=300

# Запуск с verbose async debugging
pytest tests/integration/ -v -s --log-cli-level=DEBUG

# Проверка что все сервисы healthy
docker-compose -f docker-compose.test.yml ps
```

## Best Practices

### 1. Изоляция тестов

- ✅ Каждый тест должен быть независимым
- ✅ Используйте `cleanup_test_files` fixture для автоматической очистки
- ✅ Не полагайтесь на порядок выполнения тестов

### 2. JWT токены

- ✅ Используйте function-scoped `auth_headers` fixture
- ✅ Не кешируйте токены между тестами (expiration issues)
- ✅ Генерируйте fresh токены с достаточным `expires_in`

### 3. Асинхронный код

- ✅ Всегда используйте `async def` для async tests
- ✅ Используйте `await` для всех async operations
- ✅ Properly close async resources (AsyncClient context manager)

### 4. Error handling

- ✅ Тестируйте как success, так и error cases
- ✅ Проверяйте HTTP status codes
- ✅ Валидируйте error response bodies

### 5. Test data

- ✅ Используйте fixtures для test data
- ✅ Создавайте realistic test data
- ✅ Cleanup test data после тестов

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Integration Tests

on: [push, pull_request]

jobs:
  integration-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Generate JWT keys
        run: |
          cd admin-module
          python scripts/generate_jwt_keys.py

      - name: Run integration tests
        run: |
          cd storage-element
          ./scripts/run_integration_tests.sh
```

## Performance

**Expected performance**:
- Test suite execution: ~2-5 минут
- Infrastructure startup: ~30-60 секунд
- Database migrations: ~10-20 секунд
- Per-test execution: ~1-5 секунд

**Optimization tips**:
- Использовать `pytest-xdist` для параллельного выполнения
- Использовать session-scoped fixtures для shared resources
- Минимизировать database roundtrips в тестах

## Coverage Goals

**Target coverage**: 80%+

```bash
# Запуск с coverage
pytest tests/integration/ -v --cov=app --cov-report=html --cov-report=term-missing

# Просмотр HTML report
open htmlcov/index.html
```

## Дальнейшее развитие

- [ ] Добавить performance tests (load testing)
- [ ] Добавить security tests (penetration testing)
- [ ] Добавить E2E tests (full workflow testing)
- [ ] Добавить chaos engineering tests (failure injection)
- [ ] Интеграция с Allure для красивых test reports
