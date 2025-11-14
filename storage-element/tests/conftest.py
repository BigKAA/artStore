"""
Pytest configuration and shared fixtures for Storage Element tests.

Provides:
- Database fixtures (test DB, sessions)
- FastAPI test client
- Mock services
- Test data generators
"""

import os
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Generator
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.file_metadata import FileMetadata
from app.models.storage_config import StorageConfig
from app.models.wal import WALTransaction


# ==========================================
# Test Settings Override
# ==========================================

@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """
    Override settings for test environment.

    Returns:
        Settings: Test-specific configuration
    """
    test_db_url = "sqlite+aiosqlite:///:memory:"

    # Create temporary storage directory for tests
    temp_dir = tempfile.mkdtemp(prefix="artstore_test_")

    # Override settings
    settings.db.url = test_db_url
    settings.storage.type = "local"
    settings.storage.local_base_path = temp_dir
    settings.app.debug = True

    return settings


# ==========================================
# Database Fixtures
# ==========================================

@pytest_asyncio.fixture(scope="function")
async def async_engine():
    """
    Create async SQLAlchemy engine for tests.

    Uses in-memory SQLite database with StaticPool for isolation.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Drop all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def async_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Create async SQLAlchemy session for tests.

    Args:
        async_engine: Test database engine

    Yields:
        AsyncSession: Test database session
    """
    AsyncSessionLocal = sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False
    )

    async with AsyncSessionLocal() as session:
        yield session


# ==========================================
# FastAPI Client Fixtures
# ==========================================

@pytest.fixture(scope="function")
def client(async_session) -> Generator[TestClient, None, None]:
    """
    Create FastAPI test client with database override.

    Args:
        async_session: Test database session

    Yields:
        TestClient: FastAPI test client
    """
    async def override_get_db():
        yield async_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def async_client(async_session) -> AsyncGenerator[AsyncClient, None]:
    """
    Create async HTTPX client for async tests.

    Args:
        async_session: Test database session

    Yields:
        AsyncClient: Async HTTP test client
    """
    async def override_get_db():
        yield async_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ==========================================
# Storage Fixtures
# ==========================================

@pytest.fixture(scope="function")
def temp_storage_dir() -> Generator[Path, None, None]:
    """
    Create temporary storage directory for file tests.

    Yields:
        Path: Temporary storage directory path
    """
    temp_dir = tempfile.mkdtemp(prefix="artstore_storage_")
    yield Path(temp_dir)

    # Cleanup
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope="function")
def sample_file_content() -> bytes:
    """
    Generate sample file content for tests.

    Returns:
        bytes: Sample file content
    """
    return b"This is a test file content for Storage Element testing.\n" * 100


@pytest.fixture(scope="function")
def sample_file(temp_storage_dir, sample_file_content) -> Path:
    """
    Create sample file in temporary storage.

    Args:
        temp_storage_dir: Temporary storage directory
        sample_file_content: File content

    Returns:
        Path: Path to sample file
    """
    file_path = temp_storage_dir / "test_file.txt"
    file_path.write_bytes(sample_file_content)
    return file_path


# ==========================================
# JWT Authentication Fixtures
# ==========================================

@pytest.fixture(scope="session")
def test_jwt_keys() -> tuple[str, str]:
    """
    Generate RSA key pair for JWT testing.

    Returns:
        tuple: (private_key_pem, public_key_pem)
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.backends import default_backend

    # Generate RSA key pair
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )

    # Export private key
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode('utf-8')

    # Export public key
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode('utf-8')

    return private_pem, public_pem


@pytest.fixture(scope="function")
def test_jwt_token(test_jwt_keys) -> str:
    """
    Generate valid JWT token for testing.

    Args:
        test_jwt_keys: RSA key pair

    Returns:
        str: Valid JWT access token
    """
    import jwt
    from datetime import datetime, timedelta

    private_key, _ = test_jwt_keys

    payload = {
        "sub": "1",
        "username": "testuser",
        "email": "test@artstore.local",
        "role": "user",
        "type": "access",
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=1),
        "nbf": datetime.utcnow()
    }

    token = jwt.encode(payload, private_key, algorithm="RS256")
    return token


@pytest.fixture(scope="function")
def admin_jwt_token(test_jwt_keys) -> str:
    """
    Generate admin JWT token for testing.

    Args:
        test_jwt_keys: RSA key pair

    Returns:
        str: Valid JWT admin token
    """
    import jwt
    from datetime import datetime, timedelta

    private_key, _ = test_jwt_keys

    payload = {
        "sub": "1",
        "username": "admin",
        "email": "admin@artstore.local",
        "role": "admin",
        "type": "access",
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=1),
        "nbf": datetime.utcnow()
    }

    token = jwt.encode(payload, private_key, algorithm="RS256")
    return token


@pytest.fixture(scope="function")
def auth_headers(test_jwt_token: str) -> dict:
    """
    Create authorization headers with JWT token.

    Args:
        test_jwt_token: Valid JWT token

    Returns:
        dict: Headers with Bearer token
    """
    return {"Authorization": f"Bearer {test_jwt_token}"}


@pytest.fixture(scope="function")
def admin_auth_headers(admin_jwt_token: str) -> dict:
    """
    Create admin authorization headers with JWT token.

    Args:
        admin_jwt_token: Valid admin JWT token

    Returns:
        dict: Headers with admin Bearer token
    """
    return {"Authorization": f"Bearer {admin_jwt_token}"}


# ==========================================
# Database Model Fixtures
# ==========================================

@pytest_asyncio.fixture(scope="function")
async def sample_file_metadata(async_session: AsyncSession) -> FileMetadata:
    """
    Create sample FileMetadata record in database.

    Args:
        async_session: Test database session

    Returns:
        FileMetadata: Sample file metadata record
    """
    metadata = FileMetadata(
        id=str(uuid4()),
        storage_element_id="test-storage-01",
        original_filename="test_document.pdf",
        storage_filename="test_document_testuser_20250111T120000_abc123.pdf",
        storage_path="2025/01/11/12/test_document_testuser_20250111T120000_abc123.pdf",
        mime_type="application/pdf",
        size_bytes=1024,
        checksum_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        uploaded_by="testuser",
        tags=["test", "document"],
        description="Test document for unit testing"
    )

    async_session.add(metadata)
    await async_session.commit()
    await async_session.refresh(metadata)

    return metadata


@pytest_asyncio.fixture(scope="function")
async def sample_storage_config(async_session: AsyncSession) -> StorageConfig:
    """
    Create sample StorageConfig record in database.

    Args:
        async_session: Test database session

    Returns:
        StorageConfig: Sample storage configuration
    """
    config = StorageConfig(
        id="test-storage-01",
        mode="edit",
        is_master=True
    )

    async_session.add(config)
    await async_session.commit()
    await async_session.refresh(config)

    return config


# ==========================================
# Mock Service Fixtures
# ==========================================

@pytest.fixture(scope="function")
def mock_redis():
    """
    Mock Redis client for testing.

    Returns:
        Mock: Redis mock object
    """
    from unittest.mock import MagicMock

    redis_mock = MagicMock()
    redis_mock.get.return_value = None
    redis_mock.set.return_value = True
    redis_mock.delete.return_value = 1
    redis_mock.exists.return_value = False

    return redis_mock


# ==========================================
# Pytest Configuration
# ==========================================

def pytest_configure(config):
    """
    Configure pytest markers.
    """
    config.addinivalue_line(
        "markers", "unit: mark test as a unit test"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "asyncio: mark test as async"
    )
