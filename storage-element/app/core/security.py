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
from typing import Optional, Literal

import jwt
from pydantic import BaseModel, Field, ConfigDict

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


class UnifiedJWTPayload(BaseModel):
    """
    Унифицированная схема JWT payload для всех типов токенов (Sprint 20).

    Поддерживает:
    - Admin User tokens (type="admin_user")
    - Service Account tokens (type="service_account")

    Обязательные поля:
    - sub: identifier (username для admin, UUID для service account)
    - type: admin_user | service_account
    - role: роль для authorization
    - name: display name для логов
    - jti: JWT ID для revocation
    - iat, exp, nbf: timestamps

    Опциональные поля:
    - client_id: OAuth 2.0 Client ID
    - rate_limit: API requests per minute (только для service accounts)
    - username: DEPRECATED backward compatibility
    - email: DEPRECATED backward compatibility
    """
    model_config = ConfigDict(
        extra="ignore",  # Игнорировать дополнительные поля для backward compatibility
        str_strip_whitespace=True
    )

    # Обязательные поля (unified)
    sub: str = Field(..., description="Subject identifier")
    type: Literal["admin_user", "service_account", "access", "refresh"] = Field(
        ..., description="Token type"
    )
    role: str = Field(..., description="User role")
    name: str = Field(..., description="Display name")
    jti: str = Field(..., description="JWT ID for revocation")
    iat: int = Field(..., description="Issued at timestamp")
    exp: int = Field(..., description="Expiration timestamp")
    nbf: int = Field(..., description="Not before timestamp")

    # Опциональные поля
    client_id: Optional[str] = Field(None, description="OAuth 2.0 Client ID")
    rate_limit: Optional[int] = Field(None, description="API requests per minute")

    # Backward compatibility (deprecated)
    username: Optional[str] = Field(None, description="DEPRECATED: use 'name' instead")
    email: Optional[str] = Field(None, description="DEPRECATED: optional field")


class UserContext(BaseModel):
    """
    Контекст пользователя после валидации JWT (Sprint 20 Unified Schema).

    Создается из UnifiedJWTPayload и предоставляет унифицированный интерфейс
    для работы с admin users и service accounts.
    """
    identifier: str = Field(..., description="Unique identifier (sub)")
    display_name: str = Field(..., description="Display name for logs")
    role: UserRole = Field(..., description="User role")
    token_type: Literal["admin_user", "service_account"] = Field(
        ..., description="Type of authenticated entity"
    )
    client_id: Optional[str] = Field(None, description="OAuth 2.0 Client ID")
    rate_limit: Optional[int] = Field(None, description="API rate limit")
    iat: datetime = Field(..., description="Issued at")
    exp: datetime = Field(..., description="Expires at")
    nbf: datetime = Field(..., description="Not before")

    @classmethod
    def from_unified_jwt(cls, payload: UnifiedJWTPayload) -> "UserContext":
        """
        Создание UserContext из унифицированного JWT payload (Sprint 20).

        Автоматически определяет тип токена и извлекает соответствующие поля.

        Args:
            payload: UnifiedJWTPayload из декодированного JWT

        Returns:
            UserContext: Контекст для использования в приложении
        """
        # Определение token_type
        token_type = payload.type
        if token_type in ("access", "refresh"):
            # Backward compatibility: старые токены без unified type
            # Определяем тип по наличию client_id с префиксом "sa_"
            if payload.client_id and payload.client_id.startswith("sa_"):
                token_type = "service_account"
            else:
                token_type = "admin_user"

        # Преобразование роли в enum
        try:
            role = UserRole(payload.role.lower())
        except ValueError:
            # Fallback на ADMIN для неизвестных ролей
            logger.warning(f"Unknown role '{payload.role}', defaulting to ADMIN")
            role = UserRole.ADMIN

        return cls(
            identifier=payload.sub,
            display_name=payload.name,
            role=role,
            token_type=token_type,
            client_id=payload.client_id,
            rate_limit=payload.rate_limit,
            iat=datetime.fromtimestamp(payload.iat),
            exp=datetime.fromtimestamp(payload.exp),
            nbf=datetime.fromtimestamp(payload.nbf)
        )

    @property
    def sub(self) -> str:
        """Subject для backward compatibility (alias for identifier)"""
        return self.identifier

    @property
    def user_id(self) -> str:
        """User ID для удобства (alias for identifier)"""
        return self.identifier

    @property
    def username(self) -> str:
        """Username для backward compatibility (alias for display_name)"""
        return self.display_name

    @property
    def is_admin(self) -> bool:
        """Проверка административных прав"""
        return self.role == UserRole.ADMIN

    @property
    def is_operator(self) -> bool:
        """Проверка прав оператора"""
        return self.role in (UserRole.ADMIN, UserRole.OPERATOR)

    @property
    def is_service_account(self) -> bool:
        """Проверка что это Service Account"""
        return self.token_type == "service_account"

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
        Валидация JWT токена и извлечение user context (Sprint 20 Unified Schema).

        Поддерживает:
        - Unified JWT schema (admin_user, service_account types)
        - Backward compatibility с legacy токенами

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
            >>> print(user.display_name, user.role)
        """
        if not self._public_key:
            raise InvalidTokenException("JWT public key not loaded")

        try:
            # Декодирование и валидация токена
            raw_payload = jwt.decode(
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

            # Валидация через UnifiedJWTPayload (строгая схема)
            unified_payload = UnifiedJWTPayload(**raw_payload)

            # Создание UserContext через фабричный метод
            user_context = UserContext.from_unified_jwt(unified_payload)

            logger.debug(
                "Token validated successfully",
                extra={
                    "identifier": user_context.identifier,
                    "display_name": user_context.display_name,
                    "role": user_context.role.value,
                    "token_type": user_context.token_type,
                    "is_service_account": user_context.is_service_account
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
        Валидация access токена (Sprint 20 simplified).

        Note: В унифицированной схеме проверка типа токена (access vs refresh)
        выполняется на уровне endpoint authorization, не здесь.
        Валидация через validate_token() достаточна для большинства случаев.

        Args:
            token: JWT access token

        Returns:
            UserContext: Контекст пользователя

        Raises:
            InvalidTokenException: Если токен невалидный
            TokenExpiredException: Если токен истек
        """
        # Унифицированная валидация (admin_user + service_account)
        return self.validate_token(token)


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
