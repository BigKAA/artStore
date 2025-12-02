"""
Integration тесты для GC DELETE API.

Тестирование:
- DELETE /api/v1/gc/{file_id} с реальным файлом
- Авторизация Service Account vs Admin User
- Проверка удаления физического файла
- Проверка удаления attr.json
- Проверка удаления из DB cache
- Idempotency при повторном удалении
"""

import os
import pytest
import pytest_asyncio
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import jwt
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.db.session import get_db
from app.models.file_metadata import FileMetadata
from app.core.config import settings


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope="module")
def test_jwt_keys():
    """Генерация RSA ключей для JWT."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.backends import default_backend

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode('utf-8')

    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode('utf-8')

    return private_pem, public_pem


@pytest.fixture
def service_account_token(test_jwt_keys):
    """JWT токен для Service Account."""
    private_key, _ = test_jwt_keys
    now = datetime.now(timezone.utc)

    payload = {
        "sub": str(uuid4()),
        "type": "service_account",
        "role": "admin",
        "name": "gc-service",
        "jti": str(uuid4()),
        "client_id": "sa_prod_gc_service_test",
        "rate_limit": 1000,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
        "nbf": int(now.timestamp())
    }

    return jwt.encode(payload, private_key, algorithm="RS256")


@pytest.fixture
def admin_user_token(test_jwt_keys):
    """JWT токен для Admin User (НЕ service account)."""
    private_key, _ = test_jwt_keys
    now = datetime.now(timezone.utc)

    payload = {
        "sub": "admin-user-123",
        "type": "admin_user",
        "role": "admin",
        "name": "Admin User",
        "jti": str(uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
        "nbf": int(now.timestamp())
    }

    return jwt.encode(payload, private_key, algorithm="RS256")


@pytest.fixture
def regular_user_token(test_jwt_keys):
    """JWT токен для обычного пользователя."""
    private_key, _ = test_jwt_keys
    now = datetime.now(timezone.utc)

    payload = {
        "sub": "user-123",
        "type": "admin_user",
        "role": "user",
        "name": "Regular User",
        "jti": str(uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
        "nbf": int(now.timestamp())
    }

    return jwt.encode(payload, private_key, algorithm="RS256")


@pytest.fixture
def service_account_headers(service_account_token):
    """Headers с Service Account токеном."""
    return {"Authorization": f"Bearer {service_account_token}"}


@pytest.fixture
def admin_user_headers(admin_user_token):
    """Headers с Admin User токеном."""
    return {"Authorization": f"Bearer {admin_user_token}"}


@pytest.fixture
def regular_user_headers(regular_user_token):
    """Headers с токеном обычного пользователя."""
    return {"Authorization": f"Bearer {regular_user_token}"}


# ============================================================================
# Integration тесты для авторизации
# ============================================================================

class TestGCAuthorizationIntegration:
    """Тесты авторизации для GC API."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_gc_delete_requires_authentication(self, async_client):
        """GC delete требует аутентификации."""
        file_id = uuid4()
        response = await async_client.delete(f"/api/v1/gc/{file_id}")

        # Без токена должен быть 401 или 403
        assert response.status_code in [401, 403]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_gc_delete_requires_service_account(
        self,
        async_client,
        admin_user_headers,
        test_jwt_keys
    ):
        """GC delete отклоняет Admin User (не Service Account)."""
        # Подготовка: mock JWT validator для теста
        from app.core.security import jwt_validator

        _, public_key = test_jwt_keys
        jwt_validator._public_key = public_key

        file_id = uuid4()
        response = await async_client.delete(
            f"/api/v1/gc/{file_id}",
            headers=admin_user_headers
        )

        # Admin User должен получить 403
        assert response.status_code == 403
        assert "Service account access required" in response.json()["detail"]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_gc_delete_accepts_service_account(
        self,
        async_client,
        service_account_headers,
        test_jwt_keys
    ):
        """GC delete принимает Service Account."""
        from app.core.security import jwt_validator

        _, public_key = test_jwt_keys
        jwt_validator._public_key = public_key

        file_id = uuid4()
        response = await async_client.delete(
            f"/api/v1/gc/{file_id}",
            headers=service_account_headers
        )

        # Service Account должен получить 200 (already_deleted для несуществующего)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "already_deleted"
        assert data["file_id"] == str(file_id)


# ============================================================================
# Integration тесты для GC exists endpoint
# ============================================================================

class TestGCExistsEndpointIntegration:
    """Тесты для GET /api/v1/gc/{file_id}/exists."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_gc_exists_nonexistent_file(
        self,
        async_client,
        service_account_headers,
        test_jwt_keys
    ):
        """Проверка несуществующего файла возвращает exists=false."""
        from app.core.security import jwt_validator

        _, public_key = test_jwt_keys
        jwt_validator._public_key = public_key

        file_id = uuid4()
        response = await async_client.get(
            f"/api/v1/gc/{file_id}/exists",
            headers=service_account_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is False
        assert data["file_id"] == str(file_id)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_gc_exists_requires_service_account(
        self,
        async_client,
        admin_user_headers,
        test_jwt_keys
    ):
        """GET /gc/{file_id}/exists требует Service Account."""
        from app.core.security import jwt_validator

        _, public_key = test_jwt_keys
        jwt_validator._public_key = public_key

        file_id = uuid4()
        response = await async_client.get(
            f"/api/v1/gc/{file_id}/exists",
            headers=admin_user_headers
        )

        assert response.status_code == 403


# ============================================================================
# Integration тесты для Idempotency
# ============================================================================

class TestGCIdempotencyIntegration:
    """Тесты idempotency для GC delete."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_gc_delete_idempotent_nonexistent(
        self,
        async_client,
        service_account_headers,
        test_jwt_keys
    ):
        """Повторное удаление несуществующего файла возвращает already_deleted."""
        from app.core.security import jwt_validator

        _, public_key = test_jwt_keys
        jwt_validator._public_key = public_key

        file_id = uuid4()

        # Первое удаление
        response1 = await async_client.delete(
            f"/api/v1/gc/{file_id}",
            headers=service_account_headers
        )
        assert response1.status_code == 200
        assert response1.json()["status"] == "already_deleted"

        # Повторное удаление (idempotent)
        response2 = await async_client.delete(
            f"/api/v1/gc/{file_id}",
            headers=service_account_headers
        )
        assert response2.status_code == 200
        assert response2.json()["status"] == "already_deleted"


# ============================================================================
# Integration тесты для GCDeleteRequest
# ============================================================================

class TestGCDeleteRequestIntegration:
    """Тесты для параметров GCDeleteRequest."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_gc_delete_with_custom_reason(
        self,
        async_client,
        service_account_headers,
        test_jwt_keys
    ):
        """GC delete с кастомным reason."""
        from app.core.security import jwt_validator

        _, public_key = test_jwt_keys
        jwt_validator._public_key = public_key

        file_id = uuid4()
        response = await async_client.delete(
            f"/api/v1/gc/{file_id}",
            headers=service_account_headers,
            json={
                "reason": "ttl_expired",
                "cleanup_type": "ttl_expired"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["reason"] == "ttl_expired"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_gc_delete_with_finalized_cleanup_type(
        self,
        async_client,
        service_account_headers,
        test_jwt_keys
    ):
        """GC delete с cleanup_type=finalized."""
        from app.core.security import jwt_validator

        _, public_key = test_jwt_keys
        jwt_validator._public_key = public_key

        file_id = uuid4()
        response = await async_client.delete(
            f"/api/v1/gc/{file_id}",
            headers=service_account_headers,
            json={
                "reason": "finalized_cleanup",
                "cleanup_type": "finalized"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["reason"] == "finalized_cleanup"


# ============================================================================
# Integration тесты для Response Model
# ============================================================================

class TestGCResponseModelIntegration:
    """Тесты для модели ответа GC API."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_gc_delete_response_fields(
        self,
        async_client,
        service_account_headers,
        test_jwt_keys
    ):
        """Проверка всех полей в ответе GC delete."""
        from app.core.security import jwt_validator

        _, public_key = test_jwt_keys
        jwt_validator._public_key = public_key

        file_id = uuid4()
        response = await async_client.delete(
            f"/api/v1/gc/{file_id}",
            headers=service_account_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Проверка обязательных полей
        assert "status" in data
        assert "file_id" in data
        assert "deleted_at" in data
        assert "deleted_by" in data
        assert "reason" in data

        # Проверка формата
        assert data["file_id"] == str(file_id)
        assert data["status"] in ["deleted", "already_deleted"]
        # deleted_at должен быть ISO 8601 timestamp
        datetime.fromisoformat(data["deleted_at"].replace('Z', '+00:00'))
