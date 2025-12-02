"""
Ingester Module - Upload Endpoints.

API endpoints для загрузки файлов.

Sprint 15: Добавлена поддержка Retention Policy:
- retention_policy: temporary (Edit SE) или permanent (RW SE)
- ttl_days: TTL для temporary файлов (default: 30 дней)
- Регистрация файла в Admin Module file registry
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import UserContext, jwt_validator
from app.core.exceptions import (
    InvalidTokenException,
    TokenExpiredException,
    AuthenticationException
)
from app.schemas.upload import (
    UploadRequest,
    UploadResponse,
    StorageMode,
    CompressionAlgorithm,
    RetentionPolicy,  # Sprint 15
    DEFAULT_TTL_DAYS  # Sprint 15
)
from app.services.upload_service import UploadService

logger = logging.getLogger(__name__)

router = APIRouter()
security = HTTPBearer()


def get_upload_service() -> UploadService:
    """
    Dependency для получения upload service.

    Returns:
        UploadService instance из main.py
    """
    from app.main import upload_service
    return upload_service


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]
) -> UserContext:
    """
    Dependency для получения текущего пользователя из JWT токена.

    Args:
        credentials: Bearer token credentials

    Returns:
        UserContext: Контекст пользователя

    Raises:
        HTTPException: 401 если токен невалидный или истек
    """
    try:
        user = jwt_validator.validate_token(credentials.credentials)
        return user
    except (InvalidTokenException, TokenExpiredException, AuthenticationException) as e:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"}
        )


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload File",
    description="""
    Загрузка файла в Storage Element с поддержкой Retention Policy.

    **Sprint 15: Retention Policy**

    Используйте `retention_policy` для определения типа хранения:
    - `temporary`: Файлы для работы (drafts). Хранятся в Edit SE. Автоматически удаляются через TTL.
    - `permanent`: Финализированные файлы. Хранятся в RW SE. Без автоматического удаления.

    **TTL для temporary файлов:**
    - По умолчанию: 30 дней
    - Минимум: 1 день
    - Максимум: 365 дней

    **Workflow:**
    1. Upload с `retention_policy=temporary` → файл в Edit SE
    2. Работа над документом...
    3. POST /finalize/{file_id} → Two-Phase Commit → файл копируется в RW SE
    4. Оригинал в Edit SE удаляется через GC (+24h safety margin)
    """
)
async def upload_file(
    file: Annotated[UploadFile, File(description="Файл для загрузки")],
    user: Annotated[UserContext, Depends(get_current_user)],
    upload_svc: Annotated[UploadService, Depends(get_upload_service)],
    description: Annotated[str | None, Form()] = None,
    # Sprint 15: Retention Policy parameters
    retention_policy: Annotated[str, Form(description="Политика хранения: temporary или permanent")] = "temporary",
    ttl_days: Annotated[int | None, Form(description="TTL в днях для temporary файлов (1-365)")] = None,
    # Legacy parameter (deprecated)
    storage_mode: Annotated[str | None, Form(description="[DEPRECATED] Используйте retention_policy")] = None,
    compress: Annotated[bool, Form()] = False,
    compression_algorithm: Annotated[str, Form()] = "gzip",
    # Sprint 15: User metadata
    metadata: Annotated[str | None, Form(description="JSON метаданные (опционально)")] = None
) -> UploadResponse:
    """
    Загрузка файла в Storage Element.

    Sprint 15: Добавлена поддержка retention_policy и ttl_days.

    Args:
        file: Загружаемый файл (multipart/form-data)
        user: Текущий пользователь (из JWT)
        description: Описание файла (опционально)
        retention_policy: Политика хранения (temporary/permanent)
        ttl_days: TTL в днях для temporary файлов (1-365, default: 30)
        storage_mode: [DEPRECATED] Используйте retention_policy
        compress: Включить сжатие
        compression_algorithm: Алгоритм сжатия (gzip или brotli)
        metadata: JSON метаданные (опционально)

    Returns:
        UploadResponse: Результат загрузки с file_id, retention_policy и ttl_expires_at

    Raises:
        HTTPException: 400 при ошибке валидации
        HTTPException: 503 если Storage Element недоступен
    """
    # Sprint 15: Parse metadata JSON if provided
    parsed_metadata = None
    if metadata:
        import json
        try:
            parsed_metadata = json.loads(metadata)
        except json.JSONDecodeError:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON in metadata field"
            )

    logger.info(
        "Upload request received",
        extra={
            "file_name": file.filename,
            "user_id": user.user_id,
            "username": user.username,
            "retention_policy": retention_policy,
            "ttl_days": ttl_days
        }
    )

    # Sprint 15: Создание request object с retention_policy
    # Если передан legacy storage_mode, логируем предупреждение
    if storage_mode:
        logger.warning(
            "Deprecated storage_mode parameter used, please use retention_policy",
            extra={"storage_mode": storage_mode, "user_id": user.user_id}
        )

    upload_request = UploadRequest(
        description=description,
        retention_policy=RetentionPolicy(retention_policy),
        ttl_days=ttl_days if ttl_days else DEFAULT_TTL_DAYS,
        compress=compress,
        compression_algorithm=CompressionAlgorithm(compression_algorithm),
        metadata=parsed_metadata
    )

    # Загрузка файла
    result = await upload_svc.upload_file(
        file=file,
        request=upload_request,
        user_id=user.user_id,
        username=user.username
    )

    logger.info(
        "Upload completed successfully",
        extra={
            "file_id": str(result.file_id),
            "uploaded_filename": file.filename,
            "user_id": user.user_id,
            "retention_policy": result.retention_policy.value,
            "ttl_expires_at": str(result.ttl_expires_at) if result.ttl_expires_at else None
        }
    )

    return result


@router.get(
    "/",
    summary="List Uploads",
    description="Получить список загруженных файлов (TODO)"
)
async def list_uploads(
    user: Annotated[UserContext, Depends(get_current_user)]
):
    """
    Получить список загруженных файлов.

    TODO: Реализовать в следующих итерациях.
    Требует integration с Storage Element для получения списка файлов.
    """
    return {"message": "Not implemented yet", "user": user.username}
