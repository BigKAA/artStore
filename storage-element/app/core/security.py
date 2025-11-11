"""
Система безопасности и аутентификации для Storage Element.

Функции:
- JWT token validation (RS256) через публичный ключ
- Role-Based Access Control (RBAC)
- User context management
"""

import logging
from datetime import datetime
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
    ADMIN = "admin"
    OPERATOR = "operator"
    USER = "user"


class TokenType(str, Enum):
    """Типы JWT токенов"""
    ACCESS = "access"
    REFRESH = "refresh"


class UserContext(BaseModel):
    """
    Контекст пользователя из JWT токена.

    Содержит всю информацию о пользователе из токена.
    """
    sub: str = Field(..., description="User ID (subject)")
    username: str = Field(..., description="Username")
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
        return self.role == UserRole.ADMIN

    @property
    def is_operator(self) -> bool:
        """Проверка прав оператора"""
        return self.role in (UserRole.ADMIN, UserRole.OPERATOR)

    def has_role(self, required_role: UserRole) -> bool:
        """
        Проверка наличия требуемой роли.

        Args:
            required_role: Требуемая роль

        Returns:
            bool: True если роль соответствует или выше
        """
        role_hierarchy = {
            UserRole.ADMIN: 3,
            UserRole.OPERATOR: 2,
            UserRole.USER: 1
        }
        return role_hierarchy[self.role] >= role_hierarchy[required_role]


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
            FileNotFoundError: Если файл ключа не найден
        """
        if not settings.jwt.public_key_path:
            logger.warning("JWT public key path not configured")
            return

        key_path = Path(settings.jwt.public_key_path)
        if not key_path.exists():
            raise FileNotFoundError(
                f"JWT public key not found at: {key_path}"
            )

        self._public_key = key_path.read_text(encoding="utf-8")
        logger.info(f"JWT public key loaded from: {key_path}")

    def validate_token(self, token: str) -> UserContext:
        """
        Валидация JWT токена и извлечение user context.

        Args:
            token: JWT токен (access или refresh)

        Returns:
            UserContext: Контекст пользователя из токена

        Raises:
            InvalidTokenException: Если токен невалидный
            TokenExpiredException: Если токен истек

        Примеры:
            >>> validator = JWTValidator()
            >>> user = validator.validate_token("eyJ...")
            >>> print(user.username, user.role)
        """
        if not self._public_key:
            raise InvalidTokenException("JWT public key not loaded")

        try:
            # Декодирование и валидация токена
            payload = jwt.decode(
                token,
                self._public_key,
                algorithms=[settings.jwt.algorithm],
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_nbf": True,
                    "verify_iat": True
                }
            )

            # Преобразование timestamps в datetime
            if "iat" in payload:
                payload["iat"] = datetime.fromtimestamp(payload["iat"])
            if "exp" in payload:
                payload["exp"] = datetime.fromtimestamp(payload["exp"])
            if "nbf" in payload:
                payload["nbf"] = datetime.fromtimestamp(payload["nbf"])

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
            raise TokenExpiredException()

        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {str(e)}")
            raise InvalidTokenException(str(e))

        except Exception as e:
            logger.error(f"Token validation error: {str(e)}")
            raise InvalidTokenException(f"Unexpected error: {str(e)}")

    def validate_access_token(self, token: str) -> UserContext:
        """
        Валидация access токена.

        Проверяет что тип токена = access.

        Args:
            token: JWT access token

        Returns:
            UserContext: Контекст пользователя

        Raises:
            InvalidTokenException: Если не access token
        """
        user = self.validate_token(token)

        if user.type != TokenType.ACCESS:
            raise InvalidTokenException(
                f"Expected access token, got {user.type}"
            )

        return user


# Глобальный экземпляр валидатора
jwt_validator = JWTValidator()


def require_role(required_role: UserRole, user: UserContext) -> None:
    """
    Проверка наличия требуемой роли у пользователя.

    Args:
        required_role: Требуемая роль
        user: Контекст пользователя

    Raises:
        InsufficientPermissionsException: Если недостаточно прав

    Примеры:
        >>> require_role(UserRole.ADMIN, current_user)
    """
    if not user.has_role(required_role):
        raise InsufficientPermissionsException(
            required_role=required_role.value,
            user_role=user.role.value
        )


def require_admin(user: UserContext) -> None:
    """
    Проверка административных прав.

    Args:
        user: Контекст пользователя

    Raises:
        InsufficientPermissionsException: Если не администратор
    """
    require_role(UserRole.ADMIN, user)


def require_operator(user: UserContext) -> None:
    """
    Проверка прав оператора.

    Args:
        user: Контекст пользователя

    Raises:
        InsufficientPermissionsException: Если недостаточно прав
    """
    require_role(UserRole.OPERATOR, user)
