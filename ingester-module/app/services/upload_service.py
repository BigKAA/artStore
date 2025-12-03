"""
Ingester Module - Upload Service.

Сервис для загрузки файлов в Storage Element.

Sprint 14: Интеграция с StorageSelector для динамического выбора SE.
- Sequential Fill алгоритм через Redis Registry
- Fallback на Admin Module API при недоступности Redis

Sprint 15: Retention Policy & Lifecycle.
- Поддержка temporary/permanent retention policies
- Расчёт TTL expiration для temporary файлов
- Интеграция с Admin Module для регистрации файла в file registry

Sprint 16: Удаление STORAGE_ELEMENT_BASE_URL fallback.
- Service Discovery (Redis или Admin Module) обязателен
- Local config fallback удалён

MVP реализация без Saga и Circuit Breaker (будет добавлено позже).
"""

import hashlib
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, TYPE_CHECKING
from uuid import UUID, uuid4

import httpx
from fastapi import UploadFile

from app.core.config import settings
from app.core.exceptions import (
    StorageElementUnavailableException,
    FileSizeLimitExceededException,
    NoAvailableStorageException
)
from app.schemas.upload import (
    UploadRequest,
    UploadResponse,
    StorageMode,
    CompressionAlgorithm,
    RetentionPolicy,  # Sprint 15
    DEFAULT_TTL_DAYS  # Sprint 15
)
from app.services.auth_service import AuthService

# TYPE_CHECKING для избежания circular imports
if TYPE_CHECKING:
    from app.services.storage_selector import StorageSelector
    from app.services.storage_selector import RetentionPolicy as SelectorRetentionPolicy

logger = logging.getLogger(__name__)


class UploadService:
    """
    Сервис загрузки файлов.

    Отвечает за:
    - Валидацию файлов
    - OAuth 2.0 аутентификацию через Service Account
    - Динамический выбор Storage Element через StorageSelector (Sprint 14)
    - Коммуникацию со Storage Element
    - Обработку ошибок загрузки

    Sprint 14: Интеграция с StorageSelector для Sequential Fill алгоритма.
    """

    def __init__(self, auth_service: AuthService):
        """
        Инициализация сервиса с AuthService для аутентификации.

        Args:
            auth_service: AuthService для получения JWT токенов
        """
        self.auth_service = auth_service
        self._client: Optional[httpx.AsyncClient] = None
        self._max_file_size = 1024 * 1024 * 1024  # 1GB по умолчанию

        # Sprint 14: StorageSelector для динамического выбора SE
        self._storage_selector: Optional["StorageSelector"] = None

        # Кеш HTTP клиентов для разных SE endpoints
        self._se_clients: dict[str, httpx.AsyncClient] = {}

    def set_storage_selector(self, storage_selector: "StorageSelector") -> None:
        """
        Установка StorageSelector для динамического выбора SE.

        Sprint 14: Вызывается из main.py lifespan после инициализации StorageSelector.

        Args:
            storage_selector: Инициализированный StorageSelector
        """
        self._storage_selector = storage_selector
        logger.info("StorageSelector injected into UploadService")

    async def _get_client(self) -> httpx.AsyncClient:
        """
        [DEPRECATED Sprint 16] Метод удалён.

        Storage Element выбирается динамически через StorageSelector.
        Используйте _get_client_for_endpoint() вместо этого метода.

        Raises:
            RuntimeError: Всегда - метод deprecated
        """
        raise RuntimeError(
            "Direct client creation is deprecated (Sprint 16). "
            "Use _get_client_for_endpoint() with SE from StorageSelector. "
            "Ensure StorageSelector is configured via set_storage_selector()."
        )

    async def _get_client_for_endpoint(self, endpoint: str) -> httpx.AsyncClient:
        """
        Получить HTTP клиент для указанного SE endpoint.

        Sprint 14: Поддержка multiple Storage Elements через StorageSelector.
        Кеширует клиенты для повторного использования.

        Args:
            endpoint: URL Storage Element (например: http://storage-element-01:8010)

        Returns:
            httpx.AsyncClient: Async HTTP клиент для указанного endpoint
        """
        # Проверяем кеш
        if endpoint in self._se_clients:
            return self._se_clients[endpoint]

        # Создаём новый клиент для этого endpoint
        client_config = {
            "base_url": endpoint,
            "timeout": settings.storage_element.timeout,
            "limits": httpx.Limits(
                max_connections=settings.storage_element.connection_pool_size
            ),
            "http2": True,
        }

        client = httpx.AsyncClient(**client_config)
        self._se_clients[endpoint] = client

        logger.info(
            "HTTP client created for SE endpoint",
            extra={"endpoint": endpoint}
        )

        return client

    async def close(self):
        """
        Закрытие всех HTTP клиентов.

        Sprint 14: Закрывает как default client, так и все SE-specific клиенты.
        """
        # Закрываем default client
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("Default HTTP client closed")

        # Sprint 14: Закрываем все SE-specific клиенты
        for endpoint, client in self._se_clients.items():
            try:
                await client.aclose()
                logger.debug(f"SE HTTP client closed", extra={"endpoint": endpoint})
            except Exception as e:
                logger.warning(f"Error closing SE client", extra={"endpoint": endpoint, "error": str(e)})

        self._se_clients.clear()
        logger.info("All HTTP clients closed")

    async def upload_file(
        self,
        file: UploadFile,
        request: UploadRequest,
        user_id: str,
        username: str
    ) -> UploadResponse:
        """
        Загрузка файла в Storage Element.

        Sprint 14: Динамический выбор SE через StorageSelector.
        - Маппинг storage_mode → retention_policy
        - Sequential Fill алгоритм для выбора оптимального SE
        - Fallback на статическую конфигурацию если StorageSelector не настроен

        Sprint 15: Retention Policy & Lifecycle.
        - Расчёт TTL expiration для temporary файлов
        - Передача retention_policy в Storage Element
        - Возврат полной информации о retention policy

        Args:
            file: Загружаемый файл
            request: Параметры загрузки
            user_id: ID пользователя
            username: Имя пользователя

        Returns:
            UploadResponse: Результат загрузки с retention policy info

        Raises:
            StorageElementUnavailableException: Storage Element недоступен
            FileSizeLimitExceededException: Превышен лимит размера
            NoAvailableStorageException: Нет доступного SE для загрузки
        """
        logger.info(
            "Starting file upload",
            extra={
                "uploaded_filename": file.filename,
                "content_type": file.content_type,
                "retention_policy": request.retention_policy.value,
                "ttl_days": request.ttl_days,
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

        # Sprint 15: Расчёт TTL expiration для temporary файлов
        ttl_expires_at = None
        if request.retention_policy == RetentionPolicy.TEMPORARY and request.ttl_days:
            ttl_expires_at = datetime.now(timezone.utc) + timedelta(days=request.ttl_days)

        # Sprint 14: Выбор Storage Element через StorageSelector
        storage_element_url, storage_element_id = await self._select_storage_element_with_id(
            file_size=file_size,
            retention_policy=request.retention_policy
        )

        # Формирование данных для Storage Element
        files = {
            'file': (file.filename, content, file.content_type or 'application/octet-stream')
        }

        # Sprint 15: Включаем retention policy в данные для SE
        data = {
            'description': request.description or '',
            'uploaded_by_username': username,
            'uploaded_by_id': user_id,
            # Sprint 15: Retention Policy данные
            'retention_policy': request.retention_policy.value,
            'ttl_days': str(request.ttl_days) if request.ttl_days else '',
            'ttl_expires_at': ttl_expires_at.isoformat() if ttl_expires_at else '',
        }

        # Sprint 15: Добавляем metadata если есть
        if request.metadata:
            import json
            data['metadata'] = json.dumps(request.metadata)

        # TODO: Добавить сжатие если request.compress=True
        # TODO: Добавить Circuit Breaker pattern
        # TODO: Добавить retry logic

        try:
            # Получить JWT access token для аутентификации
            access_token = await self.auth_service.get_access_token()

            # Sprint 14: Используем клиент для выбранного SE endpoint
            client = await self._get_client_for_endpoint(storage_element_url)

            # Отправка запроса в Storage Element с Authorization header
            response = await client.post(
                "/api/v1/files/upload",
                headers={'Authorization': f'Bearer {access_token}'},
                files=files,
                data=data
            )

            response.raise_for_status()
            result = response.json()

            logger.info(
                "File uploaded successfully",
                extra={
                    "file_id": result.get('file_id'),
                    "uploaded_filename": file.filename,
                    "file_size": file_size,
                    "user_id": user_id,
                    "storage_element_url": storage_element_url,
                    "storage_element_id": storage_element_id,
                    "retention_policy": request.retention_policy.value,
                    "ttl_expires_at": str(ttl_expires_at) if ttl_expires_at else None
                }
            )

            # Sprint 15: Формирование ответа с retention policy info
            return UploadResponse(
                file_id=UUID(result['file_id']),
                original_filename=file.filename or "unknown",
                storage_filename=result.get('original_filename', ''),
                file_size=file_size,
                compressed=request.compress,
                compression_ratio=None,  # TODO: calculate if compressed
                checksum=result.get('checksum', checksum),
                uploaded_at=datetime.now(timezone.utc),
                storage_element_url=storage_element_url,
                # Sprint 15: Retention Policy info
                retention_policy=request.retention_policy,
                ttl_expires_at=ttl_expires_at,
                storage_element_id=storage_element_id
            )

        except httpx.HTTPStatusError as e:
            logger.error(
                "Storage Element HTTP error",
                extra={
                    "status_code": e.response.status_code,
                    "error": str(e),
                    "storage_element_url": storage_element_url
                }
            )
            raise StorageElementUnavailableException(
                f"Storage Element returned error: {e.response.status_code}"
            )

        except httpx.RequestError as e:
            logger.error(
                "Storage Element connection error",
                extra={"error": str(e), "storage_element_url": storage_element_url}
            )
            raise StorageElementUnavailableException(
                f"Cannot connect to Storage Element: {str(e)}"
            )

    async def _select_storage_element_with_id(
        self,
        file_size: int,
        retention_policy: RetentionPolicy
    ) -> tuple[str, str]:
        """
        Выбор Storage Element для загрузки файла (Sprint 15).

        Sprint 15: Возвращает tuple (url, id) для использования в UploadResponse.

        Args:
            file_size: Размер файла в байтах
            retention_policy: Политика хранения (temporary/permanent)

        Returns:
            tuple[str, str]: (URL выбранного Storage Element, ID Storage Element)

        Raises:
            NoAvailableStorageException: Нет подходящего SE
        """
        # Sprint 16: StorageSelector обязателен, static fallback удалён
        if not self._storage_selector:
            logger.error(
                "StorageSelector not configured - Service Discovery is required",
                extra={"error": "StorageSelector must be set via set_storage_selector()"}
            )
            raise NoAvailableStorageException(
                "StorageSelector not configured. "
                "Service Discovery (Redis or Admin Module) is required. "
                "Ensure StorageSelector is initialized in application startup."
            )

        # Маппинг schema RetentionPolicy → selector RetentionPolicy
        from app.services.storage_selector import RetentionPolicy as SelectorRetentionPolicy

        if retention_policy == RetentionPolicy.TEMPORARY:
            selector_policy = SelectorRetentionPolicy.TEMPORARY
        else:
            selector_policy = SelectorRetentionPolicy.PERMANENT

        logger.debug(
            "Selecting SE via StorageSelector",
            extra={
                "file_size": file_size,
                "retention_policy": retention_policy.value
            }
        )

        # Выбор SE через StorageSelector (Sequential Fill)
        se_info = await self._storage_selector.select_storage_element(
            file_size=file_size,
            retention_policy=selector_policy
        )

        if not se_info:
            logger.error(
                "No available Storage Element found",
                extra={
                    "file_size": file_size,
                    "retention_policy": retention_policy.value
                }
            )
            raise NoAvailableStorageException(
                f"No available Storage Element for retention_policy={retention_policy.value}, "
                f"file_size={file_size} bytes"
            )

        logger.info(
            "Storage Element selected",
            extra={
                "se_id": se_info.element_id,
                "endpoint": se_info.endpoint,
                "mode": se_info.mode,
                "priority": se_info.priority,
                "capacity_free": se_info.capacity_free,
                "capacity_status": se_info.capacity_status.value
            }
        )

        return se_info.endpoint, se_info.element_id

    async def _select_storage_element(
        self,
        file_size: int,
        storage_mode: StorageMode
    ) -> str:
        """
        Выбор Storage Element для загрузки файла (Legacy метод).

        [DEPRECATED] Используйте _select_storage_element_with_id вместо этого.

        Sprint 14: Использует StorageSelector с Sequential Fill алгоритмом.
        Fallback на статическую конфигурацию если StorageSelector не настроен.

        Args:
            file_size: Размер файла в байтах
            storage_mode: Режим хранения из request (edit, rw)

        Returns:
            str: URL выбранного Storage Element

        Raises:
            NoAvailableStorageException: Нет подходящего SE
        """
        # Маппинг storage_mode → retention_policy для обратной совместимости
        if storage_mode == StorageMode.EDIT:
            retention_policy = RetentionPolicy.TEMPORARY
        else:  # StorageMode.RW
            retention_policy = RetentionPolicy.PERMANENT

        url, _ = await self._select_storage_element_with_id(file_size, retention_policy)
        return url
