"""
Pydantic schemas для Service Accounts.
Request и Response модели для service account endpoints.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field

from app.models.service_account import ServiceAccountRole, ServiceAccountStatus


class OAuth2TokenRequest(BaseModel):
    """
    OAuth 2.0 Client Credentials Grant Request.

    Соответствует стандарту RFC 6749 Section 4.4.
    """

    grant_type: str = Field(
        default="client_credentials",
        description="OAuth 2.0 grant type (всегда client_credentials)",
        pattern="^client_credentials$"
    )
    client_id: str = Field(..., description="Client ID для OAuth 2.0")
    client_secret: str = Field(..., description="Client Secret для OAuth 2.0")

    model_config = {"json_schema_extra": {
        "example": {
            "grant_type": "client_credentials",
            "client_id": "sa_prod_myapp_a1b2c3d4",
            "client_secret": "secret_XyZ123...ABC789"
        }
    }}


class OAuth2TokenResponse(BaseModel):
    """
    OAuth 2.0 Token Response.

    Соответствует стандарту RFC 6749 Section 5.1.
    """

    access_token: str = Field(..., description="Access токен (JWT)")
    refresh_token: str = Field(..., description="Refresh токен (JWT)")
    token_type: str = Field(default="Bearer", description="Тип токена (всегда Bearer)")
    expires_in: int = Field(..., description="Время жизни access токена в секундах")
    issued_at: datetime = Field(..., description="Время выдачи токена (ISO 8601)")

    model_config = {"json_schema_extra": {
        "example": {
            "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
            "refresh_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
            "token_type": "Bearer",
            "expires_in": 1800,
            "issued_at": "2025-01-13T21:00:00Z"
        }
    }}


class ServiceAccountCreate(BaseModel):
    """Запрос на создание Service Account."""

    name: str = Field(..., min_length=3, max_length=200, description="Название Service Account")
    description: Optional[str] = Field(None, max_length=500, description="Описание назначения")
    role: ServiceAccountRole = Field(default=ServiceAccountRole.USER, description="Роль Service Account")
    rate_limit: int = Field(default=100, ge=1, le=10000, description="Лимит запросов в минуту")
    environment: str = Field(default="prod", pattern="^(prod|staging|dev)$", description="Окружение")
    is_system: bool = Field(default=False, description="Флаг системного Service Account")

    model_config = {"json_schema_extra": {
        "example": {
            "name": "MyApp Production Client",
            "description": "Production API client for MyApp",
            "role": "USER",
            "rate_limit": 100,
            "environment": "prod",
            "is_system": False
        }
    }}


class ServiceAccountCreateResponse(BaseModel):
    """
    Ответ при создании Service Account.

    ВАЖНО: client_secret отображается ТОЛЬКО при создании!
    """

    id: UUID = Field(..., description="UUID Service Account")
    name: str = Field(..., description="Название Service Account")
    client_id: str = Field(..., description="Client ID для OAuth 2.0")
    client_secret: str = Field(..., description="Client Secret (отображается ТОЛЬКО при создании!)")
    role: ServiceAccountRole = Field(..., description="Роль Service Account")
    status: ServiceAccountStatus = Field(..., description="Статус Service Account")
    rate_limit: int = Field(..., description="Лимит запросов в минуту")
    secret_expires_at: datetime = Field(..., description="Дата истечения client_secret")
    created_at: datetime = Field(..., description="Дата создания")

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "MyApp Production Client",
                "client_id": "sa_prod_myapp_a1b2c3d4",
                "client_secret": "secret_XyZ123...ABC789",
                "role": "USER",
                "status": "ACTIVE",
                "rate_limit": 100,
                "secret_expires_at": "2025-04-13T21:00:00Z",
                "created_at": "2025-01-13T21:00:00Z"
            }
        }
    }


class ServiceAccountResponse(BaseModel):
    """Ответ с информацией о Service Account (без client_secret)."""

    id: UUID = Field(..., description="UUID Service Account")
    name: str = Field(..., description="Название Service Account")
    description: Optional[str] = Field(None, description="Описание назначения")
    client_id: str = Field(..., description="Client ID для OAuth 2.0")
    role: ServiceAccountRole = Field(..., description="Роль Service Account")
    status: ServiceAccountStatus = Field(..., description="Статус Service Account")
    rate_limit: int = Field(..., description="Лимит запросов в минуту")
    is_system: bool = Field(..., description="Флаг системного Service Account")
    secret_expires_at: datetime = Field(..., description="Дата истечения client_secret")
    days_until_expiry: int = Field(..., description="Количество дней до истечения secret")
    requires_rotation_warning: bool = Field(..., description="Требуется предупреждение о ротации (≤7 дней)")
    last_used_at: Optional[datetime] = Field(None, description="Дата последнего использования")
    created_at: datetime = Field(..., description="Дата создания")
    updated_at: datetime = Field(..., description="Дата обновления")

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "MyApp Production Client",
                "description": "Production API client for MyApp",
                "client_id": "sa_prod_myapp_a1b2c3d4",
                "role": "USER",
                "status": "ACTIVE",
                "rate_limit": 100,
                "is_system": False,
                "secret_expires_at": "2025-04-13T21:00:00Z",
                "days_until_expiry": 90,
                "requires_rotation_warning": False,
                "last_used_at": "2025-01-13T20:00:00Z",
                "created_at": "2025-01-13T21:00:00Z",
                "updated_at": "2025-01-13T21:00:00Z"
            }
        }
    }


class ServiceAccountUpdate(BaseModel):
    """Запрос на обновление Service Account."""

    name: Optional[str] = Field(None, min_length=3, max_length=200, description="Новое название")
    description: Optional[str] = Field(None, max_length=500, description="Новое описание")
    role: Optional[ServiceAccountRole] = Field(None, description="Новая роль")
    rate_limit: Optional[int] = Field(None, ge=1, le=10000, description="Новый лимит запросов")
    status: Optional[ServiceAccountStatus] = Field(None, description="Новый статус")

    model_config = {"json_schema_extra": {
        "example": {
            "name": "MyApp Production Client (Updated)",
            "description": "Updated description",
            "rate_limit": 200
        }
    }}


class ServiceAccountRotateSecretResponse(BaseModel):
    """
    Ответ при ротации client_secret.

    ВАЖНО: new_client_secret отображается ТОЛЬКО при ротации!
    """

    id: UUID = Field(..., description="UUID Service Account")
    name: str = Field(..., description="Название Service Account")
    client_id: str = Field(..., description="Client ID")
    new_client_secret: str = Field(..., description="Новый Client Secret (отображается ТОЛЬКО при ротации!)")
    secret_expires_at: datetime = Field(..., description="Дата истечения нового secret")
    status: ServiceAccountStatus = Field(..., description="Статус Service Account")

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "MyApp Production Client",
                "client_id": "sa_prod_myapp_a1b2c3d4",
                "new_client_secret": "new_secret_ABC456...XYZ123",
                "secret_expires_at": "2025-04-13T21:00:00Z",
                "status": "ACTIVE"
            }
        }
    }


class ServiceAccountListResponse(BaseModel):
    """Ответ со списком Service Accounts."""

    total: int = Field(..., description="Общее количество Service Accounts")
    items: list[ServiceAccountResponse] = Field(..., description="Список Service Accounts")
    skip: int = Field(..., description="Offset пагинации")
    limit: int = Field(..., description="Лимит записей")

    model_config = {"json_schema_extra": {
        "example": {
            "total": 15,
            "items": [
                {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "name": "MyApp Production Client",
                    "description": "Production API client",
                    "client_id": "sa_prod_myapp_a1b2c3d4",
                    "role": "USER",
                    "status": "ACTIVE",
                    "rate_limit": 100,
                    "is_system": False,
                    "secret_expires_at": "2025-04-13T21:00:00Z",
                    "days_until_expiry": 90,
                    "requires_rotation_warning": False,
                    "last_used_at": "2025-01-13T20:00:00Z",
                    "created_at": "2025-01-13T21:00:00Z",
                    "updated_at": "2025-01-13T21:00:00Z"
                }
            ],
            "skip": 0,
            "limit": 100
        }
    }}


class OAuth2ErrorResponse(BaseModel):
    """
    OAuth 2.0 Error Response.

    Соответствует стандарту RFC 6749 Section 5.2.
    """

    error: str = Field(..., description="Код ошибки (invalid_client, access_denied, etc.)")
    error_description: str = Field(..., description="Человекочитаемое описание ошибки")
    error_uri: Optional[str] = Field(None, description="URI с документацией об ошибке")

    model_config = {"json_schema_extra": {
        "example": {
            "error": "invalid_client",
            "error_description": "Invalid client_id or client_secret",
            "error_uri": "https://docs.artstore.local/errors/invalid_client"
        }
    }}
