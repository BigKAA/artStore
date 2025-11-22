# Sprint 22 - Comprehensive Testing & Performance Metrics

## Sprint Goals

**Дата начала**: 2025-11-22
**Приоритет**: 🟡 P1 (Important - Quality & Observability)
**Оценка времени**: 12-16 часов

---

## Executive Summary

Sprint 22 фокусируется на comprehensive testing и performance observability для завершения production-readiness Ingester Module:

1. **Unit Testing**: 90%+ coverage для AuthService и tls_utils (18+ tests)
2. **Integration Testing**: E2E mTLS scenarios и full upload workflow
3. **Performance Metrics**: JWT validation tracking и latency measurement
4. **Quality Validation**: Coverage reports и test infrastructure validation

**Обоснование приоритета**: Sprint 21 реализовал core authentication и security features, но без comprehensive testing. Sprint 22 завершает quality assurance для production deployment.

---

## Sprint 21 Context

### Завершенные функции
- ✅ AuthService (OAuth 2.0 Client Credentials authentication)
- ✅ tls_utils.py (centralized mTLS configuration)
- ✅ Token caching с automatic refresh
- ✅ HTTP/2 support
- ✅ Code duplication eliminated (89% reduction)

### Technical Debt from Sprint 21
- ⏳ **Unit Tests**: AuthService и tls_utils не покрыты тестами
- ⏳ **Integration Tests**: E2E mTLS scenarios не валидированы
- ⏳ **Performance Metrics**: Нет tracking для JWT validation latency

**Sprint 22 Objective**: Eliminate all testing debt и add performance observability.

---

## Phase 1: Unit Tests for AuthService (5-6 hours)

### Objectives
Comprehensive unit test coverage для `ingester-module/app/services/auth_service.py` с target 90%+ coverage.

### Test Categories

#### 1. Token Acquisition Success Scenarios (3 tests)

**File**: `ingester-module/tests/unit/test_auth_service.py`

```python
"""Unit tests for AuthService."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.auth_service import AuthService
from app.core.exceptions import AuthenticationException


@pytest.fixture
def auth_service():
    """Create AuthService instance for testing."""
    return AuthService(
        admin_module_url="http://test-admin:8000",
        client_id="test_client_id",
        client_secret="test_secret",
        timeout=10
    )


@pytest.mark.asyncio
async def test_get_access_token_success(auth_service):
    """Test successful token acquisition from Admin Module."""
    # Mock HTTP response
    mock_response = AsyncMock()
    mock_response.json.return_value = {
        "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
        "token_type": "Bearer",
        "expires_in": 1800
    }
    mock_response.raise_for_status = AsyncMock()

    # Mock HTTP client
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch.object(auth_service, '_get_client', return_value=mock_client):
        token = await auth_service.get_access_token()

        # Verify token returned
        assert token == "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."

        # Verify token cached
        assert auth_service._access_token == token
        assert auth_service._token_expires_at is not None

        # Verify HTTP call made
        mock_client.post.assert_called_once_with(
            "/api/v1/auth/token",
            json={
                "client_id": "test_client_id",
                "client_secret": "test_secret"
            },
            headers={"Content-Type": "application/json"}
        )


@pytest.mark.asyncio
async def test_get_access_token_uses_cache_when_valid(auth_service):
    """Test that cached token is reused when still valid."""
    # Set cached token (expires in 10 minutes - valid)
    auth_service._access_token = "cached_token_12345"
    auth_service._token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    # Mock HTTP client (should NOT be called)
    mock_client = AsyncMock()
    mock_client.post = AsyncMock()

    with patch.object(auth_service, '_get_client', return_value=mock_client):
        token = await auth_service.get_access_token()

        # Verify cached token returned
        assert token == "cached_token_12345"

        # Verify NO HTTP call made
        mock_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_get_access_token_refreshes_when_expiring_soon(auth_service):
    """Test token refresh when cached token expires in <5 minutes."""
    # Set cached token (expires in 3 minutes - invalid due to 5min threshold)
    auth_service._access_token = "old_token"
    auth_service._token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=3)

    # Mock HTTP response with new token
    mock_response = AsyncMock()
    mock_response.json.return_value = {
        "access_token": "new_token_67890",
        "expires_in": 1800
    }
    mock_response.raise_for_status = AsyncMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch.object(auth_service, '_get_client', return_value=mock_client):
        token = await auth_service.get_access_token()

        # Verify new token returned
        assert token == "new_token_67890"

        # Verify HTTP call made for refresh
        mock_client.post.assert_called_once()
```

#### 2. Error Handling Tests (4 tests)

```python
@pytest.mark.asyncio
async def test_get_access_token_http_401_error(auth_service):
    """Test authentication failure with HTTP 401 Unauthorized."""
    import httpx

    # Mock HTTP 401 response
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.text = "Invalid credentials"

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "Unauthorized",
            request=MagicMock(),
            response=mock_response
        )
    )

    with patch.object(auth_service, '_get_client', return_value=mock_client):
        with pytest.raises(AuthenticationException) as exc_info:
            await auth_service.get_access_token()

        # Verify exception message
        assert "Failed to authenticate" in str(exc_info.value)
        assert "401" in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_access_token_connection_error(auth_service):
    """Test Admin Module connection failure."""
    import httpx

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(
        side_effect=httpx.ConnectError("Connection refused")
    )

    with patch.object(auth_service, '_get_client', return_value=mock_client):
        with pytest.raises(AuthenticationException) as exc_info:
            await auth_service.get_access_token()

        # Verify exception message
        assert "Cannot connect to Admin Module" in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_access_token_invalid_response_missing_token(auth_service):
    """Test invalid response from Admin Module (missing access_token)."""
    mock_response = AsyncMock()
    mock_response.json.return_value = {
        "token_type": "Bearer",
        "expires_in": 1800
        # Missing "access_token" field!
    }
    mock_response.raise_for_status = AsyncMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch.object(auth_service, '_get_client', return_value=mock_client):
        with pytest.raises(AuthenticationException) as exc_info:
            await auth_service.get_access_token()

        # Verify exception message
        assert "Invalid token response" in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_access_token_invalid_json_response(auth_service):
    """Test invalid JSON response from Admin Module."""
    mock_response = AsyncMock()
    mock_response.json.side_effect = ValueError("Invalid JSON")
    mock_response.raise_for_status = AsyncMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch.object(auth_service, '_get_client', return_value=mock_client):
        with pytest.raises(AuthenticationException):
            await auth_service.get_access_token()
```

#### 3. Token Lifecycle Tests (3 tests)

```python
def test_is_token_valid_with_no_token(auth_service):
    """Test token validation when no token cached."""
    assert auth_service._is_token_valid() is False


def test_is_token_valid_with_expired_token(auth_service):
    """Test token validation when token expired."""
    auth_service._access_token = "expired_token"
    auth_service._token_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)

    assert auth_service._is_token_valid() is False


def test_is_token_valid_with_expiring_soon_token(auth_service):
    """Test token validation when token expires in <5 minutes."""
    auth_service._access_token = "expiring_soon_token"
    # Expires in 4 minutes - below 5 minute threshold
    auth_service._token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=4)

    assert auth_service._is_token_valid() is False


def test_is_token_valid_with_valid_token(auth_service):
    """Test token validation when token still valid (>5 min to expiry)."""
    auth_service._access_token = "valid_token"
    # Expires in 10 minutes - above 5 minute threshold
    auth_service._token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    assert auth_service._is_token_valid() is True
```

#### 4. Resource Management Tests (2 tests)

```python
@pytest.mark.asyncio
async def test_close_cleanup(auth_service):
    """Test proper cleanup on close."""
    # Setup cached token and client
    auth_service._access_token = "test_token"
    auth_service._token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    mock_client = AsyncMock()
    auth_service._client = mock_client

    # Call close
    await auth_service.close()

    # Verify cleanup
    assert auth_service._access_token is None
    assert auth_service._token_expires_at is None
    mock_client.aclose.assert_called_once()


@pytest.mark.asyncio
async def test_get_client_creates_client_once(auth_service):
    """Test HTTP client created only once and reused."""
    client1 = auth_service._get_client()
    client2 = auth_service._get_client()

    # Verify same instance returned
    assert client1 is client2
```

### Coverage Target

**Minimum**: 90% statement coverage для `auth_service.py`

**Expected Coverage**:
- Statements: 95%+
- Branches: 90%+
- Functions: 100%

---

## Phase 2: Unit Tests for tls_utils (2-3 hours)

### Objectives
Comprehensive unit test coverage для `ingester-module/app/core/tls_utils.py`.

### Test Categories

**File**: `ingester-module/tests/unit/test_tls_utils.py`

```python
"""Unit tests for TLS utilities."""

import pytest
import ssl
from unittest.mock import patch, MagicMock
from pathlib import Path

from app.core.tls_utils import create_ssl_context
from app.core.config import settings


@pytest.fixture
def mock_tls_enabled():
    """Mock TLS enabled configuration."""
    with patch.object(settings.tls, 'enabled', True), \
         patch.object(settings.tls, 'ca_cert_file', '/test/ca.pem'), \
         patch.object(settings.tls, 'cert_file', '/test/cert.pem'), \
         patch.object(settings.tls, 'key_file', '/test/key.pem'), \
         patch.object(settings.tls, 'protocol_version', 'TLSv1.3'), \
         patch.object(settings.tls, 'ciphers', 'TLS_AES_256_GCM_SHA384'):
        yield


@pytest.fixture
def mock_tls_disabled():
    """Mock TLS disabled configuration."""
    with patch.object(settings.tls, 'enabled', False):
        yield


def test_create_ssl_context_returns_none_when_tls_disabled(mock_tls_disabled):
    """Test SSL context creation returns None when TLS disabled."""
    ssl_context = create_ssl_context()

    assert ssl_context is None


def test_create_ssl_context_creates_context_when_tls_enabled(mock_tls_enabled):
    """Test SSL context created when TLS enabled."""
    with patch('ssl.create_default_context') as mock_create, \
         patch('ssl.SSLContext.load_verify_locations') as mock_load_ca, \
         patch('ssl.SSLContext.load_cert_chain') as mock_load_cert:

        mock_context = MagicMock()
        mock_create.return_value = mock_context

        ssl_context = create_ssl_context()

        # Verify context created
        assert ssl_context is not None
        mock_create.assert_called_once_with(ssl.Purpose.SERVER_AUTH)

        # Verify CA cert loaded
        mock_load_ca.assert_called_once_with(cafile='/test/ca.pem')

        # Verify client cert loaded
        mock_load_cert.assert_called_once_with(
            certfile='/test/cert.pem',
            keyfile='/test/key.pem'
        )


def test_create_ssl_context_sets_tls13_minimum_version(mock_tls_enabled):
    """Test TLS 1.3 minimum version configured."""
    with patch('ssl.create_default_context') as mock_create, \
         patch('ssl.SSLContext.load_verify_locations'), \
         patch('ssl.SSLContext.load_cert_chain'):

        mock_context = MagicMock()
        mock_create.return_value = mock_context

        create_ssl_context()

        # Verify TLS 1.3 minimum version set
        assert mock_context.minimum_version == ssl.TLSVersion.TLSv1_3


def test_create_ssl_context_sets_tls12_minimum_version():
    """Test TLS 1.2 minimum version configured."""
    with patch.object(settings.tls, 'enabled', True), \
         patch.object(settings.tls, 'protocol_version', 'TLSv1.2'), \
         patch('ssl.create_default_context') as mock_create, \
         patch('ssl.SSLContext.load_verify_locations'), \
         patch('ssl.SSLContext.load_cert_chain'):

        mock_context = MagicMock()
        mock_create.return_value = mock_context

        create_ssl_context()

        # Verify TLS 1.2 minimum version set
        assert mock_context.minimum_version == ssl.TLSVersion.TLSv1_2


def test_create_ssl_context_sets_ciphers(mock_tls_enabled):
    """Test cipher suites configuration."""
    with patch('ssl.create_default_context') as mock_create, \
         patch('ssl.SSLContext.load_verify_locations'), \
         patch('ssl.SSLContext.load_cert_chain'):

        mock_context = MagicMock()
        mock_create.return_value = mock_context

        create_ssl_context()

        # Verify ciphers set
        mock_context.set_ciphers.assert_called_once_with('TLS_AES_256_GCM_SHA384')


def test_create_ssl_context_handles_invalid_ciphers(mock_tls_enabled):
    """Test graceful handling of invalid cipher suites."""
    with patch('ssl.create_default_context') as mock_create, \
         patch('ssl.SSLContext.load_verify_locations'), \
         patch('ssl.SSLContext.load_cert_chain'):

        mock_context = MagicMock()
        mock_context.set_ciphers.side_effect = ssl.SSLError("Invalid cipher")
        mock_create.return_value = mock_context

        # Should not raise exception - falls back to defaults
        ssl_context = create_ssl_context()

        assert ssl_context is not None


def test_create_ssl_context_logs_warning_when_no_ca_cert():
    """Test warning logged when CA certificate missing."""
    with patch.object(settings.tls, 'enabled', True), \
         patch.object(settings.tls, 'ca_cert_file', ''), \
         patch.object(settings.tls, 'cert_file', '/test/cert.pem'), \
         patch.object(settings.tls, 'key_file', '/test/key.pem'), \
         patch('ssl.create_default_context') as mock_create:

        mock_context = MagicMock()
        mock_create.return_value = mock_context

        with patch('app.core.tls_utils.logger') as mock_logger:
            create_ssl_context()

            # Verify warning logged
            mock_logger.warning.assert_called()
            warning_msg = mock_logger.warning.call_args[0][0]
            assert "No CA certificate" in warning_msg
```

### Coverage Target

**Minimum**: 85% statement coverage для `tls_utils.py`

**Expected Coverage**:
- Statements: 90%+
- Branches: 85%+
- Functions: 100%

---

## Phase 3: Integration Tests (3-4 hours)

### Objectives
E2E validation для mTLS communication и full upload workflow.

### Test Scenarios

**File**: `ingester-module/tests/integration/test_mtls_integration.py`

```python
"""E2E integration tests for mTLS communication."""

import pytest
from pathlib import Path

from app.services.auth_service import AuthService
from app.services.upload_service import UploadService
from app.core.config import settings


@pytest.mark.integration
@pytest.mark.asyncio
async def test_auth_service_connects_to_admin_module():
    """Test AuthService successfully connects to Admin Module (with or without mTLS)."""
    auth_service = AuthService(
        admin_module_url=settings.service_account.admin_module_url,
        client_id=settings.service_account.client_id,
        client_secret=settings.service_account.client_secret,
        timeout=settings.service_account.timeout
    )

    try:
        # Attempt to get access token
        token = await auth_service.get_access_token()

        # Verify token obtained
        assert token is not None
        assert len(token) > 0
        assert token.startswith("eyJ")  # JWT token starts with eyJ

        # Verify token cached
        assert auth_service._access_token == token
        assert auth_service._token_expires_at is not None

    finally:
        await auth_service.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_upload_service_with_mtls_if_enabled():
    """Test UploadService can connect to Storage Element with mTLS if enabled."""
    auth_service = AuthService(
        admin_module_url=settings.service_account.admin_module_url,
        client_id=settings.service_account.client_id,
        client_secret=settings.service_account.client_secret
    )
    upload_service = UploadService(auth_service=auth_service)

    try:
        # Test connection establishment (doesn't upload, just validates mTLS setup)
        client = await upload_service._get_client()

        # Verify client created
        assert client is not None
        assert client.base_url == settings.storage_element.base_url

    finally:
        await upload_service.close()
        await auth_service.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_upload_workflow_with_authentication():
    """Test complete file upload workflow: auth → upload → verify."""
    from io import BytesIO
    from fastapi import UploadFile
    from app.schemas.upload import UploadRequest, StorageMode

    auth_service = AuthService(
        admin_module_url=settings.service_account.admin_module_url,
        client_id=settings.service_account.client_id,
        client_secret=settings.service_account.client_secret
    )
    upload_service = UploadService(auth_service=auth_service)

    try:
        # Create test file
        test_content = b"Sprint 22 Integration Test Content"
        test_file = UploadFile(
            filename="sprint22_test.txt",
            file=BytesIO(test_content)
        )

        # Create upload request
        upload_request = UploadRequest(
            description="Sprint 22 integration test",
            storage_mode=StorageMode.edit,
            compress=False
        )

        # Perform upload
        result = await upload_service.upload_file(
            file=test_file,
            request=upload_request,
            user_id="test_user_sprint22",
            username="test_user"
        )

        # Verify upload successful
        assert result is not None
        assert result.file_id is not None
        assert result.original_filename == "sprint22_test.txt"
        assert result.file_size == len(test_content)

    finally:
        await upload_service.close()
        await auth_service.close()
```

### Docker Test Environment

Reuse existing Docker test infrastructure from Sprint 11:
- `ingester-module/docker-compose.test.yml`
- Test PostgreSQL (port 5433)
- Test Redis (port 6380)
- Mock Admin Module и Storage Element

---

## Phase 4: Performance Metrics (2-3 hours)

### Objectives
Track JWT validation latency и authentication performance metrics.

### Implementation

**File**: `ingester-module/app/core/metrics.py` (NEW)

```python
"""Performance metrics tracking for Ingester Module."""

import time
import logging
from functools import wraps
from typing import Callable, Any
from prometheus_client import Counter, Histogram

logger = logging.getLogger(__name__)

# JWT Authentication Metrics
jwt_validation_total = Counter(
    'ingester_jwt_validation_total',
    'Total JWT validations',
    ['result']  # success, failure, expired
)

jwt_validation_duration = Histogram(
    'ingester_jwt_validation_duration_seconds',
    'JWT validation duration in seconds',
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
)

# OAuth 2.0 Token Acquisition Metrics
oauth_token_requests = Counter(
    'ingester_oauth_token_requests_total',
    'Total OAuth 2.0 token requests',
    ['result']  # success, cache_hit, failure
)

oauth_token_duration = Histogram(
    'ingester_oauth_token_duration_seconds',
    'OAuth 2.0 token acquisition duration in seconds',
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)


def track_jwt_validation(func: Callable) -> Callable:
    """Decorator to track JWT validation performance."""
    @wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        start_time = time.time()
        result_label = "success"

        try:
            result = func(*args, **kwargs)
            return result
        except Exception as e:
            if "expired" in str(e).lower():
                result_label = "expired"
            else:
                result_label = "failure"
            raise
        finally:
            duration = time.time() - start_time
            jwt_validation_total.labels(result=result_label).inc()
            jwt_validation_duration.observe(duration)

            if duration > 0.1:  # Log slow validations
                logger.warning(
                    "Slow JWT validation detected",
                    extra={"duration": duration, "result": result_label}
                )

    return wrapper


def track_oauth_token(func: Callable) -> Callable:
    """Decorator to track OAuth 2.0 token acquisition performance."""
    @wraps(func)
    async def wrapper(self, *args, **kwargs) -> Any:
        # Check if using cached token
        if self._is_token_valid():
            oauth_token_requests.labels(result="cache_hit").inc()
            return await func(self, *args, **kwargs)

        # Token acquisition from Admin Module
        start_time = time.time()
        result_label = "success"

        try:
            result = await func(self, *args, **kwargs)
            return result
        except Exception:
            result_label = "failure"
            raise
        finally:
            duration = time.time() - start_time
            oauth_token_requests.labels(result=result_label).inc()
            oauth_token_duration.observe(duration)

            if duration > 1.0:  # Log slow token acquisition
                logger.warning(
                    "Slow OAuth token acquisition",
                    extra={"duration": duration, "result": result_label}
                )

    return wrapper
```

**Integration with AuthService**:

```python
# In app/services/auth_service.py
from app.core.metrics import track_oauth_token

class AuthService:
    @track_oauth_token
    async def get_access_token(self) -> str:
        # Existing implementation...
        pass
```

### Metrics Validation

Run load test to verify metrics collection:

```bash
# Generate load
for i in {1..100}; do
    curl -X POST http://localhost:8020/api/v1/files/upload \
        -H "Authorization: Bearer $TOKEN" \
        -F "file=@test.txt"
done

# Check metrics endpoint
curl http://localhost:8020/metrics | grep ingester_oauth
curl http://localhost:8020/metrics | grep ingester_jwt
```

---

## Success Criteria

### Testing Requirements: ✅ Target

- [ ] Unit tests: 90%+ coverage для AuthService
- [ ] Unit tests: 85%+ coverage для tls_utils
- [ ] Integration tests: All E2E scenarios passing
- [ ] Test infrastructure: Docker environment validated
- [ ] Coverage report: Generated and verified

### Performance Metrics: ✅ Target

- [ ] OAuth token metrics: Tracked (requests, duration, cache hits)
- [ ] JWT validation metrics: Tracked (validations, duration, results)
- [ ] Prometheus metrics: Exposed at /metrics endpoint
- [ ] Performance baseline: Established для future optimization

### Documentation: ✅ Target

- [ ] Sprint 22 completion summary
- [ ] Test coverage report
- [ ] Performance metrics guide
- [ ] Testing best practices documentation

---

## Implementation Checklist

### Phase 1: AuthService Unit Tests (Day 1)
- [ ] Create `tests/unit/test_auth_service.py`
- [ ] Implement token acquisition tests (3 tests)
- [ ] Implement error handling tests (4 tests)
- [ ] Implement token lifecycle tests (4 tests)
- [ ] Implement resource management tests (2 tests)
- [ ] Run: `pytest tests/unit/test_auth_service.py -v --cov=app.services.auth_service`
- [ ] Verify: Coverage >90%

### Phase 2: tls_utils Unit Tests (Day 1)
- [ ] Create `tests/unit/test_tls_utils.py`
- [ ] Implement SSL context creation tests (6+ tests)
- [ ] Run: `pytest tests/unit/test_tls_utils.py -v --cov=app.core.tls_utils`
- [ ] Verify: Coverage >85%

### Phase 3: Integration Tests (Day 2)
- [ ] Create `tests/integration/test_mtls_integration.py`
- [ ] Implement auth connection test
- [ ] Implement upload service mTLS test
- [ ] Implement full upload workflow test
- [ ] Verify Docker test environment
- [ ] Run: `pytest tests/integration/ -v --tb=short`

### Phase 4: Performance Metrics (Day 2)
- [ ] Create `app/core/metrics.py`
- [ ] Implement OAuth token metrics
- [ ] Implement JWT validation metrics
- [ ] Integrate decorators with AuthService
- [ ] Verify metrics endpoint
- [ ] Run load test validation

### Phase 5: Documentation & Validation (Day 2)
- [ ] Generate coverage report: `pytest --cov --cov-report=html`
- [ ] Create Sprint 22 completion summary
- [ ] Document testing best practices
- [ ] Git commit with detailed changelog

---

## Technical Risks and Mitigations

### Risk 1: Test Environment Complexity
**Severity**: 🟡 Medium
**Impact**: Testing blocked если Docker environment fails

**Mitigation**:
- Reuse proven Sprint 11 Docker test infrastructure
- Fallback на unit tests если integration tests blocked
- Document troubleshooting steps

### Risk 2: Coverage Targets Too Aggressive
**Severity**: 🟢 Low
**Impact**: Sprint延期 if 90% unreachable

**Mitigation**:
- Focus on critical paths first
- Accept 85% if 90% requires excessive effort
- Document uncovered edge cases for future

### Risk 3: Performance Metrics Overhead
**Severity**: 🟢 Low
**Impact**: Metrics collection adds latency

**Mitigation**:
- Use lightweight Prometheus client
- Metrics collection <1ms overhead
- Validate performance impact с load testing

---

## Out of Scope (Deferred)

❌ **NOT in Sprint 22**:
- Redis caching для validated tokens (Sprint 23)
- Automated JWT key rotation (Sprint 23)
- OpenTelemetry distributed tracing (Sprint 24)
- Grafana dashboards (Sprint 24)
- Load testing и benchmarking (Sprint 24)

---

## Expected Outcomes

✅ **Comprehensive Test Coverage**:
- AuthService: 90%+ coverage
- tls_utils: 85%+ coverage
- Integration tests: E2E scenarios validated

✅ **Performance Observability**:
- OAuth token metrics tracked
- JWT validation metrics tracked
- Prometheus metrics exposed

✅ **Production Confidence**:
- Core functionality thoroughly tested
- Performance baseline established
- Quality gates enforced

---

**Implementation by**: Claude Code
**Sprint**: 22 - Testing & Performance Metrics
**Status**: 📋 PLANNED - Ready for Implementation
