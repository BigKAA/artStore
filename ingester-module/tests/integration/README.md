# Integration Tests - Ingester Module

## Overview

Комплексные интеграционные тесты для Ingester Module, проверяющие E2E workflows и взаимодействие между компонентами.

## Test Structure

### Test Files

#### `test_upload_flow.py` (10 tests)
E2E тесты для полного workflow загрузки файлов:
- ✅ Successful upload with authentication
- ✅ Upload without authentication (401)
- ✅ Upload with invalid token (401)
- ✅ Upload with metadata
- ✅ Large file upload (>1MB)
- ✅ Empty file upload (422)
- ✅ Multiple sequential uploads
- ✅ Special characters in filename
- ✅ Different file types (PDF, JPG, JSON, Python)
- ✅ Malformed requests (422)

#### `test_auth_flow.py` (12 tests)
JWT authentication flow тесты:
- ✅ Valid JWT allows access (200)
- ✅ Missing auth header denies access (401)
- ✅ Malformed auth header denies access (401)
- ✅ Invalid JWT signature denies access (401)
- ✅ Expired JWT denies access (401)
- ✅ Missing required claims denies access (401)
- ✅ Future nbf (not before) denies access (401)
- ✅ Admin role allows upload (200)
- ✅ User role allows upload (200)
- ✅ Readonly role behavior (200/403)
- ✅ Access token works (200)
- ✅ Refresh token behavior (200/401)

#### `test_storage_communication.py` (15 tests)
HTTP client тесты для Storage Element API:
- ✅ HTTP client configuration
- ✅ Connection pooling (lazy initialization)
- ✅ Close cleanup
- ✅ Timeout configuration
- ✅ Connection error handling
- ✅ 4xx error handling from Storage
- ✅ 5xx error handling from Storage
- ✅ Timeout handling
- ✅ Health check success
- ✅ Health check unavailability detection
- ✅ Retry logic testing
- ✅ Request header validation
- ✅ File metadata propagation

## Running Tests

### Local Execution (Without Mock Services)

```bash
# Activate virtual environment
source /home/artur/Projects/artStore/.venv/bin/activate

# Run all integration tests
pytest tests/integration/ -v

# Run specific test file
pytest tests/integration/test_upload_flow.py -v

# Run with coverage
pytest tests/integration/ --cov=app --cov-report=html
```

**Note**: Some tests require mock services and will fail or skip without them (8/15 passing in test_storage_communication.py).

### Docker Execution (With Mock Services)

```bash
# Run integration tests with mock Admin Module and Storage Element
docker-compose -f docker-compose.test.yml --profile integration up --build

# Or run specific test suite
docker-compose -f docker-compose.test.yml run --rm ingester-test pytest tests/integration/test_upload_flow.py -v
```

## Test Fixtures

### `conftest.py`

Shared fixtures for all integration tests:

**Authentication Fixtures**:
- `rsa_keys` - RSA key pair generation for JWT signing
- `test_jwt_token` - Valid JWT access token
- `auth_headers` - HTTP Authorization headers

**HTTP Client Fixtures**:
- `client` - AsyncClient with ASGITransport for FastAPI app testing

**Mock Service Fixtures**:
- `mock_admin_url` - Mock Admin Module URL (http://mock-admin:8000)
- `mock_storage_url` - Mock Storage Element URL (http://mock-storage:8010)
- `mock_storage_response` - Expected Storage Element response
- `mock_admin_token_response` - Expected Admin Module OAuth 2.0 response

**Test Data Fixtures**:
- `sample_file_content` - Test file bytes
- `sample_multipart_file` - Multipart file dict for uploads

**Configuration Fixtures**:
- `setup_test_keys` - Auto-patches settings.auth.public_key_path for all tests

## Mock Services Configuration

### Mock Admin Module

Located at: `tests/mocks/admin-mock.json`

Endpoints:
- `POST /api/auth/token` - OAuth 2.0 Client Credentials
- Response: `{"access_token": "...", "token_type": "Bearer", "expires_in": 1800}`

### Mock Storage Element

Located at: `tests/mocks/storage-mock.json`

Endpoints:
- `POST /api/v1/files/upload` - File upload
- `GET /api/v1/health/live` - Health check
- Response: File metadata with UUID and storage_filename

## Test Coverage

Integration tests provide E2E coverage for:

### Authentication Layer
- JWT RS256 validation
- Token expiration handling
- Role-based access control
- Authorization header validation

### Upload Service
- File size validation
- HTTP client configuration
- Error handling (connection, timeout, HTTP errors)
- Metadata propagation

### API Endpoints
- Request validation
- Response formatting
- Error responses
- Health checks

## Continuous Integration

Tests are designed for CI/CD pipeline integration:

```yaml
# Example GitHub Actions workflow
- name: Run Integration Tests
  run: |
    docker-compose -f docker-compose.test.yml --profile integration up --build --abort-on-container-exit
    docker-compose -f docker-compose.test.yml down
```

## Troubleshooting

### Tests Failing Without Mock Services

**Symptom**: Tests in `test_storage_communication.py` fail with connection errors.

**Solution**: Run with docker-compose to start mock services:
```bash
docker-compose -f docker-compose.test.yml --profile integration up
```

### AsyncClient Initialization Error

**Symptom**: `TypeError: AsyncClient.__init__() got an unexpected keyword argument 'app'`

**Solution**: Ensure httpx version supports ASGITransport. Update fixture:
```python
from httpx import ASGITransport
transport = ASGITransport(app=app)
async with AsyncClient(transport=transport, base_url="http://test") as ac:
    yield ac
```

### JWT Signature Validation Fails

**Symptom**: All auth tests fail with "Invalid signature"

**Solution**: Verify `setup_test_keys` fixture is active and RSA keys match:
```python
@pytest.fixture(autouse=True)
def setup_test_keys(rsa_keys, monkeypatch):
    monkeypatch.setattr(
        config.settings.auth,
        'public_key_path',
        rsa_keys["public_key_file"]
    )
```

### Timeout Errors

**Symptom**: Tests timeout after 30 seconds.

**Solution**: Check pytest.ini timeout configuration:
```ini
[pytest]
timeout = 30
```

For long-running tests, increase timeout or mark with `@pytest.mark.timeout(60)`.

## Best Practices

1. **Use Fixtures**: Leverage shared fixtures from `conftest.py` for consistency
2. **Test Isolation**: Each test should be independent and not rely on test order
3. **Mock External Services**: Use mock services for Storage Element and Admin Module
4. **Async Testing**: Use `@pytest.mark.asyncio` for all async tests
5. **Clear Assertions**: Use descriptive assertion messages
6. **Error Scenarios**: Test both success and failure paths
7. **Cleanup**: Ensure resources are properly cleaned up (async clients, connections)

## Future Enhancements

- [ ] Performance benchmarks (response time, throughput)
- [ ] Load testing (concurrent uploads)
- [ ] Chaos engineering tests (service failures)
- [ ] Security penetration tests
- [ ] End-to-end workflow tests with real Storage Element

## Contact

For questions about integration tests, contact the development team or check project documentation.
