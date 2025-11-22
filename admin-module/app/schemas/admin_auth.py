"""
Pydantic схемы для Admin Authentication.

Используются для валидации request/response данных при аутентификации
администраторов через login/password в Admin UI.
"""

from pydantic import BaseModel, EmailStr, Field, field_validator
from datetime import datetime
from typing import Optional
import uuid

from app.models.admin_user import AdminRole


# ===========================
# Request Schemas
# ===========================

class AdminLoginRequest(BaseModel):
    """
    Запрос на логин администратора.

    Используется для POST /api/admin-auth/login
    """

    username: str = Field(
        ...,
        min_length=3,
        max_length=100,
        description="Имя пользователя администратора",
        examples=["admin"]
    )

    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Пароль администратора",
        examples=["password123"]
    )

    @field_validator('username')
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Валидация username: только латиница, цифры, дефис, underscore."""
        if not v.replace('_', '').replace('-', '').isalnum():
            raise ValueError('Username может содержать только латинские буквы, цифры, дефис и underscore')
        return v.lower()  # Приводим к lowercase


class AdminRefreshRequest(BaseModel):
    """
    Запрос на обновление access token через refresh token.

    Используется для POST /api/admin-auth/refresh
    """

    refresh_token: str = Field(
        ...,
        description="JWT refresh token",
        examples=["eyJ0eXAiOiJKV1QiLCJhbGc..."]
    )


class AdminChangePasswordRequest(BaseModel):
    """
    Запрос на смену пароля администратора.

    Используется для POST /api/admin-auth/change-password
    """

    current_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Текущий пароль"
    )

    new_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Новый пароль"
    )

    confirm_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Подтверждение нового пароля"
    )

    @field_validator('new_password')
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """
        Валидация силы пароля:
        - Минимум 8 символов
        - Минимум одна заглавная буква
        - Минимум одна строчная буква
        - Минимум одна цифра
        """
        if not any(c.isupper() for c in v):
            raise ValueError('Пароль должен содержать минимум одну заглавную букву')
        if not any(c.islower() for c in v):
            raise ValueError('Пароль должен содержать минимум одну строчную букву')
        if not any(c.isdigit() for c in v):
            raise ValueError('Пароль должен содержать минимум одну цифру')
        return v

    def passwords_match(self) -> bool:
        """Проверка что новый пароль и подтверждение совпадают."""
        return self.new_password == self.confirm_password


# ===========================
# Response Schemas
# ===========================

class AdminTokenResponse(BaseModel):
    """
    Ответ с JWT токенами после успешного логина или refresh.

    Используется для POST /api/admin-auth/login и POST /api/admin-auth/refresh
    """

    access_token: str = Field(
        ...,
        description="JWT access token (RS256, expires in 30 minutes)",
        examples=["eyJ0eXAiOiJKV1QiLCJhbGc..."]
    )

    refresh_token: str = Field(
        ...,
        description="JWT refresh token (RS256, expires in 7 days)",
        examples=["eyJ0eXAiOiJKV1QiLCJhbGc..."]
    )

    token_type: str = Field(
        default="Bearer",
        description="Тип токена (всегда Bearer)"
    )

    expires_in: int = Field(
        ...,
        description="Время жизни access token в секундах (1800 = 30 minutes)",
        examples=[1800]
    )

    class Config:
        json_schema_extra = {
            "example": {
                "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9...",
                "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9...",
                "token_type": "Bearer",
                "expires_in": 1800
            }
        }


class AdminUserResponse(BaseModel):
    """
    Информация о текущем администраторе.

    Используется для GET /api/admin-auth/me
    """

    id: uuid.UUID = Field(
        ...,
        description="Уникальный UUID идентификатор администратора"
    )

    username: str = Field(
        ...,
        description="Имя пользователя администратора"
    )

    email: str = Field(
        ...,
        description="Email адрес администратора"
    )

    role: AdminRole = Field(
        ...,
        description="Роль администратора в системе"
    )

    enabled: bool = Field(
        ...,
        description="Статус активности аккаунта"
    )

    last_login_at: Optional[datetime] = Field(
        None,
        description="Дата и время последнего логина"
    )

    created_at: datetime = Field(
        ...,
        description="Дата создания аккаунта"
    )

    class Config:
        from_attributes = True  # Для работы с SQLAlchemy моделями
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "username": "admin",
                "email": "admin@artstore.local",
                "role": "admin",
                "enabled": True,
                "last_login_at": "2025-11-17T10:30:00Z",
                "created_at": "2025-11-17T00:00:00Z"
            }
        }


class AdminLogoutResponse(BaseModel):
    """
    Ответ при успешном logout.

    Используется для POST /api/admin-auth/logout
    """

    success: bool = Field(
        default=True,
        description="Статус успешности logout"
    )

    message: str = Field(
        default="Successfully logged out",
        description="Сообщение о результате"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Successfully logged out"
            }
        }


class AdminChangePasswordResponse(BaseModel):
    """
    Ответ при успешной смене пароля.

    Используется для POST /api/admin-auth/change-password
    """

    success: bool = Field(
        default=True,
        description="Статус успешности смены пароля"
    )

    message: str = Field(
        default="Password changed successfully",
        description="Сообщение о результате"
    )

    password_changed_at: datetime = Field(
        ...,
        description="Дата и время смены пароля"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Password changed successfully",
                "password_changed_at": "2025-11-17T10:30:00Z"
            }
        }


# ===========================
# JWT Payload Schemas
# ===========================

class AdminJWTPayload(BaseModel):
    """
    Payload JWT токена для администратора.

    Внутренняя схема для работы с JWT токенами.
    """

    sub: str = Field(
        ...,
        description="Subject (username администратора)"
    )

    type: str = Field(
        default="admin_user",
        description="Тип токена (admin_user vs service_account)"
    )

    role: AdminRole = Field(
        ...,
        description="Роль администратора"
    )

    exp: int = Field(
        ...,
        description="Expiration time (Unix timestamp)"
    )

    iat: int = Field(
        ...,
        description="Issued at time (Unix timestamp)"
    )

    jti: Optional[str] = Field(
        None,
        description="JWT ID (для token revocation в будущем)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "sub": "admin",
                "type": "admin_user",
                "role": "admin",
                "exp": 1700000000,
                "iat": 1699998200,
                "jti": "550e8400-e29b-41d4-a716-446655440000"
            }
        }
