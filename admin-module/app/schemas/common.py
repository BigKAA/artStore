"""
Общие Pydantic схемы, используемые в разных endpoints.
"""
from datetime import datetime
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

# Generic типы для пагинации
T = TypeVar("T")


class PaginationParams(BaseModel):
    """
    Параметры пагинации для списков.

    Используется как query параметры в GET запросах.
    """

    page: int = Field(default=1, ge=1, description="Номер страницы (начиная с 1)")
    size: int = Field(
        default=20, ge=1, le=100, description="Количество элементов на странице"
    )

    model_config = ConfigDict(
        json_schema_extra={"example": {"page": 1, "size": 20}}
    )


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Обертка для пагинированных ответов.

    Generic класс - может содержать любой тип элементов.

    Example:
        >>> PaginatedResponse[UserResponse](
        >>>     items=[user1, user2],
        >>>     total=100,
        >>>     page=1,
        >>>     size=20,
        >>>     pages=5
        >>> )
    """

    items: List[T] = Field(description="Список элементов на текущей странице")
    total: int = Field(description="Общее количество элементов")
    page: int = Field(description="Текущая страница")
    size: int = Field(description="Размер страницы")
    pages: int = Field(description="Общее количество страниц")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "items": [],
                "total": 100,
                "page": 1,
                "size": 20,
                "pages": 5,
            }
        }
    )


class SuccessResponse(BaseModel):
    """
    Стандартный ответ об успехе операции.

    Используется для операций без возврата данных (delete, activate, etc).
    """

    success: bool = Field(default=True, description="Статус операции")
    message: str = Field(description="Сообщение о результате")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"success": True, "message": "Операция выполнена успешно"}
        }
    )


class ErrorDetail(BaseModel):
    """
    Детали ошибки валидации.
    """

    loc: List[str] = Field(description="Путь к полю с ошибкой")
    msg: str = Field(description="Сообщение об ошибке")
    type: str = Field(description="Тип ошибки")


class ErrorResponse(BaseModel):
    """
    Стандартный ответ об ошибке.

    Возвращается при HTTP 4xx и 5xx ошибках.
    """

    detail: str = Field(description="Общее описание ошибки")
    errors: Optional[List[ErrorDetail]] = Field(
        default=None, description="Детали ошибок валидации (если есть)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "detail": "Validation error",
                "errors": [
                    {
                        "loc": ["body", "email"],
                        "msg": "Invalid email format",
                        "type": "value_error.email",
                    }
                ],
            }
        }
    )


class TimestampMixin(BaseModel):
    """
    Mixin для добавления временных меток.

    Используется в response схемах для отображения created_at/updated_at.
    """

    created_at: datetime = Field(description="Дата создания")
    updated_at: datetime = Field(description="Дата последнего обновления")


class IDMixin(BaseModel):
    """
    Mixin для добавления ID.
    """

    id: str = Field(description="Уникальный идентификатор")
