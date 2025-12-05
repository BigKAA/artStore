# Ingester Module - Testing Infrastructure

## Overview

Комплексная инфраструктура тестирования для Ingester Module с изолированным test environment.

## Test Structure

```
tests/
├── unit/                    # Unit тесты (47 tests)
│   ├── test_schemas.py     # Pydantic schema validation (24 tests)
│   ├── test_security.py    # JWT authentication (19 tests)
│   └── test_upload_service.py  # Service layer (4 tests)
├── integration/            # Integration тесты (future)
│   ├── test_upload_flow.py
│   ├── test_auth_flow.py
│   └── test_storage_communication.py
├── mocks/                  # Mock configurations
│   ├── admin-mock.json    # Mock Admin Module responses
│   └── storage-mock.json  # Mock Storage Element responses
├── conftest.py            # Shared pytest fixtures
└── README.md             # This file
```

## Quick Start

### 1. Unit Tests (Local)

Запуск unit тестов в локальном virtual environment:

```bash
# Активация venv
source /home/artur/Projects/artStore/.venv/bin/activate

# Запуск всех unit тестов
pytest tests/unit/ -v

# Запуск с coverage report
pytest tests/unit/ -v --cov=app --cov-report=html --cov-report=term

# Запуск отдельного test suite
pytest tests/unit/test_schemas.py -v
pytest tests/unit/test_security.py -v
pytest tests/unit/test_upload_service.py -v
```

### 2. Unit Tests (Docker)

Запуск тестов в изолированном Docker окружении:

```bash
# Build and run test environment
docker-compose -f docker-compose.test.yml up --build test-runner

# View test logs
docker-compose -f docker-compose.test.yml logs -f test-runner

# Cleanup
docker-compose -f docker-compose.test.yml down -v
```

### 3. Integration Tests (Future)

Запуск integration тестов с mock сервисами:

```bash
# Start all services including mocks
docker-compose -f docker-compose.test.yml --profile integration up --build

# Run integration tests only
pytest tests/integration/ -v

# Cleanup
docker-compose -f docker-compose.test.yml --profile integration down -v
```

## Test Environment Configuration

### Isolated Test Database

- **Host**: `postgres-test` (container) или `localhost:5433` (host)
- **User**: `test_user`
- **Password**: `test_password`
- **Database**: `ingester_test`

### Isolated Test Redis

- **Host**: `redis-test` (container) или `localhost:6380` (host)
- **Port**: 6379 (container) или 6380 (host)

### Mock Services

#### Mock Admin Module
- **URL**: `http://mock-admin:8000` (container) или `http://localhost:8001` (host)
- **Config**: `tests/mocks/admin-mock.json`
- **Endpoints**:
  - `POST /api/v1/auth/token` - OAuth 2.0 authentication
  - `GET /api/v1/internal/storage-elements/available` - Storage element list

#### Mock Storage Element
- **URL**: `http://mock-storage:8010` (container) или `http://localhost:8011` (host)
- **Config**: `tests/mocks/storage-mock.json`
- **Endpoints**:
  - `POST /api/v1/files/upload` - File upload
  - `DELETE /api/v1/files/{file_id}` - File deletion
  - `GET /health/live` - Health check (Sprint 16: стандартизированный путь)

## Current Test Status

### ✅ Unit Tests (100% Passing)

- **Total**: 47 tests
- **Schemas**: 24/24 ✅
- **Security**: 19/19 ✅
- **Upload Service**: 4/4 ✅
- **Execution Time**: ~0.58s
- **Coverage**: TBD (will be measured with full test suite)

### 🚧 Integration Tests (Planned)

- Upload workflow E2E
- JWT authentication flow
- Storage Element communication
- Error handling scenarios
- Performance benchmarks

## Test Fixtures

### Available Fixtures (conftest.py)

- `async_client` - FastAPI AsyncClient для API тестирования
- `auth_headers` - Pre-configured Authorization headers
- `test_file` - Temporary test file for upload tests
- `db_session` - Database session для integration tests
- `redis_client` - Redis client для integration tests

## Writing Tests

### Unit Test Example

```python
import pytest
from app.schemas.upload import UploadRequest, StorageMode

class TestUploadRequest:
    def test_upload_request_minimal(self):
        """Минимальный валидный UploadRequest."""
        request = UploadRequest()

        assert request.description is None
        assert request.storage_mode == StorageMode.EDIT
        assert request.compress is False
```

### Integration Test Example (Future)

```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_upload_file_flow(async_client: AsyncClient, auth_headers: dict):
    """E2E тест загрузки файла."""
    files = {"file": ("test.txt", b"test content", "text/plain")}

    response = await async_client.post(
        "/api/v1/upload",
        files=files,
        headers=auth_headers
    )

    assert response.status_code == 200
    data = response.json()
    assert data["original_filename"] == "test.txt"
```

## Coverage Requirements

### Target Metrics
- **Overall Coverage**: >80%
- **Critical Paths**: >90% (auth, upload, validation)
- **New Code**: 100% (all new features must have tests)

### Generating Coverage Report

```bash
# Terminal report
pytest tests/unit/ --cov=app --cov-report=term

# HTML report
pytest tests/unit/ --cov=app --cov-report=html

# Open HTML report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
start htmlcov/index.html  # Windows
```

## CI/CD Integration (Future)

### GitHub Actions Workflow

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run tests
        run: docker-compose -f docker-compose.test.yml up --build --exit-code-from test-runner
```

### Pre-commit Hooks

```bash
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

## Troubleshooting

### Test Database Connection Issues

```bash
# Check database is running
docker-compose -f docker-compose.test.yml ps postgres-test

# Check database logs
docker-compose -f docker-compose.test.yml logs postgres-test

# Reset database
docker-compose -f docker-compose.test.yml down -v
docker-compose -f docker-compose.test.yml up -d postgres-test
```

### Test Redis Connection Issues

```bash
# Check Redis is running
docker-compose -f docker-compose.test.yml ps redis-test

# Test Redis connection
docker exec ingester-test-redis redis-cli ping
```

### Mock Services Not Responding

```bash
# Check mock services
docker-compose -f docker-compose.test.yml --profile integration ps

# Restart mocks
docker-compose -f docker-compose.test.yml --profile integration restart mock-admin mock-storage
```

## Best Practices

### 1. Test Isolation
- Каждый тест должен быть независимым
- Используйте fixtures для setup/teardown
- Не полагайтесь на порядок выполнения тестов

### 2. Test Naming
- `test_<feature>_<scenario>_<expected_result>`
- Пример: `test_upload_request_invalid_mode_raises_validation_error`

### 3. Test Documentation
- Используйте docstrings для объяснения сложных тестов
- Комментируйте нетривиальные assertions
- Группируйте связанные тесты в классы

### 4. Async Testing
- Всегда используйте `@pytest.mark.asyncio` для async tests
- Используйте `async_client` fixture для API тестов
- Properly cleanup async resources (await close())

### 5. Mocking
- Mock external dependencies (Admin Module, Storage Element)
- Mock time-dependent operations (datetime.now())
- Don't mock code under test

## Performance Benchmarks

### Current Performance
- **Unit Tests**: ~0.58s total (~12ms per test)
- **Fastest Test**: ~5ms (enum validations)
- **Slowest Test**: ~50ms (JWT cryptography operations)

### Performance Targets
- **Unit Tests**: <1s total
- **Integration Tests**: <10s total
- **Full Test Suite**: <30s total

## Next Steps

1. ✅ Unit test infrastructure complete (47/47 passing)
2. 🚧 Create integration tests directory structure
3. 🚧 Implement E2E upload workflow tests
4. 🚧 Add JWT authentication integration tests
5. 🚧 Implement performance benchmarks
6. 🚧 Set up CI/CD pipeline
7. 🚧 Add property-based testing (Hypothesis)
8. 🚧 Measure and improve code coverage (>80% target)

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [Coverage.py](https://coverage.readthedocs.io/)
- [MockServer](https://www.mock-server.com/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
