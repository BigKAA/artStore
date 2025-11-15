"""
Ingester Module - Upload Service.

Сервис для загрузки файлов в Storage Element.
MVP реализация без Saga и Circuit Breaker (будет добавлено позже).
"""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

import httpx
from fastapi import UploadFile

from app.core.config import settings
from app.core.exceptions import (
    StorageElementUnavailableException,
    FileSizeLimitExceededException
)
from app.schemas.upload import (
    UploadRequest,
    UploadResponse,
    StorageMode,
    CompressionAlgorithm
)

logger = logging.getLogger(__name__)


class UploadService:
    """
    Сервис загрузки файлов.

    Отвечает за:
    - Валидацию файлов
    - Коммуникацию со Storage Element
    - Обработку ошибок загрузки
    """

    def __init__(self):
        """Инициализация сервиса с HTTP клиентом."""
        self._client: Optional[httpx.AsyncClient] = None
        self._max_file_size = 1024 * 1024 * 1024  # 1GB по умолчанию

    async def _get_client(self) -> httpx.AsyncClient:
        """
        Получить HTTP клиент (создает если не существует).

        Returns:
            httpx.AsyncClient: Async HTTP клиент
        """
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=settings.storage_element.base_url,
                timeout=settings.storage_element.timeout,
                limits=httpx.Limits(
                    max_connections=settings.storage_element.connection_pool_size
                )
            )
            logger.info(
                "HTTP client initialized",
                extra={"base_url": settings.storage_element.base_url}
            )

        return self._client

    async def close(self):
        """Закрытие HTTP клиента."""
        if self._client:
            await self._client.aclose()
            self._client = None  # Reset client after closing
            logger.info("HTTP client closed")

    async def upload_file(
        self,
        file: UploadFile,
        request: UploadRequest,
        user_id: str,
        username: str
    ) -> UploadResponse:
        """
        Загрузка файла в Storage Element.

        Args:
            file: Загружаемый файл
            request: Параметры загрузки
            user_id: ID пользователя
            username: Имя пользователя

        Returns:
            UploadResponse: Результат загрузки

        Raises:
            StorageElementUnavailableException: Storage Element недоступен
            FileSizeLimitExceededException: Превышен лимит размера
        """
        logger.info(
            "Starting file upload",
            extra={
                "uploaded_filename": file.filename,
                "content_type": file.content_type,
                "storage_mode": request.storage_mode.value,
                "user_id": user_id
            }
        )

        # Чтение содержимого файла
        content = await file.read()
        file_size = len(content)

        # Проверка размера файла
        if file_size > self._max_file_size:
            raise FileSizeLimitExceededException(
                f"File size {file_size} exceeds limit {self._max_file_size}"
            )

        # Расчет checksum
        checksum = hashlib.sha256(content).hexdigest()

        # Формирование данных для Storage Element
        files = {
            'file': (file.filename, content, file.content_type or 'application/octet-stream')
        }

        data = {
            'description': request.description or '',
            'uploaded_by_username': username,
            'uploaded_by_id': user_id
        }

        # TODO: Добавить сжатие если request.compress=True
        # TODO: Добавить Circuit Breaker pattern
        # TODO: Добавить retry logic

        try:
            client = await self._get_client()

            # Отправка запроса в Storage Element
            response = await client.post(
                "/api/v1/files/upload",
                files=files,
                data=data
            )

            response.raise_for_status()
            result = response.json()

            logger.info(
                "File uploaded successfully",
                extra={
                    "file_id": result.get('id'),
                    "uploaded_filename": file.filename,
                    "file_size": file_size,
                    "user_id": user_id
                }
            )

            # Формирование ответа
            return UploadResponse(
                file_id=UUID(result['id']),
                original_filename=file.filename or "unknown",
                storage_filename=result.get('storage_filename', ''),
                file_size=file_size,
                compressed=request.compress,
                compression_ratio=None,  # TODO: calculate if compressed
                checksum=checksum,
                uploaded_at=datetime.now(timezone.utc),
                storage_element_url=settings.storage_element.base_url
            )

        except httpx.HTTPStatusError as e:
            logger.error(
                "Storage Element HTTP error",
                extra={
                    "status_code": e.response.status_code,
                    "error": str(e)
                }
            )
            raise StorageElementUnavailableException(
                f"Storage Element returned error: {e.response.status_code}"
            )

        except httpx.RequestError as e:
            logger.error(
                "Storage Element connection error",
                extra={"error": str(e)}
            )
            raise StorageElementUnavailableException(
                f"Cannot connect to Storage Element: {str(e)}"
            )


# Singleton instance
upload_service = UploadService()
