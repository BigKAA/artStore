"""
Pydantic схемы для CRUD операций с Admin Users.

Используются для валидации request/response данных при управлении
администраторами через Admin UI.
"""

from pydantic import BaseModel, EmailStr, Field, field_validator
from datetime import datetime
from typing import Optional, List
import uuid

from app.models.admin_user import AdminRole


# ===========================
# Request Schemas
# ===========================

class AdminUserCreateRequest(BaseModel):
    """
    Запрос на создание нового администратора.

    Используется для POST /api/admin-users
    """

    username: str = Field(
        ...,
        min_length=3,
        max_length=100,
        description="Имя пользователя администратора (уникальное)",
        examples=["john_doe"]
    )

    email: EmailStr = Field(
        ...,
        description="Email адрес администратора (уникальный)",
        examples=["john.doe@artstore.local"]
    )

    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Пароль администратора",
        examples=["SecurePassword123"]
    )

    role: AdminRole = Field(
        default=AdminRole.ADMIN,
        description="Роль администратора в системе"
    )

    enabled: bool = Field(
        default=True,
        description="Статус активности аккаунта (True = активен)"
    )

    @field_validator('username')
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Валидация username: только латиница, цифры, дефис, underscore."""
        if not v.replace('_', '').replace('-', '').isalnum():
            raise ValueError('Username может содержать только латинские буквы, цифры, дефис и underscore')
        return v.lower()  # Приводим к lowercase

    @field_validator('password')
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

    class Config:
        json_schema_extra = {
            "example": {
                "username": "john_doe",
                "email": "john.doe@artstore.local",
                "password": "SecurePassword123",
                "role": "admin",
                "enabled": True
            }
        }


class AdminUserUpdateRequest(BaseModel):
    """
    Запрос на обновление администратора.

    Используется для PUT /api/admin-users/{id}

    Все поля опциональные - обновляются только указанные поля.
    """

    email: Optional[EmailStr] = Field(
        None,
        description="Email адрес администратора (уникальный)"
    )

    role: Optional[AdminRole] = Field(
        None,
        description="Роль администратора в системе"
    )

    enabled: Optional[bool] = Field(
        None,
        description="Статус активности аккаунта"
    )

    @field_validator('email')
    @classmethod
    def validate_email_not_empty(cls, v: Optional[str]) -> Optional[str]:
        """Валидация что email не пустой если указан."""
        if v is not None and v.strip() == "":
            raise ValueError('Email не может быть пустым')
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "email": "john.doe@artstore.local",
                "role": "readonly",
                "enabled": False
            }
        }


class AdminUserPasswordResetRequest(BaseModel):
    """
    Запрос на сброс пароля администратора (от суперадмина).

    Используется для POST /api/admin-users/{id}/reset-password
    """

    new_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Новый пароль администратора"
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

    class Config:
        json_schema_extra = {
            "example": {
                "new_password": "NewSecurePassword123"
            }
        }


# ===========================
# Response Schemas
# ===========================

class AdminUserResponse(BaseModel):
    """
    Детальная информация об администраторе.

    Используется для GET /api/admin-users/{id} и POST /api/admin-users
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

    is_system: bool = Field(
        ...,
        description="Флаг системного Admin User (не может быть удален)"
    )

    last_login_at: Optional[datetime] = Field(
        None,
        description="Дата и время последнего логина"
    )

    password_changed_at: Optional[datetime] = Field(
        None,
        description="Дата последней смены пароля"
    )

    locked_until: Optional[datetime] = Field(
        None,
        description="Дата до которой аккаунт заблокирован"
    )

    login_attempts: int = Field(
        ...,
        description="Счетчик неудачных попыток логина"
    )

    created_at: datetime = Field(
        ...,
        description="Дата создания аккаунта"
    )

    updated_at: Optional[datetime] = Field(
        None,
        description="Дата последнего обновления аккаунта"
    )

    class Config:
        from_attributes = True  # Для работы с SQLAlchemy моделями
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "username": "john_doe",
                "email": "john.doe@artstore.local",
                "role": "admin",
                "enabled": True,
                "is_system": False,
                "last_login_at": "2025-11-17T10:30:00Z",
                "password_changed_at": "2025-11-17T00:00:00Z",
                "locked_until": None,
                "login_attempts": 0,
                "created_at": "2025-11-17T00:00:00Z",
                "updated_at": "2025-11-17T10:30:00Z"
            }
        }


class AdminUserListItem(BaseModel):
    """
    Краткая информация об администраторе для списка.

    Используется для GET /api/admin-users (list endpoint)
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

    is_system: bool = Field(
        ...,
        description="Флаг системного Admin User (не может быть удален)"
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
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "username": "john_doe",
                "email": "john.doe@artstore.local",
                "role": "admin",
                "enabled": True,
                "is_system": False,
                "last_login_at": "2025-11-17T10:30:00Z",
                "created_at": "2025-11-17T00:00:00Z"
            }
        }


class AdminUserListResponse(BaseModel):
    """
    Ответ со списком администраторов (с пагинацией).

    Используется для GET /api/admin-users
    """

    items: List[AdminUserListItem] = Field(
        ...,
        description="Список администраторов"
    )

    total: int = Field(
        ...,
        description="Общее количество администраторов (без фильтрации пагинацией)"
    )

    page: int = Field(
        ...,
        description="Текущая страница (starting from 1)"
    )

    page_size: int = Field(
        ...,
        description="Размер страницы (количество элементов на странице)"
    )

    total_pages: int = Field(
        ...,
        description="Общее количество страниц"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "items": [
                    {
                        "id": "550e8400-e29b-41d4-a716-446655440000",
                        "username": "admin",
                        "email": "admin@artstore.local",
                        "role": "super_admin",
                        "enabled": True,
                        "is_system": True,
                        "last_login_at": "2025-11-17T10:30:00Z",
                        "created_at": "2025-11-17T00:00:00Z"
                    },
                    {
                        "id": "660e8400-e29b-41d4-a716-446655440001",
                        "username": "john_doe",
                        "email": "john.doe@artstore.local",
                        "role": "admin",
                        "enabled": True,
                        "is_system": False,
                        "last_login_at": "2025-11-17T09:15:00Z",
                        "created_at": "2025-11-16T00:00:00Z"
                    }
                ],
                "total": 15,
                "page": 1,
                "page_size": 10,
                "total_pages": 2
            }
        }


class AdminUserDeleteResponse(BaseModel):
    """
    Ответ при успешном удалении администратора.

    Используется для DELETE /api/admin-users/{id}
    """

    success: bool = Field(
        default=True,
        description="Статус успешности удаления"
    )

    message: str = Field(
        default="Admin user deleted successfully",
        description="Сообщение о результате"
    )

    deleted_id: uuid.UUID = Field(
        ...,
        description="UUID удаленного администратора"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Admin user deleted successfully",
                "deleted_id": "550e8400-e29b-41d4-a716-446655440000"
            }
        }


class AdminUserPasswordResetResponse(BaseModel):
    """
    Ответ при успешном сбросе пароля администратора.

    Используется для POST /api/admin-users/{id}/reset-password
    """

    success: bool = Field(
        default=True,
        description="Статус успешности сброса пароля"
    )

    message: str = Field(
        default="Password reset successfully",
        description="Сообщение о результате"
    )

    password_changed_at: datetime = Field(
        ...,
        description="Дата и время сброса пароля"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Password reset successfully",
                "password_changed_at": "2025-11-17T10:30:00Z"
            }
        }
