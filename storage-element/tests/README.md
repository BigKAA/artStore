# Storage Element - Test Suite

Comprehensive test suite for Storage Element module using pytest framework.

## Test Structure

```
tests/
├── __init__.py
├── conftest.py              # Shared fixtures and configuration
├── README.md                # This file
├── unit/                    # Unit tests (fast, isolated)
│   ├── __init__.py
│   ├── test_file_naming.py  # File naming utilities
│   ├── test_attr_utils.py   # Attribute file operations
│   ├── test_security.py     # JWT authentication
│   ├── test_wal_service.py  # Write-Ahead Log service
│   ├── test_storage_service.py  # Storage operations
│   └── test_file_service.py     # File management service
└── integration/             # Integration tests (slower, requires infrastructure)
    ├── __init__.py
    ├── test_api_files.py    # API endpoints testing
    └── test_file_flow.py    # End-to-end file operations
```

## Running Tests

### Prerequisites

Ensure all test dependencies are installed:

```bash
# Activate virtual environment
source /home/artur/Projects/artStore/.venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Basic Test Execution

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/unit/test_file_naming.py

# Run specific test class
pytest tests/unit/test_file_naming.py::TestGenerateStorageFilename

# Run specific test function
pytest tests/unit/test_file_naming.py::TestGenerateStorageFilename::test_generate_basic_filename
```

### Test Filtering

```bash
# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Skip slow tests
pytest -m "not slow"

# Run unit tests excluding integration
pytest tests/unit/
```

### Coverage Reports

```bash
# Run with coverage report
pytest --cov=app

# Generate HTML coverage report
pytest --cov=app --cov-report=html
# Open htmlcov/index.html in browser

# Generate XML coverage report (for CI/CD)
pytest --cov=app --cov-report=xml

# Coverage with missing lines
pytest --cov=app --cov-report=term-missing
```

### Parallel Execution

```bash
# Run tests in parallel (auto-detect CPU count)
pytest -n auto

# Run tests on 4 workers
pytest -n 4
```

### Debugging Tests

```bash
# Verbose output
pytest -v

# Extra verbose with captured output
pytest -vv -s

# Stop on first failure
pytest -x

# Drop into debugger on failures
pytest --pdb

# Show local variables in tracebacks
pytest -l
```

## Test Categories

### Unit Tests (`-m unit`)

Fast, isolated tests that don't require external dependencies:

- **test_file_naming.py**: File naming conventions and parsing
  - Sanitization of filenames
  - Storage filename generation
  - Path generation
  - Filename parsing

- **test_attr_utils.py**: Attribute file operations
  - Atomic write operations
  - File reading and validation
  - Consistency verification
  - Size limits (4KB)

- **test_security.py**: Authentication and security
  - JWT token validation
  - User authentication
  - Permission checks

- **test_wal_service.py**: Write-Ahead Log
  - Transaction logging
  - Recovery mechanisms
  - Atomic operations

- **test_storage_service.py**: Storage operations
  - Local/S3 storage abstraction
  - File CRUD operations
  - Path management

- **test_file_service.py**: File management
  - File metadata handling
  - Upload/download logic
  - Checksum validation

### Integration Tests (`-m integration`)

Tests requiring infrastructure (database, Redis, storage):

- **test_api_files.py**: API endpoint testing
  - File upload endpoints
  - File download endpoints
  - File search endpoints
  - File deletion endpoints

- **test_file_flow.py**: End-to-end workflows
  - Complete upload → store → retrieve flow
  - Multiple file operations
  - Error handling scenarios

## Writing New Tests

### Test Naming Conventions

```python
# Test file names
test_<module_name>.py

# Test class names
class Test<Feature>:
    ...

# Test function names
def test_<feature>_<scenario>():
    ...
```

### Using Fixtures

```python
import pytest

def test_example(async_session, temp_storage_dir, test_jwt_token):
    """
    Example test using fixtures from conftest.py

    Args:
        async_session: Database session
        temp_storage_dir: Temporary storage directory
        test_jwt_token: Valid JWT token
    """
    # Your test code here
    pass
```

### Async Tests

```python
import pytest

@pytest.mark.asyncio
async def test_async_operation():
    """Test async operation"""
    result = await some_async_function()
    assert result is not None
```

### Marking Tests

```python
import pytest

@pytest.mark.unit
def test_unit_example():
    """Fast unit test"""
    pass

@pytest.mark.integration
async def test_integration_example():
    """Integration test requiring infrastructure"""
    pass

@pytest.mark.slow
def test_slow_operation():
    """Test that takes significant time"""
    pass
```

## Available Fixtures

### Database Fixtures

- **async_engine**: SQLAlchemy async engine (in-memory SQLite)
- **async_session**: Async database session
- **sample_file_metadata**: Pre-created FileMetadata record
- **sample_storage_config**: Pre-created StorageConfig record

### Storage Fixtures

- **temp_storage_dir**: Temporary directory for file tests
- **sample_file_content**: Sample file content (bytes)
- **sample_file**: Pre-created sample file

### Authentication Fixtures

- **test_jwt_keys**: RSA key pair (private, public)
- **test_jwt_token**: Valid user JWT token
- **admin_jwt_token**: Valid admin JWT token
- **auth_headers**: Headers with user Bearer token
- **admin_auth_headers**: Headers with admin Bearer token

### Client Fixtures

- **client**: FastAPI TestClient (sync)
- **async_client**: HTTPX AsyncClient (async)

### Mock Fixtures

- **mock_redis**: Mock Redis client

## Coverage Requirements

**Minimum coverage threshold: 80%**

Coverage is configured in `pytest.ini`:

```ini
[pytest]
addopts =
    --cov=app
    --cov-fail-under=80
    --cov-branch
```

### Coverage Exclusions

Lines excluded from coverage (see `pytest.ini`):

- `pragma: no cover` comments
- Debug/repr methods
- Abstract methods
- Main entry points
- TYPE_CHECKING blocks

## Continuous Integration

### Local CI Check

Run the same checks as CI:

```bash
# Run all tests with coverage
pytest --cov=app --cov-fail-under=80

# Check for warnings
pytest -W error

# Run with strict markers
pytest --strict-markers
```

### Docker Testing

```bash
# Build test image
docker-compose -f docker-compose.test.yml build

# Run tests in Docker
docker-compose -f docker-compose.test.yml up --abort-on-container-exit

# Cleanup
docker-compose -f docker-compose.test.yml down
```

## Troubleshooting

### Common Issues

**Issue**: `pytest: command not found`
```bash
# Solution: Activate venv
source /home/artur/Projects/artStore/.venv/bin/activate
```

**Issue**: `ModuleNotFoundError: No module named 'app'`
```bash
# Solution: Run from project root
cd /home/artur/Projects/artStore/storage-element
pytest
```

**Issue**: Tests hang or timeout
```bash
# Solution: Use timeout marker or option
pytest --timeout=30
```

**Issue**: Database connection errors in tests
```bash
# Solution: Tests use in-memory SQLite, check fixtures
# Ensure async_engine fixture is used correctly
```

## Best Practices

1. **Keep tests fast**: Unit tests should run in milliseconds
2. **Isolate tests**: Each test should be independent
3. **Use fixtures**: Leverage conftest.py for common setup
4. **Clear assertions**: Use descriptive assertion messages
5. **Test edge cases**: Include boundary conditions and error cases
6. **Mock external dependencies**: Use mocks for Redis, S3, etc.
7. **Async consistency**: Use `@pytest.mark.asyncio` for async tests
8. **Cleanup**: Fixtures handle cleanup automatically
9. **Documentation**: Add docstrings to complex tests
10. **Coverage**: Aim for >80%, focus on critical paths

## Resources

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio Documentation](https://pytest-asyncio.readthedocs.io/)
- [pytest-cov Documentation](https://pytest-cov.readthedocs.io/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [SQLAlchemy Testing](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#joining-a-session-into-an-external-transaction-such-as-for-test-suites)

## Questions?

For questions or issues with tests, refer to:
- [CLAUDE.md](../CLAUDE.md) - Project development guidelines
- [README.md](../README.md) - Storage Element documentation
- [TECHNICAL_DEBT.md](../TECHNICAL_DEBT.md) - Known testing gaps
