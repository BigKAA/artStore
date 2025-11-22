"""
API endpoints для управления Service Accounts.

Предоставляет REST API для CRUD операций с Service Accounts:
- Создание Service Account с автоматической генерацией credentials
- Получение списка Service Accounts с фильтрацией и пагинацией
- Обновление параметров Service Account (role, rate_limit, status)
- Удаление Service Account (с защитой системных аккаунтов)
- Ротация client_secret

RBAC: Только SUPER_ADMIN может управлять Service Accounts
"""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.dependencies.admin_auth import get_current_admin_user, require_role
from app.models.admin_user import AdminUser, AdminRole
from app.models.service_account import ServiceAccountRole, ServiceAccountStatus
from app.schemas.service_account import (
    ServiceAccountCreate,
    ServiceAccountCreateResponse,
    ServiceAccountResponse,
    ServiceAccountUpdate,
    ServiceAccountRotateSecretResponse,
    ServiceAccountListResponse
)
from app.services.service_account_service import ServiceAccountService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/service-accounts")


@router.post(
    "/",
    response_model=ServiceAccountCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create new Service Account",
    description=(
        "Создание нового Service Account с автоматической генерацией "
        "client_id и client_secret. **ВАЖНО**: client_secret отображается "
        "ТОЛЬКО при создании! Требуется роль SUPER_ADMIN."
    )
)
async def create_service_account(
    request: ServiceAccountCreate,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_role(AdminRole.SUPER_ADMIN))
):
    """
    Создание нового Service Account.

    **Request Body:**
    - **name**: Название Service Account (уникальное)
    - **description**: Описание назначения (опционально)
    - **role**: Роль (ADMIN, USER, AUDITOR, READONLY)
    - **rate_limit**: Лимит запросов в минуту (default: 100)
    - **environment**: Окружение (prod, staging, dev)
    - **is_system**: Флаг системного аккаунта (default: false)

    **Response:**
    - Service Account с client_id и client_secret
    - **client_secret отображается ТОЛЬКО при создании!**
    - Сохраните client_secret в безопасном месте

    **RBAC:** Только SUPER_ADMIN
    """
    service = ServiceAccountService()

    try:
        # Создание Service Account
        service_account, plain_secret = await service.create_service_account(
            db=db,
            name=request.name,
            role=request.role,
            description=request.description,
            rate_limit=request.rate_limit,
            environment=request.environment,
            is_system=request.is_system
        )

        logger.info(
            f"Service Account created: {request.name} by {current_admin.username}",
            extra={
                "service_account_id": str(service_account.id),
                "client_id": service_account.client_id,
                "role": request.role.value,
                "admin_id": str(current_admin.id),
                "admin_username": current_admin.username
            }
        )

        # Возвращаем ответ с plain client_secret
        return ServiceAccountCreateResponse(
            id=service_account.id,
            name=service_account.name,
            client_id=service_account.client_id,
            client_secret=plain_secret,  # ONLY here!
            role=service_account.role,
            status=service_account.status,
            rate_limit=service_account.rate_limit,
            secret_expires_at=service_account.secret_expires_at,
            created_at=service_account.created_at
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except Exception as e:
        logger.error(
            f"Failed to create Service Account: {e}",
            extra={"admin_username": current_admin.username}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create Service Account"
        )


@router.get(
    "/",
    response_model=ServiceAccountListResponse,
    summary="Get Service Accounts list",
    description="Получение списка Service Accounts с фильтрацией и пагинацией"
)
async def get_service_accounts_list(
    skip: int = Query(0, ge=0, description="Offset пагинации"),
    limit: int = Query(100, ge=1, le=1000, description="Лимит записей"),
    role: Optional[ServiceAccountRole] = Query(None, description="Фильтр по роли"),
    status_filter: Optional[ServiceAccountStatus] = Query(None, alias="status", description="Фильтр по статусу"),
    search: Optional[str] = Query(None, description="Поиск по name или client_id"),
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin_user)
):
    """
    Получение списка Service Accounts с фильтрацией и пагинацией.

    **Query Parameters:**
    - **skip**: Offset для пагинации (default: 0)
    - **limit**: Количество записей (default: 100, max: 1000)
    - **role**: Фильтр по роли (ADMIN, USER, AUDITOR, READONLY)
    - **status**: Фильтр по статусу (ACTIVE, SUSPENDED, EXPIRED, DELETED)
    - **search**: Поиск по name или client_id

    **Response:**
    - **total**: Общее количество записей
    - **items**: Список Service Accounts (без client_secret)
    - **skip**: Текущий offset
    - **limit**: Текущий limit

    **RBAC:** Доступно всем аутентифицированным админам
    """
    service = ServiceAccountService()

    try:
        # Получаем список Service Accounts
        service_accounts = await service.list_service_accounts(
            db=db,
            skip=skip,
            limit=limit,
            role=role,
            status=status_filter
        )

        # Подсчитываем общее количество
        total = await service.count_service_accounts(
            db=db,
            status=status_filter
        )

        return ServiceAccountListResponse(
            total=total,
            items=[ServiceAccountResponse.model_validate(sa) for sa in service_accounts],
            skip=skip,
            limit=limit
        )

    except Exception as e:
        logger.error(
            f"Failed to get Service Accounts list: {e}",
            extra={"admin_username": current_admin.username}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve Service Accounts"
        )


@router.get(
    "/{service_account_id}",
    response_model=ServiceAccountResponse,
    summary="Get Service Account by ID",
    description="Получение Service Account по ID (без client_secret)"
)
async def get_service_account_by_id(
    service_account_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin_user)
):
    """
    Получение Service Account по ID.

    **Path Parameters:**
    - **service_account_id**: UUID Service Account

    **Response:**
    - Service Account без client_secret
    - Информация о статусе, роли, rate limit
    - Предупреждения о необходимости ротации secret

    **RBAC:** Доступно всем аутентифицированным админам
    """
    service = ServiceAccountService()

    try:
        service_account = await service.get_by_id(db, service_account_id)

        if not service_account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Service Account {service_account_id} not found"
            )

        return ServiceAccountResponse.model_validate(service_account)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to get Service Account {service_account_id}: {e}",
            extra={"admin_username": current_admin.username}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve Service Account"
        )


@router.put(
    "/{service_account_id}",
    response_model=ServiceAccountResponse,
    summary="Update Service Account",
    description="Обновление параметров Service Account (role, rate_limit, status)"
)
async def update_service_account(
    service_account_id: uuid.UUID,
    request: ServiceAccountUpdate,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_role(AdminRole.SUPER_ADMIN))
):
    """
    Обновление параметров Service Account.

    **Path Parameters:**
    - **service_account_id**: UUID Service Account

    **Request Body (все поля опциональны):**
    - **name**: Новое название
    - **description**: Новое описание
    - **role**: Новая роль
    - **rate_limit**: Новый rate limit
    - **status**: Новый статус (ACTIVE, SUSPENDED)

    **Ограничения:**
    - Системные Service Accounts (is_system=true) не могут быть изменены
    - Статус DELETED и EXPIRED нельзя установить вручную

    **RBAC:** Только SUPER_ADMIN
    """
    service = ServiceAccountService()

    try:
        # Получаем Service Account
        service_account = await service.get_by_id(db, service_account_id)

        if not service_account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Service Account {service_account_id} not found"
            )

        # Проверка системного Service Account
        if service_account.is_system:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot update system Service Account"
            )

        # Обновляем Service Account
        updated = await service.update_service_account(
            db=db,
            service_account_id=service_account_id,
            name=request.name,
            description=request.description,
            role=request.role,
            rate_limit=request.rate_limit,
            status_value=request.status
        )

        logger.info(
            f"Service Account updated: {service_account.name} by {current_admin.username}",
            extra={
                "service_account_id": str(service_account_id),
                "admin_id": str(current_admin.id),
                "admin_username": current_admin.username,
                "changes": request.model_dump(exclude_unset=True)
            }
        )

        return ServiceAccountResponse.model_validate(updated)

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except Exception as e:
        logger.error(
            f"Failed to update Service Account {service_account_id}: {e}",
            extra={"admin_username": current_admin.username}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update Service Account"
        )


@router.delete(
    "/{service_account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Service Account",
    description="Удаление Service Account (системные аккаунты защищены)"
)
async def delete_service_account(
    service_account_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_role(AdminRole.SUPER_ADMIN))
):
    """
    Удаление Service Account.

    **Path Parameters:**
    - **service_account_id**: UUID Service Account

    **Ограничения:**
    - Системные Service Accounts (is_system=true) не могут быть удалены
    - Soft delete: статус меняется на DELETED

    **RBAC:** Только SUPER_ADMIN
    """
    service = ServiceAccountService()

    try:
        # Получаем Service Account
        service_account = await service.get_by_id(db, service_account_id)

        if not service_account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Service Account {service_account_id} not found"
            )

        # Проверка системного Service Account
        if service_account.is_system:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot delete system Service Account"
            )

        # Удаляем Service Account
        await service.delete_service_account(db, service_account_id)

        logger.info(
            f"Service Account deleted: {service_account.name} by {current_admin.username}",
            extra={
                "service_account_id": str(service_account_id),
                "client_id": service_account.client_id,
                "admin_id": str(current_admin.id),
                "admin_username": current_admin.username
            }
        )

        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to delete Service Account {service_account_id}: {e}",
            extra={"admin_username": current_admin.username}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete Service Account"
        )


@router.post(
    "/{service_account_id}/rotate-secret",
    response_model=ServiceAccountRotateSecretResponse,
    summary="Rotate Service Account client_secret",
    description=(
        "Ротация client_secret с генерацией нового секрета. "
        "**ВАЖНО**: new_client_secret отображается ТОЛЬКО при ротации!"
    )
)
async def rotate_service_account_secret(
    service_account_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_role(AdminRole.SUPER_ADMIN))
):
    """
    Ротация client_secret Service Account.

    **Path Parameters:**
    - **service_account_id**: UUID Service Account

    **Response:**
    - Service Account с new_client_secret
    - **new_client_secret отображается ТОЛЬКО при ротации!**
    - Сохраните новый secret в безопасном месте
    - Старый secret становится недействительным

    **Features:**
    - Password history tracking (предотвращает reuse последних 5 secrets)
    - Автоматическое обновление secret_expires_at (+90 дней)
    - Старый secret добавляется в secret_history

    **RBAC:** Только SUPER_ADMIN
    """
    service = ServiceAccountService()

    try:
        # Получаем Service Account
        service_account = await service.get_by_id(db, service_account_id)

        if not service_account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Service Account {service_account_id} not found"
            )

        # Ротация secret
        updated, new_secret = await service.rotate_secret(db, service_account_id)

        logger.info(
            f"Service Account secret rotated: {service_account.name} by {current_admin.username}",
            extra={
                "service_account_id": str(service_account_id),
                "client_id": service_account.client_id,
                "admin_id": str(current_admin.id),
                "admin_username": current_admin.username
            }
        )

        return ServiceAccountRotateSecretResponse(
            id=updated.id,
            name=updated.name,
            client_id=updated.client_id,
            new_client_secret=new_secret,  # ONLY here!
            secret_expires_at=updated.secret_expires_at,
            status=updated.status
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(
            f"Failed to rotate Service Account secret {service_account_id}: {e}",
            extra={"admin_username": current_admin.username}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to rotate Service Account secret"
        )
