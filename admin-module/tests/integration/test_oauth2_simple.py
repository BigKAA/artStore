"""
Simplified integration tests для OAuth 2.0 Client Credentials flow.

Тестирует базовый flow без создания Service Account в фикстуре.
Для полноценного тестирования создайте Service Account вручную перед запуском тестов.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


# ========================================================================
# FIXTURES
# ========================================================================

@pytest.fixture
def client():
    """FastAPI TestClient для integration тестов."""
    return TestClient(app)


# ========================================================================
# OAUTH 2.0 TOKEN ENDPOINT - NEGATIVE TESTS
# ========================================================================

class TestOAuth2TokenEndpointNegative:
    """Negative тесты для POST /api/auth/token endpoint."""

    def test_token_endpoint_invalid_client_id(self, client):
        """Тест аутентификации с неправильным client_id."""
        response = client.post(
            "/api/v1/auth/token",
            json={
                "grant_type": "client_credentials",
                "client_id": "sa_nonexistent_123",
                "client_secret": "wrong_secret"
            }
        )

        # Ожидаем 401 Unauthorized
        assert response.status_code == 401
        data = response.json()
        assert "Invalid client_id or client_secret" in data["detail"]

        # Проверка RFC-compliant headers
        assert "WWW-Authenticate" in response.headers
        assert 'error="invalid_client"' in response.headers["WWW-Authenticate"]
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["Pragma"] == "no-cache"

    def test_token_endpoint_missing_client_id(self, client):
        """Тест запроса без client_id."""
        response = client.post(
            "/api/v1/auth/token",
            json={
                "grant_type": "client_credentials",
                "client_secret": "some_secret"
            }
        )

        # Ожидаем 422 Validation Error
        assert response.status_code == 422

    def test_token_endpoint_missing_client_secret(self, client):
        """Тест запроса без client_secret."""
        response = client.post(
            "/api/v1/auth/token",
            json={
                "grant_type": "client_credentials",
                "client_id": "sa_test_123"
            }
        )

        # Ожидаем 422 Validation Error
        assert response.status_code == 422

    def test_token_endpoint_missing_grant_type(self, client):
        """Тест запроса без grant_type."""
        response = client.post(
            "/api/v1/auth/token",
            json={
                "client_id": "sa_test_123",
                "client_secret": "some_secret"
            }
        )

        # Ожидаем 422 Validation Error
        assert response.status_code == 422

    def test_token_endpoint_invalid_grant_type(self, client):
        """Тест запроса с неправильным grant_type."""
        response = client.post(
            "/api/v1/auth/token",
            json={
                "grant_type": "password",  # Неподдерживаемый тип
                "client_id": "sa_test_123",
                "client_secret": "some_secret"
            }
        )

        # Ожидаем 422 Validation Error (зависит от схемы валидации)
        assert response.status_code in [401, 422]


# ========================================================================
# ENDPOINT AVAILABILITY TESTS
# ========================================================================

class TestEndpointAvailability:
    """Тесты доступности endpoints."""

    def test_token_endpoint_exists(self, client):
        """Тест что /api/v1/auth/token endpoint существует."""
        response = client.post(
            "/api/v1/auth/token",
            json={
                "grant_type": "client_credentials",
                "client_id": "test",
                "client_secret": "test"
            }
        )

        # Endpoint должен существовать (не 404)
        assert response.status_code != 404

    def test_openapi_docs_available(self, client):
        """Тест что OpenAPI документация доступна."""
        response = client.get("/docs")
        assert response.status_code == 200

    def test_openapi_json_available(self, client):
        """Тест что OpenAPI JSON доступен."""
        response = client.get("/openapi.json")
        assert response.status_code == 200

        # Проверяем что наш endpoint задокументирован
        data = response.json()
        assert "/api/v1/auth/token" in data.get("paths", {})


# ========================================================================
# RESPONSE STRUCTURE TESTS
# ========================================================================

class TestResponseStructure:
    """Тесты структуры ответов."""

    def test_error_response_structure(self, client):
        """Тест структуры error response."""
        response = client.post(
            "/api/v1/auth/token",
            json={
                "grant_type": "client_credentials",
                "client_id": "nonexistent",
                "client_secret": "wrong"
            }
        )

        assert response.status_code == 401
        data = response.json()

        # Проверяем структуру error response
        assert "detail" in data
        assert isinstance(data["detail"], str)


# ========================================================================
# ПРИМЕЧАНИЯ ДЛЯ MANUAL TESTING
# ========================================================================

"""
Для полноценного E2E тестирования OAuth flow:

1. Создайте Service Account через psql:

```sql
INSERT INTO service_accounts (
    id, name, client_id, client_secret_hash,
    role, status, rate_limit, secret_expires_at,
    created_at, updated_at
) VALUES (
    gen_random_uuid(),
    'Integration Test SA',
    'sa_test_integration_12345678',
    '$2b$12$...',  -- Используйте bcrypt hash реального секрета
    'USER',
    'ACTIVE',
    100,
    NOW() + INTERVAL '90 days',
    NOW(),
    NOW()
);
```

2. Запустите manual тест с реальными credentials:

```bash
curl -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{
    "grant_type": "client_credentials",
    "client_id": "sa_test_integration_12345678",
    "client_secret": "ваш_реальный_секрет"
  }'
```

3. Проверьте ответ - должны получить access_token и refresh_token
"""
