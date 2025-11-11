"""
Unit тесты для TokenService.
Тестируют JWT token generation и validation.
"""

import pytest
from datetime import datetime, timedelta
from jose import jwt, JWTError
from app.services.token_service import token_service
from app.core.config import settings
from app.models.user import User, UserRole, UserStatus


# Mock пользователь для тестов
@pytest.fixture
def mock_user():
    """Создание mock пользователя для тестирования."""
    user = User(
        id=1,
        username="testuser",
        email="test@example.com",
        first_name="Test",
        last_name="User",
        hashed_password="hashed_password",
        role=UserRole.USER,
        status=UserStatus.ACTIVE
    )
    return user


@pytest.fixture
def mock_admin():
    """Создание mock администратора для тестирования."""
    user = User(
        id=2,
        username="admin",
        email="admin@example.com",
        first_name="Admin",
        last_name="User",
        hashed_password="hashed_password",
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE
    )
    return user


class TestTokenService:
    """Тесты для TokenService."""

    def test_create_access_token(self, mock_user):
        """Тест создания access токена."""
        token = token_service.create_access_token(user=mock_user)

        assert token is not None
        assert isinstance(token, str)

        # Декодируем токен для проверки claims
        decoded = jwt.decode(
            token,
            token_service._public_key,
            algorithms=[settings.jwt.algorithm]
        )

        assert decoded["sub"] == str(mock_user.id)
        assert decoded["username"] == mock_user.username
        assert decoded["email"] == mock_user.email
        assert decoded["role"] == mock_user.role.value
        assert decoded["type"] == "access"
        assert "iat" in decoded
        assert "exp" in decoded
        assert "nbf" in decoded

    def test_create_access_token_with_extra_claims(self, mock_user):
        """Тест создания access токена с дополнительными claims."""
        extra_claims = {"custom_field": "custom_value", "session_id": "123"}
        token = token_service.create_access_token(user=mock_user, extra_claims=extra_claims)

        assert token is not None

        decoded = jwt.decode(
            token,
            token_service._public_key,
            algorithms=[settings.jwt.algorithm]
        )

        assert decoded["custom_field"] == "custom_value"
        assert decoded["session_id"] == "123"

    def test_create_refresh_token(self, mock_user):
        """Тест создания refresh токена."""
        token = token_service.create_refresh_token(user=mock_user)

        assert token is not None
        assert isinstance(token, str)

        # Декодируем токен для проверки claims
        decoded = jwt.decode(
            token,
            token_service._public_key,
            algorithms=[settings.jwt.algorithm]
        )

        assert decoded["sub"] == str(mock_user.id)
        assert decoded["username"] == mock_user.username
        assert decoded["type"] == "refresh"
        assert "iat" in decoded
        assert "exp" in decoded
        assert "nbf" in decoded
        # Refresh токен не должен содержать email и role
        assert "email" not in decoded
        assert "role" not in decoded

    def test_create_token_pair(self, mock_user):
        """Тест создания пары токенов (access + refresh)."""
        access_token, refresh_token = token_service.create_token_pair(user=mock_user)

        assert access_token is not None
        assert refresh_token is not None
        assert isinstance(access_token, str)
        assert isinstance(refresh_token, str)
        assert access_token != refresh_token

        # Проверяем оба токена
        access_decoded = jwt.decode(
            access_token,
            token_service._public_key,
            algorithms=[settings.jwt.algorithm]
        )
        refresh_decoded = jwt.decode(
            refresh_token,
            token_service._public_key,
            algorithms=[settings.jwt.algorithm]
        )

        assert access_decoded["type"] == "access"
        assert refresh_decoded["type"] == "refresh"
        assert access_decoded["sub"] == refresh_decoded["sub"]

    def test_decode_token_success(self, mock_user):
        """Тест успешного декодирования токена."""
        token = token_service.create_access_token(user=mock_user)
        decoded = token_service.decode_token(token)

        assert decoded is not None
        assert decoded["sub"] == str(mock_user.id)
        assert decoded["username"] == mock_user.username
        assert decoded["email"] == mock_user.email
        assert decoded["role"] == mock_user.role.value

    def test_decode_token_invalid(self):
        """Тест декодирования невалидного токена."""
        invalid_token = "invalid.token.here"

        # TokenService.decode_token логирует ошибку и может вызвать исключение
        # Мы проверяем что метод корректно обрабатывает невалидные токены
        try:
            decoded = token_service.decode_token(invalid_token)
            # Если не raises, то должен вернуть None
            assert decoded is None
        except JWTError:
            # Это тоже валидное поведение
            pass

    def test_decode_token_expired(self):
        """Тест декодирования expired токена."""
        from jose.exceptions import ExpiredSignatureError

        # Создаем токен с expired временем
        claims = {
            "sub": "1",
            "username": "testuser",
            "email": "test@example.com",
            "role": "user",
            "type": "access",
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() - timedelta(hours=1),  # Expired час назад
            "nbf": datetime.utcnow() - timedelta(hours=2)
        }

        expired_token = jwt.encode(
            claims,
            token_service._private_key,
            algorithm=settings.jwt.algorithm
        )

        # TokenService.decode_token raises ExpiredSignatureError для expired токенов
        with pytest.raises(ExpiredSignatureError):
            token_service.decode_token(expired_token)

    def test_validate_token_success(self, mock_user):
        """Тест успешной валидации access токена."""
        token = token_service.create_access_token(user=mock_user)
        decoded = token_service.validate_token(token, token_type="access")

        assert decoded is not None
        assert decoded["type"] == "access"

    def test_validate_token_wrong_type(self, mock_user):
        """Тест валидации токена с неправильным типом."""
        access_token = token_service.create_access_token(user=mock_user)

        # Пытаемся валидировать access токен как refresh
        decoded = token_service.validate_token(access_token, token_type="refresh")

        # validate_token возвращает None для неправильного типа
        assert decoded is None

    def test_refresh_access_token_success(self, mock_user):
        """Тест успешного обновления access токена."""
        # Создаем refresh токен
        refresh_token = token_service.create_refresh_token(user=mock_user)

        # Обновляем access токен
        new_access_token = token_service.refresh_access_token(
            refresh_token=refresh_token,
            user=mock_user
        )

        assert new_access_token is not None

        # Проверяем новый access токен
        decoded = jwt.decode(
            new_access_token,
            token_service._public_key,
            algorithms=[settings.jwt.algorithm]
        )

        assert decoded["sub"] == str(mock_user.id)
        assert decoded["username"] == mock_user.username
        assert decoded["email"] == mock_user.email
        assert decoded["role"] == mock_user.role.value
        assert decoded["type"] == "access"

    def test_refresh_access_token_invalid_type(self, mock_user):
        """Тест обновления access токена с неправильным типом."""
        # Пытаемся использовать access токен вместо refresh
        access_token = token_service.create_access_token(user=mock_user)

        new_access_token = token_service.refresh_access_token(
            refresh_token=access_token,
            user=mock_user
        )

        # refresh_access_token возвращает None для неправильного типа
        assert new_access_token is None

    def test_get_user_id_from_token(self, mock_user):
        """Тест извлечения user_id из токена."""
        token = token_service.create_access_token(user=mock_user)
        extracted_user_id = token_service.get_user_id_from_token(token)

        assert extracted_user_id == mock_user.id

    def test_get_user_id_from_invalid_token(self):
        """Тест извлечения user_id из невалидного токена."""
        invalid_token = "invalid.token.here"
        extracted_user_id = token_service.get_user_id_from_token(invalid_token)

        # get_user_id_from_token возвращает None при ошибке
        assert extracted_user_id is None

    def test_token_expiration_times(self, mock_user):
        """Тест времени expiration токенов."""
        access_token = token_service.create_access_token(user=mock_user)
        refresh_token = token_service.create_refresh_token(user=mock_user)

        access_decoded = jwt.decode(
            access_token,
            token_service._public_key,
            algorithms=[settings.jwt.algorithm]
        )

        refresh_decoded = jwt.decode(
            refresh_token,
            token_service._public_key,
            algorithms=[settings.jwt.algorithm]
        )

        # Access токен должен expirять через ~30 минут
        access_exp = datetime.fromtimestamp(access_decoded["exp"])
        access_iat = datetime.fromtimestamp(access_decoded["iat"])
        access_lifetime = (access_exp - access_iat).total_seconds()

        # Refresh токен должен expirять через ~7 дней
        refresh_exp = datetime.fromtimestamp(refresh_decoded["exp"])
        refresh_iat = datetime.fromtimestamp(refresh_decoded["iat"])
        refresh_lifetime = (refresh_exp - refresh_iat).total_seconds()

        # Проверяем с небольшим допуском (±10 секунд)
        assert abs(access_lifetime - settings.jwt.access_token_expire_minutes * 60) < 10
        assert abs(refresh_lifetime - settings.jwt.refresh_token_expire_days * 86400) < 10

    def test_different_roles_in_tokens(self, mock_user, mock_admin):
        """Тест что разные роли корректно отражаются в токенах."""
        user_token = token_service.create_access_token(user=mock_user)
        admin_token = token_service.create_access_token(user=mock_admin)

        user_decoded = jwt.decode(
            user_token,
            token_service._public_key,
            algorithms=[settings.jwt.algorithm]
        )

        admin_decoded = jwt.decode(
            admin_token,
            token_service._public_key,
            algorithms=[settings.jwt.algorithm]
        )

        assert user_decoded["role"] == "user"
        assert admin_decoded["role"] == "admin"
        assert user_decoded["sub"] != admin_decoded["sub"]
