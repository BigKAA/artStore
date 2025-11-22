"""
Query Module - Search API Router.

REST API endpoints для поиска файлов:
- POST /api/search - Поиск файлов с фильтрацией
- GET /api/search/{file_id} - Получение метаданных файла
"""

import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, DatabaseSession
from app.schemas.search import SearchRequest, SearchResponse, FileMetadataResponse
from app.services.search_service import SearchService
from app.services.cache_service import cache_service
from app.db.models import FileMetadata
from app.core.exceptions import (
    SearchException,
    InvalidSearchQueryException,
    SearchTimeoutException
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/search", tags=["Search"])


@router.post("", response_model=SearchResponse)
async def search_files(
    search_request: SearchRequest,
    db: DatabaseSession,
    current_user: CurrentUser
) -> SearchResponse:
    """
    Поиск файлов с Full-Text Search и фильтрацией.

    Поддерживает:
    - Full-Text Search (PostgreSQL GIN индексы)
    - Partial match (LIKE queries)
    - Exact match
    - Фильтрация по тегам, размеру, дате
    - Пагинация и сортировка

    Args:
        search_request: Параметры поиска
        db: Database session
        current_user: Authenticated user context

    Returns:
        SearchResponse: Результаты поиска с метаданными

    Raises:
        HTTPException 400: Некорректные параметры поиска
        HTTPException 401: Не авторизован
        HTTPException 500: Ошибка сервера
    """
    try:
        # NOTE: Removed criteria check to allow listing all files in File Manager
        # if not search_request.has_search_criteria():
        #     raise InvalidSearchQueryException(
        #         "At least one search criteria required",
        #         details={"request": search_request.dict()}
        #     )

        # Инициализация SearchService
        search_service = SearchService(db)

        # Выполнение поиска
        results = await search_service.search_files(search_request)

        logger.info(
            "Search completed",
            extra={
                "user_id": current_user.user_id,
                "username": current_user.username,
                "mode": search_request.mode.value,
                "results_count": len(results.results),
                "total_count": results.total_count
            }
        )

        return results

    except InvalidSearchQueryException as e:
        logger.warning(
            "Invalid search query",
            extra={"error": str(e), "user_id": current_user.user_id}
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    except SearchTimeoutException as e:
        logger.error(
            "Search timeout",
            extra={"error": str(e), "user_id": current_user.user_id}
        )
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Search operation timed out"
        )

    except SearchException as e:
        logger.error(
            "Search error",
            extra={"error": str(e), "user_id": current_user.user_id}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Search operation failed"
        )


@router.get("/{file_id}", response_model=FileMetadataResponse)
async def get_file_metadata(
    file_id: str,
    db: DatabaseSession,
    current_user: CurrentUser
) -> FileMetadataResponse:
    """
    Получение метаданных файла по ID.

    Использует multi-level caching для быстрого доступа.

    Args:
        file_id: UUID файла
        db: Database session
        current_user: Authenticated user context

    Returns:
        FileMetadataResponse: Метаданные файла

    Raises:
        HTTPException 404: Файл не найден
        HTTPException 401: Не авторизован
    """
    # Проверка кеша
    cached_metadata = cache_service.get_file_metadata(file_id)
    if cached_metadata:
        logger.debug(
            "File metadata from cache",
            extra={"file_id": file_id, "user_id": current_user.user_id}
        )
        return FileMetadataResponse(**cached_metadata)

    # Запрос из БД
    try:
        query = select(FileMetadata).where(FileMetadata.id == file_id)
        result = await db.execute(query)
        file_metadata = result.scalar_one_or_none()

        if not file_metadata:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"File not found: {file_id}"
            )

        # Конвертация в response schema
        response = FileMetadataResponse(
            id=file_metadata.id,
            filename=file_metadata.filename,
            storage_filename=file_metadata.storage_filename,
            file_size=file_metadata.file_size,
            mime_type=file_metadata.mime_type,
            sha256_hash=file_metadata.sha256_hash,
            username=file_metadata.username,
            tags=file_metadata.tags or [],
            description=file_metadata.description,
            created_at=file_metadata.created_at,
            updated_at=file_metadata.updated_at,
            storage_element_id=file_metadata.storage_element_id,
            relevance_score=None
        )

        # Кеширование метаданных
        cache_service.set_file_metadata(file_id, response.dict())

        logger.info(
            "File metadata retrieved",
            extra={
                "file_id": file_id,
                "filename": file_metadata.filename,
                "user_id": current_user.user_id
            }
        )

        return response

    except HTTPException:
        raise

    except Exception as e:
        logger.error(
            "Failed to retrieve file metadata",
            extra={"file_id": file_id, "error": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve file metadata"
        )
