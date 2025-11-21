"""
Ingester Module - Upload Endpoints.

API endpoints для загрузки файлов.
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
from app.schemas.upload import UploadRequest, UploadResponse, StorageMode, CompressionAlgorithm
from app.services.upload_service import upload_service

logger = logging.getLogger(__name__)

router = APIRouter()
security = HTTPBearer()


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
    description="Загрузка файла в Storage Element"
)
async def upload_file(
    file: Annotated[UploadFile, File(description="Файл для загрузки")],
    user: Annotated[UserContext, Depends(get_current_user)],
    description: Annotated[str | None, Form()] = None,
    storage_mode: Annotated[str, Form()] = "edit",
    compress: Annotated[bool, Form()] = False,
    compression_algorithm: Annotated[str, Form()] = "gzip"
) -> UploadResponse:
    """
    Загрузка файла в Storage Element.

    Args:
        file: Загружаемый файл (multipart/form-data)
        user: Текущий пользователь (из JWT)
        description: Описание файла (опционально)
        storage_mode: Целевой режим storage (edit или rw)
        compress: Включить сжатие
        compression_algorithm: Алгоритм сжатия (gzip или brotli)

    Returns:
        UploadResponse: Результат загрузки с file_id и метаданными

    Raises:
        HTTPException: 400 при ошибке валидации
        HTTPException: 503 если Storage Element недоступен
    """
    logger.info(
        "Upload request received",
        extra={
            "file_name": file.filename,
            "user_id": user.user_id,
            "username": user.username,
            "storage_mode": storage_mode
        }
    )

    # Создание request object
    upload_request = UploadRequest(
        description=description,
        storage_mode=StorageMode(storage_mode),
        compress=compress,
        compression_algorithm=CompressionAlgorithm(compression_algorithm)
    )

    # Загрузка файла
    result = await upload_service.upload_file(
        file=file,
        request=upload_request,
        user_id=user.user_id,
        username=user.username
    )

    logger.info(
        "Upload completed successfully",
        extra={
            "file_id": str(result.file_id),
            "filename": file.filename,
            "user_id": user.user_id
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
