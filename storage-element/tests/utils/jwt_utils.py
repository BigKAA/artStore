"""
JWT Token Generation Utilities для Integration Tests.

Предоставляет функции для генерации валидных JWT токенов
для тестирования API endpoints с аутентификацией.

Использует реальные RS256 ключи из admin-module для
создания токенов, идентичных production environment.
"""

import jwt
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional


def get_private_key_path() -> Path:
    """
    Получение пути к приватному ключу JWT.

    Returns:
        Path: Абсолютный путь к private_key.pem из admin-module
    """
    project_root = Path(__file__).parent.parent.parent.parent
    return project_root / "admin-module" / ".keys" / "private_key.pem"


def get_public_key_path() -> Path:
    """
    Получение пути к публичному ключу JWT.

    Returns:
        Path: Абсолютный путь к public_key.pem из admin-module
    """
    project_root = Path(__file__).parent.parent.parent.parent
    return project_root / "admin-module" / ".keys" / "public_key.pem"


def load_private_key() -> str:
    """
    Загрузка приватного ключа для подписи JWT токенов.

    Returns:
        str: Содержимое приватного ключа в PEM формате

    Raises:
        FileNotFoundError: Если файл ключа не найден
    """
    key_path = get_private_key_path()
    if not key_path.exists():
        raise FileNotFoundError(
            f"Private key not found at {key_path}. "
            "Ensure admin-module JWT keys are generated."
        )
    return key_path.read_text()


def load_public_key() -> str:
    """
    Загрузка публичного ключа для верификации JWT токенов.

    Returns:
        str: Содержимое публичного ключа в PEM формате

    Raises:
        FileNotFoundError: Если файл ключа не найден
    """
    key_path = get_public_key_path()
    if not key_path.exists():
        raise FileNotFoundError(
            f"Public key not found at {key_path}. "
            "Ensure admin-module JWT keys are generated."
        )
    return key_path.read_text()


def generate_test_jwt_token(
    user_id: str = "test_user_id",
    username: str = "test_user",
    email: str = "test@artstore.local",
    role: str = "admin",
    expires_in_minutes: int = 30,
    custom_claims: Optional[Dict] = None
) -> str:
    """
    Генерация валидного JWT токена для integration tests.

    Создает JWT токен с RS256 алгоритмом, идентичный токенам
    генерируемым admin-module в production environment.

    Args:
        user_id: Уникальный идентификатор пользователя
        username: Имя пользователя
        email: Email пользователя
        role: Роль пользователя (admin, user, service)
        expires_in_minutes: Время жизни токена в минутах (default: 30)
        custom_claims: Дополнительные claims для токена

    Returns:
        str: Подписанный JWT токен в формате строки

    Raises:
        FileNotFoundError: Если JWT ключи не найдены
        jwt.PyJWTError: Если произошла ошибка при генерации токена

    Example:
        >>> token = generate_test_jwt_token(
        ...     username="admin",
        ...     role="admin"
        ... )
        >>> headers = {"Authorization": f"Bearer {token}"}
    """
    private_key = load_private_key()

    now = datetime.utcnow()
    expires_at = now + timedelta(minutes=expires_in_minutes)

    # Базовые claims согласно JWT стандарту
    payload = {
        "sub": user_id,  # Subject (user ID)
        "username": username,
        "email": email,
        "role": role,
        "type": "access",  # Тип токена (access/refresh)
        "iat": int(now.timestamp()),  # Issued At
        "exp": int(expires_at.timestamp()),  # Expiration Time
        "nbf": int(now.timestamp()),  # Not Before
    }

    # Добавление custom claims если предоставлены
    if custom_claims:
        payload.update(custom_claims)

    # Генерация и подпись токена с RS256
    token = jwt.encode(
        payload,
        private_key,
        algorithm="RS256"
    )

    return token


def verify_test_jwt_token(token: str, verify_expiration: bool = False) -> Dict:
    """
    Верификация JWT токена для проверки корректности генерации.

    Используется для debugging и валидации токенов в тестах.

    Args:
        token: JWT токен в формате строки
        verify_expiration: Проверять ли expiration time (default: False для unit tests)

    Returns:
        Dict: Декодированный payload токена

    Raises:
        jwt.ExpiredSignatureError: Если токен истек и verify_expiration=True
        jwt.InvalidTokenError: Если токен невалидный
        FileNotFoundError: Если публичный ключ не найден

    Example:
        >>> token = generate_test_jwt_token()
        >>> payload = verify_test_jwt_token(token)
        >>> assert payload["username"] == "test_user"
    """
    public_key = load_public_key()

    # Для unit tests отключаем проверку expiration по умолчанию
    # чтобы избежать проблем с временными метками и асинхронным выполнением
    # ВАЖНО: Signature verification ВСЕГДА включена для безопасности
    options = {
        "verify_signature": True,  # Всегда проверяем signature
        "verify_exp": verify_expiration,
        "verify_nbf": verify_expiration,
        "verify_iat": True,  # Проверяем issued at
        "verify_aud": False,  # Audience не используется в тестах
    }

    payload = jwt.decode(
        token,
        public_key,
        algorithms=["RS256"],
        options=options
    )

    return payload


def create_auth_headers(token: Optional[str] = None, **token_kwargs) -> Dict[str, str]:
    """
    Создание HTTP headers с JWT аутентификацией для integration tests.

    Удобная функция для быстрого создания auth headers в тестах.

    Args:
        token: Готовый JWT токен (опционально)
        **token_kwargs: Параметры для generate_test_jwt_token если токен не предоставлен

    Returns:
        Dict[str, str]: HTTP headers с Authorization Bearer токеном

    Example:
        >>> headers = create_auth_headers(username="admin", role="admin")
        >>> response = await client.post("/api/v1/files/upload", headers=headers)

        >>> # Или с готовым токеном:
        >>> token = generate_test_jwt_token(role="user")
        >>> headers = create_auth_headers(token=token)
    """
    if token is None:
        token = generate_test_jwt_token(**token_kwargs)

    return {
        "Authorization": f"Bearer {token}"
    }


def create_service_account_token(
    client_id: str = "test_service_account",
    role: str = "service",
    expires_in_minutes: int = 30
) -> str:
    """
    Генерация JWT токена для service account (machine-to-machine).

    Service accounts используют OAuth 2.0 Client Credentials flow
    для machine-to-machine аутентификации без user context.

    Args:
        client_id: Идентификатор service account
        role: Роль service account (service, admin)
        expires_in_minutes: Время жизни токена в минутах

    Returns:
        str: JWT токен для service account

    Example:
        >>> token = create_service_account_token(
        ...     client_id="storage_service",
        ...     role="service"
        ... )
        >>> headers = {"Authorization": f"Bearer {token}"}
    """
    return generate_test_jwt_token(
        user_id=client_id,
        username=client_id,
        email=f"{client_id}@service.artstore.local",
        role=role,
        expires_in_minutes=expires_in_minutes,
        custom_claims={
            "type": "service_account",
            "client_id": client_id
        }
    )
