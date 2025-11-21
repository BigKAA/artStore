"""
Ingester Module - Security and Authentication.

Функции:
- JWT token validation (RS256) через публичный ключ
- Role-Based Access Control (RBAC)
- User context management
"""

import logging
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

import jwt
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.exceptions import (
    InvalidTokenException,
    TokenExpiredException,
    InsufficientPermissionsException
)

logger = logging.getLogger(__name__)


class UserRole(str, Enum):
    """Роли пользователей в системе"""
    # Service Account roles
    ADMIN = "admin"
    OPERATOR = "operator"
    USER = "user"
    # Admin User roles (for Admin UI)
    SUPER_ADMIN = "super_admin"
    READONLY = "readonly"


class TokenType(str, Enum):
    """Типы JWT токенов"""
    ACCESS = "access"
    REFRESH = "refresh"
    # Admin User token type (for Admin UI)
    ADMIN_USER = "admin_user"


class UserContext(BaseModel):
    """
    Контекст пользователя из JWT токена.

    Содержит всю информацию о пользователе из токена.
    """
    sub: str = Field(..., description="User ID (subject)")
    username: Optional[str] = Field(None, description="Username")
    email: Optional[str] = Field(None, description="Email address")
    role: UserRole = Field(..., description="User role")
    type: TokenType = Field(..., description="Token type")
    iat: datetime = Field(..., description="Issued at")
    exp: datetime = Field(..., description="Expires at")
    nbf: Optional[datetime] = Field(None, description="Not before")

    @property
    def user_id(self) -> str:
        """User ID для удобства"""
        return self.sub

    @property
    def is_admin(self) -> bool:
        """Проверка административных прав"""
        return self.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)

    @property
    def is_operator(self) -> bool:
        """Проверка прав оператора"""
        return self.role in (UserRole.ADMIN, UserRole.OPERATOR, UserRole.SUPER_ADMIN)

    def has_role(self, required_role: UserRole) -> bool:
        """
        Проверка наличия требуемой роли.

        Args:
            required_role: Требуемая роль

        Returns:
            bool: True если роль соответствует или выше
        """
        role_hierarchy = {
            UserRole.SUPER_ADMIN: 5,  # Highest level (Admin UI super admin)
            UserRole.ADMIN: 4,         # Full access (both Admin UI and Service Accounts)
            UserRole.OPERATOR: 3,      # Service Account operator
            UserRole.READONLY: 2,      # Admin UI read-only
            UserRole.USER: 1          # Service Account basic user
        }
        return role_hierarchy.get(self.role, 0) >= role_hierarchy.get(required_role, 0)


class JWTValidator:
    """
    Валидатор JWT токенов (RS256).

    Использует публичный ключ от Admin Module для проверки подписи.
    Не требует сетевых запросов - валидация полностью локальная.
    """

    def __init__(self):
        """Инициализация с загрузкой публичного ключа"""
        self._public_key: Optional[str] = None
        self._load_public_key()

    def _load_public_key(self) -> None:
        """
        Загрузка публичного ключа из файла.

        Raises:
            FileNotFoundError: Если файл с ключом не найден
        """
        key_path = settings.auth.public_key_path

        if not key_path.exists():
            logger.warning(
                "Public key file not found",
                extra={"key_path": str(key_path)}
            )
            return

        with open(key_path, 'r') as f:
            self._public_key = f.read()

        logger.info(
            "Public key loaded successfully",
            extra={"key_path": str(key_path)}
        )

    def validate_token(self, token: str) -> UserContext:
        """
        Валидация JWT токена и извлечение user context.

        Args:
            token: JWT token string

        Returns:
            UserContext: Контекст пользователя из токена

        Raises:
            InvalidTokenException: Невалидный токен
            TokenExpiredException: Токен истек
        """
        if not self._public_key:
            raise InvalidTokenException("Public key not loaded")

        try:
            # Декодирование и валидация токена
            payload = jwt.decode(
                token,
                self._public_key,
                algorithms=[settings.auth.algorithm],
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_nbf": True,
                    "verify_iat": True
                }
            )

            # Конвертация timestamp полей в datetime
            if 'iat' in payload:
                payload['iat'] = datetime.fromtimestamp(payload['iat'], tz=timezone.utc)
            if 'exp' in payload:
                payload['exp'] = datetime.fromtimestamp(payload['exp'], tz=timezone.utc)
            if 'nbf' in payload:
                payload['nbf'] = datetime.fromtimestamp(payload['nbf'], tz=timezone.utc)

            # Создание UserContext
            user_context = UserContext(**payload)

            logger.debug(
                "Token validated successfully",
                extra={
                    "user_id": user_context.user_id,
                    "username": user_context.username,
                    "role": user_context.role.value
                }
            )

            return user_context

        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            raise TokenExpiredException("JWT token has expired")

        except jwt.InvalidTokenError as e:
            logger.warning(
                "Invalid token",
                extra={"error": str(e)}
            )
            raise InvalidTokenException(f"Invalid JWT token: {str(e)}")

        except Exception as e:
            # Catch Pydantic ValidationError and other exceptions
            logger.warning(
                "Token validation failed",
                extra={"error": str(e)}
            )
            raise InvalidTokenException(f"Invalid token claims: {str(e)}")


# Singleton instance
jwt_validator = JWTValidator()


def require_role(required_role: UserRole):
    """
    Декоратор для проверки роли пользователя.

    Args:
        required_role: Минимально требуемая роль

    Raises:
        InsufficientPermissionsException: Недостаточно прав
    """
    def decorator(func):
        async def wrapper(user: UserContext, *args, **kwargs):
            if not user.has_role(required_role):
                raise InsufficientPermissionsException(
                    f"Required role: {required_role.value}, user role: {user.role.value}"
                )
            return await func(user, *args, **kwargs)
        return wrapper
    return decorator
