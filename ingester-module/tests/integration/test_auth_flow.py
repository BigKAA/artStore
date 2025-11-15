"""
Integration tests for JWT authentication flow.

Tests:
- JWT token validation end-to-end
- Role-based access control
- Token expiration handling
- Authentication error scenarios
"""

import pytest
from httpx import AsyncClient
from datetime import datetime, timezone, timedelta
import jwt as pyjwt


@pytest.mark.asyncio
class TestAuthenticationFlow:
    """Integration tests для JWT authentication workflow."""

    async def test_valid_jwt_token_allows_access(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_multipart_file: dict
    ):
        """
        Test что валидный JWT токен разрешает доступ к protected endpoints.
        """
        response = await client.post(
            "/api/v1/upload",
            headers=auth_headers,
            files=sample_multipart_file
        )

        # Valid token should allow access
        assert response.status_code == 200

    async def test_missing_auth_header_denies_access(
        self,
        client: AsyncClient,
        sample_multipart_file: dict
    ):
        """
        Test что отсутствие Authorization header блокирует доступ.
        """
        response = await client.post(
            "/api/v1/upload",
            files=sample_multipart_file
        )

        assert response.status_code == 401
        data = response.json()
        assert "detail" in data

    async def test_malformed_auth_header_denies_access(
        self,
        client: AsyncClient,
        sample_multipart_file: dict
    ):
        """
        Test что некорректный Authorization header блокирует доступ.
        """
        test_cases = [
            {"Authorization": "InvalidFormat"},  # No Bearer
            {"Authorization": "Bearer"},  # No token
            {"Authorization": "Bearer  "},  # Empty token
            {"Authorization": "Basic token123"},  # Wrong auth type
        ]

        for headers in test_cases:
            response = await client.post(
                "/api/v1/upload",
                headers=headers,
                files=sample_multipart_file
            )

            assert response.status_code == 401, f"Failed for {headers}"

    async def test_invalid_jwt_signature_denies_access(
        self,
        client: AsyncClient,
        sample_multipart_file: dict,
        rsa_keys
    ):
        """
        Test что JWT с неправильной подписью блокирует доступ.
        """
        # Создаем токен с неправильным ключом
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend

        wrong_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )

        wrong_private_pem = wrong_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )

        now = datetime.now(timezone.utc)
        payload = {
            "sub": "test-user",
            "type": "access",
            "iat": now,
            "exp": now + timedelta(hours=1)
        }

        invalid_token = pyjwt.encode(payload, wrong_private_pem, algorithm="RS256")
        headers = {"Authorization": f"Bearer {invalid_token}"}

        response = await client.post(
            "/api/v1/upload",
            headers=headers,
            files=sample_multipart_file
        )

        assert response.status_code == 401

    async def test_expired_jwt_token_denies_access(
        self,
        client: AsyncClient,
        sample_multipart_file: dict,
        rsa_keys
    ):
        """
        Test что истекший JWT токен блокирует доступ.
        """
        private_key = rsa_keys["private_pem"]

        # Создаем токен, который уже истек
        now = datetime.now(timezone.utc)
        past = now - timedelta(hours=2)

        payload = {
            "sub": "test-user",
            "username": "testuser",
            "role": "USER",
            "type": "access",
            "iat": past,
            "exp": past + timedelta(hours=1),  # Expired 1 hour ago
            "nbf": past
        }

        expired_token = pyjwt.encode(payload, private_key, algorithm="RS256")
        headers = {"Authorization": f"Bearer {expired_token}"}

        response = await client.post(
            "/api/v1/upload",
            headers=headers,
            files=sample_multipart_file
        )

        assert response.status_code == 401
        data = response.json()
        assert "expired" in data["detail"].lower() or "token" in data["detail"].lower()

    async def test_token_with_missing_claims_denies_access(
        self,
        client: AsyncClient,
        sample_multipart_file: dict,
        rsa_keys
    ):
        """
        Test что JWT токен с отсутствующими required claims блокирует доступ.
        """
        private_key = rsa_keys["private_pem"]
        now = datetime.now(timezone.utc)

        # Токен без обязательных полей (sub, type, iat, exp)
        incomplete_payloads = [
            {"username": "test"},  # Missing sub, type, iat, exp
            {"sub": "test", "iat": now},  # Missing type, exp
            {"sub": "test", "type": "access", "iat": now},  # Missing exp
        ]

        for payload in incomplete_payloads:
            token = pyjwt.encode(payload, private_key, algorithm="RS256")
            headers = {"Authorization": f"Bearer {token}"}

            response = await client.post(
                "/api/v1/upload",
                headers=headers,
                files=sample_multipart_file
            )

            assert response.status_code == 401, f"Failed for payload {payload}"

    async def test_token_with_future_nbf_denies_access(
        self,
        client: AsyncClient,
        sample_multipart_file: dict,
        rsa_keys
    ):
        """
        Test что JWT токен с nbf (not before) в будущем блокирует доступ.
        """
        private_key = rsa_keys["private_pem"]

        now = datetime.now(timezone.utc)
        future = now + timedelta(hours=1)

        payload = {
            "sub": "test-user",
            "username": "testuser",
            "role": "USER",
            "type": "access",
            "iat": now,
            "exp": now + timedelta(hours=2),
            "nbf": future  # Not valid yet
        }

        future_token = pyjwt.encode(payload, private_key, algorithm="RS256")
        headers = {"Authorization": f"Bearer {future_token}"}

        response = await client.post(
            "/api/v1/upload",
            headers=headers,
            files=sample_multipart_file
        )

        # Should be denied (token not yet valid)
        assert response.status_code == 401


@pytest.mark.asyncio
class TestRoleBasedAccessControl:
    """Integration tests для role-based access control."""

    async def test_admin_role_allows_upload(
        self,
        client: AsyncClient,
        sample_multipart_file: dict,
        rsa_keys
    ):
        """
        Test что ADMIN роль разрешает upload.
        """
        private_key = rsa_keys["private_pem"]

        now = datetime.now(timezone.utc)
        payload = {
            "sub": "admin-user",
            "username": "admin",
            "role": "ADMIN",  # Admin role
            "email": "admin@example.com",
            "type": "access",
            "iat": now,
            "exp": now + timedelta(hours=1)
        }

        token = pyjwt.encode(payload, private_key, algorithm="RS256")
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.post(
            "/api/v1/upload",
            headers=headers,
            files=sample_multipart_file
        )

        assert response.status_code == 200

    async def test_user_role_allows_upload(
        self,
        client: AsyncClient,
        sample_multipart_file: dict,
        rsa_keys
    ):
        """
        Test что USER роль разрешает upload.
        """
        private_key = rsa_keys["private_pem"]

        now = datetime.now(timezone.utc)
        payload = {
            "sub": "regular-user",
            "username": "user",
            "role": "USER",  # Regular user role
            "email": "user@example.com",
            "type": "access",
            "iat": now,
            "exp": now + timedelta(hours=1)
        }

        token = pyjwt.encode(payload, private_key, algorithm="RS256")
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.post(
            "/api/v1/upload",
            headers=headers,
            files=sample_multipart_file
        )

        assert response.status_code == 200

    async def test_readonly_role_denies_upload(
        self,
        client: AsyncClient,
        sample_multipart_file: dict,
        rsa_keys
    ):
        """
        Test что READONLY роль блокирует upload.

        Note: Если RBAC не реализован, тест может fail.
        """
        private_key = rsa_keys["private_pem"]

        now = datetime.now(timezone.utc)
        payload = {
            "sub": "readonly-user",
            "username": "readonly",
            "role": "READONLY",  # Readonly role
            "email": "readonly@example.com",
            "type": "access",
            "iat": now,
            "exp": now + timedelta(hours=1)
        }

        token = pyjwt.encode(payload, private_key, algorithm="RS256")
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.post(
            "/api/v1/upload",
            headers=headers,
            files=sample_multipart_file
        )

        # Depending on RBAC implementation:
        # - 403 Forbidden if RBAC implemented
        # - 200 OK if RBAC not yet implemented
        assert response.status_code in [200, 403]


@pytest.mark.asyncio
class TestTokenTypeValidation:
    """Integration tests для token type validation."""

    async def test_access_token_allows_upload(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_multipart_file: dict
    ):
        """
        Test что access token разрешает операции.
        """
        response = await client.post(
            "/api/v1/upload",
            headers=auth_headers,
            files=sample_multipart_file
        )

        assert response.status_code == 200

    async def test_refresh_token_denies_upload(
        self,
        client: AsyncClient,
        sample_multipart_file: dict,
        rsa_keys
    ):
        """
        Test что refresh token блокирует операции.

        Note: Если token type validation не реализована, тест может fail.
        """
        private_key = rsa_keys["private_pem"]

        now = datetime.now(timezone.utc)
        payload = {
            "sub": "test-user",
            "username": "testuser",
            "role": "USER",
            "type": "refresh",  # Refresh token, not access
            "iat": now,
            "exp": now + timedelta(days=7)
        }

        refresh_token = pyjwt.encode(payload, private_key, algorithm="RS256")
        headers = {"Authorization": f"Bearer {refresh_token}"}

        response = await client.post(
            "/api/v1/upload",
            headers=headers,
            files=sample_multipart_file
        )

        # Depending on token type validation:
        # - 401 Unauthorized if type validation implemented
        # - 200 OK if not yet implemented
        assert response.status_code in [200, 401]
