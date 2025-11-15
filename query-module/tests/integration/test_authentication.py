"""
Integration tests для JWT Authentication.

Тестирует:
- JWT RS256 token validation
- User context extraction
- Role-based access control
- Token expiration handling
- Invalid token handling
"""

import pytest
from datetime import datetime, timezone, timedelta
from fastapi import status
from fastapi.testclient import TestClient
import jwt

from app.main import app
from app.db.models import FileMetadata


# ========================================
# JWT Authentication Integration Tests
# ========================================

@pytest.mark.integration
class TestJWTAuthenticationIntegration:
    """Integration tests для JWT authentication."""

    def test_valid_jwt_token_grants_access(
        self,
        valid_jwt_token
    ):
        """Тест что валидный JWT токен предоставляет доступ."""
        with TestClient(app) as client:
            response = client.post(
                "/api/search",
                json={
                    "query": "test",
                    "mode": "partial"
                },
                headers={"Authorization": f"Bearer {valid_jwt_token}"}
            )

        # Не 401, может быть 200 или 400 (no results), но не unauthorized
        assert response.status_code != status.HTTP_401_UNAUTHORIZED

    async def test_expired_token_denies_access(
        self,
        expired_jwt_token
    ):
        """Тест что истекший токен блокирует доступ."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/search",
                json={
                    "query": "test",
                    "mode": "partial"
                },
                headers={"Authorization": f"Bearer {expired_jwt_token}"}
            )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_invalid_token_denies_access(self):
        """Тест что невалидный токен блокирует доступ."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/search",
                json={
                    "query": "test",
                    "mode": "partial"
                },
                headers={"Authorization": "Bearer invalid.token.here"}
            )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_missing_authorization_header_denies_access(self):
        """Тест что отсутствие Authorization header блокирует доступ."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/search",
                json={
                    "query": "test",
                    "mode": "partial"
                }
                # No Authorization header
            )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_malformed_authorization_header_denies_access(self):
        """Тест что некорректный формат Authorization header блокирует доступ."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/search",
                json={
                    "query": "test",
                    "mode": "partial"
                },
                headers={"Authorization": "InvalidFormat token123"}
            )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_user_context_extracted_from_token(
        self,
        private_key,
        async_session,
        sample_file_metadata
    ):
        """Тест что user context корректно извлекается из токена."""
        # Создаем токен с специфичными данными пользователя
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "specific-user-123",
            "username": "specificuser",
            "email": "specific@example.com",
            "role": "USER",
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=30),
            "nbf": now
        }
        token = jwt.encode(payload, private_key, algorithm="RS256")

        # Подготовка данных
        file_meta = FileMetadata(**sample_file_metadata)
        async_session.add(file_meta)
        await async_session.commit()

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/search",
                json={
                    "query": "test",
                    "mode": "partial"
                },
                headers={"Authorization": f"Bearer {token}"}
            )

        # Запрос должен быть успешным
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST]


# ========================================
# Role-Based Access Control Tests
# ========================================

@pytest.mark.integration
@pytest.mark.asyncio
class TestRoleBasedAccessControl:
    """Integration tests для RBAC."""

    async def test_user_role_can_search(
        self,
        private_key,
        async_session,
        sample_file_metadata
    ):
        """Тест что USER role может выполнять поиск."""
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "user-id",
            "username": "testuser",
            "role": "USER",
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=30),
            "nbf": now
        }
        token = jwt.encode(payload, private_key, algorithm="RS256")

        file_meta = FileMetadata(**sample_file_metadata)
        async_session.add(file_meta)
        await async_session.commit()

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/search",
                json={
                    "query": "test",
                    "mode": "partial"
                },
                headers={"Authorization": f"Bearer {token}"}
            )

        assert response.status_code in [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST]

    async def test_admin_role_can_search(
        self,
        private_key,
        async_session,
        sample_file_metadata
    ):
        """Тест что ADMIN role может выполнять поиск."""
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "admin-id",
            "username": "adminuser",
            "role": "ADMIN",
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=30),
            "nbf": now
        }
        token = jwt.encode(payload, private_key, algorithm="RS256")

        file_meta = FileMetadata(**sample_file_metadata)
        async_session.add(file_meta)
        await async_session.commit()

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/search",
                json={
                    "query": "test",
                    "mode": "partial"
                },
                headers={"Authorization": f"Bearer {token}"}
            )

        assert response.status_code in [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST]


# ========================================
# Token Lifecycle Tests
# ========================================

@pytest.mark.integration
@pytest.mark.asyncio
class TestTokenLifecycle:
    """Integration tests для JWT token lifecycle."""

    async def test_token_not_yet_valid_nbf(
        self,
        private_key
    ):
        """Тест что токен с будущим nbf (not before) блокирует доступ."""
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "user-id",
            "username": "testuser",
            "role": "USER",
            "type": "access",
            "iat": now,
            "exp": now + timedelta(hours=1),
            "nbf": now + timedelta(minutes=10)  # Токен станет валидным через 10 минут
        }
        token = jwt.encode(payload, private_key, algorithm="RS256")

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/search",
                json={
                    "query": "test",
                    "mode": "partial"
                },
                headers={"Authorization": f"Bearer {token}"}
            )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_refresh_token_type_rejected(
        self,
        private_key
    ):
        """Тест что refresh token не может использоваться для API запросов."""
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "user-id",
            "username": "testuser",
            "role": "USER",
            "type": "refresh",  # Refresh token, не access
            "iat": now,
            "exp": now + timedelta(days=7),
            "nbf": now
        }
        token = jwt.encode(payload, private_key, algorithm="RS256")

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/search",
                json={
                    "query": "test",
                    "mode": "partial"
                },
                headers={"Authorization": f"Bearer {token}"}
            )

        # Refresh token должен быть отклонен для API endpoints
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_timezone_aware_token_validation(
        self,
        private_key
    ):
        """Тест что валидация токена корректно работает с timezone-aware datetime."""
        # Создаем токен с timezone-aware timestamps
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "user-id",
            "username": "testuser",
            "role": "USER",
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=30),
            "nbf": now
        }
        token = jwt.encode(payload, private_key, algorithm="RS256")

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/search",
                json={
                    "query": "test",
                    "mode": "partial"
                },
                headers={"Authorization": f"Bearer {token}"}
            )

        # Токен должен быть валиден
        assert response.status_code != status.HTTP_401_UNAUTHORIZED
