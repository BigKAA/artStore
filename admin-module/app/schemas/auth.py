"""
Pydantic schemas для аутентификации.
Request и Response модели для auth endpoints.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field

from app.models.user import UserRole, UserStatus


class LoginRequest(BaseModel):
    """Запрос на логин."""

    username: str = Field(..., min_length=3, max_length=100, description="Имя пользователя или email")
    password: str = Field(..., min_length=6, description="Пароль")

    model_config = {"json_schema_extra": {
        "example": {
            "username": "admin",
            "password": "admin123"
        }
    }}


class TokenResponse(BaseModel):
    """Ответ с токенами."""

    access_token: str = Field(..., description="Access токен (JWT)")
    refresh_token: str = Field(..., description="Refresh токен (JWT)")
    token_type: str = Field(default="bearer", description="Тип токена")
    expires_in: int = Field(..., description="Время жизни access токена в секундах")

    model_config = {"json_schema_extra": {
        "example": {
            "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
            "refresh_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
            "token_type": "bearer",
            "expires_in": 1800
        }
    }}


class RefreshTokenRequest(BaseModel):
    """Запрос на обновление токена."""

    refresh_token: str = Field(..., description="Refresh токен")

    model_config = {"json_schema_extra": {
        "example": {
            "refresh_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."
        }
    }}


class UserResponse(BaseModel):
    """Ответ с информацией о пользователе."""

    id: int = Field(..., description="ID пользователя")
    username: str = Field(..., description="Имя пользователя")
    email: str = Field(..., description="Email")  # Используем str вместо EmailStr для поддержки .local доменов
    first_name: Optional[str] = Field(None, description="Имя")
    last_name: Optional[str] = Field(None, description="Фамилия")
    role: UserRole = Field(..., description="Роль пользователя")
    status: UserStatus = Field(..., description="Статус пользователя")
    is_ldap_user: bool = Field(..., description="Флаг LDAP пользователя")
    is_system: bool = Field(..., description="Флаг системного пользователя")
    last_login: Optional[datetime] = Field(None, description="Дата последнего входа")
    created_at: datetime = Field(..., description="Дата создания")

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": 1,
                "username": "admin",
                "email": "admin@artstore.local",
                "first_name": "Admin",
                "last_name": "User",
                "role": "ADMIN",
                "status": "ACTIVE",
                "is_ldap_user": False,
                "is_system": True,
                "last_login": "2025-01-09T21:00:00Z",
                "created_at": "2025-01-01T00:00:00Z"
            }
        }
    }


class PasswordResetRequest(BaseModel):
    """Запрос на сброс пароля."""

    email: EmailStr = Field(..., description="Email пользователя")

    model_config = {"json_schema_extra": {
        "example": {
            "email": "user@artstore.local"
        }
    }}


class PasswordResetConfirm(BaseModel):
    """Подтверждение сброса пароля."""

    reset_token: str = Field(..., description="Токен сброса пароля")
    new_password: str = Field(..., min_length=6, description="Новый пароль")

    model_config = {"json_schema_extra": {
        "example": {
            "reset_token": "reset_token_here",
            "new_password": "newSecurePassword123"
        }
    }}


class MessageResponse(BaseModel):
    """Общий ответ с сообщением."""

    message: str = Field(..., description="Сообщение")

    model_config = {"json_schema_extra": {
        "example": {
            "message": "Operation completed successfully"
        }
    }}
