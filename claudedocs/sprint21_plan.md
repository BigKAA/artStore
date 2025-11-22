# Sprint 21 - AuthService Implementation & mTLS Security Enhancement

## Sprint Goals

**Дата начала**: 2025-11-22
**Приоритет**: 🔴 P0 (Critical - Security & Authentication)
**Оценка времени**: 8-12 часов

---

## Executive Summary

Sprint 21 фокусируется на критических архитектурных улучшениях безопасности и аутентификации для Ingester Module на основе рекомендаций Sprint 20 и требований CLAUDE.md:

1. **AuthService Implementation**: Centralized OAuth 2.0 Client Credentials authentication для Ingester → Storage Element communication
2. **mTLS Security Enhancement**: TLS 1.3 mutual authentication для всех inter-service connections
3. **Comprehensive Testing**: Unit и E2E тесты для новых security компонентов
4. **Production Readiness**: Security hardening для production deployment

**Обоснование приоритета**: Sprint 20 показал, что Ingester Module успешно общается с Storage Element, но использует ХАРДКОДИРОВАННЫЕ credentials и НЕ использует mTLS. Это критический security gap для production deployment.

---

## Sprint 20 Context

### Завершенные функции
- ✅ Unified JWT Schema (admin_user + service_account)
- ✅ Network connectivity (все микросервисы на artstore_network)
- ✅ E2E file upload workflow (JWT → Ingester → Storage Element)
- ✅ Backward compatibility (UserContext property aliases)

### Идентифицированные Gaps
Из анализа кода Ingester Module (`ingester-module/app/services/upload_service.py`):

```python
# ТЕКУЩАЯ РЕАЛИЗАЦИЯ - ПРОБЛЕМЫ:
# 1. НЕТ AuthService - токены должны получаться динамически
# 2. НЕТ mTLS - inter-service communication незащищена
# 3. НЕТ token caching - каждый upload делает Auth request
# 4. НЕТ comprehensive error handling для auth failures

async def upload_file(self, file: UploadFile, ...):
    # TODO: Получить JWT access token для аутентификации
    access_token = await self.auth_service.get_access_token()  # ОТСУТСТВУЕТ!

    # HTTP client БЕЗ mTLS configuration
    client = await self._get_client()  # НЕТ SSL context!
```

### Sprint 20 Recommendations (Prioritized)
1. **🔴 CRITICAL**: AuthService для OAuth 2.0 Client Credentials (Sprint 21)
2. **🔴 CRITICAL**: mTLS для inter-service communication (Sprint 21)
3. **🟡 IMPORTANT**: JWT Validation Metrics (Sprint 22)
4. **🟡 IMPORTANT**: Performance Testing для Pydantic validation (Sprint 22)
5. **🟢 RECOMMENDED**: Redis Caching для validated tokens (Sprint 23)
6. **🟢 RECOMMENDED**: Automated JWT Key Rotation (Sprint 23)

---

## Phase 1: AuthService Implementation (4-5 hours)

### Objectives
Реализация централизованного сервиса аутентификации для Ingester Module с OAuth 2.0 Client Credentials flow.

### Architecture Design

**Файл**: `ingester-module/app/services/auth_service.py`

```python
"""
Ingester Module - Authentication Service.

Centralized OAuth 2.0 Client Credentials authentication for inter-service communication.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.exceptions import AuthenticationException

logger = logging.getLogger(__name__)


class TokenResponse(BaseModel):
    """OAuth 2.0 Token Response."""
    access_token: str
    token_type: str = "Bearer"
    expires_in: int = Field(gt=0, description="Token lifetime in seconds")


class AuthService:
    """
    Centralized authentication service for Ingester Module.

    Responsibilities:
    - OAuth 2.0 Client Credentials token acquisition
    - Token caching with automatic refresh
    - HTTP client lifecycle management
    - Comprehensive error handling
    """

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._cached_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
        self._lock = asyncio.Lock()  # Thread-safe token refresh

    async def _get_client(self) -> httpx.AsyncClient:
        """
        Получить HTTP client для Admin Module communication.

        Returns:
            httpx.AsyncClient with optional mTLS configuration
        """
        if self._client is None:
            client_config = {
                "base_url": settings.admin_module.base_url,
                "timeout": settings.admin_module.timeout,
                "http2": True,
            }

            # mTLS configuration если TLS enabled
            if settings.tls.enabled:
                import ssl
                ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)

                if settings.tls.ca_cert_file:
                    ssl_context.load_verify_locations(cafile=settings.tls.ca_cert_file)

                if settings.tls.cert_file and settings.tls.key_file:
                    ssl_context.load_cert_chain(
                        certfile=settings.tls.cert_file,
                        keyfile=settings.tls.key_file
                    )

                if settings.tls.protocol_version == "TLSv1.3":
                    ssl_context.minimum_version = ssl.TLSVersion.TLSv1_3
                elif settings.tls.protocol_version == "TLSv1.2":
                    ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2

                if settings.tls.ciphers:
                    ssl_context.set_ciphers(settings.tls.ciphers)

                client_config["verify"] = ssl_context

                logger.info(
                    "mTLS enabled for Admin Module authentication",
                    extra={
                        "protocol": settings.tls.protocol_version,
                        "ciphers": settings.tls.ciphers
                    }
                )

            self._client = httpx.AsyncClient(**client_config)
            logger.info("Auth HTTP client initialized")

        return self._client

    async def close(self):
        """Закрытие HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("Auth HTTP client closed")

    async def get_access_token(self) -> str:
        """
        Получить JWT access token с automatic caching и refresh.

        Returns:
            str: Valid JWT access token

        Raises:
            AuthenticationException: Authentication failed
        """
        # Check cached token validity
        if self._cached_token and self._token_expires_at:
            # 60 second buffer для предотвращения race conditions
            if datetime.now(timezone.utc) < (self._token_expires_at - timedelta(seconds=60)):
                logger.debug("Using cached access token")
                return self._cached_token

        # Acquire lock для thread-safe token refresh
        async with self._lock:
            # Double-check после получения lock
            if self._cached_token and self._token_expires_at:
                if datetime.now(timezone.utc) < (self._token_expires_at - timedelta(seconds=60)):
                    return self._cached_token

            # Request new token from Admin Module
            try:
                client = await self._get_client()

                response = await client.post(
                    "/api/v1/auth/token",
                    json={
                        "client_id": settings.service_account.client_id,
                        "client_secret": settings.service_account.client_secret.get_secret_value()
                    }
                )

                response.raise_for_status()
                token_data = TokenResponse(**response.json())

                # Cache token with expiration
                self._cached_token = token_data.access_token
                self._token_expires_at = datetime.now(timezone.utc) + timedelta(
                    seconds=token_data.expires_in
                )

                logger.info(
                    "Access token acquired successfully",
                    extra={
                        "expires_in": token_data.expires_in,
                        "client_id": settings.service_account.client_id
                    }
                )

                return self._cached_token

            except httpx.HTTPStatusError as e:
                logger.error(
                    "Admin Module authentication failed",
                    extra={
                        "status_code": e.response.status_code,
                        "error": str(e)
                    }
                )
                raise AuthenticationException(
                    f"Authentication failed: {e.response.status_code}"
                )

            except httpx.RequestError as e:
                logger.error(
                    "Admin Module connection error",
                    extra={"error": str(e)}
                )
                raise AuthenticationException(
                    f"Cannot connect to Admin Module: {str(e)}"
                )
```

### Configuration Updates

**Файл**: `ingester-module/app/core/config.py`

Добавить новые settings sections:

```python
class AdminModuleSettings(BaseModel):
    """Admin Module connection settings."""
    base_url: str = Field(
        default="http://artstore_admin_module:8000",
        description="Admin Module base URL"
    )
    timeout: float = Field(
        default=30.0,
        description="HTTP request timeout (seconds)"
    )


class ServiceAccountSettings(BaseModel):
    """Service Account credentials for OAuth 2.0."""
    client_id: str = Field(
        description="OAuth 2.0 Client ID"
    )
    client_secret: SecretStr = Field(
        description="OAuth 2.0 Client Secret"
    )

    class Config:
        env_prefix = "SERVICE_ACCOUNT_"


class Settings(BaseSettings):
    """Application settings."""
    # ... existing fields ...

    admin_module: AdminModuleSettings = Field(default_factory=AdminModuleSettings)
    service_account: ServiceAccountSettings
```

**Environment Variables** (`ingester-module/.env`):

```bash
# Admin Module Connection
ADMIN_MODULE__BASE_URL=http://artstore_admin_module:8000
ADMIN_MODULE__TIMEOUT=30.0

# Service Account Credentials (OAuth 2.0 Client Credentials)
SERVICE_ACCOUNT__CLIENT_ID=sa_ingester_production_xxxxx
SERVICE_ACCOUNT__CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxx
```

### Integration with UploadService

**Файл**: `ingester-module/app/services/upload_service.py`

```python
from app.services.auth_service import AuthService

class UploadService:
    """Сервис загрузки файлов."""

    def __init__(self, auth_service: AuthService):
        """
        Инициализация сервиса с AuthService для аутентификации.

        Args:
            auth_service: AuthService для получения JWT токенов
        """
        self.auth_service = auth_service
        self._client: Optional[httpx.AsyncClient] = None

    async def upload_file(self, ...):
        """Загрузка файла в Storage Element."""
        try:
            # Получить JWT access token для аутентификации
            access_token = await self.auth_service.get_access_token()

            client = await self._get_client()

            # Отправка запроса в Storage Element с Authorization header
            response = await client.post(
                "/api/v1/files/upload",
                headers={'Authorization': f'Bearer {access_token}'},
                files=files,
                data=data
            )
            # ... rest of implementation
```

### Dependency Injection Updates

**Файл**: `ingester-module/app/main.py`

```python
from app.services.auth_service import AuthService

# Create singletons
auth_service = AuthService()
upload_service = UploadService(auth_service=auth_service)

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup на shutdown."""
    await upload_service.close()
    await auth_service.close()  # NEW: Close auth client
    logger.info("Application shutdown complete")
```

### Testing Requirements

**Unit Tests** (`ingester-module/tests/unit/test_auth_service.py`):

```python
"""Unit tests for AuthService."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from app.services.auth_service import AuthService, TokenResponse
from app.core.exceptions import AuthenticationException


@pytest.fixture
def auth_service():
    """Create AuthService instance."""
    return AuthService()


@pytest.mark.asyncio
async def test_get_access_token_success(auth_service):
    """Test successful token acquisition."""
    # Mock HTTP response
    mock_response = AsyncMock()
    mock_response.json.return_value = {
        "access_token": "eyJhbGc...",
        "token_type": "Bearer",
        "expires_in": 1800
    }
    mock_response.raise_for_status = AsyncMock()

    with patch.object(auth_service, '_get_client') as mock_client:
        mock_client.return_value.post = AsyncMock(return_value=mock_response)

        token = await auth_service.get_access_token()

        assert token == "eyJhbGc..."
        assert auth_service._cached_token == "eyJhbGc..."
        assert auth_service._token_expires_at is not None


@pytest.mark.asyncio
async def test_get_access_token_uses_cache(auth_service):
    """Test that cached token is reused."""
    # Set cached token
    auth_service._cached_token = "cached_token"
    auth_service._token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    token = await auth_service.get_access_token()

    assert token == "cached_token"


@pytest.mark.asyncio
async def test_get_access_token_refreshes_expired(auth_service):
    """Test token refresh when expired."""
    # Set expired token
    auth_service._cached_token = "old_token"
    auth_service._token_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)

    mock_response = AsyncMock()
    mock_response.json.return_value = {
        "access_token": "new_token",
        "token_type": "Bearer",
        "expires_in": 1800
    }
    mock_response.raise_for_status = AsyncMock()

    with patch.object(auth_service, '_get_client') as mock_client:
        mock_client.return_value.post = AsyncMock(return_value=mock_response)

        token = await auth_service.get_access_token()

        assert token == "new_token"


@pytest.mark.asyncio
async def test_get_access_token_http_error(auth_service):
    """Test authentication failure handling."""
    import httpx

    mock_response = AsyncMock()
    mock_response.status_code = 401

    with patch.object(auth_service, '_get_client') as mock_client:
        mock_client.return_value.post = AsyncMock(
            side_effect=httpx.HTTPStatusError("Unauthorized", request=None, response=mock_response)
        )

        with pytest.raises(AuthenticationException):
            await auth_service.get_access_token()


# Additional tests:
# - test_get_access_token_connection_error
# - test_close_cleanup
# - test_thread_safe_token_refresh
```

---

## Phase 2: mTLS Enhancement (3-4 hours)

### Objectives
Добавить TLS 1.3 mutual authentication для всех inter-service connections (Ingester → Admin Module, Ingester → Storage Element).

### Current mTLS Implementation Analysis

**Файл**: `ingester-module/app/services/upload_service.py:77-124`

Код УЖЕ содержит базовую mTLS реализацию, НО:

```python
# ТЕКУЩИЙ КОД - ЧАСТИЧНО ГОТОВ:
if settings.tls.enabled:
    import ssl
    ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)

    # CA certificate для валидации server certificate
    if settings.tls.ca_cert_file:
        ssl_context.load_verify_locations(cafile=settings.tls.ca_cert_file)

    # Client certificate для mTLS authentication
    if settings.tls.cert_file and settings.tls.key_file:
        ssl_context.load_cert_chain(
            certfile=settings.tls.cert_file,
            keyfile=settings.tls.key_file
        )

    # TLS 1.3 protocol
    if settings.tls.protocol_version == "TLSv1.3":
        ssl_context.minimum_version = ssl.TLSVersion.TLSv1_3

    client_config["verify"] = ssl_context
```

**Проблемы**:
1. ❌ НЕ протестировано в E2E scenarios
2. ❌ НЕ настроены TLS certificates в Docker окружении
3. ❌ НЕ добавлено в AuthService (дублирование кода)

### Implementation Tasks

#### Task 1: Extract mTLS Configuration to Utility

**Файл**: `ingester-module/app/core/tls_utils.py` (NEW)

```python
"""TLS/mTLS utility functions."""

import logging
import ssl
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


def create_ssl_context() -> Optional[ssl.SSLContext]:
    """
    Create SSL context для mTLS communication.

    Returns:
        ssl.SSLContext if TLS enabled, None otherwise
    """
    if not settings.tls.enabled:
        return None

    ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)

    # CA certificate для server validation
    if settings.tls.ca_cert_file:
        ssl_context.load_verify_locations(cafile=settings.tls.ca_cert_file)
        logger.info(
            "Loaded CA certificate",
            extra={"ca_cert": settings.tls.ca_cert_file}
        )

    # Client certificate для mTLS
    if settings.tls.cert_file and settings.tls.key_file:
        ssl_context.load_cert_chain(
            certfile=settings.tls.cert_file,
            keyfile=settings.tls.key_file
        )
        logger.info(
            "Loaded client certificate for mTLS",
            extra={
                "cert_file": settings.tls.cert_file,
                "key_file": settings.tls.key_file
            }
        )

    # TLS protocol version
    if settings.tls.protocol_version == "TLSv1.3":
        ssl_context.minimum_version = ssl.TLSVersion.TLSv1_3
    elif settings.tls.protocol_version == "TLSv1.2":
        ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2

    # Cipher suites
    if settings.tls.ciphers:
        ssl_context.set_ciphers(settings.tls.ciphers)

    logger.info(
        "SSL context created",
        extra={
            "protocol": settings.tls.protocol_version,
            "ciphers": settings.tls.ciphers
        }
    )

    return ssl_context
```

#### Task 2: Update AuthService to Use Utility

```python
from app.core.tls_utils import create_ssl_context

class AuthService:
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            client_config = {
                "base_url": settings.admin_module.base_url,
                "timeout": settings.admin_module.timeout,
                "http2": True,
            }

            # Apply mTLS configuration
            ssl_context = create_ssl_context()
            if ssl_context:
                client_config["verify"] = ssl_context

            self._client = httpx.AsyncClient(**client_config)
```

#### Task 3: Update UploadService to Use Utility

```python
from app.core.tls_utils import create_ssl_context

class UploadService:
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            client_config = {
                "base_url": settings.storage_element.base_url,
                "timeout": settings.storage_element.timeout,
                "limits": httpx.Limits(
                    max_connections=settings.storage_element.connection_pool_size
                ),
                "http2": True,
            }

            # Apply mTLS configuration
            ssl_context = create_ssl_context()
            if ssl_context:
                client_config["verify"] = ssl_context

            self._client = httpx.AsyncClient(**client_config)
```

### E2E Testing Requirements

**Test Scenarios** (`ingester-module/tests/integration/test_mtls.py`):

```python
"""E2E tests for mTLS communication."""

import pytest
from app.services.auth_service import AuthService
from app.services.upload_service import UploadService


@pytest.mark.integration
@pytest.mark.asyncio
async def test_auth_service_mtls_connection():
    """Test AuthService connects to Admin Module with mTLS."""
    auth_service = AuthService()

    try:
        token = await auth_service.get_access_token()
        assert token is not None
        assert len(token) > 0
    finally:
        await auth_service.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_upload_service_mtls_connection():
    """Test UploadService connects to Storage Element with mTLS."""
    auth_service = AuthService()
    upload_service = UploadService(auth_service=auth_service)

    # Test implementation depends on mocked file upload
    # See existing integration tests for file upload pattern
```

---

## Phase 3: Comprehensive Testing (2-3 hours)

### Unit Test Coverage Goals

Target: **90%+ coverage** для новых компонентов

**Files to Test**:
1. `app/services/auth_service.py` - AuthService class (12+ tests)
2. `app/core/tls_utils.py` - SSL context creation (6+ tests)

**Test Categories**:
- ✅ Success scenarios (happy path)
- ✅ Error handling (HTTP errors, connection errors)
- ✅ Edge cases (token expiration, cache invalidation)
- ✅ Thread safety (concurrent token refresh)
- ✅ Resource cleanup (client close)

### Integration Test Coverage Goals

**E2E Scenarios**:
1. OAuth 2.0 Client Credentials flow (Admin Module authentication)
2. mTLS connection establishment (Ingester → Admin Module)
3. mTLS connection establishment (Ingester → Storage Element)
4. Full file upload workflow with authentication

**Test Infrastructure**:
- Docker test environment (reuse existing from Sprint 11)
- Test service account credentials
- Test TLS certificates (self-signed for testing)

---

## Success Criteria

### Functional Requirements
- [ ] AuthService successfully obtains JWT tokens from Admin Module
- [ ] Token caching works correctly with automatic refresh
- [ ] mTLS connections established successfully for all inter-service communication
- [ ] No hardcoded credentials in source code
- [ ] Graceful error handling for authentication failures

### Testing Requirements
- [ ] Unit tests: 90%+ coverage для AuthService и tls_utils
- [ ] Integration tests: All E2E scenarios passing
- [ ] No test failures in existing test suite
- [ ] Docker test environment validates mTLS communication

### Documentation Requirements
- [ ] Sprint 21 completion summary created
- [ ] AuthService API documentation
- [ ] mTLS configuration guide
- [ ] Troubleshooting guide для common auth issues

### Code Quality
- [ ] Type hints для всех новых функций
- [ ] Docstrings для modules, classes, public methods
- [ ] Russian comments для implementation details
- [ ] Logging для всех critical operations
- [ ] No Pydantic validation warnings

---

## Technical Risks and Mitigations

### Risk 1: mTLS Certificate Management
**Severity**: 🟡 Medium
**Probability**: High
**Impact**: Development blocked if certificates misconfigured

**Mitigation**:
- Use self-signed certificates для testing
- Document certificate generation process
- Provide working example certificates in repo
- Add validation для certificate files at startup

### Risk 2: Token Caching Race Conditions
**Severity**: 🟡 Medium
**Probability**: Medium
**Impact**: Duplicate token requests, performance degradation

**Mitigation**:
- Use asyncio.Lock для thread-safe token refresh
- Comprehensive unit tests для concurrent scenarios
- 60-second expiration buffer для предотвращения edge cases

### Risk 3: Breaking Existing E2E Tests
**Severity**: 🟡 Medium
**Probability**: Medium
**Impact**: Regression in working functionality

**Mitigation**:
- Run full test suite before and after changes
- Incremental implementation с verification после each phase
- Keep backward compatibility где possible

---

## Dependencies

### Internal Dependencies
- ✅ Sprint 20 Complete (Unified JWT Schema)
- ✅ Admin Module OAuth 2.0 endpoint functional
- ✅ Storage Element JWT validation working

### External Dependencies
- ✅ httpx library (already in requirements.txt)
- ⏳ TLS certificates (self-signed для testing)
- ⏳ Service account credentials (configuration)

---

## Out of Scope (Deferred to Future Sprints)

❌ **NOT in Sprint 21**:
- JWT Validation Metrics (Sprint 22)
- Performance Testing Pydantic validation (Sprint 22)
- Redis Caching для validated tokens (Sprint 23)
- Automated JWT Key Rotation (Sprint 23)
- OpenTelemetry distributed tracing (Sprint 24)
- Prometheus metrics collection (Sprint 24)

---

## Implementation Checklist

### Phase 1: AuthService (Day 1)
- [ ] Create `app/services/auth_service.py`
- [ ] Add AdminModuleSettings to config
- [ ] Add ServiceAccountSettings to config
- [ ] Update UploadService constructor
- [ ] Update main.py dependency injection
- [ ] Add shutdown cleanup for AuthService
- [ ] Create unit tests (12+ tests)
- [ ] Run tests: `pytest tests/unit/test_auth_service.py -v`

### Phase 2: mTLS Enhancement (Day 1-2)
- [ ] Create `app/core/tls_utils.py`
- [ ] Refactor UploadService._get_client()
- [ ] Refactor AuthService._get_client()
- [ ] Add unit tests for tls_utils (6+ tests)
- [ ] Create E2E mTLS tests
- [ ] Generate test certificates
- [ ] Update Docker configuration for TLS

### Phase 3: Testing & Documentation (Day 2)
- [ ] Run full test suite: `pytest tests/ -v --cov`
- [ ] Verify coverage >90% for new code
- [ ] Run E2E tests with mTLS enabled
- [ ] Create Sprint 21 completion summary
- [ ] Update CLAUDE.md if needed
- [ ] Git commit with detailed changelog

---

## Expected Outcomes

✅ **AuthService Operational**:
- Centralized OAuth 2.0 authentication
- Token caching с automatic refresh
- Comprehensive error handling

✅ **mTLS Security Enhanced**:
- TLS 1.3 для all inter-service communication
- Client certificate validation
- Cipher suite configuration

✅ **Production Ready**:
- No hardcoded credentials
- Security best practices
- Comprehensive testing

✅ **Documentation Complete**:
- Sprint 21 summary
- Configuration guides
- Troubleshooting documentation

---

## Next Sprint Preview (Sprint 22)

**Focus**: Performance & Observability

1. JWT Validation Metrics (track latency, failure rates)
2. Performance Testing (measure Pydantic validation overhead)
3. OpenTelemetry distributed tracing basics
4. Prometheus metrics collection

**Dependency**: Sprint 21 must be complete (secure authentication foundation)

---

**Implementation by**: Claude Code
**Sprint**: 21 - AuthService & mTLS Security
**Status**: 📋 PLANNED - Ready for Implementation
