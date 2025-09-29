from passlib.context import CryptContext # type: ignore
from datetime import datetime, timedelta, timezone
from typing import Any, Union, Optional

from jose import jwt, JWTError # type: ignore
from app.core.config import settings
from pydantic import ValidationError

# Загрузка ключей при старте модуля
try:
    with open(settings.PRIVATE_KEY_PATH, "r") as f:
        PRIVATE_KEY = f.read()
except FileNotFoundError:
    raise RuntimeError(f"Не найден файл приватного ключа: {settings.PRIVATE_KEY_PATH}")

try:
    with open(settings.PUBLIC_KEY_PATH, "r") as f:
        PUBLIC_KEY = f.read()
except FileNotFoundError:
    raise RuntimeError(f"Не найден файл публичного ключа: {settings.PUBLIC_KEY_PATH}")


# Контекст для хеширования паролей
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "RS256"

def create_access_token(
    subject: Union[str, Any], expires_delta: Optional[timedelta] = None
) -> str:
    """
    Создание JWT access токена, подписанного ключом RS256.
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    to_encode = {"exp": expire, "sub": str(subject)}
    
    encoded_jwt = jwt.encode(to_encode, PRIVATE_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str, credentials_exception) -> Optional[str]:
    """
    Проверка JWT токена.
    """
    try:
        payload = jwt.decode(token, PUBLIC_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        return username
    except (JWTError, ValidationError):
        raise credentials_exception

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Проверка пароля.
    """
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """
    Хеширование пароля.
    """
    return pwd_context.hash(password)