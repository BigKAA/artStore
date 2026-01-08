"""
Admin Module - File Registry API Endpoints.

Sprint 15.2: REST API для централизованного реестра файлов.

Endpoints:
- POST /api/v1/files - Регистрация нового файла
- GET /api/v1/files/{file_id} - Получение метаданных файла
- PUT /api/v1/files/{file_id} - Обновление файла (финализация)
- DELETE /api/v1/files/{file_id} - Soft delete файла
- GET /api/v1/files - Список файлов с pagination

ВАЖНО:
- Используется Service Account authentication (OAuth 2.0 Bearer token)
- Все операции audit logged через AuditMiddleware
- Transaction safety через async SQLAlchemy
"""

import logging
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import get_db
from app.api.dependencies.auth import get_current_service_account
from app.models.service_account import ServiceAccount, ServiceAccountRole
from app.models.file import RetentionPolicy
from app.schemas.file import (
    FileRegisterRequest,
    FileUpdateRequest,
    FileResponse,
    FileListResponse,
    FileDeleteResponse,
)
from app.services.file_service import get_file_service, FileService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/files", tags=["file-registry"])


def require_admin_or_user_role(
    current_account: Annotated[ServiceAccount, Depends(get_current_service_account)]
) -> ServiceAccount:
    """
    Dependency для проверки роли ADMIN или USER.

    Args:
        current_account: Текущий Service Account из JWT

    Returns:
        ServiceAccount: Валидный аккаунт

    Raises:
        HTTPException 403: Insufficient permissions
    """
    if current_account.role not in [ServiceAccountRole.ADMIN, ServiceAccountRole.USER]:
        logger.warning(
            "Access denied: insufficient permissions",
            extra={
                "client_id": current_account.client_id,
                "role": current_account.role.value,
                "required_roles": ["ADMIN", "USER"]
            }
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. Required: ADMIN or USER role"
        )
    return current_account


def require_admin_role(
    current_account: Annotated[ServiceAccount, Depends(get_current_service_account)]
) -> ServiceAccount:
    """
    Dependency для проверки роли ADMIN.

    Args:
        current_account: Текущий Service Account из JWT

    Returns:
        ServiceAccount: Валидный аккаунт

    Raises:
        HTTPException 403: Insufficient permissions
    """
    if current_account.role != ServiceAccountRole.ADMIN:
        logger.warning(
            "Access denied: admin role required",
            extra={
                "client_id": current_account.client_id,
                "role": current_account.role.value
            }
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. Required: ADMIN role"
        )
    return current_account


@router.post(
    "",
    response_model=FileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register New File",
    description="""
    Регистрация нового файла в file registry.

    **Sprint 15.2: Ingester Module Integration**

    Этот endpoint вызывается Ingester Module после успешной загрузки файла
    в Storage Element для создания записи в централизованном реестре.

    **Workflow:**
    1. Ingester загружает файл в Storage Element
    2. Storage Element возвращает file_id и metadata
    3. Ingester вызывает этот endpoint для регистрации файла
    4. Admin Module создает запись в file registry (PostgreSQL)

    **Required Permissions:** ADMIN or USER role

    **Idempotence:** Если файл с таким file_id уже существует, возвращается 400 Bad Request.
    """
)
async def register_file(
    request: FileRegisterRequest,
    db: AsyncSession = Depends(get_db),
    file_service: FileService = Depends(get_file_service),
    current_account: ServiceAccount = Depends(require_admin_or_user_role)
) -> FileResponse:
    """
    Регистрация нового файла в file registry.

    Sprint 15.2: Вызывается Ingester Module после upload.

    Args:
        request: Данные файла для регистрации
        db: Database session
        file_service: FileService instance
        current_account: Authenticated Service Account

    Returns:
        FileResponse: Зарегистрированный файл

    Raises:
        HTTPException 400: File already exists или validation error
        HTTPException 500: Internal server error
    """
    logger.info(
        "File registration request received",
        extra={
            "file_id": str(request.file_id),
            "filename": request.original_filename,
            "retention_policy": request.retention_policy.value,
            "storage_element_id": request.storage_element_id,
            "client_id": current_account.client_id
        }
    )

    try:
        file = await file_service.register_file(db, request)

        logger.info(
            "File registered successfully",
            extra={
                "file_id": str(file.file_id),
                "filename": file.original_filename,
                "client_id": current_account.client_id
            }
        )

        return file

    except ValueError as e:
        logger.warning(
            "File registration validation error",
            extra={
                "file_id": str(request.file_id),
                "error": str(e),
                "client_id": current_account.client_id
            }
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    except SQLAlchemyError as e:
        logger.error(
            "Database error during file registration",
            extra={
                "file_id": str(request.file_id),
                "error": str(e),
                "client_id": current_account.client_id
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register file"
        )


@router.get(
    "/{file_id}",
    response_model=FileResponse,
    summary="Get File Metadata",
    description="""
    Получение метаданных файла по ID.

    **Sprint 15.2: File Registry Lookup**

    Используется Query Module для получения информации о файле перед download,
    а также Ingester Module для проверки существования файла перед финализацией.

    **Required Permissions:** ADMIN, USER, AUDITOR, or READONLY role

    **404 Not Found:** Если файл не найден или был удален (soft delete)
    """
)
async def get_file_by_id(
    file_id: UUID = Path(..., description="UUID файла"),
    include_deleted: bool = Query(
        False,
        description="Включать ли удаленные файлы (требуется ADMIN роль)"
    ),
    db: AsyncSession = Depends(get_db),
    file_service: FileService = Depends(get_file_service),
    current_account: ServiceAccount = Depends(get_current_service_account)
) -> FileResponse:
    """
    Получение метаданных файла по ID.

    Args:
        file_id: UUID файла
        include_deleted: Включать ли удаленные файлы
        db: Database session
        file_service: FileService instance
        current_account: Authenticated Service Account

    Returns:
        FileResponse: Метаданные файла

    Raises:
        HTTPException 403: Недостаточно прав для include_deleted=True
        HTTPException 404: Файл не найден
    """
    # Проверка прав для include_deleted
    if include_deleted and current_account.role != ServiceAccountRole.ADMIN:
        logger.warning(
            "Access denied: admin role required for include_deleted=True",
            extra={
                "file_id": str(file_id),
                "client_id": current_account.client_id,
                "role": current_account.role.value
            }
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. ADMIN role required for include_deleted=True"
        )

    logger.debug(
        "File metadata request",
        extra={
            "file_id": str(file_id),
            "include_deleted": include_deleted,
            "client_id": current_account.client_id
        }
    )

    file = await file_service.get_file_by_id(db, file_id, include_deleted)

    if not file:
        logger.warning(
            "File not found",
            extra={
                "file_id": str(file_id),
                "client_id": current_account.client_id
            }
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File {file_id} not found"
        )

    return file


@router.put(
    "/{file_id}",
    response_model=FileResponse,
    summary="Update File Metadata",
    description="""
    Обновление метаданных файла (финализация).

    **Sprint 15.2: File Finalization Support**

    Этот endpoint вызывается Ingester Module при Two-Phase Commit для обновления:
    - `retention_policy`: temporary → permanent
    - `storage_element_id`: edit_se → rw_se
    - `storage_path`: новый путь в RW SE
    - `finalized_at`: timestamp финализации

    **Workflow (Finalization):**
    1. Ingester копирует файл из Edit SE в RW SE
    2. Ingester проверяет checksum (source == target)
    3. Ingester вызывает этот endpoint для обновления registry
    4. Admin Module обновляет запись: retention_policy=permanent, storage_element_id=rw_se

    **Required Permissions:** ADMIN or USER role

    **Validation:**
    - Нельзя изменить permanent → temporary
    - file_id должен существовать

    **404 Not Found:** Если файл не найден
    """
)
async def update_file(
    request: FileUpdateRequest,
    file_id: UUID = Path(..., description="UUID файла"),
    db: AsyncSession = Depends(get_db),
    file_service: FileService = Depends(get_file_service),
    current_account: ServiceAccount = Depends(require_admin_or_user_role)
) -> FileResponse:
    """
    Обновление метаданных файла (финализация).

    Sprint 15.2: Вызывается Ingester Module при finalize.

    Args:
        file_id: UUID файла
        request: Данные для обновления
        db: Database session
        file_service: FileService instance
        current_account: Authenticated Service Account

    Returns:
        FileResponse: Обновленный файл

    Raises:
        HTTPException 400: Validation error
        HTTPException 404: Файл не найден
        HTTPException 500: Internal server error
    """
    logger.info(
        "File update request received",
        extra={
            "file_id": str(file_id),
            "retention_policy": request.retention_policy.value if request.retention_policy else None,
            "storage_element_id": request.storage_element_id,
            "client_id": current_account.client_id
        }
    )

    try:
        file = await file_service.update_file(db, file_id, request)

        if not file:
            logger.warning(
                "File not found for update",
                extra={
                    "file_id": str(file_id),
                    "client_id": current_account.client_id
                }
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"File {file_id} not found"
            )

        logger.info(
            "File updated successfully",
            extra={
                "file_id": str(file.file_id),
                "retention_policy": file.retention_policy.value,
                "finalized": file.is_finalized,
                "client_id": current_account.client_id
            }
        )

        return file

    except ValueError as e:
        logger.warning(
            "File update validation error",
            extra={
                "file_id": str(file_id),
                "error": str(e),
                "client_id": current_account.client_id
            }
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    except SQLAlchemyError as e:
        logger.error(
            "Database error during file update",
            extra={
                "file_id": str(file_id),
                "error": str(e),
                "client_id": current_account.client_id
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update file"
        )


@router.delete(
    "/{file_id}",
    response_model=FileDeleteResponse,
    summary="Delete File (Soft Delete)",
    description="""
    Мягкое удаление файла (soft delete).

    **Sprint 15.2: File Lifecycle Management**

    Файл помечается как удаленный (deleted_at, deletion_reason) но физически
    остается в БД для audit trail.

    **ВАЖНО:** Физическое удаление файла из Storage Element выполняется отдельно
    через Garbage Collector service.

    **Required Permissions:** ADMIN role (только администраторы могут удалять файлы)

    **Deletion Reasons:**
    - `manual`: Ручное удаление через API
    - `ttl_expired`: TTL истек для temporary файла
    - `gc_cleanup`: Garbage Collector cleanup
    - `finalized`: Удаление source файла после финализации

    **Idempotence:** Повторное удаление возвращает 200 OK с информацией о предыдущем удалении
    """
)
async def delete_file(
    file_id: UUID = Path(..., description="UUID файла"),
    deletion_reason: str = Query(
        "manual",
        max_length=255,
        description="Причина удаления: manual, ttl_expired, gc_cleanup, finalized"
    ),
    db: AsyncSession = Depends(get_db),
    file_service: FileService = Depends(get_file_service),
    current_account: ServiceAccount = Depends(require_admin_role)
) -> FileDeleteResponse:
    """
    Мягкое удаление файла.

    Sprint 15.2: Только ADMIN роль может удалять файлы.

    Args:
        file_id: UUID файла
        deletion_reason: Причина удаления
        db: Database session
        file_service: FileService instance
        current_account: Authenticated Service Account (ADMIN role)

    Returns:
        FileDeleteResponse: Результат удаления

    Raises:
        HTTPException 404: Файл не найден
        HTTPException 500: Internal server error
    """
    logger.info(
        "File deletion request received",
        extra={
            "file_id": str(file_id),
            "deletion_reason": deletion_reason,
            "client_id": current_account.client_id
        }
    )

    try:
        result = await file_service.delete_file(db, file_id, deletion_reason)

        if not result:
            logger.warning(
                "File not found for deletion",
                extra={
                    "file_id": str(file_id),
                    "client_id": current_account.client_id
                }
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"File {file_id} not found"
            )

        logger.info(
            "File deleted successfully",
            extra={
                "file_id": str(file_id),
                "deleted_at": str(result.deleted_at),
                "deletion_reason": result.deletion_reason,
                "client_id": current_account.client_id
            }
        )

        return result

    except SQLAlchemyError as e:
        logger.error(
            "Database error during file deletion",
            extra={
                "file_id": str(file_id),
                "error": str(e),
                "client_id": current_account.client_id
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete file"
        )


@router.get(
    "",
    response_model=FileListResponse,
    summary="List Files",
    description="""
    Получение списка файлов с pagination и фильтрацией.

    **Sprint 15.2: File Registry Query**

    Используется Query Module и Admin UI для отображения списка файлов.

    **Pagination:**
    - page: Номер страницы (1-based, default: 1)
    - page_size: Размер страницы (1-1000, default: 50)

    **Filters:**
    - retention_policy: temporary или permanent
    - storage_element_id: Фильтр по Storage Element
    - include_deleted: Включать ли удаленные файлы (требуется ADMIN роль)

    **Sorting:** По created_at DESC (новые файлы первыми)

    **Required Permissions:** ADMIN, USER, AUDITOR, or READONLY role
    """
)
async def list_files(
    page: int = Query(1, ge=1, description="Номер страницы"),
    page_size: int = Query(50, ge=1, le=1000, description="Размер страницы"),
    retention_policy: Optional[RetentionPolicy] = Query(
        None,
        description="Фильтр по retention policy: temporary или permanent"
    ),
    storage_element_id: Optional[str] = Query(
        None,
        max_length=255,
        description="Фильтр по Storage Element ID"
    ),
    include_deleted: bool = Query(
        False,
        description="Включать ли удаленные файлы (требуется ADMIN роль)"
    ),
    db: AsyncSession = Depends(get_db),
    file_service: FileService = Depends(get_file_service),
    current_account: ServiceAccount = Depends(get_current_service_account)
) -> FileListResponse:
    """
    Получение списка файлов с pagination.

    Args:
        page: Номер страницы
        page_size: Размер страницы
        retention_policy: Фильтр по retention policy
        storage_element_id: Фильтр по Storage Element
        include_deleted: Включать ли удаленные файлы
        db: Database session
        file_service: FileService instance
        current_account: Authenticated Service Account

    Returns:
        FileListResponse: Список файлов с metadata

    Raises:
        HTTPException 403: Недостаточно прав для include_deleted=True
    """
    # Проверка прав для include_deleted
    if include_deleted and current_account.role != ServiceAccountRole.ADMIN:
        logger.warning(
            "Access denied: admin role required for include_deleted=True",
            extra={
                "client_id": current_account.client_id,
                "role": current_account.role.value
            }
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. ADMIN role required for include_deleted=True"
        )

    logger.debug(
        "File list request",
        extra={
            "page": page,
            "page_size": page_size,
            "retention_policy": retention_policy.value if retention_policy else None,
            "storage_element_id": storage_element_id,
            "include_deleted": include_deleted,
            "client_id": current_account.client_id
        }
    )

    result = await file_service.list_files(
        db=db,
        page=page,
        page_size=page_size,
        retention_policy=retention_policy,
        storage_element_id=storage_element_id,
        include_deleted=include_deleted
    )

    logger.info(
        "File list retrieved",
        extra={
            "total": result.total,
            "page": result.page,
            "returned_count": len(result.files),
            "client_id": current_account.client_id
        }
    )

    return result
