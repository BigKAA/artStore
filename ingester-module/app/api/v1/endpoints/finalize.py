"""
Ingester Module - Finalize Endpoints.

Sprint 15: API endpoints для финализации temporary файлов.

Two-Phase Commit Process:
1. POST /finalize/{file_id} - Запуск финализации
2. GET /finalize/{transaction_id}/status - Статус транзакции

Workflow:
1. Клиент загружает файл с retention_policy=temporary → файл в Edit SE
2. Клиент работает над документом (редактирует, обновляет)
3. Клиент вызывает POST /finalize/{file_id} → Two-Phase Commit
4. Файл копируется в RW SE, проверяется checksum
5. Оригинал в Edit SE добавляется в cleanup queue (+24h safety margin)
"""

import logging
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import UserContext
from app.api.v1.endpoints.upload import get_current_user
from app.schemas.upload import (
    FinalizeRequest,
    FinalizeResponse,
    FinalizeStatus,
    FinalizeTransactionStatus
)
from app.services.finalize_service import get_finalize_service, FinalizeService

logger = logging.getLogger(__name__)

router = APIRouter()


def get_finalize_svc() -> FinalizeService:
    """
    Dependency для получения FinalizeService.

    Returns:
        FinalizeService: Инициализированный сервис финализации

    Raises:
        HTTPException 503: Сервис не инициализирован
    """
    service = get_finalize_service()
    if not service:
        logger.error("FinalizeService not initialized")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Finalize service not available"
        )
    return service


@router.post(
    "/{file_id}",
    response_model=FinalizeResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Finalize Temporary File",
    description="""
    Запуск финализации temporary файла (Two-Phase Commit).

    **Sprint 15: Retention Policy Lifecycle**

    Финализация переносит файл из Edit SE в RW SE:
    - temporary (Edit SE) → permanent (RW SE)

    **Two-Phase Commit Process:**
    1. **COPYING**: Копирование файла на target RW SE
    2. **VERIFYING**: Проверка checksum source == target
    3. **COMPLETED**: Успешная финализация (metadata обновлена)
    4. **FAILED**: Ошибка → откат транзакции

    **Safety Features:**
    - Checksum verification предотвращает data corruption
    - 24-hour safety margin перед удалением из source SE
    - Transaction log для recovery

    **Возвращает HTTP 202 Accepted** - финализация выполняется асинхронно.
    Используйте GET /finalize/{transaction_id}/status для отслеживания.
    """
)
async def finalize_file(
    file_id: UUID,
    user: Annotated[UserContext, Depends(get_current_user)],
    finalize_svc: Annotated[FinalizeService, Depends(get_finalize_svc)],
    request: Optional[FinalizeRequest] = None
) -> FinalizeResponse:
    """
    Финализация temporary файла.

    Sprint 15: Two-Phase Commit для переноса файла из Edit SE в RW SE.

    Args:
        file_id: UUID файла для финализации
        user: Текущий пользователь (из JWT)
        request: Параметры финализации (опционально)

    Returns:
        FinalizeResponse: Результат запуска финализации с transaction_id

    Raises:
        HTTPException 404: Файл не найден
        HTTPException 400: Файл не является temporary или уже финализирован
        HTTPException 503: Storage Element недоступен
    """
    logger.info(
        "Finalize request received",
        extra={
            "file_id": str(file_id),
            "user_id": user.user_id,
            "username": user.username
        }
    )

    # Создаём request если не передан
    if request is None:
        request = FinalizeRequest()

    # TODO: Sprint 15.2 - Получить информацию о файле из Admin Module file registry
    # Для MVP используем заглушку - в production нужно получить:
    # - source_se_id: ID Edit SE где хранится файл
    # - source_se_endpoint: URL Edit SE
    # - file_size: Размер файла
    # - checksum: SHA-256 checksum
    # - retention_policy: Проверить что файл temporary

    # Временная заглушка для MVP (в production это будет запрос к Admin Module)
    # TODO: Реализовать получение данных из file registry
    try:
        # Placeholder данные для MVP тестирования
        # В production эти данные придут из Admin Module /api/v1/files/{file_id}
        from app.core.config import settings

        source_se_id = "storage-element-01"  # TODO: из file registry
        source_se_endpoint = settings.storage_element.base_url  # TODO: из file registry
        file_size = 0  # TODO: из file registry
        checksum = ""  # TODO: из file registry

        response = await finalize_svc.finalize_file(
            file_id=file_id,
            source_se_id=source_se_id,
            source_se_endpoint=source_se_endpoint,
            file_size=file_size,
            checksum=checksum,
            request=request,
            user_id=user.user_id
        )

        logger.info(
            "Finalize transaction started",
            extra={
                "file_id": str(file_id),
                "transaction_id": str(response.transaction_id),
                "status": response.status.value,
                "user_id": user.user_id
            }
        )

        return response

    except ValueError as e:
        # Файл не найден или не temporary
        logger.warning(
            "Finalize validation failed",
            extra={
                "file_id": str(file_id),
                "error": str(e),
                "user_id": user.user_id
            }
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    except Exception as e:
        logger.error(
            "Finalize failed",
            extra={
                "file_id": str(file_id),
                "error": str(e),
                "user_id": user.user_id
            }
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Finalization failed: {str(e)}"
        )


@router.get(
    "/{transaction_id}/status",
    response_model=FinalizeStatus,
    summary="Get Finalize Transaction Status",
    description="""
    Получение статуса транзакции финализации.

    **Sprint 15: Polling endpoint для отслеживания Two-Phase Commit**

    Используйте этот endpoint для отслеживания прогресса финализации:
    - **COPYING** (25%): Копирование файла на target SE
    - **COPIED** (50%): Файл скопирован, ожидание верификации
    - **VERIFYING** (75%): Проверка checksum
    - **COMPLETED** (100%): Успешная финализация
    - **FAILED** (0%): Ошибка, см. error_message
    - **ROLLED_BACK** (0%): Транзакция откачена

    **Рекомендуемый polling interval**: 1-2 секунды
    """
)
async def get_finalize_status(
    transaction_id: UUID,
    user: Annotated[UserContext, Depends(get_current_user)],
    finalize_svc: Annotated[FinalizeService, Depends(get_finalize_svc)]
) -> FinalizeStatus:
    """
    Получение статуса транзакции финализации.

    Args:
        transaction_id: UUID транзакции
        user: Текущий пользователь (из JWT)

    Returns:
        FinalizeStatus: Текущий статус транзакции с progress_percent

    Raises:
        HTTPException 404: Транзакция не найдена
    """
    logger.debug(
        "Finalize status request",
        extra={
            "transaction_id": str(transaction_id),
            "user_id": user.user_id
        }
    )

    status_result = await finalize_svc.get_transaction_status(transaction_id)

    if not status_result:
        logger.warning(
            "Finalize transaction not found",
            extra={
                "transaction_id": str(transaction_id),
                "user_id": user.user_id
            }
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction {transaction_id} not found"
        )

    return status_result
