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
    """ >;8 ?>;L7>20B5;59 2 A8AB5<5"""
    # Service Account roles
    ADMIN = "admin"
    OPERATOR = "operator"
    USER = "user"
    # Admin User roles (for Admin UI)
    SUPER_ADMIN = "super_admin"
    READONLY = "readonly"


class TokenType(str, Enum):
    """"8?K JWT B>:5=>2"""
    ACCESS = "access"
    REFRESH = "refresh"
    # Admin User token type (for Admin UI)
    ADMIN_USER = "admin_user"


class UserContext(BaseModel):
    """
    >=B5:AB ?>;L7>20B5;O 87 JWT B>:5=0.

    !>45@68B 2AN 8=D>@<0F8N > ?>;L7>20B5;5 87 B>:5=0.
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
        """User ID 4;O C4>1AB20"""
        return self.sub

    @property
    def is_admin(self) -> bool:
        """@>25@:0 04<8=8AB@0B82=KE ?@02"""
        return self.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)

    @property
    def is_operator(self) -> bool:
        """@>25@:0 ?@02 >?5@0B>@0"""
        return self.role in (UserRole.ADMIN, UserRole.OPERATOR, UserRole.SUPER_ADMIN)

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
        """=8F80;870F8O A 703@C7:>9 ?C1;8G=>3> :;NG0"""
        self._public_key: Optional[str] = None
        self._load_public_key()

    def _load_public_key(self) -> None:
        """
        03@C7:0 ?C1;8G=>3> :;NG0 87 D09;0.

        Raises:
            FileNotFoundError: A;8 D09; A :;NG>< =5 =0945=
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
        0;840F8O JWT B>:5=0 8 872;5G5=85 user context.

        Args:
            token: JWT token string

        Returns:
            UserContext: >=B5:AB ?>;L7>20B5;O 87 B>:5=0

        Raises:
            InvalidTokenException: 520;84=K9 B>:5=
            TokenExpiredException: ">:5= 8AB5:
        """
        if not self._public_key:
            raise InvalidTokenException("Public key not loaded")

        try:
            # 5:>48@>20=85 8 20;840F8O B>:5=0
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

            # >=25@B0F8O timestamp ?>;59 2 datetime (timezone-aware)
            if 'iat' in payload:
                payload['iat'] = datetime.fromtimestamp(payload['iat'], tz=timezone.utc)
            if 'exp' in payload:
                payload['exp'] = datetime.fromtimestamp(payload['exp'], tz=timezone.utc)
            if 'nbf' in payload:
                payload['nbf'] = datetime.fromtimestamp(payload['nbf'], tz=timezone.utc)

            # !>740=85 UserContext
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
