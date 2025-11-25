"""
Unit тесты для AuthService.
Тестируют локальную аутентификацию, password management, и user lookups.
"""

import pytest
from datetime import datetime, timedelta
from app.services.auth_service import auth_service
from app.models.user import User, UserRole, UserStatus

# Этот модуль содержит async тесты
pytestmark = pytest.mark.asyncio


# Helper функция для создания локального пользователя
def create_local_user():
    """Создание локального пользователя для тестирования."""
    hashed_password = auth_service.hash_password("password123")
    return User(
        username="localuser",
        email="local@example.com",
        first_name="Local",
        last_name="User",
        hashed_password=hashed_password,
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
        role=UserRole.USER,
        status=UserStatus.LOCKED,
        is_system=False,
        failed_login_attempts=5,
        lockout_until=datetime.utcnow() + timedelta(minutes=30)
    )


class TestPasswordManagement:
    """Тесты для управления паролями."""

    def test_hash_password(self):
        """Тест хеширования пароля."""
        password = "test_password_123"
        hashed = auth_service.hash_password(password)

        assert hashed is not None
        assert isinstance(hashed, str)
        assert len(hashed) > 0
        # bcrypt хеш должен начинаться с $2b$
        assert hashed.startswith("$2b$")

    def test_hash_password_different_each_time(self):
        """Тест что хеш одинакового пароля каждый раз разный (salt)."""
        password = "test_password_123"
        hash1 = auth_service.hash_password(password)
        hash2 = auth_service.hash_password(password)

        assert hash1 != hash2

    def test_verify_password_correct(self):
        """Тест верификации правильного пароля."""
        password = "correct_password"
        hashed = auth_service.hash_password(password)

        assert auth_service.verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """Тест верификации неправильного пароля."""
        password = "correct_password"
        hashed = auth_service.hash_password(password)

        assert auth_service.verify_password("wrong_password", hashed) is False

    def test_verify_password_empty(self):
        """Тест верификации пустого пароля."""
        password = "test_password"
        hashed = auth_service.hash_password(password)

        assert auth_service.verify_password("", hashed) is False

    def test_verify_password_invalid_hash(self):
        """Тест верификации с невалидным хешем."""
        password = "test_password"
        invalid_hash = "not_a_valid_hash"

        assert auth_service.verify_password(password, invalid_hash) is False


class TestLocalAuthentication:
    """Тесты для локальной аутентификации."""

    @pytest.mark.asyncio
    async def test_authenticate_local_success(self, db_session):
        """Тест успешной локальной аутентификации."""
        # Создаем и добавляем пользователя в БД
        local_user = create_local_user()
        db_session.add(local_user)
        await db_session.commit()

        # Аутентифицируем
        user = await auth_service.authenticate_local(
            db_session,
            "localuser",
            "password123"
        )

        assert user is not None
        assert user.username == "localuser"
        assert user.failed_login_attempts == 0
        assert user.last_login is not None

    @pytest.mark.asyncio
    async def test_authenticate_local_by_email(self, db_session):
        """Тест аутентификации по email вместо username."""
        local_user = create_local_user()
        db_session.add(local_user)
        await db_session.commit()

        user = await auth_service.authenticate_local(
            db_session,
            "local@example.com",  # email вместо username
            "password123"
        )

        assert user is not None
        assert user.email == "local@example.com"

    @pytest.mark.asyncio
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

        # Проверяем что failed_attempts увеличился
        await db_session.refresh(local_user)
        assert local_user.failed_login_attempts == 1

    @pytest.mark.asyncio
    async def test_authenticate_local_user_not_found(self, db_session):
        """Тест с несуществующим пользователем."""
        user = await auth_service.authenticate_local(
            db_session,
            "nonexistent_user",
            "password123"
        )

        assert user is None

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
    async def test_authenticate_local_multiple_failed_attempts(self, db_session):
        """Тест блокировки после множественных неудачных попыток."""
        local_user = create_local_user()
        db_session.add(local_user)
        await db_session.commit()

        # Делаем 5 неудачных попыток
        for _ in range(5):
            await auth_service.authenticate_local(
                db_session,
                "localuser",
                "wrong_password"
            )
            await db_session.refresh(local_user)

        # Пользователь должен быть заблокирован
        assert local_user.failed_login_attempts >= 5
        assert local_user.status == UserStatus.LOCKED
        assert local_user.lockout_until is not None

    @pytest.mark.asyncio
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


class TestUserLookup:
    """Тесты для поиска пользователей."""

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
    async def test_get_user_by_id_not_found(self, db_session):
        """Тест поиска несуществующего пользователя по ID."""
        user = await auth_service.get_user_by_id(db_session, 99999)

        assert user is None

    @pytest.mark.asyncio
    async def test_get_user_by_username_found(self, db_session):
        """Тест поиска пользователя по username."""
        local_user = create_local_user()
        db_session.add(local_user)
        await db_session.commit()

        user = await auth_service.get_user_by_username(db_session, "localuser")

        assert user is not None
        assert user.username == "localuser"

    @pytest.mark.asyncio
    async def test_get_user_by_username_not_found(self, db_session):
        """Тест поиска несуществующего пользователя по username."""
        user = await auth_service.get_user_by_username(db_session, "nonexistent")

        assert user is None


class TestPasswordReset:
    """Тесты для сброса пароля."""

    @pytest.mark.asyncio
    async def test_create_password_reset_token_success(self, db_session):
        """Тест создания токена для сброса пароля."""
        local_user = create_local_user()
        db_session.add(local_user)
        await db_session.commit()

        token = await auth_service.create_password_reset_token(
            db_session,
            "local@example.com"
        )

        # Пока возвращается placeholder
        assert token is not None

    @pytest.mark.asyncio
    async def test_create_password_reset_token_user_not_found(self, db_session):
        """Тест создания токена для несуществующего email."""
        token = await auth_service.create_password_reset_token(
            db_session,
            "nonexistent@example.com"
        )

        # Не раскрываем что пользователь не найден (security)
        assert token is None

    @pytest.mark.asyncio
    async def test_reset_password(self, db_session):
        """Тест сброса пароля (пока заглушка)."""
        success = await auth_service.reset_password(
            db_session,
            "reset_token",
            "new_password"
        )

        # Пока возвращается False (TODO: implement)
        assert success is False
