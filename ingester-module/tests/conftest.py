"""
Pytest configuration and shared fixtures for Ingester Module tests.

Provides:
- FastAPI test client fixtures
- JWT authentication fixtures
- Test file generators
- Mock services for Storage Element
"""

import io
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import AsyncGenerator, Dict
from uuid import uuid4

# Sprint 23: Set default test environment variables BEFORE importing app modules
os.environ.setdefault("APP_DEBUG", "on")  # Boolean format: on/off
os.environ.setdefault("LOG_FORMAT", "text")
os.environ.setdefault("LOG_LEVEL", "DEBUG")
os.environ.setdefault("SERVICE_ACCOUNT_CLIENT_ID", "test-client-id")
os.environ.setdefault("SERVICE_ACCOUNT_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("SERVICE_ACCOUNT_ADMIN_MODULE_URL", "http://test-admin:8000")

import pytest
import pytest_asyncio
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from httpx import AsyncClient
import jwt as pyjwt

from app.core.config import settings
from app.main import app


# ==========================================
# Test Settings Override
# ==========================================

@pytest.fixture(scope="session", autouse=True)
def test_environment_setup():
    """
    Configure test environment variables before app initialization.

    Sets up:
    - Debug mode enabled
    - Test logging format
    - Disabled auth for some tests (optional)
    - Service account test credentials (Sprint 23)
    """
    # Ensure debug mode for tests
    os.environ["APP_DEBUG"] = "true"
    os.environ["LOG_FORMAT"] = "text"
    os.environ["LOG_LEVEL"] = "DEBUG"

    # Service Account test credentials (Sprint 23: for metrics tests)
    os.environ.setdefault("SERVICE_ACCOUNT__CLIENT_ID", "test-client-id")
    os.environ.setdefault("SERVICE_ACCOUNT__CLIENT_SECRET", "test-client-secret")
    os.environ.setdefault("SERVICE_ACCOUNT__ADMIN_MODULE_URL", "http://test-admin:8000")

    yield

    # Cleanup after tests
    pass


# ==========================================
# JWT Test Infrastructure
# ==========================================

@pytest.fixture(scope="session")
def test_rsa_keys():
    """
    Generate RSA key pair for JWT testing.

    Returns:
        tuple: (private_key, public_key) both as PEM-encoded bytes
    """
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
    )

    # Export public key
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    return private_pem, public_pem


@pytest.fixture(scope="session")
def test_public_key_file(test_rsa_keys, tmp_path_factory) -> Path:
    """
    Create temporary public key file for JWT validation.

    Args:
        test_rsa_keys: RSA key pair fixture
        tmp_path_factory: Pytest temporary path factory

    Returns:
        Path: Path to temporary public_key.pem file
    """
    _, public_pem = test_rsa_keys

    # Create temporary keys directory
    keys_dir = tmp_path_factory.mktemp("keys")
    public_key_path = keys_dir / "public_key.pem"

    # Write public key
    public_key_path.write_bytes(public_pem)

    # Override settings to use test public key
    settings.auth.public_key_path = public_key_path

    return public_key_path


def generate_test_jwt_token(
    test_rsa_keys,
    user_id: str = "test-user-id",
    username: str = "testuser",
    role: str = "USER",
    email: str = "test@example.com",
    expires_delta: timedelta = timedelta(hours=1)
) -> str:
    """
    Generate JWT token for testing.

    Args:
        test_rsa_keys: RSA key pair from fixture
        user_id: User ID claim
        username: Username claim
        role: User role (ADMIN, OPERATOR, USER)
        email: User email
        expires_delta: Token expiration time

    Returns:
        str: JWT token string
    """
    private_pem, _ = test_rsa_keys

    # Create claims
    now = datetime.now(timezone.utc)
    claims = {
        "sub": user_id,
        "username": username,
        "role": role,
        "email": email,
        "token_type": "access",
        "iat": now,
        "exp": now + expires_delta,
        "jti": str(uuid4())
    }

    # Encode token with RS256
    token = pyjwt.encode(
        claims,
        private_pem,
        algorithm="RS256"
    )

    return token


@pytest.fixture
def test_jwt_token(test_rsa_keys, test_public_key_file) -> str:
    """
    Generate valid JWT token for testing.

    Returns:
        str: Valid JWT access token
    """
    return generate_test_jwt_token(
        test_rsa_keys,
        user_id="test-user-123",
        username="testuser",
        role="USER",
        email="test@example.com"
    )


@pytest.fixture
def admin_jwt_token(test_rsa_keys, test_public_key_file) -> str:
    """
    Generate JWT token with ADMIN role.

    Returns:
        str: Valid JWT access token with ADMIN role
    """
    return generate_test_jwt_token(
        test_rsa_keys,
        user_id="admin-user-123",
        username="admin",
        role="ADMIN",
        email="admin@example.com"
    )


@pytest.fixture
def expired_jwt_token(test_rsa_keys, test_public_key_file) -> str:
    """
    Generate expired JWT token for testing.

    Returns:
        str: Expired JWT token
    """
    return generate_test_jwt_token(
        test_rsa_keys,
        expires_delta=timedelta(seconds=-3600)  # Expired 1 hour ago
    )


@pytest.fixture
def auth_headers(test_jwt_token) -> Dict[str, str]:
    """
    Create authorization headers with valid JWT token.

    Args:
        test_jwt_token: Valid JWT token fixture

    Returns:
        dict: Headers with Bearer token
    """
    return {"Authorization": f"Bearer {test_jwt_token}"}


@pytest.fixture
def admin_auth_headers(admin_jwt_token) -> Dict[str, str]:
    """
    Create authorization headers with admin JWT token.

    Args:
        admin_jwt_token: Admin JWT token fixture

    Returns:
        dict: Headers with admin Bearer token
    """
    return {"Authorization": f"Bearer {admin_jwt_token}"}


# ==========================================
# FastAPI Test Client Fixtures
# ==========================================

@pytest.fixture(scope="function")
def test_client() -> TestClient:
    """
    Create FastAPI test client (synchronous).

    Returns:
        TestClient: Synchronous test client for FastAPI app
    """
    return TestClient(app)


@pytest_asyncio.fixture(scope="function")
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """
    Create async HTTP client for testing.

    Yields:
        AsyncClient: Async HTTP client for FastAPI app
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


# ==========================================
# Test File Fixtures
# ==========================================

@pytest.fixture
def test_file_small() -> io.BytesIO:
    """
    Generate small test file (1KB).

    Returns:
        BytesIO: Small test file content
    """
    content = b"Test file content " * 50  # ~1KB
    return io.BytesIO(content)


@pytest.fixture
def test_file_medium() -> io.BytesIO:
    """
    Generate medium test file (1MB).

    Returns:
        BytesIO: Medium test file content
    """
    content = b"A" * (1024 * 1024)  # 1MB
    return io.BytesIO(content)


@pytest.fixture
def test_file_large() -> io.BytesIO:
    """
    Generate large test file (10MB).

    Returns:
        BytesIO: Large test file content
    """
    content = b"B" * (10 * 1024 * 1024)  # 10MB
    return io.BytesIO(content)


@pytest.fixture
def test_pdf_file() -> io.BytesIO:
    """
    Generate minimal valid PDF file for testing.

    Returns:
        BytesIO: Minimal PDF file
    """
    # Minimal PDF structure
    pdf_content = b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj
2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj
3 0 obj
<<
/Type /Page
/Parent 2 0 R
/Resources <<
/Font <<
/F1 <<
/Type /Font
/Subtype /Type1
/BaseFont /Helvetica
>>
>>
>>
/MediaBox [0 0 612 792]
/Contents 4 0 R
>>
endobj
4 0 obj
<<
/Length 44
>>
stream
BT
/F1 12 Tf
100 700 Td
(Test PDF) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000317 00000 n
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
409
%%EOF
"""
    return io.BytesIO(pdf_content)


# ==========================================
# Mock Storage Element Fixtures
# ==========================================

@pytest.fixture
def mock_storage_element_response():
    """
    Mock successful Storage Element upload response.

    Returns:
        dict: Mocked upload response data
    """
    return {
        "file_id": str(uuid4()),
        "original_filename": "test.txt",
        "storage_filename": "test_testuser_20250114T120000_abc123.txt",
        "file_size": 1024,
        "checksum": "abc123def456",
        "compressed": False,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "storage_mode": "edit"
    }


# ==========================================
# Test Data Generators
# ==========================================

@pytest.fixture
def generate_upload_request():
    """
    Factory for generating upload request data.

    Returns:
        callable: Function to generate upload request dict
    """
    def _generate(
        description: str = "Test file upload",
        storage_mode: str = "edit",
        compress: bool = False,
        compression_algorithm: str = "gzip"
    ) -> dict:
        return {
            "description": description,
            "storage_mode": storage_mode,
            "compress": compress,
            "compression_algorithm": compression_algorithm
        }

    return _generate


# ==========================================
# Pytest Configuration
# ==========================================

@pytest.fixture(autouse=True)
def reset_settings_after_test():
    """
    Reset settings to default after each test.

    Ensures test isolation by resetting modified settings.
    """
    yield
    # Settings reset happens automatically via Settings class reinitialization
