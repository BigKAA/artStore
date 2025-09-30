"""
Pydantic схемы для работы с пользователями.
"""
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.common import IDMixin, TimestampMixin


class UserBase(BaseModel):
    """
    Базовая схема пользователя с общими полями.
    """

    login: str = Field(..., min_length=3, max_length=100, description="Логин пользователя")
    email: EmailStr = Field(..., description="Email адрес")
    last_name: str = Field(..., min_length=1, max_length=100, description="Фамилия")
    first_name: str = Field(..., min_length=1, max_length=100, description="Имя")
    middle_name: Optional[str] = Field(None, max_length=100, description="Отчество (опционально)")
    description: Optional[str] = Field(None, description="Описание пользователя")


class UserCreate(UserBase):
    """
    Схема для создания пользователя.

    Используется в POST /api/users/
    """

    password: str = Field(..., min_length=8, description="Пароль (минимум 8 символов)")
    is_admin: bool = Field(default=False, description="Является ли администратором")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "login": "ivanov_ii",
                "email": "ivanov@example.com",
                "last_name": "Иванов",
                "first_name": "Иван",
                "middle_name": "Иванович",
                "password": "SecurePassword123",
                "is_admin": False,
                "description": "Менеджер отдела продаж",
            }
        }
    )


class UserUpdate(BaseModel):
    """
    Схема для обновления пользователя.

    Используется в PUT/PATCH /api/users/{user_id}
    Все поля опциональны - обновляются только переданные.
    """

    email: Optional[EmailStr] = Field(None, description="Email адрес")
    last_name: Optional[str] = Field(None, min_length=1, max_length=100, description="Фамилия")
    first_name: Optional[str] = Field(None, min_length=1, max_length=100, description="Имя")
    middle_name: Optional[str] = Field(None, max_length=100, description="Отчество")
    description: Optional[str] = Field(None, description="Описание пользователя")
    is_active: Optional[bool] = Field(None, description="Активен ли пользователь")
    is_admin: Optional[bool] = Field(None, description="Является ли администратором")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "new_email@example.com",
                "last_name": "Петров",
                "first_name": "Петр",
                "middle_name": "Петрович",
                "is_active": True,
                "description": "Обновленное описание",
            }
        }
    )


class UserChangePassword(BaseModel):
    """
    Схема для изменения пароля пользователя.

    Используется в POST /api/users/{user_id}/change-password
    """

    old_password: str = Field(..., description="Текущий пароль")
    new_password: str = Field(..., min_length=8, description="Новый пароль (минимум 8 символов)")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "old_password": "OldPassword123",
                "new_password": "NewSecurePassword456",
            }
        }
    )


class UserResponse(UserBase, IDMixin, TimestampMixin):
    """
    Схема пользователя в ответе API.

    Используется в GET /api/users/, GET /api/users/{user_id}
    Содержит все данные кроме пароля.
    """

    is_active: bool = Field(description="Активен ли пользователь")
    is_admin: bool = Field(description="Является ли администратором")
    is_system: bool = Field(description="Системный пользователь (защищен от удаления)")
    full_name: str = Field(description="Полное имя (ФИО)")

    model_config = ConfigDict(
        from_attributes=True,  # Для работы с ORM моделями
        json_schema_extra={
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "login": "ivanov_ii",
                "email": "ivanov@example.com",
                "last_name": "Иванов",
                "first_name": "Иван",
                "middle_name": "Иванович",
                "full_name": "Иванов Иван Иванович",
                "is_active": True,
                "is_admin": False,
                "is_system": False,
                "description": "Менеджер отдела продаж",
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-01-15T10:30:00Z",
            }
        },
    )


class UserInDB(UserResponse):
    """
    Схема пользователя как в БД.

    Используется внутри приложения для работы с полными данными пользователя.
    Содержит hashed_password для внутренних проверок.
    """

    hashed_password: str = Field(description="Хешированный пароль")

    model_config = ConfigDict(from_attributes=True)
