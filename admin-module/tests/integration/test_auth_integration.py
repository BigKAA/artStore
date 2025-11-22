"""
Integration тесты для authentication system.
Тестируют AuthService с базой данных и auth API endpoints.
"""

import pytest
from datetime import datetime, timedelta
from httpx import AsyncClient
from app.main import app
from app.services.auth_service import auth_service
from app.services.token_service import token_service
from app.models.user import User, UserRole, UserStatus


# Этот модуль содержит async тесты
pytestmark = pytest.mark.asyncio


# Helper функции для создания тестовых пользователей
def create_local_user():
    """Создание локального пользователя для тестирования."""
    hashed_password = auth_service.hash_password("password123")
    return User(
        username="localuser",
        email="local@example.com",
        first_name="Local",
        last_name="User",
        hashed_password=hashed_password,
        ldap_dn=None,
        role=UserRole.USER,
        status=UserStatus.ACTIVE,
        is_system=False,
        failed_login_attempts=0,
        lockout_until=None
    )


def create_ldap_user():
    """Создание LDAP пользователя для тестирования."""
    return User(
        username="ldapuser",
        email="ldap@example.com",
        first_name="LDAP",
        last_name="User",
        hashed_password=None,
        ldap_dn="cn=ldapuser,ou=users,dc=example,dc=com",
        role=UserRole.USER,
        status=UserStatus.ACTIVE,
        is_system=False,
        failed_login_attempts=0,
        lockout_until=None
    )


def create_locked_user():
    """Создание заблокированного пользователя."""
    hashed_password = auth_service.hash_password("password123")
    return User(
        username="lockeduser",
        email="locked@example.com",
        first_name="Locked",
        last_name="User",
        hashed_password=hashed_password,
        ldap_dn=None,
        role=UserRole.USER,
        status=UserStatus.LOCKED,
        is_system=False,
        failed_login_attempts=5,
        lockout_until=datetime.utcnow() + timedelta(minutes=30)
    )


# ============ AuthService Integration Tests ============

class TestAuthServiceIntegration:
    """Integration тесты для AuthService с базой данных."""

    async def test_authenticate_local_success(self, db_session):
        """Тест успешной локальной аутентификации."""
        local_user = create_local_user()
        db_session.add(local_user)
        await db_session.commit()

        user = await auth_service.authenticate_local(
            db_session,
            "localuser",
            "password123"
        )

        assert user is not None
        assert user.username == "localuser"
        assert user.failed_login_attempts == 0
        assert user.last_login is not None

    async def test_authenticate_local_by_email(self, db_session):
        """Тест аутентификации по email."""
        local_user = create_local_user()
        db_session.add(local_user)
        await db_session.commit()

        user = await auth_service.authenticate_local(
            db_session,
            "local@example.com",
            "password123"
        )

        assert user is not None
        assert user.email == "local@example.com"

    async def test_authenticate_local_wrong_password(self, db_session):
        """Тест с неправильным паролем."""
        local_user = create_local_user()
        db_session.add(local_user)
        await db_session.commit()

        user = await auth_service.authenticate_local(
            db_session,
            "localuser",
            "wrong_password"
        )

        assert user is None
        await db_session.refresh(local_user)
        assert local_user.failed_login_attempts == 1

    async def test_authenticate_local_user_not_found(self, db_session):
        """Тест с несуществующим пользователем."""
        user = await auth_service.authenticate_local(
            db_session,
            "nonexistent_user",
            "password123"
        )

        assert user is None

    async def test_authenticate_local_ldap_user_rejected(self, db_session):
        """Тест что LDAP пользователь не может авторизоваться локально."""
        ldap_user = create_ldap_user()
        db_session.add(ldap_user)
        await db_session.commit()

        user = await auth_service.authenticate_local(
            db_session,
            "ldapuser",
            "password123"
        )

        assert user is None

    async def test_authenticate_local_locked_user(self, db_session):
        """Тест что заблокированный пользователь не может войти."""
        locked_user = create_locked_user()
        db_session.add(locked_user)
        await db_session.commit()

        user = await auth_service.authenticate_local(
            db_session,
            "lockeduser",
            "password123"
        )

        assert user is None

    async def test_authenticate_local_inactive_user(self, db_session):
        """Тест что неактивный пользователь не может войти."""
        local_user = create_local_user()
        local_user.status = UserStatus.INACTIVE
        db_session.add(local_user)
        await db_session.commit()

        user = await auth_service.authenticate_local(
            db_session,
            "localuser",
            "password123"
        )

        assert user is None

    async def test_authenticate_local_multiple_failed_attempts(self, db_session):
        """Тест блокировки после множественных неудачных попыток."""
        local_user = create_local_user()
        db_session.add(local_user)
        await db_session.commit()

        for _ in range(5):
            await auth_service.authenticate_local(
                db_session,
                "localuser",
                "wrong_password"
            )
            await db_session.refresh(local_user)

        assert local_user.failed_login_attempts >= 5
        assert local_user.status == UserStatus.LOCKED
        assert local_user.lockout_until is not None

    async def test_authenticate_local_resets_failed_attempts_on_success(self, db_session):
        """Тест что failed_attempts сбрасывается при успешной аутентификации."""
        local_user = create_local_user()
        local_user.failed_login_attempts = 3
        db_session.add(local_user)
        await db_session.commit()

        user = await auth_service.authenticate_local(
            db_session,
            "localuser",
            "password123"
        )

        assert user is not None
        assert user.failed_login_attempts == 0
        assert user.last_login is not None

    async def test_get_user_by_id_found(self, db_session):
        """Тест поиска пользователя по ID."""
        local_user = create_local_user()
        db_session.add(local_user)
        await db_session.commit()
        await db_session.refresh(local_user)

        user = await auth_service.get_user_by_id(db_session, local_user.id)

        assert user is not None
        assert user.id == local_user.id
        assert user.username == "localuser"

    async def test_get_user_by_id_not_found(self, db_session):
        """Тест поиска несуществующего пользователя по ID."""
        user = await auth_service.get_user_by_id(db_session, 99999)

        assert user is None

    async def test_get_user_by_username_found(self, db_session):
        """Тест поиска пользователя по username."""
        local_user = create_local_user()
        db_session.add(local_user)
        await db_session.commit()

        user = await auth_service.get_user_by_username(db_session, "localuser")

        assert user is not None
        assert user.username == "localuser"

    async def test_get_user_by_username_not_found(self, db_session):
        """Тест поиска несуществующего пользователя по username."""
        user = await auth_service.get_user_by_username(db_session, "nonexistent")

        assert user is None


# ============ Auth API Endpoints Integration Tests ============

class TestAuthAPIEndpoints:
    """Integration тесты для auth API endpoints."""

    async def test_login_success(self, db_session):
        """Тест успешного логина через API."""
        # Создаем тестового пользователя
        local_user = create_local_user()
        db_session.add(local_user)
        await db_session.commit()

        # Выполняем запрос логина
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/login",
                json={
                    "username": "localuser",
                    "password": "password123"
                }
            )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    async def test_login_wrong_password(self, db_session):
        """Тест логина с неправильным паролем."""
        local_user = create_local_user()
        db_session.add(local_user)
        await db_session.commit()

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/login",
                json={
                    "username": "localuser",
                    "password": "wrong_password"
                }
            )

        assert response.status_code == 401
        assert "detail" in response.json()

    async def test_login_user_not_found(self):
        """Тест логина с несуществующим пользователем."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/login",
                json={
                    "username": "nonexistent",
                    "password": "password123"
                }
            )

        assert response.status_code == 401

    async def test_get_current_user(self, db_session):
        """Тест получения текущего пользователя."""
        local_user = create_local_user()
        db_session.add(local_user)
        await db_session.commit()
        await db_session.refresh(local_user)

        # Создаем токен для пользователя
        access_token = token_service.create_access_token(local_user)

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {access_token}"}
            )

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "localuser"
        assert data["email"] == "local@example.com"
        assert data["role"] == "user"

    async def test_get_current_user_invalid_token(self):
        """Тест получения пользователя с невалидным токеном."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/auth/me",
                headers={"Authorization": "Bearer invalid_token"}
            )

        assert response.status_code == 401

    async def test_get_current_user_no_token(self):
        """Тест получения пользователя без токена."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/api/v1/auth/me")

        assert response.status_code == 403  # Forbidden

    async def test_refresh_token_success(self, db_session):
        """Тест обновления access токена через refresh токен."""
        local_user = create_local_user()
        db_session.add(local_user)
        await db_session.commit()
        await db_session.refresh(local_user)

        # Создаем refresh токен
        refresh_token = token_service.create_refresh_token(local_user)

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": refresh_token}
            )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    async def test_refresh_token_invalid(self):
        """Тест обновления с невалидным refresh токеном."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": "invalid_token"}
            )

        assert response.status_code == 401

    async def test_refresh_token_wrong_type(self, db_session):
        """Тест обновления с access токеном вместо refresh."""
        local_user = create_local_user()
        db_session.add(local_user)
        await db_session.commit()
        await db_session.refresh(local_user)

        # Создаем access токен вместо refresh
        access_token = token_service.create_access_token(local_user)

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": access_token}
            )

        assert response.status_code == 401
