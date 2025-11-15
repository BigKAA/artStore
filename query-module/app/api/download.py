"""
Query Module - Download API Router.

REST API endpoints для скачивания файлов:
- GET /api/download/{file_id} - Скачивание файла
- GET /api/download/{file_id}/metadata - Метаданные для скачивания
- GET /api/download/{file_id}/progress - Прогресс скачивания
"""

import logging

from fastapi import APIRouter, HTTPException, status, Header
from fastapi.responses import StreamingResponse
from typing import Annotated, Optional

from app.api.dependencies import CurrentUser
from app.services.download_service import download_service
from app.services.cache_service import cache_service
from app.schemas.download import (
    DownloadMetadata,
    DownloadProgress,
    RangeRequest
)
from app.core.exceptions import (
    FileNotFoundException,
    StorageElementUnavailableException,
    RangeNotSatisfiableException,
    DownloadException
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/download", tags=["Download"])


@router.get("/{file_id}/metadata", response_model=DownloadMetadata)
async def get_download_metadata(
    file_id: str,
    current_user: CurrentUser
) -> DownloadMetadata:
    """
    Получение метаданных файла для скачивания.

    Возвращает информацию необходимую для инициализации скачивания:
    - Размер файла
    - SHA256 хеш для верификации
    - Storage Element URL
    - Поддержка resumable downloads

    Args:
        file_id: UUID файла
        current_user: Authenticated user context

    Returns:
        DownloadMetadata: Метаданные для скачивания

    Raises:
        HTTPException 404: Файл не найден
        HTTPException 503: Storage Element недоступен
    """
    try:
        # Получение метаданных из кеша
        cached_metadata = cache_service.get_file_metadata(file_id)
        if not cached_metadata:
            raise FileNotFoundException(
                f"File metadata not found: {file_id}",
                details={"file_id": file_id}
            )

        storage_element_url = cached_metadata.get("storage_element_url")
        if not storage_element_url:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Storage Element URL not configured"
            )

        # Получение метаданных для скачивания
        metadata = await download_service.get_file_metadata(
            file_id=file_id,
            storage_element_url=storage_element_url
        )

        logger.info(
            "Download metadata retrieved",
            extra={
                "file_id": file_id,
                "filename": metadata.filename,
                "user_id": current_user.user_id
            }
        )

        return metadata

    except FileNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

    except StorageElementUnavailableException as e:
        logger.error(
            "Storage Element unavailable",
            extra={"file_id": file_id, "error": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage Element unavailable"
        )


@router.get("/{file_id}")
async def download_file(
    file_id: str,
    current_user: CurrentUser,
    range_header: Annotated[Optional[str], Header(alias="Range")] = None
):
    """
    Скачивание файла с поддержкой resumable downloads.

    Поддерживает HTTP Range requests для возобновления прерванных скачиваний.
    Использует streaming для эффективной передачи больших файлов.

    Args:
        file_id: UUID файла
        current_user: Authenticated user context
        range_header: HTTP Range header (optional)

    Returns:
        StreamingResponse: File content stream

    Raises:
        HTTPException 404: Файл не найден
        HTTPException 416: Range not satisfiable
        HTTPException 503: Storage Element недоступен
    """
    try:
        # Получение метаданных из кеша
        cached_metadata = cache_service.get_file_metadata(file_id)
        if not cached_metadata:
            raise FileNotFoundException(
                f"File metadata not found: {file_id}",
                details={"file_id": file_id}
            )

        storage_element_url = cached_metadata.get("storage_element_url")
        filename = cached_metadata.get("filename", "download")

        # Парсинг Range header
        range_request = None
        if range_header:
            try:
                # Формат: "bytes=start-end" или "bytes=start-"
                range_value = range_header.replace("bytes=", "")
                parts = range_value.split("-")
                start = int(parts[0])
                end = int(parts[1]) if parts[1] else None
                range_request = RangeRequest(start=start, end=end)

                logger.debug(
                    "Range request",
                    extra={
                        "file_id": file_id,
                        "range": range_header,
                        "user_id": current_user.user_id
                    }
                )

            except (ValueError, IndexError):
                logger.warning(
                    "Invalid range header",
                    extra={"range": range_header, "file_id": file_id}
                )
                # Игнорируем некорректный Range header

        # Streaming download
        file_stream = download_service.download_file_stream(
            file_id=file_id,
            storage_element_url=storage_element_url,
            range_request=range_request
        )

        # Response headers
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Accept-Ranges": "bytes"
        }

        if range_request:
            # Partial content response
            status_code = status.HTTP_206_PARTIAL_CONTENT
        else:
            status_code = status.HTTP_200_OK

        logger.info(
            "File download started",
            extra={
                "file_id": file_id,
                "filename": filename,
                "resumed": range_request is not None,
                "user_id": current_user.user_id
            }
        )

        return StreamingResponse(
            file_stream,
            status_code=status_code,
            headers=headers,
            media_type="application/octet-stream"
        )

    except FileNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

    except RangeNotSatisfiableException as e:
        raise HTTPException(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            detail=str(e)
        )

    except StorageElementUnavailableException as e:
        logger.error(
            "Storage Element unavailable",
            extra={"file_id": file_id, "error": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage Element unavailable"
        )

    except DownloadException as e:
        logger.error(
            "Download failed",
            extra={"file_id": file_id, "error": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Download failed"
        )
