"""
Files API Endpoints - операции с файлами.

Endpoints для загрузки, скачивания, удаления и поиска файлов.
Все операции защищены JWT аутентификацией.
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, OperatorUser, get_db
from app.core.config import settings, StorageMode
from app.core.exceptions import FileOperationException, StorageException
from app.models.file_metadata import FileMetadata
from app.services.file_service import FileService

logger = logging.getLogger(__name__)

router = APIRouter()


# Pydantic Models для responses
class FileMetadataResponse(BaseModel):
    """Модель ответа с метаданными файла"""
    file_id: UUID
    original_filename: str
    storage_filename: str
    file_size: int
    content_type: str
    created_at: str
    created_by_username: str
    created_by_fullname: Optional[str] = None
    description: Optional[str] = None
    version: Optional[str] = None
    storage_path: str
    checksum: str

    class Config:
        from_attributes = True


class FileUploadResponse(BaseModel):
    """Модель ответа при загрузке файла"""
    file_id: UUID
    original_filename: str
    file_size: int
    checksum: str
    message: str


class FileListResponse(BaseModel):
    """Модель ответа со списком файлов"""
    total: int
    files: list[FileMetadataResponse]


class FileUpdateRequest(BaseModel):
    """Модель запроса на обновление метаданных"""
    description: Optional[str] = None
    version: Optional[str] = None
    metadata: Optional[dict] = None


@router.post(
    "/upload",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Загрузить файл",
    description="Загрузить новый файл в хранилище. Требуется аутентификация."
)
async def upload_file(
    file: UploadFile = File(..., description="Файл для загрузки"),
    description: Optional[str] = Form(None, description="Описание содержимого"),
    version: Optional[str] = Form(None, description="Версия документа"),
    user: CurrentUser = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """
    Загрузить файл в хранилище.

    Процесс:
    - Валидация режима хранилища (edit/rw)
    - Создание FileService
    - Загрузка файла через Consistency Protocol (WAL → Storage → Attr → DB → Commit)
    - Возврат метаданных созданного файла

    Args:
        file: Загружаемый файл (multipart/form-data)
        description: Описание содержимого (опционально)
        version: Версия документа (опционально)
        user: Текущий пользователь из JWT
        db: Database session

    Returns:
        FileUploadResponse: Метаданные загруженного файла

    Raises:
        HTTPException 400: Режим хранилища не разрешает загрузку
        HTTPException 500: Ошибка загрузки файла
    """
    # Проверка режима хранилища
    if settings.app.mode not in [StorageMode.EDIT, StorageMode.RW]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File upload not allowed in {settings.app.mode.value} mode"
        )

    try:
        # Инициализация File Service
        file_service = FileService(db)

        # Создание файла через координированный процесс
        file_id = await file_service.create_file(
            file_data=file.file,
            original_filename=file.filename,
            content_type=file.content_type or "application/octet-stream",
            user_id=user.sub,
            username=user.username,
            description=description,
            version=version
        )

        # Получение метаданных созданного файла
        metadata = await file_service.get_file_metadata(file_id)

        logger.info(
            "File uploaded successfully",
            extra={
                "file_id": str(file_id),
                "filename": file.filename,
                "user_id": user.sub
            }
        )

        return FileUploadResponse(
            file_id=file_id,
            original_filename=metadata.original_filename,
            file_size=metadata.file_size,
            checksum=metadata.checksum,
            message="File uploaded successfully"
        )

    except FileOperationException as e:
        logger.error(
            f"File upload failed: {e.message}",
            extra={"error_code": e.error_code, "details": e.details}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=e.message
        )
    except Exception as e:
        logger.error(f"Unexpected error during file upload: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload file"
        )


@router.get(
    "/{file_id}",
    response_model=FileMetadataResponse,
    summary="Получить метаданные файла",
    description="Получить метаданные файла по ID"
)
async def get_file_metadata(
    file_id: UUID,
    user: CurrentUser = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """
    Получить метаданные файла.

    Args:
        file_id: UUID файла
        user: Текущий пользователь из JWT
        db: Database session

    Returns:
        FileMetadataResponse: Метаданные файла

    Raises:
        HTTPException 404: Файл не найден
    """
    try:
        file_service = FileService(db)
        metadata = await file_service.get_file_metadata(file_id)

        if not metadata:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"File {file_id} not found"
            )

        return FileMetadataResponse(
            file_id=metadata.file_id,
            original_filename=metadata.original_filename,
            storage_filename=metadata.storage_filename,
            file_size=metadata.file_size,
            content_type=metadata.content_type,
            created_at=metadata.created_at.isoformat(),
            created_by_username=metadata.created_by_username,
            created_by_fullname=metadata.created_by_fullname,
            description=metadata.description,
            version=metadata.version,
            storage_path=metadata.storage_path,
            checksum=metadata.checksum
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get file metadata: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve file metadata"
        )


@router.get(
    "/{file_id}/download",
    summary="Скачать файл",
    description="Скачать файл по ID (streaming)",
    response_class=StreamingResponse
)
async def download_file(
    file_id: UUID,
    user: CurrentUser = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """
    Скачать файл (streaming).

    Args:
        file_id: UUID файла
        user: Текущий пользователь из JWT
        db: Database session

    Returns:
        StreamingResponse: Streaming download файла

    Raises:
        HTTPException 404: Файл не найден
    """
    try:
        file_service = FileService(db)

        # Получение метаданных для content-type и filename
        metadata = await file_service.get_file_metadata(file_id)

        if not metadata:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"File {file_id} not found"
            )

        # Streaming generator
        async def file_stream():
            async for chunk in file_service.get_file(file_id):
                yield chunk

        logger.info(
            "File download started",
            extra={
                "file_id": str(file_id),
                "filename": metadata.original_filename,
                "user_id": user.sub
            }
        )

        return StreamingResponse(
            file_stream(),
            media_type=metadata.content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{metadata.original_filename}"',
                "Content-Length": str(metadata.file_size)
            }
        )

    except HTTPException:
        raise
    except FileOperationException as e:
        if e.error_code == "FILE_NOT_FOUND":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=e.message
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=e.message
        )
    except Exception as e:
        logger.error(f"Failed to download file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to download file"
        )


@router.delete(
    "/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить файл",
    description="Удалить файл (только edit mode, требуется роль operator/admin)"
)
async def delete_file(
    file_id: UUID,
    operator: OperatorUser = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """
    Удалить файл из хранилища.

    Требует:
    - Режим хранилища EDIT
    - Роль OPERATOR или ADMIN

    Args:
        file_id: UUID файла
        operator: Оператор или администратор из JWT
        db: Database session

    Raises:
        HTTPException 400: Режим не разрешает удаление
        HTTPException 403: Недостаточно прав
        HTTPException 404: Файл не найден
    """
    # Проверка режима хранилища
    if settings.app.mode != StorageMode.EDIT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File deletion not allowed in {settings.app.mode.value} mode. Only EDIT mode allows deletion."
        )

    try:
        file_service = FileService(db)

        await file_service.delete_file(
            file_id=file_id,
            user_id=operator.sub
        )

        logger.info(
            "File deleted successfully",
            extra={
                "file_id": str(file_id),
                "user_id": operator.sub
            }
        )

        return None  # 204 No Content

    except FileOperationException as e:
        if e.error_code == "FILE_NOT_FOUND":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=e.message
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=e.message
        )
    except Exception as e:
        logger.error(f"Failed to delete file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete file"
        )


@router.patch(
    "/{file_id}",
    response_model=FileMetadataResponse,
    summary="Обновить метаданные файла",
    description="Обновить описание, версию или дополнительные метаданные"
)
async def update_file_metadata(
    file_id: UUID,
    update_data: FileUpdateRequest,
    user: CurrentUser = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """
    Обновить метаданные файла.

    Args:
        file_id: UUID файла
        update_data: Новые значения метаданных
        user: Текущий пользователь из JWT
        db: Database session

    Returns:
        FileMetadataResponse: Обновленные метаданные

    Raises:
        HTTPException 400: Режим не разрешает обновление
        HTTPException 404: Файл не найден
    """
    # Проверка режима хранилища
    if settings.app.mode not in [StorageMode.EDIT, StorageMode.RW]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Metadata update not allowed in {settings.app.mode.value} mode"
        )

    try:
        file_service = FileService(db)

        await file_service.update_file_metadata(
            file_id=file_id,
            user_id=user.sub,
            description=update_data.description,
            version=update_data.version,
            metadata=update_data.metadata
        )

        # Получение обновленных метаданных
        metadata = await file_service.get_file_metadata(file_id)

        logger.info(
            "File metadata updated successfully",
            extra={
                "file_id": str(file_id),
                "user_id": user.sub
            }
        )

        return FileMetadataResponse(
            file_id=metadata.file_id,
            original_filename=metadata.original_filename,
            storage_filename=metadata.storage_filename,
            file_size=metadata.file_size,
            content_type=metadata.content_type,
            created_at=metadata.created_at.isoformat(),
            created_by_username=metadata.created_by_username,
            created_by_fullname=metadata.created_by_fullname,
            description=metadata.description,
            version=metadata.version,
            storage_path=metadata.storage_path,
            checksum=metadata.checksum
        )

    except FileOperationException as e:
        if e.error_code == "FILE_NOT_FOUND":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=e.message
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=e.message
        )
    except Exception as e:
        logger.error(f"Failed to update file metadata: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update file metadata"
        )


@router.get(
    "/",
    response_model=FileListResponse,
    summary="Список файлов",
    description="Получить список файлов с пагинацией"
)
async def list_files(
    skip: int = 0,
    limit: int = 100,
    user: CurrentUser = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """
    Получить список файлов с пагинацией.

    Args:
        skip: Количество файлов для пропуска (pagination offset)
        limit: Максимальное количество файлов (max 100)
        user: Текущий пользователь из JWT
        db: Database session

    Returns:
        FileListResponse: Список файлов с общим количеством
    """
    try:
        # Ограничение limit
        if limit > 100:
            limit = 100

        # Получение общего количества
        count_result = await db.execute(
            select(FileMetadata).count()
        )
        total = count_result.scalar()

        # Получение файлов с пагинацией
        result = await db.execute(
            select(FileMetadata)
            .order_by(FileMetadata.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        files = result.scalars().all()

        # Преобразование в response models
        file_responses = [
            FileMetadataResponse(
                file_id=f.file_id,
                original_filename=f.original_filename,
                storage_filename=f.storage_filename,
                file_size=f.file_size,
                content_type=f.content_type,
                created_at=f.created_at.isoformat(),
                created_by_username=f.created_by_username,
                created_by_fullname=f.created_by_fullname,
                description=f.description,
                version=f.version,
                storage_path=f.storage_path,
                checksum=f.checksum
            )
            for f in files
        ]

        return FileListResponse(
            total=total,
            files=file_responses
        )

    except Exception as e:
        logger.error(f"Failed to list files: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve file list"
        )
