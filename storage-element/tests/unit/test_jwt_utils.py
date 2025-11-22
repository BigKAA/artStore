"""
Unit tests для JWT Token Generation Utilities.

Тестируют корректность генерации, верификации и валидации
JWT токенов для integration tests.
"""

import pytest
import jwt
from datetime import datetime, timedelta, timezone

from tests.utils.jwt_utils import (
    generate_test_jwt_token,
    verify_test_jwt_token,
    create_auth_headers,
    create_service_account_token,
    load_private_key,
    load_public_key,
)


class TestJWTKeyLoading:
    """Тесты для загрузки JWT ключей"""

    def test_load_private_key_exists(self):
        """Тест что приватный ключ существует и загружается"""
        private_key = load_private_key()

        assert private_key is not None
        assert isinstance(private_key, str)
        assert "-----BEGIN PRIVATE KEY-----" in private_key
        assert "-----END PRIVATE KEY-----" in private_key

    def test_load_public_key_exists(self):
        """Тест что публичный ключ существует и загружается"""
        public_key = load_public_key()

        assert public_key is not None
        assert isinstance(public_key, str)
        assert "-----BEGIN PUBLIC KEY-----" in public_key
        assert "-----END PUBLIC KEY-----" in public_key


class TestJWTTokenGeneration:
    """Тесты для генерации JWT токенов"""

    def test_generate_basic_token(self):
        """Тест генерации токена с базовыми параметрами"""
        token = generate_test_jwt_token()

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 100  # JWT токены длинные

    def test_generate_token_with_custom_params(self):
        """Тест генерации токена с custom параметрами"""
        token = generate_test_jwt_token(
            user_id="custom_user",
            username="admin",
            email="admin@artstore.local",
            role="admin"
        )

        # Декодируем и проверяем payload
        payload = verify_test_jwt_token(token)

        assert payload["sub"] == "custom_user"
        assert payload["username"] == "admin"
        assert payload["email"] == "admin@artstore.local"
        assert payload["role"] == "admin"

    def test_generate_token_with_custom_claims(self):
        """Тест добавления custom claims в токен"""
        custom_claims = {
            "department": "Engineering",
            "permissions": ["read", "write", "delete"]
        }

        token = generate_test_jwt_token(custom_claims=custom_claims)
        payload = verify_test_jwt_token(token)

        assert payload["department"] == "Engineering"
        assert payload["permissions"] == ["read", "write", "delete"]

    def test_token_expiration_time(self):
        """Тест что expiration time установлен корректно"""
        expires_in = 60  # 60 минут
        token = generate_test_jwt_token(expires_in_minutes=expires_in)
        payload = verify_test_jwt_token(token)

        # Проверка что exp установлен
        assert "exp" in payload
        assert "iat" in payload

        # Проверка что разница примерно 60 минут (с погрешностью 10 секунд)
        exp_time = datetime.fromtimestamp(payload["exp"])
        iat_time = datetime.fromtimestamp(payload["iat"])
        delta = exp_time - iat_time

        assert abs(delta.total_seconds() - (expires_in * 60)) < 10

    def test_token_contains_required_claims(self):
        """Тест что токен содержит все обязательные claims"""
        token = generate_test_jwt_token()
        payload = verify_test_jwt_token(token)

        # Обязательные JWT claims
        assert "sub" in payload  # Subject (user ID)
        assert "iat" in payload  # Issued At
        assert "exp" in payload  # Expiration Time
        assert "nbf" in payload  # Not Before

        # Application-specific claims
        assert "username" in payload
        assert "email" in payload
        assert "role" in payload
        assert "type" in payload
        assert payload["type"] == "access"


class TestJWTTokenVerification:
    """Тесты для верификации JWT токенов"""

    def test_verify_valid_token(self):
        """Тест верификации валидного токена"""
        token = generate_test_jwt_token(username="test_verify")
        payload = verify_test_jwt_token(token)

        assert payload is not None
        assert payload["username"] == "test_verify"

    def test_verify_token_algorithm(self):
        """Тест что используется RS256 алгоритм"""
        token = generate_test_jwt_token()

        # Декодируем header без верификации
        header = jwt.get_unverified_header(token)

        assert header["alg"] == "RS256"
        assert header["typ"] == "JWT"

    def test_verify_expired_token_fails(self):
        """Тест что expired токен не проходит верификацию"""
        # Создаем токен с истекшим временем (expires_in = -1 минута в прошлом)
        private_key = load_private_key()
        now = datetime.now(timezone.utc)
        expired_time = now - timedelta(minutes=1)

        payload = {
            "sub": "expired_user",
            "username": "expired",
            "email": "expired@test.local",
            "role": "user",
            "type": "access",
            "iat": int(now.timestamp()),
            "exp": int(expired_time.timestamp()),  # Expired
            "nbf": int(now.timestamp()),
        }

        expired_token = jwt.encode(payload, private_key, algorithm="RS256")

        # Верификация должна вызвать ExpiredSignatureError когда verify_expiration=True
        with pytest.raises(jwt.ExpiredSignatureError):
            verify_test_jwt_token(expired_token, verify_expiration=True)

    def test_verify_invalid_signature_fails(self):
        """Тест что токен с invalid signature не проходит верификацию"""
        token = generate_test_jwt_token()

        # Изменяем middle часть signature (гарантированно портим signature)
        parts = token.split('.')
        if len(parts) == 3:
            # Изменяем signature часть (3-я часть токена)
            signature = parts[2]
            # Заменяем несколько символов в середине signature
            mid = len(signature) // 2
            corrupted_sig = signature[:mid] + "XXXXX" + signature[mid+5:]
            invalid_token = f"{parts[0]}.{parts[1]}.{corrupted_sig}"
        else:
            # Fallback на изменение последнего символа
            invalid_token = token[:-1] + ("X" if token[-1] != "X" else "Y")

        # Верификация должна вызвать InvalidSignatureError
        with pytest.raises(jwt.InvalidSignatureError):
            verify_test_jwt_token(invalid_token)


class TestAuthHeadersCreation:
    """Тесты для создания HTTP auth headers"""

    def test_create_auth_headers_default(self):
        """Тест создания headers с default параметрами"""
        headers = create_auth_headers()

        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Bearer ")

        # Извлекаем и верифицируем токен
        token = headers["Authorization"].replace("Bearer ", "")
        payload = verify_test_jwt_token(token)

        assert payload["username"] == "test_user"
        assert payload["role"] == "admin"

    def test_create_auth_headers_with_params(self):
        """Тест создания headers с custom параметрами"""
        headers = create_auth_headers(
            username="custom_admin",
            role="admin",
            email="custom@artstore.local"
        )

        token = headers["Authorization"].replace("Bearer ", "")
        payload = verify_test_jwt_token(token)

        assert payload["username"] == "custom_admin"
        assert payload["email"] == "custom@artstore.local"

    def test_create_auth_headers_with_token(self):
        """Тест создания headers с готовым токеном"""
        token = generate_test_jwt_token(username="pregenerated")
        headers = create_auth_headers(token=token)

        assert headers["Authorization"] == f"Bearer {token}"

        # Верифицируем что это наш токен
        extracted_token = headers["Authorization"].replace("Bearer ", "")
        payload = verify_test_jwt_token(extracted_token)
        assert payload["username"] == "pregenerated"


class TestServiceAccountTokens:
    """Тесты для service account токенов"""

    def test_create_service_account_token(self):
        """Тест создания service account токена"""
        token = create_service_account_token(
            client_id="test_service",
            role="service"
        )

        payload = verify_test_jwt_token(token)

        assert payload["sub"] == "test_service"
        assert payload["username"] == "test_service"
        assert payload["role"] == "service"
        assert payload["type"] == "service_account"
        assert payload["client_id"] == "test_service"

    def test_service_account_email_format(self):
        """Тест формата email для service account"""
        client_id = "storage_service"
        token = create_service_account_token(client_id=client_id)
        payload = verify_test_jwt_token(token)

        expected_email = f"{client_id}@service.artstore.local"
        assert payload["email"] == expected_email

    def test_service_account_with_admin_role(self):
        """Тест создания service account с admin ролью"""
        token = create_service_account_token(
            client_id="admin_service",
            role="admin"
        )

        payload = verify_test_jwt_token(token)

        assert payload["role"] == "admin"
        assert payload["type"] == "service_account"


class TestJWTTokenIntegration:
    """Integration тесты для JWT token workflow"""

    def test_full_workflow_generate_verify(self):
        """Тест полного workflow: генерация → верификация"""
        # Генерация
        token = generate_test_jwt_token(
            username="integration_user",
            role="admin"
        )

        # Верификация
        payload = verify_test_jwt_token(token)

        # Проверка данных
        assert payload["username"] == "integration_user"
        assert payload["role"] == "admin"

    def test_multiple_tokens_independent(self):
        """Тест что несколько токенов независимы друг от друга"""
        token1 = generate_test_jwt_token(username="user1")
        token2 = generate_test_jwt_token(username="user2")

        # Токены должны быть разными
        assert token1 != token2

        # Каждый токен верифицируется независимо
        payload1 = verify_test_jwt_token(token1)
        payload2 = verify_test_jwt_token(token2)

        assert payload1["username"] == "user1"
        assert payload2["username"] == "user2"

    def test_auth_headers_usable_in_requests(self):
        """Тест что auth headers подходят для HTTP requests"""
        headers = create_auth_headers(
            username="api_user",
            role="admin"
        )

        # Проверка формата headers
        assert isinstance(headers, dict)
        assert "Authorization" in headers
        assert isinstance(headers["Authorization"], str)

        # Проверка что токен валидный
        token = headers["Authorization"].replace("Bearer ", "")
        payload = verify_test_jwt_token(token)
        assert payload["username"] == "api_user"
