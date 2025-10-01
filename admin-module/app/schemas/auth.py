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

    username: str = Field(..., description="Логин пользователя")
    password: str = Field(..., description="Пароль")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "username": "admin",
                "password": "admin123",
            }
        }
    )


class TokenResponse(BaseModel):
    """
    Схема ответа с JWT токенами.

    Используется в POST /api/auth/login
    """

    access_token: str = Field(description="JWT access токен")
    refresh_token: str = Field(description="JWT refresh токен")
    token_type: str = Field(default="bearer", description="Тип токена")
    expires_in: int = Field(description="Время жизни access токена в секундах")


class LoginResponse(TokenResponse):
    """
    Схема ответа при успешном входе.

    Используется в POST /api/auth/login
    Расширяет TokenResponse добавляя информацию о пользователе.
    """

    user: "UserInfo" = Field(description="Информация о пользователе")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 1800,
                "user": {
                    "id": "123e4567-e89b-12d3-a456-426614174000",
                    "username": "admin",
                    "email": "admin@artstore.local",
                    "last_name": "Администратор",
                    "first_name": "Системный",
                    "middle_name": None,
                    "is_admin": True,
                    "is_active": True,
                    "auth_provider": "local",
                },
            }
        }
    )


class AccessTokenResponse(BaseModel):
    """
    Схема ответа с обновленным access токеном.

    Используется в POST /api/auth/refresh
    """

    access_token: str = Field(description="JWT access токен")
    token_type: str = Field(default="bearer", description="Тип токена")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
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
    username: str = Field(description="Логин пользователя")
    is_admin: bool = Field(description="Является ли администратором")
    exp: int = Field(description="Expiration time (Unix timestamp)")
    iat: int = Field(description="Issued at (Unix timestamp)")
    iss: str = Field(description="Issuer")
    type: str = Field(description="Тип токена (access или refresh)")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "sub": "123e4567-e89b-12d3-a456-426614174000",
                "username": "admin",
                "is_admin": True,
                "exp": 1705315200,
                "iat": 1705313400,
                "iss": "artstore-admin",
                "type": "access",
            }
        }
    )


class UserInfo(BaseModel):
    """
    Схема информации о текущем пользователе.

    Используется в GET /api/auth/me
    """

    id: str = Field(description="ID пользователя")
    username: str = Field(description="Логин пользователя")
    email: str = Field(description="Email адрес")
    last_name: str = Field(description="Фамилия")
    first_name: str = Field(description="Имя")
    middle_name: Optional[str] = Field(None, description="Отчество")
    is_admin: bool = Field(description="Является ли администратором")
    is_active: bool = Field(description="Активен ли пользователь")
    auth_provider: str = Field(description="Источник аутентификации")

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "username": "admin",
                "email": "admin@artstore.local",
                "last_name": "Администратор",
                "first_name": "Системный",
                "middle_name": None,
                "is_admin": True,
                "is_active": True,
                "auth_provider": "local",
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
