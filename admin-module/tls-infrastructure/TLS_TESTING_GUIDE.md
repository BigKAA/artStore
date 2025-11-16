# TLS Integration Testing Guide

**Last Updated**: 2025-11-16
**Status**: Production-Ready
**Coverage**: Admin Module, Storage Element, Ingester Module, Query Module

## Table of Contents

1. [Overview](#overview)
2. [Test Infrastructure](#test-infrastructure)
3. [Running Tests](#running-tests)
4. [Test Categories](#test-categories)
5. [Test Files](#test-files)
6. [Common Issues](#common-issues)
7. [Writing New Tests](#writing-new-tests)
8. [Performance Benchmarks](#performance-benchmarks)

## Overview

Комплексные integration tests для проверки TLS 1.3 и mTLS authentication infrastructure ArtStore.

### What is Tested

✅ **TLS 1.3 Protocol**:
- Server certificate validation
- Client certificate authentication (mTLS)
- Protocol version enforcement (TLS 1.3 only)
- Cipher suite configuration (AEAD only)

✅ **mTLS Authentication**:
- Client certificate validation
- CN (Common Name) whitelist enforcement
- Certificate chain validation
- Certificate expiration checks

✅ **Inter-Service Communication**:
- Ingester → Storage Element mTLS
- Query → Storage Element mTLS
- Connection pooling and HTTP/2
- Error handling and retry logic

✅ **Performance**:
- TLS handshake latency
- Connection reuse and pooling
- Concurrent connection handling
- HTTP/2 multiplexing

### Test Coverage by Module

| Module | Test File | Tests | Focus |
|--------|-----------|-------|-------|
| Admin Module | `tests/integration/test_tls_connections.py` | 25+ | Server TLS, mTLS middleware |
| Storage Element | `tests/integration/test_tls_server.py` | 20+ | Server config, mTLS validation |
| Ingester Module | `tests/integration/test_mtls_storage_communication.py` | 20+ | mTLS upload client |
| Query Module | `tests/integration/test_mtls_storage_download.py` | 20+ | mTLS download client |

**Total**: 85+ integration tests

## Test Infrastructure

### Docker Compose Setup

Используется изолированная test environment с отдельными портами:

```yaml
Services:
  postgres-test:    Port 5433 (dev: 5432)
  redis-test:       Port 6380 (dev: 6379)
  minio-test:       Port 9001 (dev: 9000)
  admin-module:     Port 8000 (HTTPS)
  storage-element:  Port 8010 (HTTPS)
  ingester-module:  Port 8020 (HTTPS)
  query-module:     Port 8030 (HTTPS)
```

### Certificate Infrastructure

**Location**: `admin-module/tls-infrastructure/`

```
tls-infrastructure/
├── ca/
│   ├── ca-cert.pem          # Root CA certificate
│   └── ca-key.pem           # Root CA private key
├── server-certs/
│   ├── admin-module/        # Admin server certificate
│   ├── storage-element/     # Storage server certificate
│   ├── ingester-module/     # Ingester server certificate
│   └── query-module/        # Query server certificate
├── client-certs/
│   ├── admin-client-cert.pem     # Admin client certificate
│   ├── ingester-client-cert.pem  # Ingester client certificate
│   └── query-client-cert.pem     # Query client certificate
└── docker-compose.tls-test.yml   # Test environment
```

## Running Tests

### Quick Start

```bash
# 1. Ensure certificates are generated
cd admin-module/tls-infrastructure
./generate-certs.sh

# 2. Start test environment
docker-compose -f docker-compose.tls-test.yml up -d

# 3. Wait for services to be healthy
docker-compose -f docker-compose.tls-test.yml ps

# 4. Run all TLS tests
docker-compose -f docker-compose.tls-test.yml run --rm admin-module-test pytest tests/integration/test_tls_connections.py -v
docker-compose -f docker-compose.tls-test.yml run --rm storage-element-test pytest tests/integration/test_tls_server.py -v
docker-compose -f docker-compose.tls-test.yml run --rm ingester-module-test pytest tests/integration/test_mtls_storage_communication.py -v
docker-compose -f docker-compose.tls-test.yml run --rm query-module-test pytest tests/integration/test_mtls_storage_download.py -v

# 5. Stop and cleanup
docker-compose -f docker-compose.tls-test.yml down -v
```

### Running Specific Test Categories

```bash
# Certificate validation tests only
pytest tests/integration/test_tls_connections.py::TestCertificateValidation -v

# TLS protocol tests only
pytest tests/integration/test_tls_connections.py::TestTLS13Protocol -v

# mTLS authentication tests only
pytest tests/integration/test_tls_connections.py::TestMTLSAuthentication -v

# Performance tests only
pytest tests/integration/test_tls_connections.py::TestTLSPerformance -v
```

### Running with Coverage

```bash
docker-compose -f docker-compose.tls-test.yml run --rm admin-module-test \
  pytest tests/integration/test_tls_connections.py -v \
  --cov=app.core.tls_middleware \
  --cov-report=html
```

### Running Individual Tests

```bash
# Specific test method
pytest tests/integration/test_tls_connections.py::TestTLS13Protocol::test_tls13_connection_success -v

# With detailed output
pytest tests/integration/test_tls_connections.py::TestMTLSAuthentication::test_mtls_connection_with_valid_client_cert -vv
```

## Test Categories

### 1. Certificate Validation Tests

**Purpose**: Проверка существования и валидности certificates

**Tests**:
- CA certificate validation
- Server certificate validation
- Client certificate validation
- Certificate chain validation
- Certificate expiration checks
- SAN (Subject Alternative Names) validation

**Example**:
```python
def test_ca_certificate_exists(self):
    """CA certificate должен существовать и быть валидным."""
    assert CA_CERT_PATH.exists()

    with open(CA_CERT_PATH, "rb") as f:
        cert = x509.load_pem_x509_certificate(f.read(), default_backend())

    assert cert is not None
    validity_days = (cert.not_valid_after - cert.not_valid_before).days
    assert validity_days >= 1825  # 5 years minimum
```

### 2. TLS Protocol Tests

**Purpose**: Проверка TLS 1.3 protocol enforcement

**Tests**:
- TLS 1.3 connection success
- TLS 1.2 connection rejection
- Plain HTTP connection rejection
- Invalid certificate rejection

**Example**:
```python
async def test_tls13_connection_success(self, tls_client):
    """Успешное TLS 1.3 соединение с admin module."""
    response = await tls_client.get(f"{ADMIN_MODULE_TLS_URL}/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
```

### 3. mTLS Authentication Tests

**Purpose**: Проверка mutual TLS authentication

**Tests**:
- Valid client certificate acceptance
- Missing client certificate rejection
- Invalid client certificate rejection
- CN whitelist enforcement
- Path-based mTLS requirements

**Example**:
```python
async def test_mtls_required_endpoint_without_client_cert(self, tls_client):
    """Endpoints, требующие mTLS, должны отклонять запросы без client certificate."""
    response = await tls_client.get(f"{ADMIN_MODULE_TLS_URL}/api/internal/status")
    assert response.status_code in [401, 403, 404]
```

### 4. Cipher Suite Tests

**Purpose**: Проверка TLS cipher suite configuration

**Tests**:
- AEAD cipher suites only
- Weak cipher rejection
- Cipher suite ordering

**Example**:
```python
def test_aead_cipher_suites_only(self, ssl_context):
    """Только AEAD cipher suites должны быть разрешены."""
    assert ssl_context.minimum_version == ssl.TLSVersion.TLSv1_3
    # TLS 1.3 автоматически использует только AEAD ciphers
```

### 5. Performance Tests

**Purpose**: Проверка производительности TLS connections

**Tests**:
- HTTP/2 support
- Connection pooling efficiency
- Concurrent connection handling
- TLS handshake latency
- Session resumption

**Example**:
```python
async def test_concurrent_tls_connections_handling(self, tls_client):
    """Storage Element должен обрабатывать множественные concurrent connections."""
    tasks = [tls_client.get(f"{URL}/health/live") for _ in range(10)]
    responses = await asyncio.gather(*tasks)
    assert all(r.status_code == 200 for r in responses)
```

### 6. Error Handling Tests

**Purpose**: Проверка graceful error handling

**Tests**:
- Certificate verification failure handling
- Expired certificate handling
- Hostname verification
- TLS handshake failure handling
- Server unavailability handling

**Example**:
```python
async def test_certificate_verification_failure(self):
    """Ошибка проверки certificate должна быть обработана."""
    wrong_ca_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    # Не загружаем CA certificate

    with pytest.raises((ssl.SSLError, httpx.ConnectError)):
        async with httpx.AsyncClient(verify=wrong_ca_context) as client:
            await client.get(f"{URL}/health/live")
```

### 7. Integration Flow Tests

**Purpose**: End-to-end scenarios

**Tests**:
- Full authentication flow (OAuth 2.0 + TLS + mTLS)
- File upload flow (Ingester → Storage)
- File download flow (Query → Storage)
- Concurrent operations
- Retry logic
- Circuit breaker patterns

**Example**:
```python
async def test_ingester_to_storage_upload_scenario(self, mtls_client):
    """End-to-end загрузка файла через Ingester → Storage с mTLS."""
    # 1. Ingester аутентифицируется в Admin Module
    # 2. Ingester получает список Storage Elements
    # 3. Ingester устанавливает mTLS соединение
    # 4. Ingester загружает файл
    # 5. Верификация успешной загрузки
```

## Test Files

### Admin Module: `test_tls_connections.py`

**Purpose**: Testing Admin Module as TLS server

**Test Classes**:
- `TestCertificateValidation`: Certificate existence and validity
- `TestTLS13Protocol`: TLS 1.3 protocol enforcement
- `TestMTLSAuthentication`: mTLS middleware functionality
- `TestTLSCipherSuites`: Cipher suite configuration
- `TestTLSPerformance`: HTTP/2 and connection pooling
- `TestTLSErrorHandling`: Error scenarios
- `TestTLSIntegrationFlow`: End-to-end scenarios

**Key Focus**:
- Server-side TLS configuration
- mTLS middleware enforcement
- CN whitelist validation
- Protected endpoint access control

### Storage Element: `test_tls_server.py`

**Purpose**: Testing Storage Element as TLS/mTLS server

**Test Classes**:
- `TestStorageServerCertificate`: Server certificate configuration
- `TestStorageTLSServerConfiguration`: TLS 1.3 server setup
- `TestStorageMTLSClientAuthentication`: Client certificate validation
- `TestStorageCNWhitelistEnforcement`: CN whitelist rules
- `TestStorageTLSCipherSuites`: Cipher suite configuration
- `TestStorageTLSPerformance`: Concurrent connection handling
- `TestStorageTLSErrorHandling`: Error scenarios

**Key Focus**:
- Server certificate serving
- mTLS client authentication
- CN whitelist enforcement (ingester-client, query-client)
- File operation endpoint protection

### Ingester Module: `test_mtls_storage_communication.py`

**Purpose**: Testing Ingester as mTLS client (upload operations)

**Test Classes**:
- `TestIngesterCertificates`: Client certificate validation
- `TestIngesterMTLSCommunication`: mTLS connection establishment
- `TestIngesterTLSConnectionPooling`: Connection reuse
- `TestIngesterMTLSErrorHandling`: Error scenarios
- `TestIngesterMTLSPerformance`: Upload performance with TLS
- `TestIngesterMTLSIntegrationScenarios`: End-to-end flows

**Key Focus**:
- Client certificate authentication
- Connection pooling for uploads
- Retry logic on TLS failures
- Bulk upload efficiency

### Query Module: `test_mtls_storage_download.py`

**Purpose**: Testing Query as mTLS client (download operations)

**Test Classes**:
- `TestQueryCertificates`: Client certificate validation
- `TestQueryMTLSCommunication`: mTLS connection establishment
- `TestQueryStreamingDownload`: Streaming download through TLS
- `TestQueryTLSConnectionPooling`: Connection reuse
- `TestQueryMTLSErrorHandling`: Error scenarios
- `TestQueryMTLSPerformance`: Download performance with TLS
- `TestQueryMTLSIntegrationScenarios`: End-to-end flows

**Key Focus**:
- Client certificate authentication
- Streaming download through TLS
- Connection pooling for multiple downloads
- Retry logic on connection failures

## Common Issues

### Issue: Certificate Verification Failure

**Symptom**: `ssl.SSLError: certificate verify failed`

**Причина**: Client не может проверить server certificate

**Решение**:
```python
# Ensure CA certificate is loaded
context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
context.load_verify_locations(str(CA_CERT_PATH))  # Must be correct path

# Check certificate paths in Docker volumes
docker-compose -f docker-compose.tls-test.yml exec admin-module ls -l /app/tls/
```

### Issue: TLS 1.2 Not Rejected

**Symptom**: TLS 1.2 connections succeed when they should fail

**Причина**: Server не правильно настроен на TLS 1.3 only

**Решение**:
```python
# Server configuration должна включать
TLS_PROTOCOL_VERSION: TLSv1.3
TLS_MINIMUM_VERSION: TLSv1.3

# Verify в коде:
context.minimum_version = ssl.TLSVersion.TLSv1_3
context.maximum_version = ssl.TLSVersion.TLSv1_3
```

### Issue: mTLS Authentication Not Required

**Symptom**: Requests without client certificate succeed

**Причина**: mTLS middleware не активирован или неправильно сконфигурирован

**Решение**:
```python
# Check middleware configuration
MTLS_ENABLED: "true"
MTLS_REQUIRED_PATHS: "/api/internal/.*,/api/files/.*"
MTLS_STRICT_MODE: "true"

# Verify middleware is added:
from app.core.tls_middleware import add_mtls_middleware
add_mtls_middleware(app, ca_cert_path="...", ...)
```

### Issue: Connection Pooling Not Working

**Symptom**: Each request establishes new TLS connection

**Причина**: httpx.AsyncClient не переиспользует connections

**Решение**:
```python
# Use context manager для persistent client
async with httpx.AsyncClient(
    verify=ssl_context,
    cert=(cert_path, key_path),
    http2=True,  # Enable HTTP/2
    limits=httpx.Limits(
        max_connections=100,
        max_keepalive_connections=20  # Keep connections alive
    )
) as client:
    # Multiple requests reuse connection
    response1 = await client.get(url1)
    response2 = await client.get(url2)
```

### Issue: Tests Fail Due to Service Unavailability

**Symptom**: `httpx.ConnectError: Connection refused`

**Причина**: Services не стартовали или unhealthy

**Решение**:
```bash
# Check service health
docker-compose -f docker-compose.tls-test.yml ps

# View logs
docker-compose -f docker-compose.tls-test.yml logs admin-module
docker-compose -f docker-compose.tls-test.yml logs storage-element

# Restart services
docker-compose -f docker-compose.tls-test.yml restart

# Recreate from scratch
docker-compose -f docker-compose.tls-test.yml down -v
docker-compose -f docker-compose.tls-test.yml up -d
```

## Writing New Tests

### Test Template

```python
"""
Integration tests for [feature description].

Проверяет:
- [What is tested 1]
- [What is tested 2]
- [What is tested 3]
"""

import ssl
from pathlib import Path
import httpx
import pytest


# Constants
TLS_INFRA_DIR = Path(__file__).parent.parent.parent / "tls-infrastructure"
CA_CERT_PATH = TLS_INFRA_DIR / "ca" / "ca-cert.pem"
# ... other paths


# Fixtures
@pytest.fixture
def ssl_context() -> ssl.SSLContext:
    """SSL context for tests."""
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    context.load_verify_locations(str(CA_CERT_PATH))
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    return context


# Tests
@pytest.mark.integration
@pytest.mark.asyncio
class TestNewFeature:
    """Test class description."""

    async def test_specific_scenario(self, ssl_context):
        """Test description."""
        async with httpx.AsyncClient(verify=ssl_context) as client:
            response = await client.get("https://service:port/endpoint")
            assert response.status_code == 200
```

### Best Practices

1. **Use Descriptive Names**:
   ```python
   # Good
   def test_tls13_connection_with_valid_server_certificate()

   # Bad
   def test_connection()
   ```

2. **Document What is Tested**:
   ```python
   async def test_mtls_authentication(self):
       """
       mTLS authentication с валидным client certificate.

       Проверяет:
       - Client certificate принимается
       - Server проверяет certificate chain
       - CN whitelist enforcement работает
       """
   ```

3. **Use Fixtures for Common Setup**:
   ```python
   @pytest.fixture
   async def mtls_client(ssl_context) -> AsyncGenerator[httpx.AsyncClient, None]:
       """Reusable mTLS client fixture."""
       async with httpx.AsyncClient(
           verify=ssl_context,
           cert=(cert_path, key_path)
       ) as client:
           yield client
   ```

4. **Handle Service Unavailability**:
   ```python
   try:
       response = await client.get(url)
   except httpx.ConnectError:
       pytest.skip("Service unavailable for test")
   ```

5. **Use Proper Assertions**:
   ```python
   # Good - specific check
   assert response.status_code == 200
   assert response.json() == {"status": "healthy"}

   # Bad - generic check
   assert response.ok
   ```

## Performance Benchmarks

### Expected Performance Metrics

**TLS Handshake**:
- First connection: < 100ms (1-RTT)
- Session resumption: < 10ms (0-RTT)

**HTTP/2 Multiplexing**:
- Concurrent requests: 10+ requests over single connection
- Connection overhead: < 5% vs plain HTTP

**Connection Pooling**:
- Connection reuse: 90%+ for sequential requests
- Pool exhaustion: Graceful degradation with waiting

**mTLS Overhead**:
- Client cert validation: < 50ms additional overhead
- CN whitelist check: < 1ms

### Running Performance Tests

```bash
# Performance tests только
pytest tests/integration/test_tls_connections.py -m performance -v

# С timing output
pytest tests/integration/test_tls_connections.py::TestTLSPerformance -v --durations=10

# Benchmark mode (если pytest-benchmark установлен)
pytest tests/integration/test_tls_connections.py::TestTLSPerformance --benchmark-only
```

## Summary

**Total Tests**: 85+ integration tests
**Coverage**: TLS 1.3, mTLS, certificate validation, error handling, performance
**Execution Time**: ~2-3 minutes (full suite)
**Infrastructure**: Isolated Docker environment with separate ports

**Status**: ✅ Production-Ready

---

**Last Updated**: 2025-11-16
**Maintained by**: ArtStore Development Team
