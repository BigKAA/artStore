"""
Garbage Collection API Endpoints - операции для GC cleanup.

Системные endpoints для GarbageCollectorService из Admin Module.
Доступны только для Service Accounts.
Не зависят от режима хранилища (работают всегда).
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_service_account
from app.core.security import UserContext
from app.core.exceptions import StorageException
from app.services.file_service import FileService

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# Pydantic Models для GC API
# ============================================================================

class GCDeleteResponse(BaseModel):
    """Ответ на успешное удаление файла через GC"""
    status: str = Field(default="deleted", description="Статус операции")
    file_id: UUID = Field(..., description="UUID удалённого файла")
    deleted_at: str = Field(..., description="Timestamp удаления (ISO 8601)")
    deleted_by: str = Field(..., description="Service Account ID")
    reason: str = Field(default="gc_cleanup", description="Причина удаления")


class GCDeleteRequest(BaseModel):
    """Опциональные параметры для GC delete"""
    reason: str = Field(
        default="gc_cleanup",
        description="Причина удаления (для audit log)"
    )
    cleanup_type: Optional[str] = Field(
        default=None,
        description="Тип cleanup: ttl_expired | finalized | orphaned"
    )


# ============================================================================
# GC Endpoints
# ============================================================================

@router.delete(
    "/{file_id}",
    response_model=GCDeleteResponse,
    status_code=status.HTTP_200_OK,
    summary="Удалить файл через GC",
    description="""
    Удалить файл из хранилища по запросу GarbageCollector.

    **Особенности**:
    - Доступен только для Service Accounts (GC job использует service account токен)
    - НЕ зависит от режима хранилища (работает в edit, rw, ro, ar)
    - Записывает audit log с причиной удаления
    - Idempotent: повторное удаление возвращает успех

    **Используется**:
    - GarbageCollectorService в Admin Module
    - Cleanup очередь для TTL-expired файлов
    - Очистка finalized файлов с Edit SE
    - Удаление orphaned файлов
    """
)
async def gc_delete_file(
    file_id: UUID,
    request: Optional[GCDeleteRequest] = None,
    service_account: UserContext = Depends(require_service_account),
    db: AsyncSession = Depends(get_db),
):
    """
    Удалить файл через Garbage Collector.

    Системный endpoint для GC job из Admin Module.

    Args:
        file_id: UUID файла для удаления
        request: Опциональные параметры (reason, cleanup_type)
        service_account: Service Account из JWT токена
        db: Database session

    Returns:
        GCDeleteResponse: Информация об удалённом файле

    Raises:
        HTTPException 403: Если вызывающий не Service Account
        HTTPException 404: Файл не найден
        HTTPException 500: Ошибка удаления
    """
    # Параметры по умолчанию
    reason = "gc_cleanup"
    cleanup_type = None
    if request:
        reason = request.reason
        cleanup_type = request.cleanup_type

    # Audit log: начало операции
    logger.info(
        "GC delete operation started",
        extra={
            "file_id": str(file_id),
            "service_account_id": service_account.sub,
            "service_account_name": service_account.username,
            "reason": reason,
            "cleanup_type": cleanup_type
        }
    )

    try:
        file_service = FileService(db)

        # Проверка существования файла (для idempotency)
        metadata = await file_service.get_file_metadata(file_id)

        if not metadata:
            # Idempotent: файл уже удалён или не существует
            logger.info(
                "GC delete: file already deleted or not found (idempotent success)",
                extra={
                    "file_id": str(file_id),
                    "service_account_id": service_account.sub
                }
            )
            return GCDeleteResponse(
                status="already_deleted",
                file_id=file_id,
                deleted_at=datetime.now(timezone.utc).isoformat(),
                deleted_by=service_account.sub,
                reason=reason
            )

        # Удаление файла через FileService (WAL protocol)
        await file_service.delete_file(
            file_id=file_id,
            user_id=service_account.sub
        )

        deleted_at = datetime.now(timezone.utc)

        # Audit log: успешное удаление
        logger.info(
            "GC delete operation completed successfully",
            extra={
                "file_id": str(file_id),
                "original_filename": metadata.original_filename,
                "file_size": metadata.file_size,
                "service_account_id": service_account.sub,
                "service_account_name": service_account.username,
                "reason": reason,
                "cleanup_type": cleanup_type,
                "deleted_at": deleted_at.isoformat(),
                "action": "file_delete",
                "audit": True  # Маркер для audit log aggregation
            }
        )

        return GCDeleteResponse(
            status="deleted",
            file_id=file_id,
            deleted_at=deleted_at.isoformat(),
            deleted_by=service_account.sub,
            reason=reason
        )

    except StorageException as e:
        if e.error_code == "FILE_NOT_FOUND":
            # Idempotent: файл не найден = уже удалён
            logger.info(
                "GC delete: file not found (idempotent success)",
                extra={
                    "file_id": str(file_id),
                    "service_account_id": service_account.sub,
                    "error_code": e.error_code
                }
            )
            return GCDeleteResponse(
                status="already_deleted",
                file_id=file_id,
                deleted_at=datetime.now(timezone.utc).isoformat(),
                deleted_by=service_account.sub,
                reason=reason
            )

        # Audit log: ошибка
        logger.error(
            "GC delete operation failed",
            extra={
                "file_id": str(file_id),
                "service_account_id": service_account.sub,
                "error_code": e.error_code,
                "error_message": e.message,
                "action": "file_delete_failed",
                "audit": True
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete file: {e.message}"
        )

    except Exception as e:
        # Audit log: unexpected error
        logger.error(
            "GC delete operation failed with unexpected error",
            extra={
                "file_id": str(file_id),
                "service_account_id": service_account.sub,
                "error": str(e),
                "action": "file_delete_failed",
                "audit": True
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete file"
        )


@router.get(
    "/{file_id}/exists",
    status_code=status.HTTP_200_OK,
    summary="Проверить существование файла",
    description="""
    Проверить существует ли файл в хранилище.

    Используется GC для проверки перед удалением и для
    верификации результата cleanup операций.
    """
)
async def gc_check_file_exists(
    file_id: UUID,
    service_account: UserContext = Depends(require_service_account),
    db: AsyncSession = Depends(get_db),
):
    """
    Проверить существование файла.

    Args:
        file_id: UUID файла
        service_account: Service Account из JWT
        db: Database session

    Returns:
        dict: {"exists": bool, "file_id": UUID}
    """
    try:
        file_service = FileService(db)
        metadata = await file_service.get_file_metadata(file_id)

        return {
            "exists": metadata is not None,
            "file_id": str(file_id)
        }

    except Exception as e:
        logger.error(f"Failed to check file existence: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check file existence"
        )
