"""
Pydantic schemas for Admin Module.
"""

from .auth import (
    LoginRequest,
    TokenResponse,
    RefreshTokenRequest,
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
from .admin_user import (
    AdminUserCreateRequest,
    AdminUserUpdateRequest,
    AdminUserPasswordResetRequest,
    AdminUserResponse,
    AdminUserListItem,
    AdminUserListResponse,
    AdminUserDeleteResponse,
    AdminUserPasswordResetResponse,
)
from .file import (
    FileRegisterRequest,
    FileUpdateRequest,
    FileResponse,
    FileListResponse,
    FileDeleteResponse,
)

__all__ = [
    # Auth
    "LoginRequest",
    "TokenResponse",
    "RefreshTokenRequest",
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
    # Admin User
    "AdminUserCreateRequest",
    "AdminUserUpdateRequest",
    "AdminUserPasswordResetRequest",
    "AdminUserResponse",
    "AdminUserListItem",
    "AdminUserListResponse",
    "AdminUserDeleteResponse",
    "AdminUserPasswordResetResponse",
    # File Registry
    "FileRegisterRequest",
    "FileUpdateRequest",
    "FileResponse",
    "FileListResponse",
    "FileDeleteResponse",
]
