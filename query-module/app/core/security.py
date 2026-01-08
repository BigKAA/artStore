"""
Query Module - Security and Authentication.

$C=:F88:
- JWT token validation (RS256) G5@57 ?C1;8G=K9 :;NG
- Role-Based Access Control (RBAC)
- User context management
"""

import logging
from datetime import datetime, timezone
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
    """ >;8 ?>;L7>20B5;59 2 A8AB5<5"""
    # Service Account roles
    ADMIN = "admin"
    OPERATOR = "operator"
    USER = "user"
    # Admin User roles (for Admin UI)
    SUPER_ADMIN = "super_admin"
    READONLY = "readonly"


class TokenType(str, Enum):
    """"8?K JWT B>:5=>2 (DEPRECATED - use UnifiedJWTPayload.type)"""
    ACCESS = "access"
    REFRESH = "refresh"
    ADMIN_USER = "admin_user"


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
    >=B5:AB ?>;L7>20B5;O 87 JWT B>:5=0.

    !>45@68B 2AN 8=D>@<0F8N > ?>;L7>20B5;5 87 B>:5=0.
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
            iat=datetime.fromtimestamp(payload.iat, tz=timezone.utc),
            exp=datetime.fromtimestamp(payload.exp, tz=timezone.utc),
            nbf=datetime.fromtimestamp(payload.nbf, tz=timezone.utc)
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
        """@>25@:0 04<8=8AB@0B82=KE ?@02"""
        return self.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)

    @property
    def is_operator(self) -> bool:
        """@>25@:0 ?@02 >?5@0B>@0"""
        return self.role in (UserRole.ADMIN, UserRole.OPERATOR, UserRole.SUPER_ADMIN)

    @property
    def is_service_account(self) -> bool:
        """Проверка что это Service Account"""
        return self.token_type == "service_account"

    def has_role(self, required_role: UserRole) -> bool:
        """
        @>25@:0 =0;8G8O B@51C5<>9 @>;8.

        Args:
            required_role: "@51C5<0O @>;L

        Returns:
            bool: True 5A;8 @>;L A>>B25BAB2C5B 8;8 2KH5
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
    0;840B>@ JWT B>:5=>2 (RS256).

    A?>;L7C5B ?C1;8G=K9 :;NG >B Admin Module 4;O ?@>25@:8 ?>4?8A8.
    5 B@51C5B A5B52KE 70?@>A>2 - 20;840F8O ?>;=>ABLN ;>:0;L=0O.
    """

    def __init__(self):
        """Initialization with hot-reload support via JWTKeyManager."""
        from app.core.jwt_key_manager import get_jwt_key_manager

        self._key_manager = get_jwt_key_manager()

    def validate_token(self, token: str) -> UserContext:
        """
        0;840F8O JWT B>:5=0 8 872;5G5=85 user context.

        Args:
            token: JWT token string

        Returns:
            UserContext: >=B5:AB ?>;L7>20B5;O 87 B>:5=0

        Raises:
            InvalidTokenException: 520;84=K9 B>:5=
            TokenExpiredException: ">:5= 8AB5:
        """
        try:
            # Get public key from manager (hot-reload support)
            public_key = self._key_manager.get_public_key_sync()

            # 5:>48@>20=85 8 20;840F8O B>:5=0
            payload = jwt.decode(
                token,
                public_key,
                algorithms=[settings.auth.algorithm],
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_nbf": True,
                    "verify_iat": True
                }
            )

            # >=25@B0F8O timestamp ?>;59 2 datetime (timezone-aware)
            # Валидация через UnifiedJWTPayload (строгая схема)
            unified_payload = UnifiedJWTPayload(**payload)

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
    5:>@0B>@ 4;O ?@>25@:8 @>;8 ?>;L7>20B5;O.

    Args:
        required_role: 8=8<0;L=> B@51C5<0O @>;L

    Raises:
        InsufficientPermissionsException: 54>AB0B>G=> ?@02
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
