"""
Unit tests для JWT security validation модуля Ingester.

Тестирует:
- JWTValidator класс
- Token validation (valid, expired, invalid)
- UserContext extraction
- Role-based access control
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt as pyjwt

from app.core.exceptions import (
    InvalidTokenException,
    TokenExpiredException,
)
from app.core.security import JWTValidator, TokenType, UserContext, UserRole


class TestJWTValidator:
    """Тесты для JWTValidator класса."""

    @pytest.fixture
    def rsa_keys(self):
        """Generate RSA key pair for testing."""
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )

        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )

        public_key = private_key.public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        return private_pem, public_pem

    @pytest.fixture
    def public_key_file(self, rsa_keys, tmp_path):
        """Create temporary public key file."""
        _, public_pem = rsa_keys
        public_key_path = tmp_path / "public_key.pem"
        public_key_path.write_bytes(public_pem)
        return public_key_path

    @pytest.fixture
    def jwt_validator(self, public_key_file, monkeypatch):
        """Create JWTValidator instance with mocked settings."""
        # Patch settings to use test public key
        from app.core import config
        monkeypatch.setattr(config.settings.auth, 'public_key_path', public_key_file)
        return JWTValidator()

    def generate_token(
        self,
        rsa_keys,
        user_id: str = "test-user-id",
        username: str = "testuser",
        role: str = "USER",
        expires_delta: timedelta = timedelta(hours=1),
        **extra_claims
    ) -> str:
        """Helper to generate JWT tokens."""
        private_pem, _ = rsa_keys

        now = datetime.now(timezone.utc)
        claims = {
            "sub": user_id,
            "username": username,
            "role": role,
            "email": f"{username}@example.com",
            "type": "access",  # Changed from token_type to type (JWT standard)
            "iat": now,
            "exp": now + expires_delta,
            "jti": str(uuid4()),
            **extra_claims
        }

        return pyjwt.encode(claims, private_pem, algorithm="RS256")

    def test_validate_token_success(self, jwt_validator, rsa_keys):
        """Валидация корректного токена."""
        token = self.generate_token(
            rsa_keys,
            user_id="user-123",
            username="testuser",
            role="USER"
        )

        user_context = jwt_validator.validate_token(token)

        assert isinstance(user_context, UserContext)
        assert user_context.user_id == "user-123"
        assert user_context.username == "testuser"
        assert user_context.role == UserRole.USER
        assert user_context.email == "testuser@example.com"
        assert user_context.type == TokenType.ACCESS  # Changed from token_type to type

    def test_validate_token_admin_role(self, jwt_validator, rsa_keys):
        """Валидация токена с ADMIN ролью."""
        token = self.generate_token(
            rsa_keys,
            user_id="admin-123",
            username="admin",
            role="ADMIN"
        )

        user_context = jwt_validator.validate_token(token)

        assert user_context.role == UserRole.ADMIN
        assert user_context.username == "admin"

    def test_validate_token_operator_role(self, jwt_validator, rsa_keys):
        """Валидация токена с OPERATOR ролью."""
        token = self.generate_token(
            rsa_keys,
            user_id="operator-123",
            username="operator",
            role="OPERATOR"
        )

        user_context = jwt_validator.validate_token(token)

        assert user_context.role == UserRole.OPERATOR

    def test_validate_token_expired(self, jwt_validator, rsa_keys):
        """Валидация истекшего токена."""
        token = self.generate_token(
            rsa_keys,
            expires_delta=timedelta(seconds=-3600)  # Expired 1 hour ago
        )

        with pytest.raises(TokenExpiredException) as exc_info:
            jwt_validator.validate_token(token)

        assert "expired" in str(exc_info.value.message).lower()

    def test_validate_token_invalid_signature(self, jwt_validator):
        """Валидация токена с неправильной подписью."""
        # Create token with different key
        different_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        different_pem = different_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )

        now = datetime.now(timezone.utc)
        claims = {
            "sub": "user-id",
            "username": "testuser",
            "role": "USER",
            "email": "test@example.com",
            "type": "access",  # Changed from token_type to type
            "iat": now,
            "exp": now + timedelta(hours=1),
        }

        invalid_token = pyjwt.encode(claims, different_pem, algorithm="RS256")

        with pytest.raises(InvalidTokenException) as exc_info:
            jwt_validator.validate_token(invalid_token)

        assert "invalid" in str(exc_info.value.message).lower()

    def test_validate_token_malformed(self, jwt_validator):
        """Валидация некорректно сформированного токена."""
        malformed_tokens = [
            "not.a.jwt",
            "invalid-token",
            "",
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",  # Incomplete JWT
        ]

        for token in malformed_tokens:
            with pytest.raises(InvalidTokenException):
                jwt_validator.validate_token(token)

    def test_validate_token_missing_claims(self, jwt_validator, rsa_keys):
        """Валидация токена с отсутствующими обязательными claims."""
        private_pem, _ = rsa_keys

        # Token без обязательного claim 'sub'
        incomplete_claims = {
            "username": "testuser",
            "role": "USER",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1)
        }

        token = pyjwt.encode(incomplete_claims, private_pem, algorithm="RS256")

        with pytest.raises(InvalidTokenException):
            jwt_validator.validate_token(token)

    def test_validate_token_refresh_type(self, jwt_validator, rsa_keys):
        """Валидация refresh токена."""
        token = self.generate_token(
            rsa_keys,
            type="refresh"  # Changed from token_type to type
        )

        user_context = jwt_validator.validate_token(token)

        assert user_context.type == TokenType.REFRESH  # Changed from token_type to type

    def test_validator_caches_public_key(self, public_key_file, monkeypatch):
        """Проверка кеширования публичного ключа."""
        from app.core import config
        monkeypatch.setattr(config.settings.auth, 'public_key_path', public_key_file)
        validator = JWTValidator()

        # Public key should be loaded on initialization
        assert validator._public_key is not None

        # Second access should use cached key
        cached_key = validator._public_key
        assert validator._public_key is cached_key


class TestUserContext:
    """Тесты для UserContext модели."""

    def test_user_context_creation(self):
        """Создание UserContext с валидными данными."""
        now = datetime.now(timezone.utc)
        context = UserContext(
            sub="user-123",  # JWT standard: sub instead of user_id
            username="testuser",
            role=UserRole.USER,
            email="test@example.com",
            type=TokenType.ACCESS,  # JWT standard: type instead of token_type
            iat=now,  # Required field
            exp=now + timedelta(hours=1)  # Required field
        )

        assert context.user_id == "user-123"  # Property accessor
        assert context.sub == "user-123"  # Direct field
        assert context.username == "testuser"
        assert context.role == UserRole.USER
        assert context.email == "test@example.com"
        assert context.type == TokenType.ACCESS

    def test_user_context_role_hierarchy(self):
        """Проверка иерархии ролей."""
        now = datetime.now(timezone.utc)
        admin = UserContext(
            sub="admin",
            username="admin",
            role=UserRole.ADMIN,
            email="admin@example.com",
            type=TokenType.ACCESS,
            iat=now,
            exp=now + timedelta(hours=1)
        )

        operator = UserContext(
            sub="operator",
            username="operator",
            role=UserRole.OPERATOR,
            email="operator@example.com",
            type=TokenType.ACCESS,
            iat=now,
            exp=now + timedelta(hours=1)
        )

        user = UserContext(
            sub="user",
            username="user",
            role=UserRole.USER,
            email="user@example.com",
            type=TokenType.ACCESS,
            iat=now,
            exp=now + timedelta(hours=1)
        )

        # Проверка значений enum
        assert admin.role == UserRole.ADMIN
        assert operator.role == UserRole.OPERATOR
        assert user.role == UserRole.USER

    def test_user_context_optional_email(self):
        """email поле опциональное."""
        now = datetime.now(timezone.utc)
        context = UserContext(
            sub="user-123",
            username="testuser",
            role=UserRole.USER,
            type=TokenType.ACCESS,
            iat=now,
            exp=now + timedelta(hours=1)
        )

        assert context.email is None

    def test_user_context_default_token_type(self):
        """Проверка значения type поля."""
        now = datetime.now(timezone.utc)
        context = UserContext(
            sub="user-123",
            username="testuser",
            role=UserRole.USER,
            type=TokenType.ACCESS,  # Explicitly set
            iat=now,
            exp=now + timedelta(hours=1)
        )

        assert context.type == TokenType.ACCESS  # Changed from token_type to type


class TestUserRole:
    """Тесты для UserRole enum."""

    def test_user_role_values(self):
        """Проверка значений UserRole."""
        assert UserRole.ADMIN.value == "ADMIN"
        assert UserRole.OPERATOR.value == "OPERATOR"
        assert UserRole.USER.value == "USER"

    def test_user_role_from_string(self):
        """Создание UserRole из строки."""
        assert UserRole("ADMIN") == UserRole.ADMIN
        assert UserRole("OPERATOR") == UserRole.OPERATOR
        assert UserRole("USER") == UserRole.USER

    def test_user_role_invalid(self):
        """Невалидная роль."""
        with pytest.raises(ValueError):
            UserRole("SUPERUSER")


class TestTokenType:
    """Тесты для TokenType enum."""

    def test_token_type_values(self):
        """Проверка значений TokenType."""
        assert TokenType.ACCESS.value == "access"
        assert TokenType.REFRESH.value == "refresh"

    def test_token_type_from_string(self):
        """Создание TokenType из строки."""
        assert TokenType("access") == TokenType.ACCESS
        assert TokenType("refresh") == TokenType.REFRESH

    def test_token_type_invalid(self):
        """Невалидный тип токена."""
        with pytest.raises(ValueError):
            TokenType("bearer")
