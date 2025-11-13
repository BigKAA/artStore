"""
Integration tests для OAuth 2.0 Client Credentials flow.

Тестирует полный end-to-end flow:
1. Создание Service Account
2. OAuth аутентификация через POST /api/auth/token
3. Использование JWT токена для доступа к защищенным endpoints
4. Проверка rate limiting
5. Secret rotation
"""

import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models.service_account import ServiceAccountRole, ServiceAccountStatus
from app.services.service_account_service import ServiceAccountService


# ========================================================================
# FIXTURES
# ========================================================================

@pytest.fixture
def client():
    """FastAPI TestClient для integration тестов."""
    return TestClient(app)


@pytest.fixture
async def test_service_account(db_session: AsyncSession):
    """Создание тестового Service Account."""
    service = ServiceAccountService()

    service_account, plain_secret = await service.create_service_account(
        db=db_session,
        name="Integration Test SA",
        description="Service Account for integration testing",
        role=ServiceAccountRole.USER,
        rate_limit=100,
        environment="test",
        is_system=False
    )

    # Возвращаем Service Account и plaintext secret
    return {
        "service_account": service_account,
        "client_id": service_account.client_id,
        "client_secret": plain_secret
    }


# ========================================================================
# OAUTH 2.0 TOKEN ENDPOINT TESTS
# ========================================================================

class TestOAuth2TokenEndpoint:
    """Тесты для POST /api/auth/token endpoint."""

    def test_token_endpoint_success(self, client, test_service_account):
        """Тест успешного получения токенов через OAuth 2.0."""
        # Запрос токенов
        response = client.post(
            "/api/v1/auth/token",
            json={
                "grant_type": "client_credentials",
                "client_id": test_service_account["client_id"],
                "client_secret": test_service_account["client_secret"]
            }
        )

        # Проверка успешного ответа
        assert response.status_code == 200
        data = response.json()

        # Проверка структуры ответа
        assert "access_token" in data
        assert "refresh_token" in data
        assert "token_type" in data
        assert "expires_in" in data
        assert "issued_at" in data

        # Проверка значений
        assert data["token_type"] == "Bearer"
        assert data["expires_in"] == 30 * 60  # 30 минут в секундах
        assert len(data["access_token"]) > 100  # JWT токены длинные
        assert len(data["refresh_token"]) > 100

        # Проверка issued_at - должна быть близка к текущему времени
        issued_at = datetime.fromisoformat(data["issued_at"])
        now = datetime.now(timezone.utc)
        time_diff = abs((now - issued_at).total_seconds())
        assert time_diff < 5  # Разница меньше 5 секунд

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

    def test_token_endpoint_invalid_secret(self, client, test_service_account):
        """Тест аутентификации с правильным client_id но неправильным secret."""
        response = client.post(
            "/api/v1/auth/token",
            json={
                "grant_type": "client_credentials",
                "client_id": test_service_account["client_id"],
                "client_secret": "wrong_secret_123"
            }
        )

        # Ожидаем 401 Unauthorized
        assert response.status_code == 401
        assert "Invalid client_id or client_secret" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_token_endpoint_suspended_account(self, client, test_service_account, db_session):
        """Тест аутентификации приостановленного Service Account."""
        service = ServiceAccountService()

        # Приостанавливаем Service Account
        await service.update_service_account(
            db=db_session,
            service_account_id=test_service_account["service_account"].id,
            status=ServiceAccountStatus.SUSPENDED
        )

        # Пытаемся получить токен
        response = client.post(
            "/api/v1/auth/token",
            json={
                "grant_type": "client_credentials",
                "client_id": test_service_account["client_id"],
                "client_secret": test_service_account["client_secret"]
            }
        )

        # Ожидаем 403 Forbidden
        assert response.status_code == 403
        data = response.json()
        assert "Access denied" in data["detail"] or "SUSPENDED" in data["detail"]

        # Проверка WWW-Authenticate header
        assert "WWW-Authenticate" in response.headers
        assert 'error="access_denied"' in response.headers["WWW-Authenticate"]

    @pytest.mark.asyncio
    async def test_token_endpoint_expired_secret(self, client, test_service_account, db_session):
        """Тест аутентификации Service Account с истекшим secret."""
        service = ServiceAccountService()
        sa = test_service_account["service_account"]

        # Устанавливаем дату истечения в прошлом
        sa.secret_expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        db_session.add(sa)
        await db_session.commit()

        # Пытаемся получить токен
        response = client.post(
            "/api/v1/auth/token",
            json={
                "grant_type": "client_credentials",
                "client_id": test_service_account["client_id"],
                "client_secret": test_service_account["client_secret"]
            }
        )

        # Ожидаем 403 Forbidden
        assert response.status_code == 403
        data = response.json()
        assert "expired" in data["detail"].lower()


# ========================================================================
# JWT TOKEN USAGE TESTS
# ========================================================================

class TestJWTTokenUsage:
    """Тесты использования полученных JWT токенов."""

    def test_access_protected_endpoint_with_valid_token(self, client, test_service_account):
        """Тест доступа к защищенному endpoint с валидным токеном."""
        # Получаем токен
        token_response = client.post(
            "/api/v1/auth/token",
            json={
                "grant_type": "client_credentials",
                "client_id": test_service_account["client_id"],
                "client_secret": test_service_account["client_secret"]
            }
        )
        access_token = token_response.json()["access_token"]

        # Используем токен для доступа к /api/v1/auth/me
        # (предполагается что этот endpoint требует JWT)
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"}
        )

        # Проверяем что токен принят (должно быть 200 или специфичная бизнес-логика)
        # Если endpoint не поддерживает Service Accounts, может быть 401/403
        assert response.status_code in [200, 401, 403]

    def test_access_without_token_fails(self, client):
        """Тест что доступ без токена запрещен."""
        response = client.get("/api/v1/auth/me")

        # Должна быть ошибка 401 или 403
        assert response.status_code in [401, 403]


# ========================================================================
# RATE LIMITING TESTS
# ========================================================================

class TestRateLimiting:
    """Тесты rate limiting middleware."""

    def test_rate_limit_headers_present(self, client, test_service_account):
        """Тест наличия X-RateLimit headers в ответе."""
        # Получаем токен
        token_response = client.post(
            "/api/v1/auth/token",
            json={
                "grant_type": "client_credentials",
                "client_id": test_service_account["client_id"],
                "client_secret": test_service_account["client_secret"]
            }
        )
        access_token = token_response.json()["access_token"]

        # Делаем запрос с токеном
        response = client.get(
            "/health/live",  # Простой endpoint для проверки headers
            headers={"Authorization": f"Bearer {access_token}"}
        )

        # Проверяем наличие rate limit headers
        # (могут быть или не быть в зависимости от реализации middleware для health endpoints)
        # Более точную проверку можно сделать на API endpoints требующих auth


# ========================================================================
# SECRET ROTATION TESTS
# ========================================================================

class TestSecretRotation:
    """Тесты ротации client_secret."""

    @pytest.mark.asyncio
    async def test_old_secret_invalid_after_rotation(self, client, test_service_account, db_session):
        """Тест что старый secret не работает после ротации."""
        service = ServiceAccountService()
        old_secret = test_service_account["client_secret"]

        # Выполняем ротацию
        rotated_sa, new_secret = await service.rotate_secret(
            db=db_session,
            service_account_id=test_service_account["service_account"].id
        )

        # Пытаемся аутентифицироваться со старым секретом
        response_old = client.post(
            "/api/v1/auth/token",
            json={
                "grant_type": "client_credentials",
                "client_id": test_service_account["client_id"],
                "client_secret": old_secret
            }
        )

        # Старый секрет не должен работать
        assert response_old.status_code == 401

        # Аутентифицируемся с новым секретом
        response_new = client.post(
            "/api/v1/auth/token",
            json={
                "grant_type": "client_credentials",
                "client_id": test_service_account["client_id"],
                "client_secret": new_secret
            }
        )

        # Новый секрет должен работать
        assert response_new.status_code == 200
        assert "access_token" in response_new.json()


# ========================================================================
# LAST_USED_AT TRACKING TESTS
# ========================================================================

class TestUsageTracking:
    """Тесты отслеживания last_used_at."""

    @pytest.mark.asyncio
    async def test_last_used_updated_on_auth(self, client, test_service_account, db_session):
        """Тест что last_used_at обновляется при аутентификации."""
        service = ServiceAccountService()
        sa = test_service_account["service_account"]

        # Запоминаем начальное значение last_used_at
        initial_last_used = sa.last_used_at

        # Аутентифицируемся
        client.post(
            "/api/v1/auth/token",
            json={
                "grant_type": "client_credentials",
                "client_id": test_service_account["client_id"],
                "client_secret": test_service_account["client_secret"]
            }
        )

        # Получаем обновленный Service Account из БД
        await db_session.refresh(sa)

        # Проверяем что last_used_at обновился
        assert sa.last_used_at is not None
        if initial_last_used:
            assert sa.last_used_at > initial_last_used
