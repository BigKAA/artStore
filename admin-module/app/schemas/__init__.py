"""
Pydantic schemas for Admin Module.
"""

from .auth import (
    LoginRequest,
    TokenResponse,
    RefreshTokenRequest,
    UserResponse,
    PasswordResetRequest,
    PasswordResetConfirm,
    MessageResponse,
)
from .service_account import (
    OAuth2TokenRequest,
    OAuth2TokenResponse,
    ServiceAccountCreate,
    ServiceAccountCreateResponse,
    ServiceAccountResponse,
    ServiceAccountUpdate,
    ServiceAccountRotateSecretResponse,
    ServiceAccountListResponse,
    OAuth2ErrorResponse,
)

__all__ = [
    # Auth
    "LoginRequest",
    "TokenResponse",
    "RefreshTokenRequest",
    "UserResponse",
    "PasswordResetRequest",
    "PasswordResetConfirm",
    "MessageResponse",
    # Service Account
    "OAuth2TokenRequest",
    "OAuth2TokenResponse",
    "ServiceAccountCreate",
    "ServiceAccountCreateResponse",
    "ServiceAccountResponse",
    "ServiceAccountUpdate",
    "ServiceAccountRotateSecretResponse",
    "ServiceAccountListResponse",
    "OAuth2ErrorResponse",
]
