# Technical Patterns - OAuth 2.0 + Docker Healthcheck

**Category**: Implementation Patterns & Common Issues
**Last Updated**: 2025-11-13
**Applicability**: OAuth 2.0, Docker containerization, FastAPI health checks

## Pattern 1: OAuth 2.0 Client Credentials Implementation

### Context
Implementing OAuth 2.0 Client Credentials Grant (RFC 6749 Section 4.4) для machine-to-machine authentication в FastAPI приложении.

### Pattern
```python
# 1. Request Schema с RFC compliance
class OAuth2TokenRequest(BaseModel):
    grant_type: str = Field(
        default="client_credentials",
        pattern="^client_credentials$"  # Enforce specific grant type
    )
    client_id: str
    client_secret: str

# 2. Token Generation Service
class TokenService:
    def create_service_account_access_token(self, sa: ServiceAccount) -> str:
        claims = {
            "sub": str(sa.id),
            "client_id": sa.client_id,
            "role": sa.role.value,
            "rate_limit": sa.rate_limit,
            "type": "access",
            # Standard JWT claims
        }
        return jwt.encode(claims, private_key, algorithm="RS256")

# 3. Authentication Endpoint
@router.post("/token", response_model=OAuth2TokenResponse)
async def oauth2_token(
    request: OAuth2TokenRequest,
    db: AsyncSession = Depends(get_db)
):
    # Authenticate via bcrypt
    sa = await service.authenticate_service_account(
        db, request.client_id, request.client_secret
    )
    if not sa:
        raise HTTPException(401, "Invalid client_id or client_secret")
    
    # Generate tokens
    access_token, refresh_token = token_service.create_service_account_token_pair(sa)
    
    return OAuth2TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt.access_token_expire_minutes * 60
    )
```

### Key Points
- **RFC 6749 Compliance**: Include `grant_type` field with pattern validation
- **bcrypt Secrets**: Hash client_secret с bcrypt (не MD5/SHA256)
- **RS256 JWT**: Asymmetric signing для distributed validation
- **Rate Limiting**: Include rate_limit в JWT claims для middleware enforcement
- **Error Headers**: RFC-compliant `WWW-Authenticate` header on 401

### Common Mistakes
- ❌ Forgetting `grant_type` field в request schema
- ❌ Using symmetric HMAC instead of asymmetric RS256
- ❌ Not including cache control headers (`no-store`, `no-cache`)
- ❌ Missing `WWW-Authenticate` header в error responses

## Pattern 2: Docker Healthcheck Path Configuration

### Context
Настройка Docker healthcheck для FastAPI приложения с health endpoints.

### Problem
FastAPI router с `prefix="/health"` creates endpoints at `/health/live`, но healthcheck может ошибочно указывать `/api/health/live`.

### Pattern
```yaml
# docker-compose.yml
services:
  app:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health/live"]
      # NOT: /api/health/live
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
```

```python
# FastAPI router registration
app.include_router(health.router, prefix="/health", tags=["health"])
# Creates: /health/live, /health/ready
# NOT: /api/health/live
```

### Validation
```bash
# 1. Check actual endpoint
curl http://localhost:8000/health/live

# 2. Verify healthcheck config
docker inspect container_name --format='{{json .Config.Healthcheck.Test}}'

# 3. Check health status
docker ps --filter name=container_name
# Should show: (healthy), not (unhealthy)
```

### Key Points
- **Consistency**: Production (`docker-compose.yml`) and dev (`docker-compose.dev.yml`) must match
- **Prefix Awareness**: FastAPI prefix applies directly, no `/api` wrapper needed
- **Start Period**: Allow sufficient time для initialization (10-40s depending on dependencies)
- **Rebuild Required**: After changing healthcheck, rebuild container to apply

### Common Mistakes
- ❌ Adding `/api` prefix где его нет в actual router
- ❌ Inconsistent paths between production и dev configs
- ❌ Too short `start_period` causing false unhealthy states
- ❌ Forgetting to rebuild container after healthcheck changes

## Pattern 3: Integration Testing FastAPI с Async Dependencies

### Context
Тестирование FastAPI endpoints которые используют async database operations.

### Problem
FastAPI `TestClient` is synchronous, conflicts with async fixtures и async database sessions.

### Anti-Pattern (Don't Do This)
```python
# ❌ This will fail with event loop errors
@pytest.mark.asyncio
async def test_endpoint(async_db_session):
    client = TestClient(app)
    response = client.post("/endpoint", json=data)
    # Event loop conflict when endpoint tries to use database
```

### Pattern: Simplified Negative Tests
```python
# ✅ Test without database dependencies
class TestOAuth2TokenEndpointNegative:
    def test_token_endpoint_invalid_client_id(self, client):
        """Test with non-existent client."""
        response = client.post(
            "/api/v1/auth/token",
            json={
                "grant_type": "client_credentials",
                "client_id": "sa_nonexistent_123",
                "client_secret": "wrong_secret"
            }
        )
        
        assert response.status_code == 401
        assert "Invalid client_id" in response.json()["detail"]
        
        # Validate RFC compliance
        assert "WWW-Authenticate" in response.headers
        assert response.headers["Cache-Control"] == "no-store"
```

### Alternative: httpx AsyncClient
```python
# For tests requiring database operations
import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_with_database():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/api/v1/auth/token", json=data)
    assert response.status_code == 200
```

### Key Points
- **TestClient Limitations**: Use for negative tests (validation, structure checks)
- **AsyncClient Alternative**: For tests requiring database/async operations
- **Coverage Strategy**: Negative tests + endpoint availability + OpenAPI validation covers critical paths
- **Known Issues**: Accept event loop errors as known limitation when unavoidable

## Pattern 4: Redis Singleton Export для Middleware

### Context
FastAPI middleware requiring Redis client instance.

### Problem
Middleware imports `redis_client`, но он не экспортирован из модуля.

### Pattern
```python
# app/core/redis.py

# Connection pool и client functions
def get_redis_pool() -> ConnectionPool:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = ConnectionPool.from_url(...)
    return _redis_pool

def get_redis() -> Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis(connection_pool=get_redis_pool())
    return _redis_client

# ✅ EXPORT global instance для middleware
redis_client = get_redis()
```

```python
# app/main.py
from app.core.redis import redis_client  # ✅ Now importable

app.add_middleware(RateLimitMiddleware, redis_client=redis_client)
```

### Key Points
- **Global Instance**: Create и export для reuse across application
- **Lazy Initialization**: Still initialize pool on first `get_redis()` call
- **Middleware Access**: Direct import без calling function каждый раз
- **Singleton Pattern**: Ensures single Redis connection pool

## Pattern 5: JSON Logging для Production

### Context
Production-ready logging configuration для containerized applications.

### Pattern
```yaml
# docker-compose.yml (Production)
environment:
  LOG_LEVEL: "INFO"
  LOG_FORMAT: "json"  # ✅ Mandatory for production
```

```yaml
# docker-compose.dev.yml (Development)  
environment:
  LOG_LEVEL: "DEBUG"
  LOG_FORMAT: "text"  # ✅ Allowed only in dev
```

```python
# app/core/logging_config.py
import logging
from pythonjsonlogger import jsonlogger

def setup_logging():
    if settings.logging.format == "json":
        # Production: structured JSON
        formatter = jsonlogger.JsonFormatter(
            '%(timestamp)s %(level)s %(logger)s %(module)s %(function)s %(line)s %(message)s'
        )
    else:
        # Development: human-readable
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
```

### Key Points
- **JSON Production**: Required для ELK Stack, Splunk, CloudWatch integration
- **Text Development**: Easier debugging during local development
- **Structured Fields**: timestamp, level, logger, module, function, line, message
- **Integration Ready**: JSON logs directly consumable by log aggregation systems

### Common Mistakes
- ❌ Using text format в production
- ❌ Missing required fields (timestamp, level)
- ❌ Not configuring via environment variables
- ❌ Hardcoding format instead of making it configurable

## Cross-Pattern Insights

### OAuth + Docker + Health + Testing Together

**Complete Implementation Checklist**:

1. **OAuth 2.0 Endpoint**:
   - ✅ RFC 6749 compliant request schema
   - ✅ bcrypt secret hashing
   - ✅ RS256 JWT generation
   - ✅ Rate limiting integration
   - ✅ RFC error responses

2. **Docker Configuration**:
   - ✅ Multi-stage Dockerfile
   - ✅ Non-root user
   - ✅ JSON logging in production
   - ✅ Correct healthcheck paths
   - ✅ External network integration

3. **Health Checks**:
   - ✅ `/health/live` и `/health/ready` endpoints
   - ✅ Consistent paths в docker-compose
   - ✅ Appropriate start_period
   - ✅ Container rebuild after changes

4. **Testing Strategy**:
   - ✅ Unit tests для business logic
   - ✅ Negative integration tests (no async)
   - ✅ Endpoint availability tests
   - ✅ OpenAPI validation tests
   - ✅ Accept event loop limitations

5. **Production Readiness**:
   - ✅ JSON logging configured
   - ✅ Health checks passing
   - ✅ Security hardened (bcrypt, RS256)
   - ✅ Rate limiting enabled
   - ✅ Monitoring ready (Prometheus)

## When to Use These Patterns

- **OAuth 2.0**: Machine-to-machine authentication, service accounts, API clients
- **Healthcheck Fix**: Any FastAPI app with health endpoints in Docker
- **Integration Testing**: FastAPI apps with async database operations
- **Redis Singleton**: Middleware requiring Redis client access
- **JSON Logging**: All production containerized applications

## References

- RFC 6749: OAuth 2.0 Authorization Framework
- FastAPI TestClient limitations: Known async incompatibility
- Docker healthcheck best practices
- Python JSON logging standards
