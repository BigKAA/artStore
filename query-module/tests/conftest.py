"""
Query Module - Test Fixtures.

Shared fixtures для всех тестов:
- Mock database sessions
- Mock Redis connections
- JWT tokens для аутентификации
- Test data generators
"""

import os
from pathlib import Path
import tempfile

# ========================================
# CRITICAL: Setup BEFORE any app imports
# ========================================

# Create temporary public key file BEFORE importing app modules
public_key_content = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAqXDrQgyOZKpjIRz2uwXD
Jbu6/QPSOwvArP/ETWnGrckYmTSEgkXQM0WF3eYZnA3C1h2FkVImeOU7w0m3cY+8
7nDYqDI++z8ns+bZzz4B+vTsMnbGzAfyDbVPy53mVUyTOT9Vt/+Ll0CAeXRgeNyj
hGjIAs0ARY/TQSdYNcscHuRxL0hzOxlh3Ioe56g7kGNxOrhyRfIAnhGEnXvIaynG
uXs7LJXIhlN1PDS1Mx+fEDR8lyDkFXUgz0HCHcMc7IxFpceJli+4sKiieRxbkqam
ZTlSIIJakpwUHwnr2t6HcyWISThPlEkOl3jyXH02cCifhbcwbmZCz9D23ujb7qni
jQIDAQAB
-----END PUBLIC KEY-----"""

# Create temp file and set env var
temp_key_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.pem')
temp_key_file.write(public_key_content)
temp_key_file.flush()
_temp_key_path = temp_key_file.name
temp_key_file.close()

os.environ["AUTH_PUBLIC_KEY_PATH"] = _temp_key_path

# NOW import pytest and other modules
import pytest
from datetime import datetime, timezone, timedelta
from typing import AsyncGenerator, Generator
from unittest.mock import Mock, AsyncMock, MagicMock, patch

import jwt
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

# NOW safe to import app modules
from app.main import app
from app.db.database import Base, get_db_session
from app.core.security import UserContext, UserRole, TokenType
from app.core.config import settings


# ========================================
# Database Fixtures
# ========================================

@pytest.fixture(scope="function")
async def async_engine():
    """Async SQLite engine для тестов (in-memory)."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        echo=False
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture(scope="function")
async def async_session(async_engine) -> AsyncSession:
    """
    Async database session для тестов.

    Returns session directly (not generator) для использования в тестах.
    """
    async_session_maker = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    async with async_session_maker() as session:
        yield session
        await session.rollback()


@pytest.fixture
def override_get_db(async_session):
    """
    Override get_db_session dependency для FastAPI.

    ВАЖНО: Возвращает функцию которая yields async_session.
    """
    async def _override_get_db():
        yield async_session

    return _override_get_db


# ========================================
# Authentication Fixtures
# ========================================

@pytest.fixture
def private_key() -> str:
    """Mock RSA private key для генерации JWT токенов."""
    return """-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQCpcOtCDI5kqmMh
HPa7BcMlu7r9A9I7C8Cs/8RNacatyRiZNISCRdAzRYXd5hmcDcLWHYWRUiZ45TvD
Sbdxj7zucNioMj77Pyez5tnPPgH69OwydsbMB/INtU/LneZVTJM5P1W3/4uXQIB5
dGB43KOEaMgCzQBFj9NBJ1g1yxwe5HEvSHM7GWHcih7nqDuQY3E6uHJF8gCeEYSd
e8hrKca5ezsslciGU3U8NLUzH58QNHyXIOQVdSDPQcIdwxzsjEWlx4mWL7iwqKJ5
HFuSpqZlOVIgglqSnBQfCeva3odzJYhJOE+USQ6XePJcfTZwKJ+FtzBuZkLP0Pbe
6NvuqeKNAgMBAAECggEANFFA2rJ8zvlLRWCnkCSd1ktKV7Az2/Zrhh8s8ggsh+FV
PozYM08yE3qudE8FbklTdQBFixLV/TMuikR7J03N9MOUKg7lonckH6iybQqE2wN/
4K8K/9meM/xdSI4XHhRYSu9S3M7DP67zXE0CMp9Rv+MIitDYeiIIBRCMbIOryZ+X
o4QKNBaTIVswgWgH8FrtMxmABt2p+B4DbxVyMoXJYIg+ytvcp/NGHCfpupNJSvyB
w2o3YSIYjv8rpH/VABZ3gdyfPl2oGxtpbfvAKgK/XWFeuZvav2isKlYd3HirJgI8
vvWPKn5AJ0QDFLGk/2IApJ1OJn1Nzxpr36KrweSwEwKBgQDfTeVCw2ZzMCR+E8oy
LkR2benIvMgv+/OObj5XuFttci4GjQg0EpMEVOsckrhYPZv4udVgurADeDqe/ojK
u5rczrJF4D2Ap52P3IHminuPdRkSgkCufSMB7qDZvxRtDVmV3jEOfucAKqtq5mJB
HcPGrz0VXSdIT9K4uIo+rOhslwKBgQDCQBJlpQLtqYcI+D6y5vpAx2V8fLZZ39xS
NPjxqDx/Ca7kinfYYMAxjea8dFb1XzBxzLwqte8DLStF6qAJDntkpgVNyzN/owgK
1SnxfU4sKJJo/MI9epf6AayHpfA5ucaSx7S5P6uQNjYntzlBTbnHh5rRZYv4C/4u
CCBxL6i6ewKBgQCISQRJMPSQDKvY/r8CzVYfaYmrZ/xNvNmy7fnCk9PJAkyw1tZQ
4Z00oZc0wx8bS86riM9/z7CpDXHJo9Nc2A72AHixSOCAaswxBwWI7K/oqDD7KN/N
HraE8VzeSE5xGBq66vbJwA2//krMXXtN/pqD4mPHbCkTaxRShN5qziC0VQKBgGL9
r+JowyNGf3BMwfb9yo50jv1vuKX4dRjXsf3E1H+Q+bWx8v0r4QXf4LQtPZtx1QhJ
Y6MIcDNYM3M/7CpxXOSfzpgkc6wZ8yFCHEvapZnPWz1xgbM+5HAdpkTChbeFOvLW
Hv1AuzeUyOhYcS8cYw6Rxo3rh/bydagTsCS+Oug9AoGAY5Fal3++gu2yuTeOREEq
/0qV3kdvhl8WjSvL5bOFVPWT2kPpTTeRBeN4VifBoQnDaOJc9yafF7NEY3RhPGUl
3QU4hNBdtR+me70QJk6idsCdXiX6rm/XGYrM2vmA3adO1/dIxPI7YuKpvEa9bBDz
FUv3CGXG4YfuXPuA1Mh5hFc=
-----END PRIVATE KEY-----"""


@pytest.fixture
def public_key() -> str:
    """Mock RSA public key для валидации JWT токенов."""
    return """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAqXDrQgyOZKpjIRz2uwXD
Jbu6/QPSOwvArP/ETWnGrckYmTSEgkXQM0WF3eYZnA3C1h2FkVImeOU7w0m3cY+8
7nDYqDI++z8ns+bZzz4B+vTsMnbGzAfyDbVPy53mVUyTOT9Vt/+Ll0CAeXRgeNyj
hGjIAs0ARY/TQSdYNcscHuRxL0hzOxlh3Ioe56g7kGNxOrhyRfIAnhGEnXvIaynG
uXs7LJXIhlN1PDS1Mx+fEDR8lyDkFXUgz0HCHcMc7IxFpceJli+4sKiieRxbkqam
ZTlSIIJakpwUHwnr2t6HcyWISThPlEkOl3jyXH02cCifhbcwbmZCz9D23ujb7qni
jQIDAQAB
-----END PUBLIC KEY-----"""


@pytest.fixture
def valid_jwt_token(private_key) -> str:
    """
    Валидный JWT токен для тестов.

    Включает все обязательные поля UnifiedJWTPayload:
    - sub, type, role, name, jti, iat, exp, nbf
    """
    import uuid
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "test-user-id",
        "type": "admin_user",  # Unified type (admin_user или service_account)
        "role": "USER",
        "name": "testuser",  # Обязательное поле для display name
        "jti": str(uuid.uuid4()),  # JWT ID для revocation
        "iat": int(now.timestamp()),  # Целочисленный timestamp
        "exp": int((now + timedelta(minutes=30)).timestamp()),
        "nbf": int(now.timestamp()),
        # Backward compatibility (deprecated)
        "username": "testuser",
        "email": "test@example.com",
        "client_id": "test-client"
    }

    return jwt.encode(payload, private_key, algorithm="RS256")


@pytest.fixture
def expired_jwt_token(private_key) -> str:
    """
    Истекший JWT токен для тестов.

    Включает все обязательные поля UnifiedJWTPayload.
    """
    import uuid
    now = datetime.now(timezone.utc)
    past = now - timedelta(hours=2)
    payload = {
        "sub": "test-user-id",
        "type": "admin_user",
        "role": "USER",
        "name": "testuser",
        "jti": str(uuid.uuid4()),
        "iat": int(past.timestamp()),
        "exp": int((now - timedelta(hours=1)).timestamp()),  # Истекший
        "nbf": int(past.timestamp()),
        "username": "testuser",
        "client_id": "test-client"
    }

    return jwt.encode(payload, private_key, algorithm="RS256")


@pytest.fixture
def user_context() -> UserContext:
    """Mock UserContext для тестов."""
    now = datetime.now(timezone.utc)
    return UserContext(
        sub="test-user-id",
        username="testuser",
        email="test@example.com",
        role=UserRole.USER,
        type=TokenType.ACCESS,
        iat=now,
        exp=now + timedelta(minutes=30),
        nbf=now
    )


@pytest.fixture
def admin_context() -> UserContext:
    """Mock Admin UserContext для тестов."""
    now = datetime.now(timezone.utc)
    return UserContext(
        sub="admin-user-id",
        username="adminuser",
        email="admin@example.com",
        role=UserRole.ADMIN,
        type=TokenType.ACCESS,
        iat=now,
        exp=now + timedelta(minutes=30),
        nbf=now
    )


# ========================================
# Service Fixtures
# ========================================

@pytest.fixture
def mock_redis():
    """Mock Redis client для тестов."""
    redis_mock = MagicMock()
    redis_mock.ping.return_value = True
    redis_mock.get.return_value = None
    redis_mock.setex.return_value = True
    redis_mock.delete.return_value = 1
    return redis_mock


@pytest.fixture
def mock_cache_service(mock_redis):
    """Mock CacheService для тестов."""
    from app.services.cache_service import CacheService
    
    cache_service = CacheService()
    if cache_service.redis_cache:
        cache_service.redis_cache._redis_client = mock_redis
        cache_service.redis_cache._is_available = True
    
    return cache_service


@pytest.fixture
def mock_http_client():
    """Mock HTTP client для Download Service."""
    client_mock = AsyncMock()
    client_mock.get = AsyncMock()
    client_mock.stream = AsyncMock()
    return client_mock


# ========================================
# Test Data Fixtures
# ========================================

@pytest.fixture
def sample_file_metadata() -> dict:
    """Sample file metadata для тестов."""
    return {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "filename": "test-document.pdf",
        "storage_filename": "test-document_testuser_20250115T120000_550e8400.pdf",
        "file_size": 1024000,
        "mime_type": "application/pdf",
        "sha256_hash": "a" * 64,
        "username": "testuser",
        "tags": ["test", "document", "pdf"],
        "description": "Test document for unit tests",
        "storage_element_id": "storage-01",
        "storage_element_url": "http://storage-element:8010",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    }


@pytest.fixture
def sample_search_request() -> dict:
    """Sample search request для тестов."""
    return {
        "query": "test document",
        "mode": "partial",
        "limit": 100,
        "offset": 0,
        "sort_by": "created_at",
        "sort_order": "desc"
    }


# ========================================
# FastAPI Test Client
# ========================================

@pytest.fixture
def test_client(override_get_db) -> TestClient:
    """FastAPI test client с override dependencies."""
    app.dependency_overrides[get_db_session] = override_get_db
    
    client = TestClient(app)
    yield client
    
    app.dependency_overrides.clear()


# ========================================
# Utility Fixtures
# ========================================

@pytest.fixture
def freeze_time():
    """Fixture для фиксации времени в тестах."""
    frozen_time = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    
    def _freeze():
        return frozen_time
    
    return _freeze
