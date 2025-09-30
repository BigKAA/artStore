"""
Функции безопасности: JWT токены, хеширование паролей, валидация.
"""
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from jose import JWTError, jwt
from passlib.context import CryptContext

# Контекст для хеширования паролей (bcrypt)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Глобальные переменные для ключей (будут загружены при инициализации)
PRIVATE_KEY: Optional[str] = None
PUBLIC_KEY: Optional[str] = None


def load_rsa_key(key_path: str, is_private: bool = False) -> str:
    """
    Загружает RSA ключ из файла.

    Args:
        key_path: Путь к PEM файлу
        is_private: True для приватного ключа, False для публичного

    Returns:
        Содержимое ключа в виде строки

    Raises:
        FileNotFoundError: Если файл ключа не найден
    """
    key_file = Path(key_path)
    if not key_file.exists():
        key_type = "приватного" if is_private else "публичного"
        raise FileNotFoundError(
            f"Файл {key_type} ключа не найден: {key_path}\n"
            f"Сгенерируйте ключи командой: python scripts/generate_jwt_keys.py"
        )

    with open(key_file, "r") as f:
        return f.read()


def init_keys(private_key_path: str, public_key_path: str) -> None:
    """
    Инициализирует JWT ключи при старте приложения.

    Args:
        private_key_path: Путь к приватному ключу
        public_key_path: Путь к публичному ключу
    """
    global PRIVATE_KEY, PUBLIC_KEY
    PRIVATE_KEY = load_rsa_key(private_key_path, is_private=True)
    PUBLIC_KEY = load_rsa_key(public_key_path, is_private=False)


def hash_password(password: str) -> str:
    """
    Хеширует пароль с использованием bcrypt.

    Args:
        password: Пароль в открытом виде

    Returns:
        Хешированный пароль

    Example:
        >>> hashed = hash_password("mypassword123")
        >>> verify_password("mypassword123", hashed)
        True
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Проверяет соответствие пароля хешу.

    Args:
        plain_password: Пароль в открытом виде
        hashed_password: Хешированный пароль

    Returns:
        True если пароль верный, иначе False
    """
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
    access_token_expire_minutes: int = 30,
    algorithm: str = "RS256",
    issuer: str = "artstore-admin",
) -> str:
    """
    Создает JWT access токен, подписанный приватным ключом RS256.

    Args:
        data: Payload токена (например, {"sub": "user_id", "is_admin": True})
        expires_delta: Время жизни токена (по умолчанию из параметра)
        access_token_expire_minutes: Время жизни в минутах (если expires_delta не указан)
        algorithm: Алгоритм подписи (RS256)
        issuer: Издатель токена

    Returns:
        JWT токен в виде строки

    Example:
        >>> token = create_access_token({"sub": "123", "username": "admin"})
    """
    if PRIVATE_KEY is None:
        raise RuntimeError("JWT ключи не инициализированы. Вызовите init_keys()")

    to_encode = data.copy()

    # Установка времени истечения
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=access_token_expire_minutes)

    # Добавление стандартных JWT claims
    to_encode.update(
        {
            "exp": expire,  # Expiration time
            "iat": datetime.utcnow(),  # Issued at
            "iss": issuer,  # Issuer
            "type": "access",  # Тип токена
        }
    )

    # Подпись токена приватным ключом
    encoded_jwt = jwt.encode(to_encode, PRIVATE_KEY, algorithm=algorithm)
    return encoded_jwt


def create_refresh_token(
    data: Dict[str, Any],
    refresh_token_expire_days: int = 7,
    algorithm: str = "RS256",
    issuer: str = "artstore-admin",
) -> str:
    """
    Создает JWT refresh токен с длительным сроком действия.

    Args:
        data: Payload токена (обычно только {"sub": "user_id"})
        refresh_token_expire_days: Время жизни в днях
        algorithm: Алгоритм подписи (RS256)
        issuer: Издатель токена

    Returns:
        JWT refresh токен
    """
    if PRIVATE_KEY is None:
        raise RuntimeError("JWT ключи не инициализированы. Вызовите init_keys()")

    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=refresh_token_expire_days)

    to_encode.update(
        {
            "exp": expire,
            "iat": datetime.utcnow(),
            "iss": issuer,
            "type": "refresh",  # Важно: отличается от access токена
        }
    )

    encoded_jwt = jwt.encode(to_encode, PRIVATE_KEY, algorithm=algorithm)
    return encoded_jwt


def decode_token(
    token: str, algorithm: str = "RS256", issuer: str = "artstore-admin"
) -> Dict[str, Any]:
    """
    Декодирует и валидирует JWT токен.

    Args:
        token: JWT токен для проверки
        algorithm: Алгоритм проверки подписи (RS256)
        issuer: Ожидаемый издатель токена

    Returns:
        Payload токена (dict)

    Raises:
        JWTError: Если токен невалиден или истек

    Example:
        >>> payload = decode_token(token)
        >>> user_id = payload["sub"]
    """
    if PUBLIC_KEY is None:
        raise RuntimeError("JWT ключи не инициализированы. Вызовите init_keys()")

    try:
        payload = jwt.decode(
            token, PUBLIC_KEY, algorithms=[algorithm], issuer=issuer
        )
        return payload
    except JWTError as e:
        raise JWTError(f"Невалидный токен: {str(e)}")


def validate_password_strength(
    password: str,
    min_length: int = 8,
    require_complexity: bool = True,
    require_uppercase: bool = True,
    require_lowercase: bool = True,
    require_digits: bool = True,
    require_special: bool = False,
) -> Tuple[bool, Optional[str]]:
    """
    Проверяет надежность пароля согласно политике безопасности.

    Args:
        password: Пароль для проверки
        min_length: Минимальная длина пароля
        require_complexity: Требовать сложность
        require_uppercase: Требовать заглавные буквы
        require_lowercase: Требовать строчные буквы
        require_digits: Требовать цифры
        require_special: Требовать специальные символы

    Returns:
        Tuple (валиден, сообщение об ошибке)

    Example:
        >>> valid, error = validate_password_strength("weak")
        >>> if not valid:
        >>>     print(error)
    """
    # Проверка минимальной длины
    if len(password) < min_length:
        return False, f"Пароль должен быть не менее {min_length} символов"

    # Проверка сложности (если включена)
    if require_complexity:
        errors = []

        if require_uppercase and not any(c.isupper() for c in password):
            errors.append("заглавные буквы")

        if require_lowercase and not any(c.islower() for c in password):
            errors.append("строчные буквы")

        if require_digits and not any(c.isdigit() for c in password):
            errors.append("цифры")

        if require_special and not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
            errors.append("специальные символы")

        if errors:
            return False, f"Пароль должен содержать: {', '.join(errors)}"

    return True, None
