# Integration Tests - Ingester Module

E2E интеграционные тесты для валидации mTLS communication и OAuth 2.0 authentication.

## Sprint 22 Phase 3: E2E Integration Tests ✅

**Implemented Tests:** 10 comprehensive E2E scenarios
**Coverage Areas:** Authentication, mTLS, Upload Workflow, Configuration, Performance

## Prerequisites

### Required Services

1. **Admin Module** (для OAuth 2.0 authentication)
   ```bash
   cd /home/artur/Projects/artStore
   docker-compose up -d admin-module
   ```

2. **Storage Element** (для file upload tests)
   ```bash
   docker-compose up -d storage-element
   ```

### Configuration

Environment variables (already configured in .env):
- `SERVICE_ACCOUNT_ADMIN_MODULE_URL`
- `SERVICE_ACCOUNT_CLIENT_ID`
- `SERVICE_ACCOUNT_CLIENT_SECRET`
- `STORAGE_ELEMENT_BASE_URL`
- `TLS_ENABLED` (опционально для mTLS testing)

## Running Tests

### All Integration Tests
```bash
pytest tests/integration/ -v -m integration
```

### Specific Categories
```bash
# Только authentication
pytest tests/integration/ -v -k "auth"

# Только upload workflow
pytest tests/integration/ -v -k "upload"

# Performance tests
pytest tests/integration/ -v -m "slow"
```

### Skip Integration (Unit Tests Only)
```bash
pytest -v -m "not integration"
```

## Test Coverage

### 1. OAuth 2.0 Authentication (3 tests)
- ✅ `test_auth_service_connects_to_admin_module`
- ✅ `test_auth_service_token_refresh_on_expiry`
- ✅ `test_auth_service_handles_invalid_credentials`

### 2. mTLS Communication (2 tests)
- ✅ `test_upload_service_mtls_connection`
- ✅ `test_full_upload_workflow_with_authentication`

### 3. Configuration Validation (2 tests)
- ✅ `test_tls_configuration_validation`
- ✅ `test_auth_service_with_mtls_if_configured`

### 4. Performance & Reliability (2 tests)
- ✅ `test_auth_service_concurrent_token_requests`
- ✅ `test_upload_service_connection_pool_reuse`

## Expected Behavior

**When Services Available:**
- All tests execute E2E scenarios
- Real HTTP requests to Admin Module/Storage Element
- JWT tokens obtained and validated
- Files uploaded and verified

**When Services Unavailable:**
- Tests gracefully skipped with clear messages
- No false failures
- Helpful instructions displayed

## Troubleshooting

**Issue:** Tests skipped with "Admin Module not available"
**Solution:** `docker-compose up -d admin-module`

**Issue:** Authentication failed (401)
**Solution:** Check SERVICE_ACCOUNT_CLIENT_ID/SECRET in .env

**Issue:** TLS certificate errors
**Solution:** Verify TLS_CERT_FILE, TLS_KEY_FILE paths

## Sprint 22 Deliverables ✅

- 10 comprehensive E2E integration tests
- Full OAuth 2.0 flow validation
- mTLS communication verification
- Performance and concurrency testing
- Complete documentation and examples
