"""
Pydantic схемы для аутентификации и авторизации.
"""
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    """
    Схема для входа в систему.

    Используется в POST /api/auth/login
    """

    login: str = Field(..., description="Логин пользователя")
    password: str = Field(..., description="Пароль")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "login": "admin",
                "password": "admin123",
            }
        }
    )


class TokenResponse(BaseModel):
    """
    Схема ответа с JWT токенами.

    Используется в POST /api/auth/login, POST /api/auth/refresh
    """

    access_token: str = Field(description="JWT access токен")
    refresh_token: str = Field(description="JWT refresh токен")
    token_type: str = Field(default="bearer", description="Тип токена")
    expires_in: int = Field(description="Время жизни access токена в секундах")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 1800,
            }
        }
    )


class RefreshTokenRequest(BaseModel):
    """
    Схема для обновления access токена.

    Используется в POST /api/auth/refresh
    """

    refresh_token: str = Field(..., description="Refresh токен")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "refresh_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
            }
        }
    )


class TokenPayload(BaseModel):
    """
    Схема payload JWT токена.

    Используется для декодирования и валидации токенов.
    """

    sub: str = Field(description="Subject (user_id)")
    login: str = Field(description="Логин пользователя")
    is_admin: bool = Field(description="Является ли администратором")
    exp: int = Field(description="Expiration time (Unix timestamp)")
    iat: int = Field(description="Issued at (Unix timestamp)")
    iss: str = Field(description="Issuer")
    type: str = Field(description="Тип токена (access или refresh)")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "sub": "123e4567-e89b-12d3-a456-426614174000",
                "login": "admin",
                "is_admin": True,
                "exp": 1705315200,
                "iat": 1705313400,
                "iss": "artstore-admin",
                "type": "access",
            }
        }
    )


class CurrentUser(BaseModel):
    """
    Схема текущего аутентифицированного пользователя.

    Используется как dependency в protected endpoints.
    """

    id: str = Field(description="ID пользователя")
    login: str = Field(description="Логин пользователя")
    email: str = Field(description="Email адрес")
    full_name: str = Field(description="Полное имя")
    is_admin: bool = Field(description="Является ли администратором")
    is_active: bool = Field(description="Активен ли пользователь")

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "login": "admin",
                "email": "admin@example.com",
                "full_name": "Администратор Системы Главный",
                "is_admin": True,
                "is_active": True,
            }
        },
    )


class ChangePasswordRequest(BaseModel):
    """
    Схема для изменения своего пароля текущим пользователем.

    Используется в POST /api/auth/change-password
    """

    current_password: str = Field(..., description="Текущий пароль")
    new_password: str = Field(..., min_length=8, description="Новый пароль (минимум 8 символов)")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "current_password": "OldPassword123",
                "new_password": "NewSecurePassword456",
            }
        }
    )


class LogoutRequest(BaseModel):
    """
    Схема для выхода из системы.

    Используется в POST /api/auth/logout
    """

    refresh_token: Optional[str] = Field(None, description="Refresh токен для инвалидации")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "refresh_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
            }
        }
    )
