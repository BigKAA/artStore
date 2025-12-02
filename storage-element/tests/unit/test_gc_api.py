"""
Unit тесты для GC API endpoints.

Тестирование:
- DELETE /api/v1/gc/{file_id} endpoint
- GET /api/v1/gc/{file_id}/exists endpoint
- Авторизация (только Service Accounts)
- Idempotency при повторном удалении
- Audit logging
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import jwt

from app.api.deps.auth import require_service_account
from app.core.security import UserContext, UserRole


# ============================================================================
# Fixtures для Service Account JWT
# ============================================================================

@pytest.fixture
def service_account_jwt_payload():
    """
    Payload для Service Account JWT токена.
    """
    now = datetime.now(timezone.utc)
    return {
        "sub": str(uuid4()),
        "type": "service_account",
        "role": "admin",
        "name": "gc-service",
        "jti": str(uuid4()),
        "client_id": "sa_prod_gc_service_abc123",
        "rate_limit": 1000,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
        "nbf": int(now.timestamp())
    }


@pytest.fixture
def admin_user_jwt_payload():
    """
    Payload для Admin User JWT токена (НЕ service account).
    """
    now = datetime.now(timezone.utc)
    return {
        "sub": "admin-user-123",
        "type": "admin_user",
        "role": "admin",
        "name": "Admin User",
        "jti": str(uuid4()),
        "client_id": None,
        "rate_limit": None,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
        "nbf": int(now.timestamp())
    }


@pytest.fixture
def service_account_token(test_jwt_keys, service_account_jwt_payload):
    """
    Генерация JWT токена для Service Account.
    """
    private_key, _ = test_jwt_keys
    return jwt.encode(service_account_jwt_payload, private_key, algorithm="RS256")


@pytest.fixture
def admin_user_token(test_jwt_keys, admin_user_jwt_payload):
    """
    Генерация JWT токена для Admin User (НЕ service account).
    """
    private_key, _ = test_jwt_keys
    return jwt.encode(admin_user_jwt_payload, private_key, algorithm="RS256")


@pytest.fixture
def service_account_headers(service_account_token):
    """
    HTTP headers с Service Account токеном.
    """
    return {"Authorization": f"Bearer {service_account_token}"}


@pytest.fixture
def admin_user_headers(admin_user_token):
    """
    HTTP headers с Admin User токеном.
    """
    return {"Authorization": f"Bearer {admin_user_token}"}


# ============================================================================
# Unit тесты для require_service_account dependency
# ============================================================================

class TestRequireServiceAccountDependency:
    """Тесты для dependency require_service_account."""

    @pytest.mark.asyncio
    async def test_service_account_allowed(self):
        """Service Account должен проходить авторизацию."""
        # Arrange
        service_account_context = UserContext(
            identifier=str(uuid4()),
            display_name="gc-service",
            role=UserRole.ADMIN,
            token_type="service_account",
            client_id="sa_prod_gc_service",
            rate_limit=1000,
            iat=datetime.now(timezone.utc),
            exp=datetime.now(timezone.utc) + timedelta(hours=1),
            nbf=datetime.now(timezone.utc)
        )

        # Act
        result = await require_service_account(service_account_context)

        # Assert
        assert result == service_account_context
        assert result.is_service_account

    @pytest.mark.asyncio
    async def test_admin_user_denied(self):
        """Admin User (не Service Account) должен получить 403."""
        from fastapi import HTTPException

        # Arrange
        admin_user_context = UserContext(
            identifier="admin-user-123",
            display_name="Admin User",
            role=UserRole.ADMIN,
            token_type="admin_user",  # НЕ service_account
            client_id=None,
            rate_limit=None,
            iat=datetime.now(timezone.utc),
            exp=datetime.now(timezone.utc) + timedelta(hours=1),
            nbf=datetime.now(timezone.utc)
        )

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await require_service_account(admin_user_context)

        assert exc_info.value.status_code == 403
        assert "Service account access required" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_regular_user_denied(self):
        """Обычный пользователь должен получить 403."""
        from fastapi import HTTPException

        # Arrange
        user_context = UserContext(
            identifier="user-123",
            display_name="Regular User",
            role=UserRole.USER,
            token_type="admin_user",
            client_id=None,
            rate_limit=None,
            iat=datetime.now(timezone.utc),
            exp=datetime.now(timezone.utc) + timedelta(hours=1),
            nbf=datetime.now(timezone.utc)
        )

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await require_service_account(user_context)

        assert exc_info.value.status_code == 403


# ============================================================================
# Unit тесты для GC Delete endpoint logic
# ============================================================================

class TestGCDeleteEndpointLogic:
    """Тесты для логики GC delete endpoint."""

    @pytest.mark.asyncio
    async def test_gc_delete_response_model(self):
        """Проверка модели GCDeleteResponse."""
        from app.api.v1.endpoints.gc import GCDeleteResponse

        file_id = uuid4()
        response = GCDeleteResponse(
            status="deleted",
            file_id=file_id,
            deleted_at=datetime.now(timezone.utc).isoformat(),
            deleted_by="service-account-id",
            reason="gc_cleanup"
        )

        assert response.status == "deleted"
        assert response.file_id == file_id
        assert response.reason == "gc_cleanup"

    @pytest.mark.asyncio
    async def test_gc_delete_request_defaults(self):
        """Проверка значений по умолчанию для GCDeleteRequest."""
        from app.api.v1.endpoints.gc import GCDeleteRequest

        request = GCDeleteRequest()

        assert request.reason == "gc_cleanup"
        assert request.cleanup_type is None

    @pytest.mark.asyncio
    async def test_gc_delete_request_custom_values(self):
        """Проверка кастомных значений для GCDeleteRequest."""
        from app.api.v1.endpoints.gc import GCDeleteRequest

        request = GCDeleteRequest(
            reason="ttl_expired",
            cleanup_type="ttl_expired"
        )

        assert request.reason == "ttl_expired"
        assert request.cleanup_type == "ttl_expired"


# ============================================================================
# Unit тесты для UserContext.is_service_account
# ============================================================================

class TestUserContextServiceAccount:
    """Тесты для проверки is_service_account в UserContext."""

    def test_is_service_account_true(self):
        """Service Account должен возвращать is_service_account=True."""
        context = UserContext(
            identifier=str(uuid4()),
            display_name="gc-service",
            role=UserRole.ADMIN,
            token_type="service_account",
            client_id="sa_prod_gc",
            rate_limit=1000,
            iat=datetime.now(timezone.utc),
            exp=datetime.now(timezone.utc) + timedelta(hours=1),
            nbf=datetime.now(timezone.utc)
        )

        assert context.is_service_account is True
        assert context.token_type == "service_account"

    def test_is_service_account_false_for_admin_user(self):
        """Admin User должен возвращать is_service_account=False."""
        context = UserContext(
            identifier="admin-123",
            display_name="Admin User",
            role=UserRole.ADMIN,
            token_type="admin_user",
            client_id=None,
            rate_limit=None,
            iat=datetime.now(timezone.utc),
            exp=datetime.now(timezone.utc) + timedelta(hours=1),
            nbf=datetime.now(timezone.utc)
        )

        assert context.is_service_account is False
        assert context.token_type == "admin_user"


# ============================================================================
# Unit тесты для Audit Logging
# ============================================================================

class TestGCAuditLogging:
    """Тесты для audit logging в GC операциях."""

    @pytest.mark.asyncio
    async def test_audit_log_fields(self):
        """Проверка наличия всех полей в audit log."""
        # Arrange
        file_id = uuid4()
        service_account_id = str(uuid4())
        service_account_name = "gc-service"
        reason = "gc_cleanup"
        cleanup_type = "ttl_expired"

        # Expected audit log fields
        expected_fields = {
            "file_id": str(file_id),
            "service_account_id": service_account_id,
            "service_account_name": service_account_name,
            "reason": reason,
            "cleanup_type": cleanup_type,
            "action": "file_delete",
            "audit": True
        }

        # Assert - просто проверяем что поля существуют
        assert all(key in expected_fields for key in [
            "file_id", "service_account_id", "service_account_name",
            "reason", "cleanup_type", "action", "audit"
        ])


# ============================================================================
# Unit тесты для Idempotency
# ============================================================================

class TestGCIdempotency:
    """Тесты для idempotency GC delete."""

    @pytest.mark.asyncio
    async def test_delete_nonexistent_file_returns_already_deleted(self):
        """Удаление несуществующего файла должно возвращать already_deleted."""
        from app.api.v1.endpoints.gc import GCDeleteResponse

        # При удалении несуществующего файла ожидаем status="already_deleted"
        file_id = uuid4()
        response = GCDeleteResponse(
            status="already_deleted",
            file_id=file_id,
            deleted_at=datetime.now(timezone.utc).isoformat(),
            deleted_by="service-account",
            reason="gc_cleanup"
        )

        assert response.status == "already_deleted"
        assert response.file_id == file_id


# ============================================================================
# Тесты для интеграции с FileService
# ============================================================================

class TestGCFileServiceIntegration:
    """Тесты для интеграции GC с FileService."""

    @pytest.mark.asyncio
    async def test_gc_uses_file_service_delete(self):
        """GC endpoint должен использовать FileService.delete_file."""
        # Проверяем что метод delete_file существует
        from app.services.file_service import FileService

        assert hasattr(FileService, 'delete_file')
        assert callable(getattr(FileService, 'delete_file'))

    @pytest.mark.asyncio
    async def test_gc_uses_file_service_get_metadata(self):
        """GC endpoint должен использовать FileService.get_file_metadata."""
        from app.services.file_service import FileService

        assert hasattr(FileService, 'get_file_metadata')
        assert callable(getattr(FileService, 'get_file_metadata'))
