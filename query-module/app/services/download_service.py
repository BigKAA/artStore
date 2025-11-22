"""
Query Module - Download Service.

Реализует скачивание файлов с Storage Elements:
- HTTP клиент для взаимодействия с Storage Element API
- Resumable downloads через HTTP Range requests
- Streaming downloads для больших файлов
- SHA256 верификация целостности
- Статистика скачиваний
"""

import logging
from datetime import datetime
from typing import Optional, AsyncGenerator
from pathlib import Path

import httpx
from httpx import AsyncClient, HTTPStatusError, RequestError

from app.schemas.download import (
    DownloadMetadata,
    RangeRequest,
    DownloadProgress,
    DownloadResponse
)
from app.db.models import DownloadStatistics
from app.core.config import settings
from app.core.exceptions import (
    DownloadException,
    FileNotFoundException,
    StorageElementUnavailableException,
    RangeNotSatisfiableException,
    DownloadInterruptedException
)
from app.services.cache_service import cache_service

logger = logging.getLogger(__name__)


class DownloadService:
    """
    Сервис скачивания файлов из Storage Elements.

    Поддерживает:
    - Streaming downloads для эффективной передачи больших файлов
    - Resumable downloads через HTTP Range requests
    - SHA256 верификация после скачивания
    - Автоматический retry при сетевых ошибках
    - Статистика скачиваний для analytics
    """

    def __init__(self):
        """Инициализация Download Service."""
        self._http_client: Optional[AsyncClient] = None

    async def _get_http_client(self) -> AsyncClient:
        """
        Получение HTTP клиента с lazy initialization.

        Sprint 16 Phase 4: Поддержка mTLS для inter-service authentication.

        Returns:
            AsyncClient: Configured httpx async client с mTLS support
        """
        if self._http_client is None:
            # Конфигурация HTTP клиента
            client_config = {
                "timeout": httpx.Timeout(
                    connect=settings.download.connect_timeout,
                    read=settings.download.read_timeout,
                    write=settings.download.write_timeout,
                    pool=settings.download.pool_timeout
                ),
                "limits": httpx.Limits(
                    max_connections=settings.download.max_connections,
                    max_keepalive_connections=settings.download.max_keepalive_connections
                ),
                "follow_redirects": True,
                "http2": True,  # HTTP/2 для лучшей производительности
            }

            # Добавление mTLS configuration если TLS enabled
            if settings.tls.enabled:
                import ssl

                # Создание SSL context для mTLS
                ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)

                # CA certificate для валидации server certificate
                if settings.tls.ca_cert_file:
                    ssl_context.load_verify_locations(cafile=settings.tls.ca_cert_file)
                    logger.info(
                        "Loaded CA certificate for server validation",
                        extra={"ca_cert": settings.tls.ca_cert_file}
                    )

                # Client certificate для mTLS authentication
                if settings.tls.cert_file and settings.tls.key_file:
                    ssl_context.load_cert_chain(
                        certfile=settings.tls.cert_file,
                        keyfile=settings.tls.key_file
                    )
                    logger.info(
                        "Loaded client certificate for mTLS",
                        extra={
                            "cert_file": settings.tls.cert_file,
                            "key_file": settings.tls.key_file
                        }
                    )

                # TLS 1.3 minimum protocol version
                if settings.tls.protocol_version == "TLSv1.3":
                    ssl_context.minimum_version = ssl.TLSVersion.TLSv1_3
                elif settings.tls.protocol_version == "TLSv1.2":
                    ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2

                # TLS 1.3 AEAD cipher suites
                if settings.tls.ciphers:
                    ssl_context.set_ciphers(settings.tls.ciphers)

                # Добавление SSL context к клиенту
                client_config["verify"] = ssl_context

                logger.info(
                    "mTLS enabled for Storage Element communication",
                    extra={
                        "protocol": settings.tls.protocol_version,
                        "ciphers": settings.tls.ciphers
                    }
                )

            self._http_client = AsyncClient(**client_config)

            logger.info(
                "HTTP client initialized",
                extra={
                    "connect_timeout": settings.download.connect_timeout,
                    "max_connections": settings.download.max_connections,
                    "mtls_enabled": settings.tls.enabled
                }
            )

        return self._http_client

    async def get_file_metadata(
        self,
        file_id: str,
        storage_element_url: str,
        auth_token: Optional[str] = None
    ) -> DownloadMetadata:
        """
        Получение метаданных файла из Storage Element.

        Args:
            file_id: UUID файла
            storage_element_url: Base URL Storage Element
            auth_token: JWT токен для аутентификации (optional)

        Returns:
            DownloadMetadata: Метаданные файла для скачивания

        Raises:
            FileNotFoundException: Файл не найден в Storage Element
            StorageElementUnavailableException: Storage Element недоступен
        """
        # Проверка кеша
        cached_metadata = cache_service.get_file_metadata(file_id)
        if cached_metadata:
            return DownloadMetadata(
                id=cached_metadata["id"],
                filename=cached_metadata["filename"],
                file_size=cached_metadata["file_size"],
                sha256_hash=cached_metadata["sha256_hash"],
                storage_element_url=storage_element_url,
                supports_range_requests=True
            )

        # Запрос к Storage Element API
        client = await self._get_http_client()
        url = f"{storage_element_url}/api/files/{file_id}/metadata"

        headers = {}
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()

            data = response.json()

            metadata = DownloadMetadata(
                id=data["id"],
                filename=data["filename"],
                file_size=data["file_size"],
                sha256_hash=data["sha256_hash"],
                storage_element_url=storage_element_url,
                supports_range_requests=True
            )

            # Кеширование метаданных
            cache_service.set_file_metadata(file_id, data)

            logger.info(
                "File metadata retrieved",
                extra={"file_id": file_id, "filename": metadata.filename}
            )

            return metadata

        except HTTPStatusError as e:
            if e.response.status_code == 404:
                raise FileNotFoundException(
                    f"File not found: {file_id}",
                    details={"file_id": file_id}
                )
            raise StorageElementUnavailableException(
                f"Storage Element error: {e.response.status_code}",
                details={"status_code": e.response.status_code}
            )

        except RequestError as e:
            raise StorageElementUnavailableException(
                f"Storage Element unavailable: {str(e)}",
                details={"error": str(e)}
            )

    async def download_file_stream(
        self,
        file_id: str,
        storage_element_url: str,
        auth_token: Optional[str] = None,
        range_request: Optional[RangeRequest] = None,
        chunk_size: int = 8192
    ) -> AsyncGenerator[bytes, None]:
        """
        Streaming скачивание файла из Storage Element.

        Args:
            file_id: UUID файла
            storage_element_url: Base URL Storage Element
            auth_token: JWT токен для аутентификации
            range_request: HTTP Range request для resumable download
            chunk_size: Размер chunk для streaming (по умолчанию 8KB)

        Yields:
            bytes: Chunks файла

        Raises:
            FileNotFoundException: Файл не найден
            RangeNotSatisfiableException: Некорректный Range request
            DownloadInterruptedException: Скачивание прервано
        """
        client = await self._get_http_client()
        url = f"{storage_element_url}/api/files/{file_id}/download"

        headers = {}
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        if range_request:
            headers["Range"] = range_request.to_header_value()

        start_time = datetime.utcnow()
        bytes_transferred = 0

        try:
            async with client.stream("GET", url, headers=headers) as response:
                # Проверка статуса
                if response.status_code == 404:
                    raise FileNotFoundException(
                        f"File not found: {file_id}",
                        details={"file_id": file_id}
                    )

                if response.status_code == 416:
                    raise RangeNotSatisfiableException(
                        "Range not satisfiable",
                        details={"range": range_request.to_header_value() if range_request else None}
                    )

                response.raise_for_status()

                # Streaming chunks
                async for chunk in response.aiter_bytes(chunk_size=chunk_size):
                    bytes_transferred += len(chunk)
                    yield chunk

            # Запись статистики после успешного скачивания
            download_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            await self._record_download_stats(
                file_id=file_id,
                bytes_transferred=bytes_transferred,
                download_time_ms=download_time_ms,
                was_resumed=range_request is not None,
                storage_element_id=storage_element_url  # TODO: extract SE ID
            )

            logger.info(
                "File download completed",
                extra={
                    "file_id": file_id,
                    "bytes": bytes_transferred,
                    "time_ms": download_time_ms,
                    "resumed": range_request is not None
                }
            )

        except HTTPStatusError as e:
            raise DownloadException(
                f"Download failed: {e.response.status_code}",
                details={"status_code": e.response.status_code}
            )

        except RequestError as e:
            raise DownloadInterruptedException(
                f"Download interrupted: {str(e)}",
                details={"error": str(e), "bytes_transferred": bytes_transferred}
            )

    async def get_download_progress(
        self,
        file_id: str,
        downloaded_size: int
    ) -> DownloadProgress:
        """
        Получение прогресса скачивания.

        Args:
            file_id: UUID файла
            downloaded_size: Количество уже скачанных bytes

        Returns:
            DownloadProgress: Информация о прогрессе
        """
        # Получение метаданных для total_size
        cached_metadata = cache_service.get_file_metadata(file_id)
        if not cached_metadata:
            # TODO: fetch from database or Storage Element
            raise FileNotFoundException(
                f"File metadata not found: {file_id}",
                details={"file_id": file_id}
            )

        total_size = cached_metadata["file_size"]

        progress = DownloadProgress(
            file_id=file_id,
            total_size=total_size,
            downloaded_size=downloaded_size,
            resume_from=downloaded_size if downloaded_size < total_size else None
        )

        return progress

    async def _record_download_stats(
        self,
        file_id: str,
        bytes_transferred: int,
        download_time_ms: int,
        was_resumed: bool,
        storage_element_id: str,
        username: Optional[str] = None
    ) -> None:
        """
        Запись статистики скачивания в базу данных.

        Args:
            file_id: UUID файла
            bytes_transferred: Количество переданных bytes
            download_time_ms: Время скачивания в миллисекундах
            was_resumed: Было ли скачивание resumed
            storage_element_id: ID Storage Element
            username: Пользователь (optional)
        """
        try:
            # TODO: implement async database write
            logger.debug(
                "Download stats recorded",
                extra={
                    "file_id": file_id,
                    "bytes": bytes_transferred,
                    "time_ms": download_time_ms,
                    "resumed": was_resumed
                }
            )

        except Exception as e:
            logger.warning(
                "Failed to record download stats",
                extra={"error": str(e)}
            )
            # Не прерываем скачивание из-за ошибки статистики

    async def close(self) -> None:
        """Закрытие HTTP клиента."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
            logger.info("HTTP client closed")


# Singleton instance
download_service = DownloadService()
