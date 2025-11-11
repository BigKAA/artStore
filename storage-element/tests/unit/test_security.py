"""
Unit tests для app/core/security.py

Тестируемые компоненты:
- UserRole: Enum для ролей пользователей
- TokenType: Enum для типов токенов
- UserContext: Контекст пользователя из JWT
- JWTValidator: Валидация JWT токенов
- Permission functions: require_role, require_admin, require_operator
"""

import pytest
from datetime import datetime, timedelta
import jwt

from app.core.security import (
    UserRole,
    TokenType,
    UserContext,
    JWTValidator,
    require_role,
    require_admin,
    require_operator
)
from app.core.exceptions import (
    InvalidTokenException,
    TokenExpiredException,
    InsufficientPermissionsException
)


# ==========================================
# Test UserContext
# ==========================================

class TestUserContext:
    """Тесты для UserContext модели"""

    def test_create_user_context(self):
        """Создание user context"""
        user = UserContext(
            sub="123",
            username="testuser",
            email="test@example.com",
            role=UserRole.USER,
            type=TokenType.ACCESS,
            iat=datetime.now(),
            exp=datetime.now() + timedelta(hours=1)
        )

        assert user.user_id == "123"
        assert user.username == "testuser"
        assert user.role == UserRole.USER

    def test_is_admin_property(self):
        """Проверка is_admin property"""
        admin = UserContext(
            sub="1",
            username="admin",
            role=UserRole.ADMIN,
            type=TokenType.ACCESS,
            iat=datetime.now(),
            exp=datetime.now() + timedelta(hours=1)
        )

        user = UserContext(
            sub="2",
            username="user",
            role=UserRole.USER,
            type=TokenType.ACCESS,
            iat=datetime.now(),
            exp=datetime.now() + timedelta(hours=1)
        )

        assert admin.is_admin is True
        assert user.is_admin is False

    def test_is_operator_property(self):
        """Проверка is_operator property"""
        admin = UserContext(
            sub="1",
            username="admin",
            role=UserRole.ADMIN,
            type=TokenType.ACCESS,
            iat=datetime.now(),
            exp=datetime.now() + timedelta(hours=1)
        )

        operator = UserContext(
            sub="2",
            username="operator",
            role=UserRole.OPERATOR,
            type=TokenType.ACCESS,
            iat=datetime.now(),
            exp=datetime.now() + timedelta(hours=1)
        )

        user = UserContext(
            sub="3",
            username="user",
            role=UserRole.USER,
            type=TokenType.ACCESS,
            iat=datetime.now(),
            exp=datetime.now() + timedelta(hours=1)
        )

        assert admin.is_operator is True
        assert operator.is_operator is True
        assert user.is_operator is False

    def test_has_role_hierarchy(self):
        """Проверка иерархии ролей"""
        admin = UserContext(
            sub="1",
            username="admin",
            role=UserRole.ADMIN,
            type=TokenType.ACCESS,
            iat=datetime.now(),
            exp=datetime.now() + timedelta(hours=1)
        )

        operator = UserContext(
            sub="2",
            username="operator",
            role=UserRole.OPERATOR,
            type=TokenType.ACCESS,
            iat=datetime.now(),
            exp=datetime.now() + timedelta(hours=1)
        )

        user = UserContext(
            sub="3",
            username="user",
            role=UserRole.USER,
            type=TokenType.ACCESS,
            iat=datetime.now(),
            exp=datetime.now() + timedelta(hours=1)
        )

        # Admin имеет все роли
        assert admin.has_role(UserRole.ADMIN) is True
        assert admin.has_role(UserRole.OPERATOR) is True
        assert admin.has_role(UserRole.USER) is True

        # Operator имеет operator и user
        assert operator.has_role(UserRole.ADMIN) is False
        assert operator.has_role(UserRole.OPERATOR) is True
        assert operator.has_role(UserRole.USER) is True

        # User имеет только user
        assert user.has_role(UserRole.ADMIN) is False
        assert user.has_role(UserRole.OPERATOR) is False
        assert user.has_role(UserRole.USER) is True


# ==========================================
# Test Permission Functions
# ==========================================

class TestPermissionFunctions:
    """Тесты для функций проверки прав"""

    def test_require_role_success(self):
        """Успешная проверка роли"""
        admin = UserContext(
            sub="1",
            username="admin",
            role=UserRole.ADMIN,
            type=TokenType.ACCESS,
            iat=datetime.now(),
            exp=datetime.now() + timedelta(hours=1)
        )

        # Не должно выбросить исключение
        require_role(UserRole.USER, admin)
        require_role(UserRole.OPERATOR, admin)
        require_role(UserRole.ADMIN, admin)

    def test_require_role_insufficient_permissions(self):
        """Недостаточно прав"""
        user = UserContext(
            sub="1",
            username="user",
            role=UserRole.USER,
            type=TokenType.ACCESS,
            iat=datetime.now(),
            exp=datetime.now() + timedelta(hours=1)
        )

        with pytest.raises(InsufficientPermissionsException):
            require_role(UserRole.ADMIN, user)

    def test_require_admin_success(self):
        """Успешная проверка admin роли"""
        admin = UserContext(
            sub="1",
            username="admin",
            role=UserRole.ADMIN,
            type=TokenType.ACCESS,
            iat=datetime.now(),
            exp=datetime.now() + timedelta(hours=1)
        )

        require_admin(admin)  # Не должно выбросить исключение

    def test_require_admin_failure(self):
        """Провал проверки admin роли"""
        user = UserContext(
            sub="1",
            username="user",
            role=UserRole.USER,
            type=TokenType.ACCESS,
            iat=datetime.now(),
            exp=datetime.now() + timedelta(hours=1)
        )

        with pytest.raises(InsufficientPermissionsException):
            require_admin(user)

    def test_require_operator_success(self):
        """Успешная проверка operator роли"""
        operator = UserContext(
            sub="1",
            username="operator",
            role=UserRole.OPERATOR,
            type=TokenType.ACCESS,
            iat=datetime.now(),
            exp=datetime.now() + timedelta(hours=1)
        )

        require_operator(operator)  # Не должно выбросить исключение

    def test_require_operator_admin_success(self):
        """Admin также проходит проверку operator"""
        admin = UserContext(
            sub="1",
            username="admin",
            role=UserRole.ADMIN,
            type=TokenType.ACCESS,
            iat=datetime.now(),
            exp=datetime.now() + timedelta(hours=1)
        )

        require_operator(admin)  # Не должно выбросить исключение

    def test_require_operator_failure(self):
        """Провал проверки operator роли"""
        user = UserContext(
            sub="1",
            username="user",
            role=UserRole.USER,
            type=TokenType.ACCESS,
            iat=datetime.now(),
            exp=datetime.now() + timedelta(hours=1)
        )

        with pytest.raises(InsufficientPermissionsException):
            require_operator(user)


# ==========================================
# Test JWTValidator
# ==========================================

class TestJWTValidator:
    """Тесты для JWTValidator (упрощенные)"""

    def test_validate_token_success(self, test_jwt_keys, test_jwt_token):
        """Успешная валидация токена (integration with conftest fixtures)"""
        # Этот тест зависит от fixtures из conftest.py
        # В реальной реализации нужно mock settings.jwt.public_key_path
        pass

    def test_validate_expired_token(self):
        """Валидация истекшего токена"""
        # TODO: Требует mock для settings и генерации истекшего токена
        pass

    def test_validate_invalid_signature(self):
        """Валидация токена с невалидной подписью"""
        # TODO: Требует mock для settings и токена с неправильной подписью
        pass


# Примечание: Полноценное тестирование JWTValidator требует:
# 1. Mock для settings.jwt.public_key_path
# 2. Временные файлы с публичным ключом
# 3. Генерация различных типов токенов
# Эти тесты будут добавлены в следующей итерации
