# Testing Infrastructure Patterns - Lessons from Sprint 11

**Last Updated**: 2025-11-14
**Source**: Sprint 11 Phase 1 - Ingester Module Testing Infrastructure
**Status**: Production-Ready Patterns

## Multi-Stage Docker Build Pattern

### Builder → Test → Runtime Separation

**Pattern**:
```dockerfile
# Stage 1: Builder - Dependencies compilation
FROM python:3.12-slim as builder
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt /tmp/
RUN pip install -r /tmp/requirements.txt

# Stage 2: Test - Testing environment
FROM python:3.12-slim as test
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install pytest pytest-asyncio pytest-cov
COPY ./app /app/app
COPY ./tests /app/tests
CMD ["pytest", "tests/", "-v"]

# Stage 3: Runtime - Production minimal
FROM python:3.12-slim
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY ./app /app/app
CMD ["python", "-m", "uvicorn", "app.main:app"]
```

**Benefits**:
- Production image size: ~200MB (vs ~500MB monolithic)
- Test stage: Independent test environment
- Builder stage: Cached dependency compilation
- Security: Minimal attack surface in production

**When to Use**:
- All Python microservices
- Applications requiring test automation
- CI/CD pipelines with Docker

## Isolated Test Environment Pattern

### Separate Ports and Networks

**Pattern**:
```yaml
# docker-compose.test.yml
services:
  postgres-test:
    image: postgres:15-alpine
    ports:
      - "5433:5432"  # Different from dev (5432)
    networks:
      - test-network
    
  redis-test:
    image: redis:7-alpine
    ports:
      - "6380:6379"  # Different from dev (6379)
    networks:
      - test-network

networks:
  test-network:
    name: module-test-network
    driver: bridge
```

**Benefits**:
- No conflicts with development services
- Parallel test execution possible
- Clean separation of concerns
- Easy cleanup with `down -v`

**When to Use**:
- All module test infrastructures
- CI/CD test environments
- Parallel development and testing

## Health Check Integration Pattern

### Reliable Container Orchestration

**Pattern**:
```yaml
services:
  postgres-test:
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U test_user"]
      interval: 5s
      timeout: 5s
      retries: 5
  
  test-runner:
    depends_on:
      postgres-test:
        condition: service_healthy
      redis-test:
        condition: service_healthy
```

**Benefits**:
- Prevents race conditions
- Eliminates flaky tests
- Reliable container startup order
- Fast failure detection

**When to Use**:
- All Docker-based testing
- Services with dependencies
- CI/CD pipelines

## Mock Service Pattern

### JSON-Based Mock Configurations

**Pattern**:
```yaml
# docker-compose.test.yml
services:
  mock-admin:
    image: mockserver/mockserver:latest
    environment:
      MOCKSERVER_INITIALIZATION_JSON_PATH: /config/mock.json
    volumes:
      - ./tests/mocks/admin-mock.json:/config/mock.json:ro
    profiles:
      - integration  # Only for integration tests
```

```json
// tests/mocks/admin-mock.json
{
  "expectations": [
    {
      "httpRequest": {
        "method": "POST",
        "path": "/api/auth/token"
      },
      "httpResponse": {
        "statusCode": 200,
        "body": {"access_token": "mock-token"}
      }
    }
  ]
}
```

**Benefits**:
- Version-controlled mock configurations
- Profile-based activation (fast unit tests)
- Easy to modify and extend
- No external dependencies in tests

**When to Use**:
- Integration testing
- External API mocking
- Microservice testing

## Lazy Initialization Pattern

### Performance Optimization for Services

**Pattern**:
```python
class UploadService:
    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._max_file_size = 1024 * 1024 * 1024
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy HTTP client initialization."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                limits=httpx.Limits(max_connections=100)
            )
        return self._client
    
    async def close(self):
        """Cleanup resources."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
```

**Benefits**:
- Resource efficiency (no client if not needed)
- Faster initialization
- Easier testing (mock _get_client)
- Clean resource management

**When to Use**:
- HTTP clients in services
- Database connections
- Expensive resource initialization

## JWT Standard Compliance Pattern

### Using Standard JWT Claims

**Pattern**:
```python
class UserContext(BaseModel):
    # JWT standard fields (NOT custom names)
    sub: str  # Subject (user ID)
    type: str  # Token type (access/refresh)
    iat: datetime  # Issued at
    exp: datetime  # Expires at
    nbf: Optional[datetime]  # Not before
    
    # Additional claims
    username: str
    email: Optional[str]
    role: UserRole
    
    @property
    def user_id(self) -> str:
        """Convenience property for backward compatibility."""
        return self.sub
```

**Benefits**:
- Standards compliance
- Interoperability with other systems
- Library compatibility (PyJWT, python-jose)
- Future-proof design

**When to Use**:
- All JWT implementations
- OAuth 2.0 integrations
- Microservice authentication

## Pytest Fixture Monkeypatch Pattern

### Settings Override in Tests

**Pattern**:
```python
@pytest.fixture
def jwt_validator(public_key_file, monkeypatch):
    """Create JWTValidator with test settings."""
    from app.core import config
    
    # Override settings for this test only
    monkeypatch.setattr(
        config.settings.auth,
        'public_key_path',
        public_key_file
    )
    
    # Create instance (reads from patched settings)
    return JWTValidator()

def test_with_custom_settings(jwt_validator):
    # Test uses patched settings
    assert jwt_validator._public_key is not None
```

**Benefits**:
- Test isolation
- No global state modification
- Clean teardown (automatic)
- Easy to understand

**When to Use**:
- Settings-dependent code testing
- Environment variable testing
- Configuration override needs

## Async Testing Pattern

### Proper Async Test Handling

**Pattern**:
```python
@pytest.mark.asyncio
async def test_async_operation():
    """Test async code properly."""
    service = UploadService()
    
    # Async operation
    client = await service._get_client()
    
    # Assertions
    assert client is not None
    
    # Cleanup async resources
    await service.close()
```

**Benefits**:
- Proper async/await handling
- Resource cleanup
- Realistic async behavior testing
- No event loop issues

**When to Use**:
- All async code testing
- FastAPI endpoint testing
- Async service layer testing

## Comprehensive Test Structure Pattern

### Organized Test Hierarchy

**Pattern**:
```
tests/
├── unit/                    # Fast, isolated tests
│   ├── test_schemas.py     # Pydantic validation
│   ├── test_security.py    # Authentication logic
│   └── test_services.py    # Service layer
├── integration/            # Slower, integration tests
│   ├── test_api_flow.py    # E2E API workflows
│   └── test_db_ops.py      # Database operations
├── mocks/                  # Mock configurations
│   ├── admin-mock.json
│   └── storage-mock.json
├── conftest.py            # Shared fixtures
└── README.md              # Test documentation
```

**Benefits**:
- Clear separation of test types
- Easy to run specific test suites
- Shared fixtures centralized
- Mock configurations organized

**When to Use**:
- All projects with tests
- Multi-layer applications
- Team collaboration

## Environment-Specific Logging Pattern

### Production vs Development Logging

**Pattern**:
```yaml
# docker-compose.yml (development)
environment:
  LOG_FORMAT: text  # Human-readable

# docker-compose.test.yml (testing)
environment:
  LOG_FORMAT: text  # Debug-friendly

# Production deployment
environment:
  LOG_FORMAT: json  # Structured, parseable
```

```python
# Logging configuration
if settings.log_format == "json":
    handler.setFormatter(JsonFormatter())
else:
    handler.setFormatter(TextFormatter())
```

**Benefits**:
- Development: Easy debugging
- Production: Structured logs for ELK/Splunk
- Testing: Human-readable output
- Flexibility: Easy to switch

**When to Use**:
- All applications with logging
- Multi-environment deployments
- Log aggregation systems

## Test Documentation Pattern

### Comprehensive Test README

**Pattern**:
```markdown
# Testing Guide

## Quick Start
```bash
pytest tests/unit/ -v
```

## Docker Testing
```bash
docker-compose -f docker-compose.test.yml up --build
```

## Writing Tests
```python
def test_example():
    # Arrange
    service = MyService()
    
    # Act
    result = service.do_something()
    
    # Assert
    assert result == expected
```

## Troubleshooting
### Issue: Database not ready
**Solution**: Check health checks in docker-compose.test.yml
```

**Benefits**:
- Faster onboarding
- Self-service debugging
- Best practices documentation
- Examples for common patterns

**When to Use**:
- All projects with tests
- Team collaboration
- Open source projects

## Summary: Key Patterns Applied

1. **Multi-Stage Docker Build**: Builder → Test → Runtime
2. **Isolated Test Environment**: Separate ports/networks
3. **Health Check Integration**: Reliable orchestration
4. **Mock Service Pattern**: JSON-based configurations
5. **Lazy Initialization**: Performance optimization
6. **JWT Standard Compliance**: Standard claims usage
7. **Pytest Monkeypatch**: Settings override in tests
8. **Async Testing**: Proper async/await handling
9. **Test Structure**: Organized hierarchy
10. **Environment Logging**: Production vs development

These patterns are production-ready and can be applied to all future microservice implementations.
