"""
Simple Integration tests для JWT Authentication.

Тестирует основной JWT authentication flow без async сложностей.
"""

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.main import app


@pytest.mark.integration
class TestAuthenticationSimple:
    """Простые integration tests для JWT authentication."""

    def test_missing_token_denies_access(self):
        """Тест что отсутствие токена блокирует доступ."""
        with TestClient(app) as client:
            response = client.post(
                "/api/search",
                json={
                    "query": "test",
                    "mode": "partial"
                }
                # No Authorization header
            )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_invalid_token_format_denies_access(self):
        """Тест что некорректный формат токена блокирует доступ."""
        with TestClient(app) as client:
            response = client.post(
                "/api/search",
                json={
                    "query": "test",
                    "mode": "partial"
                },
                headers={"Authorization": "InvalidFormat token123"}
            )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_malformed_jwt_token_denies_access(self):
        """Тест что некорректный JWT токен блокирует доступ."""
        with TestClient(app) as client:
            response = client.post(
                "/api/search",
                json={
                    "query": "test",
                    "mode": "partial"
                },
                headers={"Authorization": "Bearer invalid.token.here"}
            )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_valid_token_grants_access(self, valid_jwt_token):
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