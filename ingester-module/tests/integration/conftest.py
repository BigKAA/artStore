"""
Integration test fixtures and configuration.

Provides fixtures for E2E testing with mock services.

Sprint 16: Добавлен mock_auth_service для тестов UploadService без реального Admin Module.
"""

import pytest
from httpx import AsyncClient
from app.main import app
from datetime import datetime, timezone, timedelta
import jwt as pyjwt
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
async def client():
    """
    AsyncClient для integration тестов с реальным FastAPI приложением.

    Usage:
        async def test_upload(client):
            response = await client.post("/api/v1/upload", ...)
            assert response.status_code == 200
    """
    from fastapi.testclient import TestClient
    from httpx import ASGITransport

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_admin_url():
    """Mock Admin Module URL (из docker-compose.test.yml)."""
    return "http://mock-admin:8000"


@pytest.fixture
def mock_storage_url():
    """Mock Storage Element URL (из docker-compose.test.yml)."""
    return "http://mock-storage:8010"


@pytest.fixture
def test_jwt_token(rsa_keys):
    """
    Генерация валидного JWT токена для integration тестов.

    Использует RSA ключи для создания реального токена.
    """
    private_key = rsa_keys["private_pem"]

    now = datetime.now(timezone.utc)
    payload = {
        "sub": "test-user-id",
        "username": "testuser",
        "role": "USER",
        "email": "testuser@example.com",
        "type": "access",
        "iat": now,
        "exp": now + timedelta(hours=1),
        "nbf": now,
        "jti": "test-token-id"
    }

    token = pyjwt.encode(payload, private_key, algorithm="RS256")
    return token


@pytest.fixture
def auth_headers(test_jwt_token):
    """
    HTTP headers с Authorization для authenticated requests.

    Usage:
        response = await client.post("/api/v1/upload", headers=auth_headers, ...)
    """
    return {
        "Authorization": f"Bearer {test_jwt_token}"
    }


@pytest.fixture
def sample_file_content():
    """Тестовый контент файла для upload тестов."""
    return b"This is a test file content for integration testing."


@pytest.fixture
def sample_multipart_file(sample_file_content):
    """
    Multipart file data для upload requests.

    Returns:
        dict: {"file": (filename, content, content_type)}
    """
    return {
        "file": ("test_file.txt", sample_file_content, "text/plain")
    }


@pytest.fixture
def rsa_keys(tmp_path):
    """
    Генерация RSA ключевой пары для JWT тестов.

    Создает временные файлы с ключами и возвращает их пути.
    """
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend

    # Генерация RSA ключевой пары
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )

    public_key = private_key.public_key()

    # Сериализация приватного ключа
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

    # Сериализация публичного ключа
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    # Сохранение ключей во временные файлы
    private_key_file = tmp_path / "private_key.pem"
    public_key_file = tmp_path / "public_key.pem"

    private_key_file.write_bytes(private_pem)
    public_key_file.write_bytes(public_pem)

    return {
        "private_pem": private_pem,
        "public_pem": public_pem,
        "private_key_file": str(private_key_file),
        "public_key_file": str(public_key_file)
    }


@pytest.fixture(autouse=True)
def setup_test_keys(rsa_keys, monkeypatch):
    """
    Автоматически настраивает публичный ключ для всех integration тестов.

    Патчит settings.auth.public_key_path для использования тестового ключа.
    """
    from app.core import config
    monkeypatch.setattr(
        config.settings.auth,
        'public_key_path',
        rsa_keys["public_key_file"]
    )


@pytest.fixture
async def mock_storage_response():
    """
    Ожидаемый response от Mock Storage Element.

    Соответствует конфигурации в tests/mocks/storage-mock.json
    """
    return {
        "file_id": "550e8400-e29b-41d4-a716-446655440000",
        "original_filename": "test-file.txt",
        "storage_filename": "test-file_testuser_20250114T120000_abc123.txt",
        "file_size": 1024,
        "compressed": False,
        "checksum": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "uploaded_at": "2025-01-14T12:00:00Z",
        "storage_element_url": "http://mock-storage:8010"
    }


@pytest.fixture
async def mock_admin_token_response():
    """
    Ожидаемый response от Mock Admin Module для OAuth 2.0 token endpoint.

    Соответствует конфигурации в tests/mocks/admin-mock.json
    """
    return {
        "access_token": "mock-jwt-token-eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9",
        "token_type": "Bearer",
        "expires_in": 1800
    }


@pytest.fixture
def mock_auth_service():
    """
    Mock AuthService для тестов UploadService без реального Admin Module.

    Sprint 16: Используется для тестов, которые не требуют E2E аутентификации.
    """
    from app.services.auth_service import AuthService

    mock = MagicMock(spec=AuthService)
    mock.get_token = AsyncMock(return_value="mock-jwt-token")
    mock.close = AsyncMock()
    return mock


@pytest.fixture
def upload_service_with_mock_auth(mock_auth_service):
    """
    UploadService с mock AuthService для unit/integration тестов.

    Sprint 16: Для тестов HTTP client без реальной аутентификации.
    """
    from app.services.upload_service import UploadService

    service = UploadService(auth_service=mock_auth_service)
    return service
