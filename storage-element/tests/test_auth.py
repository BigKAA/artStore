"""
Unit tests для JWT authentication и RBAC system.

Тестирует:
- JWT token validation с RS256
- User model и permissions
- RBAC permission matrix
- FastAPI dependencies
"""

import pytest
import jwt
from datetime import datetime, timezone, timedelta
from pathlib import Path

from app.core.auth import (
    User,
    UserRole,
    Permission,
    TokenPayload,
    JWTValidator,
    AuthenticationError,
    AuthorizationError,
    ROLE_PERMISSIONS,
    validate_token_and_get_user,
    check_permission,
    check_any_permission,
    check_role,
)


class TestUserModel:
    """Тесты для User model и permission checks."""

    def test_user_has_role(self):
        """Тест проверки наличия роли."""
        user = User(
            user_id="123",
            username="testuser",
            roles=[UserRole.USER, UserRole.READONLY]
        )

        assert user.has_role(UserRole.USER) is True
        assert user.has_role(UserRole.READONLY) is True
        assert user.has_role(UserRole.ADMIN) is False

    def test_user_has_any_role(self):
        """Тест проверки наличия хотя бы одной роли."""
        user = User(
            user_id="123",
            username="testuser",
            roles=[UserRole.USER]
        )

        assert user.has_any_role([UserRole.USER, UserRole.ADMIN]) is True
        assert user.has_any_role([UserRole.ADMIN, UserRole.OPERATOR]) is False

    def test_user_has_permission(self):
        """Тест проверки наличия разрешения."""
        user = User(
            user_id="123",
            username="testuser",
            roles=[UserRole.USER]
        )

        # USER имеет FILE_CREATE permission
        assert user.has_permission(Permission.FILE_CREATE) is True
        assert user.has_permission(Permission.FILE_READ) is True

        # USER не имеет ADMIN permissions
        assert user.has_permission(Permission.ADMIN_USERS) is False

    def test_user_has_any_permission(self):
        """Тест проверки наличия хотя бы одного разрешения."""
        user = User(
            user_id="123",
            username="testuser",
            roles=[UserRole.READONLY]
        )

        # READONLY имеет FILE_READ
        assert user.has_any_permission([
            Permission.FILE_READ,
            Permission.FILE_CREATE
        ]) is True

        # READONLY не имеет FILE_DELETE или ADMIN_USERS
        assert user.has_any_permission([
            Permission.FILE_DELETE,
            Permission.ADMIN_USERS
        ]) is False

    def test_user_has_all_permissions(self):
        """Тест проверки наличия всех разрешений."""
        user = User(
            user_id="123",
            username="admin",
            roles=[UserRole.ADMIN]
        )

        # ADMIN имеет все permissions
        assert user.has_all_permissions([
            Permission.FILE_CREATE,
            Permission.FILE_DELETE,
            Permission.ADMIN_USERS
        ]) is True

        readonly_user = User(
            user_id="456",
            username="readonly",
            roles=[UserRole.READONLY]
        )

        # READONLY не имеет FILE_CREATE
        assert readonly_user.has_all_permissions([
            Permission.FILE_READ,
            Permission.FILE_CREATE
        ]) is False

    def test_user_is_admin_property(self):
        """Тест is_admin property."""
        admin = User(
            user_id="1",
            username="admin",
            roles=[UserRole.ADMIN]
        )
        user = User(
            user_id="2",
            username="user",
            roles=[UserRole.USER]
        )

        assert admin.is_admin is True
        assert user.is_admin is False

    def test_user_all_permissions_property(self):
        """Тест all_permissions property."""
        user = User(
            user_id="123",
            username="user",
            roles=[UserRole.USER, UserRole.READONLY]
        )

        permissions = user.all_permissions

        # Должны быть permissions от обеих ролей
        assert Permission.FILE_CREATE in permissions  # от USER
        assert Permission.FILE_READ in permissions  # от обеих
        assert Permission.FILE_DELETE in permissions  # от USER
        assert Permission.ADMIN_USERS not in permissions  # нет ни у одной


class TestRolePermissions:
    """Тесты для матрицы разрешений ролей."""

    def test_admin_has_all_permissions(self):
        """ADMIN должен иметь все permissions."""
        admin_perms = ROLE_PERMISSIONS[UserRole.ADMIN]

        # Проверяем что есть все типы permissions
        assert Permission.FILE_CREATE in admin_perms
        assert Permission.FILE_DELETE in admin_perms
        assert Permission.ADMIN_USERS in admin_perms
        assert Permission.MODE_TRANSITION in admin_perms

    def test_readonly_has_only_read_permissions(self):
        """READONLY должен иметь только read permissions."""
        readonly_perms = ROLE_PERMISSIONS[UserRole.READONLY]

        # Должны быть только read permissions
        assert Permission.FILE_READ in readonly_perms
        assert Permission.FILE_SEARCH in readonly_perms
        assert Permission.METADATA_READ in readonly_perms

        # Не должно быть write/delete permissions
        assert Permission.FILE_CREATE not in readonly_perms
        assert Permission.FILE_DELETE not in readonly_perms
        assert Permission.FILE_UPDATE not in readonly_perms

    def test_operator_can_manage_modes(self):
        """OPERATOR должен иметь MODE_TRANSITION permission."""
        operator_perms = ROLE_PERMISSIONS[UserRole.OPERATOR]

        assert Permission.MODE_TRANSITION in operator_perms
        assert Permission.MODE_READ in operator_perms
        assert Permission.ADMIN_STORAGE in operator_perms

        # Но не должен иметь file creation/deletion
        assert Permission.FILE_CREATE not in operator_perms
        assert Permission.FILE_DELETE not in operator_perms

    def test_user_has_file_operations(self):
        """USER должен иметь основные файловые операции."""
        user_perms = ROLE_PERMISSIONS[UserRole.USER]

        assert Permission.FILE_CREATE in user_perms
        assert Permission.FILE_READ in user_perms
        assert Permission.FILE_UPDATE in user_perms
        assert Permission.FILE_DELETE in user_perms

        # Но не должен иметь admin permissions
        assert Permission.ADMIN_USERS not in user_perms
        assert Permission.ADMIN_SYSTEM not in user_perms


class TestJWTValidator:
    """Тесты для JWT validator."""

    @pytest.fixture
    def private_key(self):
        """Загрузка private key для генерации test tokens."""
        key_path = Path("keys/private_key.pem")
        with open(key_path, 'r') as f:
            return f.read()

    @pytest.fixture
    def validator(self):
        """Create validator instance."""
        return JWTValidator()

    def create_test_token(self, private_key: str, payload: dict) -> str:
        """
        Helper для создания test JWT token.

        Args:
            private_key: RSA private key PEM
            payload: Token payload

        Returns:
            str: Encoded JWT token
        """
        return jwt.encode(payload, private_key, algorithm="RS256")

    def test_validate_valid_token(self, validator, private_key):
        """Тест валидации корректного токена."""
        # Создаем valid token
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "user123",
            "username": "testuser",
            "roles": ["user"],
            "exp": int((now + timedelta(minutes=30)).timestamp()),
            "iat": int(now.timestamp())
        }

        token = self.create_test_token(private_key, payload)

        # Валидация
        token_payload = validator.validate_token(token)

        assert token_payload.sub == "user123"
        assert token_payload.username == "testuser"
        assert token_payload.roles == ["user"]

    def test_validate_expired_token(self, validator, private_key):
        """Тест валидации истекшего токена."""
        # Создаем expired token
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "user123",
            "username": "testuser",
            "roles": ["user"],
            "exp": int((now - timedelta(minutes=1)).timestamp()),  # Expired
            "iat": int((now - timedelta(minutes=31)).timestamp())
        }

        token = self.create_test_token(private_key, payload)

        # Должна быть ошибка
        with pytest.raises(AuthenticationError, match="expired"):
            validator.validate_token(token)

    def test_validate_invalid_signature(self, validator):
        """Тест валидации токена с неверной подписью."""
        # Создаем token с другим ключом
        other_key = """-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEAwMwz+GjcKKh/WCxHKLqjcBvH5gFDz7mH0u9cJJz4aGHjW3+Y
-----END RSA PRIVATE KEY-----"""

        now = datetime.now(timezone.utc)
        payload = {
            "sub": "user123",
            "username": "testuser",
            "roles": ["user"],
            "exp": int((now + timedelta(minutes=30)).timestamp()),
            "iat": int(now.timestamp())
        }

        # Token с wrong signature
        token = jwt.encode(payload, "wrong_key", algorithm="HS256")

        # Должна быть ошибка
        with pytest.raises(AuthenticationError):
            validator.validate_token(token)

    def test_validate_malformed_token(self, validator):
        """Тест валидации некорректного токена."""
        malformed_token = "not.a.valid.jwt.token"

        with pytest.raises(AuthenticationError):
            validator.validate_token(malformed_token)

    def test_create_user_from_token(self, validator, private_key):
        """Тест создания User из token payload."""
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "user123",
            "username": "testuser",
            "roles": ["admin", "user"],
            "email": "test@example.com",
            "full_name": "Test User",
            "exp": int((now + timedelta(minutes=30)).timestamp()),
            "iat": int(now.timestamp())
        }

        token = self.create_test_token(private_key, payload)
        token_payload = validator.validate_token(token)
        user = validator.create_user_from_token(token_payload)

        assert user.user_id == "user123"
        assert user.username == "testuser"
        assert UserRole.ADMIN in user.roles
        assert UserRole.USER in user.roles
        assert user.email == "test@example.com"
        assert user.full_name == "Test User"

    def test_create_user_with_invalid_role(self, validator, private_key):
        """Тест создания User с неизвестной ролью."""
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "user123",
            "username": "testuser",
            "roles": ["invalid_role", "user"],  # Invalid + valid role
            "exp": int((now + timedelta(minutes=30)).timestamp()),
            "iat": int(now.timestamp())
        }

        token = self.create_test_token(private_key, payload)
        token_payload = validator.validate_token(token)
        user = validator.create_user_from_token(token_payload)

        # Invalid role игнорируется, остается только USER
        assert UserRole.USER in user.roles
        assert len(user.roles) == 1

    def test_create_user_with_no_roles(self, validator, private_key):
        """Тест создания User без ролей (должна назначиться USER)."""
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "user123",
            "username": "testuser",
            "roles": [],  # No roles
            "exp": int((now + timedelta(minutes=30)).timestamp()),
            "iat": int(now.timestamp())
        }

        token = self.create_test_token(private_key, payload)
        token_payload = validator.validate_token(token)
        user = validator.create_user_from_token(token_payload)

        # Должна назначиться USER роль по умолчанию
        assert UserRole.USER in user.roles
        assert len(user.roles) == 1


class TestPermissionChecks:
    """Тесты для permission check functions."""

    def test_check_permission_success(self):
        """Тест успешной проверки разрешения."""
        user = User(
            user_id="123",
            username="testuser",
            roles=[UserRole.USER]
        )

        # Не должно быть exception
        check_permission(user, Permission.FILE_CREATE)

    def test_check_permission_failure(self):
        """Тест неуспешной проверки разрешения."""
        user = User(
            user_id="123",
            username="testuser",
            roles=[UserRole.READONLY]
        )

        # Должна быть AuthorizationError
        with pytest.raises(AuthorizationError):
            check_permission(user, Permission.FILE_CREATE)

    def test_check_any_permission_success(self):
        """Тест успешной проверки хотя бы одного разрешения."""
        user = User(
            user_id="123",
            username="testuser",
            roles=[UserRole.READONLY]
        )

        # READONLY имеет FILE_READ
        check_any_permission(user, [
            Permission.FILE_CREATE,
            Permission.FILE_READ
        ])

    def test_check_any_permission_failure(self):
        """Тест неуспешной проверки разрешений."""
        user = User(
            user_id="123",
            username="testuser",
            roles=[UserRole.READONLY]
        )

        # READONLY не имеет ни одного из этих permissions
        with pytest.raises(AuthorizationError):
            check_any_permission(user, [
                Permission.FILE_CREATE,
                Permission.FILE_DELETE
            ])

    def test_check_role_success(self):
        """Тест успешной проверки роли."""
        user = User(
            user_id="123",
            username="admin",
            roles=[UserRole.ADMIN]
        )

        # Не должно быть exception
        check_role(user, UserRole.ADMIN)

    def test_check_role_failure(self):
        """Тест неуспешной проверки роли."""
        user = User(
            user_id="123",
            username="user",
            roles=[UserRole.USER]
        )

        # Должна быть AuthorizationError
        with pytest.raises(AuthorizationError):
            check_role(user, UserRole.ADMIN)


class TestIntegrationScenarios:
    """Integration tests для реальных сценариев использования."""

    @pytest.fixture
    def private_key(self):
        """Загрузка private key."""
        key_path = Path("keys/private_key.pem")
        with open(key_path, 'r') as f:
            return f.read()

    def create_test_token(self, private_key: str, payload: dict) -> str:
        """Helper для создания test token."""
        return jwt.encode(payload, private_key, algorithm="RS256")

    def test_admin_full_access_workflow(self, private_key):
        """Тест полного workflow администратора."""
        # Создаем admin token
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "admin1",
            "username": "admin",
            "roles": ["admin"],
            "exp": int((now + timedelta(minutes=30)).timestamp()),
            "iat": int(now.timestamp())
        }

        token = self.create_test_token(private_key, payload)

        # Валидация и получение user
        user = validate_token_and_get_user(token)

        # Admin должен иметь все permissions
        assert user.is_admin is True
        assert user.has_permission(Permission.FILE_CREATE) is True
        assert user.has_permission(Permission.FILE_DELETE) is True
        assert user.has_permission(Permission.ADMIN_USERS) is True
        assert user.has_permission(Permission.MODE_TRANSITION) is True

        # Все permission checks должны проходить
        check_permission(user, Permission.ADMIN_SYSTEM)
        check_role(user, UserRole.ADMIN)

    def test_readonly_restricted_access_workflow(self, private_key):
        """Тест ограниченного доступа readonly пользователя."""
        # Создаем readonly token
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "readonly1",
            "username": "readonly_user",
            "roles": ["readonly"],
            "exp": int((now + timedelta(minutes=30)).timestamp()),
            "iat": int(now.timestamp())
        }

        token = self.create_test_token(private_key, payload)
        user = validate_token_and_get_user(token)

        # Readonly может только читать
        assert user.has_permission(Permission.FILE_READ) is True
        assert user.has_permission(Permission.FILE_SEARCH) is True

        # Readonly НЕ может создавать/удалять
        assert user.has_permission(Permission.FILE_CREATE) is False
        assert user.has_permission(Permission.FILE_DELETE) is False
        assert user.has_permission(Permission.ADMIN_USERS) is False

        # Permission checks должны фейлиться
        with pytest.raises(AuthorizationError):
            check_permission(user, Permission.FILE_CREATE)

    def test_operator_mode_management_workflow(self, private_key):
        """Тест workflow оператора управляющего режимами."""
        # Создаем operator token
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "op1",
            "username": "operator",
            "roles": ["operator"],
            "exp": int((now + timedelta(minutes=30)).timestamp()),
            "iat": int(now.timestamp())
        }

        token = self.create_test_token(private_key, payload)
        user = validate_token_and_get_user(token)

        # Operator может управлять режимами
        assert user.has_permission(Permission.MODE_TRANSITION) is True
        assert user.has_permission(Permission.ADMIN_STORAGE) is True

        # Но не может создавать/удалять файлы
        assert user.has_permission(Permission.FILE_CREATE) is False
        assert user.has_permission(Permission.FILE_DELETE) is False

        # Mode transition check должен проходить
        check_permission(user, Permission.MODE_TRANSITION)

        # File creation check должен фейлиться
        with pytest.raises(AuthorizationError):
            check_permission(user, Permission.FILE_CREATE)
