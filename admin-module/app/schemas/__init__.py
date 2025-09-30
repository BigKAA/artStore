"""
Pydantic schemas package.
"""
from app.schemas.auth import (
    ChangePasswordRequest,
    CurrentUser,
    LoginRequest,
    LogoutRequest,
    RefreshTokenRequest,
    TokenPayload,
    TokenResponse,
)
from app.schemas.common import (
    ErrorDetail,
    ErrorResponse,
    IDMixin,
    PaginatedResponse,
    PaginationParams,
    SuccessResponse,
    TimestampMixin,
)
from app.schemas.storage_element import (
    StorageElementChangeModeRequest,
    StorageElementCreate,
    StorageElementInDB,
    StorageElementResponse,
    StorageElementUpdate,
)
from app.schemas.user import (
    UserChangePassword,
    UserCreate,
    UserInDB,
    UserResponse,
    UserUpdate,
)

__all__ = [
    # Common
    "PaginationParams",
    "PaginatedResponse",
    "SuccessResponse",
    "ErrorDetail",
    "ErrorResponse",
    "TimestampMixin",
    "IDMixin",
    # Auth
    "LoginRequest",
    "TokenResponse",
    "RefreshTokenRequest",
    "TokenPayload",
    "CurrentUser",
    "ChangePasswordRequest",
    "LogoutRequest",
    # User
    "UserCreate",
    "UserUpdate",
    "UserChangePassword",
    "UserResponse",
    "UserInDB",
    # Storage Element
    "StorageElementCreate",
    "StorageElementUpdate",
    "StorageElementChangeModeRequest",
    "StorageElementResponse",
    "StorageElementInDB",
]
