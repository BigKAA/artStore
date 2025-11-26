"""
Integration tests для Service Accounts API endpoints.

Тестирует:
- POST /api/v1/service-accounts - Создание Service Account
- GET /api/v1/service-accounts - Список Service Accounts с фильтрацией
- GET /api/v1/service-accounts/{id} - Получение Service Account по ID
- PUT /api/v1/service-accounts/{id} - Обновление Service Account
- DELETE /api/v1/service-accounts/{id} - Удаление Service Account
- POST /api/v1/service-accounts/{id}/rotate-secret - Ротация секрета

RBAC: Требуется SUPER_ADMIN роль для всех endpoints (кроме GET)
"""

import pytest
import uuid
from fastapi.testclient import TestClient
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
async def admin_user(db_session: AsyncSession):
    """Создание admin user с SUPER_ADMIN ролью для аутентификации."""
    from app.models.admin_user import AdminUser, AdminRole
    from app.services.admin_user_service import AdminUserService

    service = AdminUserService()

    # Создаем SUPER_ADMIN пользователя
    test_id = str(uuid.uuid4())[:8]
    admin = await service.create_admin_user(
        db=db_session,
        username=f"test_superadmin_{test_id}",
        email=f"superadmin_{test_id}@test.com",
        password="SecurePass123!",
        full_name="Test Super Admin",
        role=AdminRole.SUPER_ADMIN
    )

    return admin


@pytest.fixture
async def admin_token(client, admin_user, db_session):
    """
    Получение JWT токена для SUPER_ADMIN.

    Использует admin authentication endpoint для получения токена.
    """
    from app.services.admin_auth_service import AdminAuthService

    service = AdminAuthService()

    # Аутентифицируемся и получаем токен
    token = await service.authenticate_and_generate_token(
        db=db_session,
        username=admin_user.username,
        password="SecurePass123!"
    )

    return token


@pytest.fixture
async def service_account_with_secret(db_session: AsyncSession):
    """
    Создание тестового Service Account и возврат с plain secret.

    Returns:
        tuple: (service_account, plain_secret)
    """
    service = ServiceAccountService()

    test_id = str(uuid.uuid4())[:8]
    sa, secret = await service.create_service_account(
        db=db_session,
        name=f"test_sa_{test_id}",
        description="Test Service Account",
        role=ServiceAccountRole.USER,
        rate_limit=100,
        environment="test",
        is_system=False
    )

    yield sa, secret

    # Cleanup after test
    try:
        await service.delete_service_account(db_session, sa.id)
    except Exception:
        pass  # Already deleted or cleanup failed


# ========================================================================
# CREATE SERVICE ACCOUNT TESTS
# ========================================================================

class TestCreateServiceAccount:
    """Тесты для POST /api/v1/service-accounts endpoint."""

    def test_create_service_account_success(self, client, admin_token):
        """Тест успешного создания Service Account."""
        test_id = str(uuid.uuid4())[:8]
        response = client.post(
            "/api/v1/service-accounts/",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": f"integration_test_sa_{test_id}",
                "description": "Integration test Service Account",
                "role": "USER",
                "rate_limit": 150,
                "environment": "test",
                "is_system": False
            }
        )

        assert response.status_code == 201
        data = response.json()

        # Проверяем структуру ответа
        assert "id" in data
        assert "client_id" in data
        assert "client_secret" in data  # ONLY here!
        assert data["name"] == f"integration_test_sa_{test_id}"
        assert data["role"] == "USER"
        assert data["status"] == "ACTIVE"
        assert data["rate_limit"] == 150

        # Проверяем что client_secret не пустой
        assert len(data["client_secret"]) >= 16

    def test_create_service_account_duplicate_name(self, client, admin_token, service_account_with_secret):
        """Тест создания Service Account с дублирующимся именем."""
        sa, _ = service_account_with_secret

        response = client.post(
            "/api/v1/service-accounts/",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": sa.name,  # Дублирующееся имя
                "role": "USER"
            }
        )

        assert response.status_code == 409
        assert "already exists" in response.json()["detail"].lower()

    def test_create_service_account_without_auth(self, client):
        """Тест создания Service Account без аутентификации."""
        response = client.post(
            "/api/v1/service-accounts/",
            json={
                "name": "unauthorized_sa",
                "role": "USER"
            }
        )

        assert response.status_code == 401

    def test_create_service_account_invalid_role(self, client, admin_token):
        """Тест создания Service Account с неправильной ролью."""
        response = client.post(
            "/api/v1/service-accounts/",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": "invalid_role_sa",
                "role": "INVALID_ROLE"
            }
        )

        assert response.status_code == 422  # Validation error


# ========================================================================
# LIST SERVICE ACCOUNTS TESTS
# ========================================================================

class TestListServiceAccounts:
    """Тесты для GET /api/v1/service-accounts endpoint."""

    def test_list_service_accounts_success(self, client, admin_token, service_account_with_secret):
        """Тест получения списка Service Accounts."""
        response = client.get(
            "/api/v1/service-accounts/",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Проверяем структуру ответа
        assert "total" in data
        assert "items" in data
        assert "skip" in data
        assert "limit" in data
        assert isinstance(data["items"], list)
        assert data["total"] >= 1  # Minimum 1 (our test SA)

    def test_list_service_accounts_with_pagination(self, client, admin_token):
        """Тест пагинации списка Service Accounts."""
        response = client.get(
            "/api/v1/service-accounts/?skip=0&limit=10",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["skip"] == 0
        assert data["limit"] == 10
        assert len(data["items"]) <= 10

    def test_list_service_accounts_filter_by_role(self, client, admin_token):
        """Тест фильтрации по роли."""
        response = client.get(
            "/api/v1/service-accounts/?role=ADMIN",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Проверяем что все возвращенные SA имеют роль ADMIN
        for item in data["items"]:
            assert item["role"] == "ADMIN"

    def test_list_service_accounts_filter_by_status(self, client, admin_token):
        """Тест фильтрации по статусу."""
        response = client.get(
            "/api/v1/service-accounts/?status=ACTIVE",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Проверяем что все возвращенные SA имеют статус ACTIVE
        for item in data["items"]:
            assert item["status"] == "ACTIVE"

    def test_list_service_accounts_no_client_secret(self, client, admin_token, service_account_with_secret):
        """Тест что client_secret НЕ возвращается в списке."""
        response = client.get(
            "/api/v1/service-accounts/",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Проверяем что ни один item не содержит client_secret
        for item in data["items"]:
            assert "client_secret" not in item


# ========================================================================
# GET SERVICE ACCOUNT BY ID TESTS
# ========================================================================

class TestGetServiceAccountById:
    """Тесты для GET /api/v1/service-accounts/{id} endpoint."""

    def test_get_service_account_success(self, client, admin_token, service_account_with_secret):
        """Тест получения Service Account по ID."""
        sa, _ = service_account_with_secret

        response = client.get(
            f"/api/v1/service-accounts/{sa.id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["id"] == str(sa.id)
        assert data["name"] == sa.name
        assert data["client_id"] == sa.client_id
        assert "client_secret" not in data  # Secret НЕ возвращается

    def test_get_service_account_not_found(self, client, admin_token):
        """Тест получения несуществующего Service Account."""
        fake_id = "00000000-0000-0000-0000-000000000000"

        response = client.get(
            f"/api/v1/service-accounts/{fake_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 404

    def test_get_service_account_invalid_uuid(self, client, admin_token):
        """Тест с невалидным UUID."""
        response = client.get(
            "/api/v1/service-accounts/invalid-uuid",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 422  # Validation error


# ========================================================================
# UPDATE SERVICE ACCOUNT TESTS
# ========================================================================

class TestUpdateServiceAccount:
    """Тесты для PUT /api/v1/service-accounts/{id} endpoint."""

    def test_update_service_account_success(self, client, admin_token, service_account_with_secret):
        """Тест успешного обновления Service Account."""
        sa, _ = service_account_with_secret

        response = client.put(
            f"/api/v1/service-accounts/{sa.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "description": "Updated description",
                "rate_limit": 200
            }
        )

        assert response.status_code == 200
        data = response.json()

        assert data["description"] == "Updated description"
        assert data["rate_limit"] == 200

    def test_update_service_account_change_role(self, client, admin_token, service_account_with_secret):
        """Тест изменения роли Service Account."""
        sa, _ = service_account_with_secret

        response = client.put(
            f"/api/v1/service-accounts/{sa.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "role": "AUDITOR"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "AUDITOR"

    async def test_update_system_service_account_forbidden(self, client, admin_token, db_session):
        """Тест что системные Service Accounts нельзя обновить."""
        # Находим системный Service Account (admin-service)
        service = ServiceAccountService()
        system_sa = await service.get_by_client_id(db_session, "admin-service")

        if system_sa:
            response = client.put(
                f"/api/v1/service-accounts/{system_sa.id}",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={
                    "description": "Try to update system account"
                }
            )

            assert response.status_code == 403
            assert "system" in response.json()["detail"].lower()


# ========================================================================
# DELETE SERVICE ACCOUNT TESTS
# ========================================================================

class TestDeleteServiceAccount:
    """Тесты для DELETE /api/v1/service-accounts/{id} endpoint."""

    def test_delete_service_account_success(self, client, admin_token, service_account_with_secret):
        """Тест успешного удаления Service Account."""
        sa, _ = service_account_with_secret

        response = client.delete(
            f"/api/v1/service-accounts/{sa.id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 204

    def test_delete_service_account_not_found(self, client, admin_token):
        """Тест удаления несуществующего Service Account."""
        fake_id = "00000000-0000-0000-0000-000000000000"

        response = client.delete(
            f"/api/v1/service-accounts/{fake_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 404

    async def test_delete_system_service_account_forbidden(self, client, admin_token, db_session):
        """Тест что системные Service Accounts нельзя удалить."""
        service = ServiceAccountService()
        system_sa = await service.get_by_client_id(db_session, "admin-service")

        if system_sa:
            response = client.delete(
                f"/api/v1/service-accounts/{system_sa.id}",
                headers={"Authorization": f"Bearer {admin_token}"}
            )

            assert response.status_code == 403
            assert "system" in response.json()["detail"].lower()


# ========================================================================
# ROTATE SECRET TESTS
# ========================================================================

class TestRotateSecret:
    """Тесты для POST /api/v1/service-accounts/{id}/rotate-secret endpoint."""

    def test_rotate_secret_success(self, client, admin_token, service_account_with_secret):
        """Тест успешной ротации client_secret."""
        sa, old_secret = service_account_with_secret

        response = client.post(
            f"/api/v1/service-accounts/{sa.id}/rotate-secret",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Проверяем структуру ответа
        assert "id" in data
        assert "new_client_secret" in data  # ONLY here!
        assert data["id"] == str(sa.id)

        # Проверяем что новый секрет отличается от старого
        new_secret = data["new_client_secret"]
        assert new_secret != old_secret
        assert len(new_secret) >= 16

    def test_rotate_secret_not_found(self, client, admin_token):
        """Тест ротации для несуществующего Service Account."""
        fake_id = "00000000-0000-0000-0000-000000000000"

        response = client.post(
            f"/api/v1/service-accounts/{fake_id}/rotate-secret",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 404

    def test_rotate_secret_old_secret_invalid_after_rotation(
        self, client, admin_token, service_account_with_secret
    ):
        """Тест что старый секрет не работает после ротации."""
        sa, old_secret = service_account_with_secret

        # Выполняем ротацию
        rotate_response = client.post(
            f"/api/v1/service-accounts/{sa.id}/rotate-secret",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert rotate_response.status_code == 200

        # Пытаемся аутентифицироваться со старым секретом
        auth_response = client.post(
            "/api/v1/auth/token",
            json={
                "grant_type": "client_credentials",
                "client_id": sa.client_id,
                "client_secret": old_secret
            }
        )

        # Ожидаем 401 Unauthorized
        assert auth_response.status_code == 401

    def test_rotate_secret_new_secret_works(
        self, client, admin_token, service_account_with_secret
    ):
        """Тест что новый секрет работает после ротации."""
        sa, _ = service_account_with_secret

        # Выполняем ротацию
        rotate_response = client.post(
            f"/api/v1/service-accounts/{sa.id}/rotate-secret",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert rotate_response.status_code == 200

        new_secret = rotate_response.json()["new_client_secret"]

        # Аутентифицируемся с новым секретом
        auth_response = client.post(
            "/api/v1/auth/token",
            json={
                "grant_type": "client_credentials",
                "client_id": sa.client_id,
                "client_secret": new_secret
            }
        )

        # Ожидаем успех
        assert auth_response.status_code == 200
        token_data = auth_response.json()
        assert "access_token" in token_data
        assert token_data["token_type"] == "bearer"
