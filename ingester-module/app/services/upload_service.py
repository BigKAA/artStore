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
    NoAvailableStorageException,
    InsufficientStorageException,  # Sprint 17
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
from app.core.metrics import record_lazy_se_config_reload  # Sprint 21

# TYPE_CHECKING для избежания circular imports
if TYPE_CHECKING:
    from app.services.storage_selector import StorageSelector
    from app.services.storage_selector import RetentionPolicy as SelectorRetentionPolicy
    from app.services.capacity_monitor import AdaptiveCapacityMonitor

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

    Sprint 17: Retry logic и Lazy Update интеграция.
    - Обработка 507 Insufficient Storage с retry на другой SE
    - Интеграция с AdaptiveCapacityMonitor для lazy update
    - Исключение failed SE из повторного выбора
    - Конфигурируемое количество retry (default: 3)
    """

    # Sprint 17: Максимальное количество retry при 507
    DEFAULT_MAX_RETRIES = 3

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

        # Sprint 17: AdaptiveCapacityMonitor для lazy update
        self._capacity_monitor: Optional["AdaptiveCapacityMonitor"] = None

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

    def set_capacity_monitor(self, capacity_monitor: "AdaptiveCapacityMonitor") -> None:
        """
        Установка AdaptiveCapacityMonitor для lazy update.

        Sprint 17: Вызывается из main.py lifespan после инициализации CapacityMonitor.
        При 507 ошибках UploadService триггерит lazy update через этот monitor.

        Args:
            capacity_monitor: Инициализированный AdaptiveCapacityMonitor
        """
        self._capacity_monitor = capacity_monitor
        logger.info("AdaptiveCapacityMonitor injected into UploadService")

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

        Sprint 17: Retry Logic с Lazy Update.
        - Обработка 507 Insufficient Storage с retry на другой SE
        - Интеграция с AdaptiveCapacityMonitor для lazy update
        - Исключение failed SE из повторного выбора

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
            InsufficientStorageException: Все SE переполнены (после retry)
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

        # Sprint 17: Retry logic при 507 Insufficient Storage
        # Исключаем SE которые вернули 507 и пробуем другие
        excluded_se_ids: set[str] = set()
        last_insufficient_storage_error: Optional[InsufficientStorageException] = None

        for attempt in range(self.DEFAULT_MAX_RETRIES):
            try:
                result = await self._upload_to_storage_element(
                    content=content,
                    filename=file.filename,
                    content_type=file.content_type,
                    data=data,
                    file_size=file_size,
                    retention_policy=request.retention_policy,
                    excluded_se_ids=excluded_se_ids,
                )

                logger.info(
                    "File uploaded successfully",
                    extra={
                        "file_id": result["file_id"],
                        "uploaded_filename": file.filename,
                        "file_size": file_size,
                        "user_id": user_id,
                        "storage_element_url": result["storage_element_url"],
                        "storage_element_id": result["storage_element_id"],
                        "retention_policy": request.retention_policy.value,
                        "ttl_expires_at": str(ttl_expires_at) if ttl_expires_at else None,
                        "attempt": attempt + 1,
                    }
                )

                # Sprint 15.2: Регистрация файла в Admin Module file registry
                try:
                    from app.services.admin_client import get_admin_client, AdminClientError

                    admin_client = await get_admin_client()

                    # Подготовка данных для регистрации
                    file_register_data = {
                        "file_id": str(result['file_id']),
                        "original_filename": file.filename or "unknown",
                        "storage_filename": result.get('storage_filename', result['file_id']),
                        "file_size": file_size,
                        "checksum_sha256": result.get('checksum', checksum),
                        "content_type": file.content_type,
                        "description": request.description,
                        "retention_policy": request.retention_policy.value,
                        "ttl_expires_at": ttl_expires_at.isoformat() if ttl_expires_at else None,
                        "ttl_days": request.ttl_days,
                        "storage_element_id": result["storage_element_id"],
                        "storage_path": f"/files/{result['file_id']}",
                        "compressed": request.compress,
                        "compression_algorithm": request.compression_algorithm.value if request.compress else None,
                        "original_size": file_size if request.compress else None,
                        "uploaded_by": user_id,
                        "upload_source_ip": None,  # TODO: extract from request
                        "user_metadata": request.metadata,
                    }

                    # Регистрация в file registry
                    registry_result = await admin_client.register_file(file_register_data)

                    logger.info(
                        "File registered in Admin Module registry",
                        extra={
                            "file_id": str(result['file_id']),
                            "registry_file_id": registry_result.get('file_id'),
                        }
                    )

                except AdminClientError as e:
                    # NON-CRITICAL: Файл загружен в SE, но не зарегистрирован в Admin Module
                    # Может быть зарегистрирован позже через reconciliation job
                    logger.error(
                        "Failed to register file in Admin Module registry",
                        extra={
                            "file_id": str(result['file_id']),
                            "error": str(e),
                            "user_id": user_id
                        }
                    )
                    # Не прерываем операцию - файл уже в SE
                    # TODO Sprint 15.3: Implement reconciliation job для retry

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
                    storage_element_url=result["storage_element_url"],
                    # Sprint 15: Retention Policy info
                    retention_policy=request.retention_policy,
                    ttl_expires_at=ttl_expires_at,
                    storage_element_id=result["storage_element_id"]
                )

            except InsufficientStorageException as e:
                # Sprint 17: 507 Insufficient Storage - trigger lazy update и retry
                last_insufficient_storage_error = e
                excluded_se_ids.add(e.storage_element_id)

                logger.warning(
                    "Storage Element returned 507 Insufficient Storage",
                    extra={
                        "se_id": e.storage_element_id,
                        "attempt": attempt + 1,
                        "max_retries": self.DEFAULT_MAX_RETRIES,
                        "excluded_se_ids": list(excluded_se_ids),
                        "file_size": file_size,
                    }
                )

                # Trigger lazy update через CapacityMonitor
                if self._capacity_monitor:
                    await self._capacity_monitor.trigger_lazy_update(
                        se_id=e.storage_element_id,
                        reason="insufficient_storage"
                    )

                # Если есть ещё попытки - продолжаем с другим SE
                if attempt < self.DEFAULT_MAX_RETRIES - 1:
                    logger.info(
                        "Retrying upload with different Storage Element",
                        extra={
                            "attempt": attempt + 2,
                            "excluded_se_ids": list(excluded_se_ids),
                        }
                    )
                    continue

                # Все попытки исчерпаны
                logger.error(
                    "All Storage Elements exhausted (507 Insufficient Storage)",
                    extra={
                        "excluded_se_ids": list(excluded_se_ids),
                        "file_size": file_size,
                        "retention_policy": request.retention_policy.value,
                    }
                )
                raise

            except NoAvailableStorageException:
                # Нет доступных SE (все в excluded или все заняты)
                if last_insufficient_storage_error:
                    logger.error(
                        "No available Storage Elements after 507 retries",
                        extra={
                            "excluded_se_ids": list(excluded_se_ids),
                            "file_size": file_size,
                        }
                    )
                    raise last_insufficient_storage_error
                raise

        # Fallback - не должны сюда попасть
        raise NoAvailableStorageException(
            "Upload failed after all retry attempts"
        )

    async def _upload_to_storage_element(
        self,
        content: bytes,
        filename: str,
        content_type: Optional[str],
        data: dict,
        file_size: int,
        retention_policy: RetentionPolicy,
        excluded_se_ids: set[str],
    ) -> dict:
        """
        Внутренний метод для загрузки файла на конкретный SE.

        Sprint 17: Выделен из upload_file для поддержки retry logic.

        Args:
            content: Содержимое файла
            filename: Имя файла
            content_type: MIME тип
            data: Данные для multipart form
            file_size: Размер файла
            retention_policy: Политика хранения
            excluded_se_ids: Множество ID SE для исключения из выбора

        Returns:
            dict: Результат от Storage Element + storage_element_url, storage_element_id

        Raises:
            InsufficientStorageException: SE вернул 507
            StorageElementUnavailableException: SE недоступен
            NoAvailableStorageException: Нет подходящего SE
        """
        # Выбор Storage Element через StorageSelector
        storage_element_url, storage_element_id = await self._select_storage_element_with_id(
            file_size=file_size,
            retention_policy=retention_policy,
            excluded_se_ids=excluded_se_ids,
        )

        # Формирование файла для multipart
        files = {
            'file': (filename, content, content_type or 'application/octet-stream')
        }

        try:
            # Получить JWT access token для аутентификации
            access_token = await self.auth_service.get_access_token()

            # Используем клиент для выбранного SE endpoint
            client = await self._get_client_for_endpoint(storage_element_url)

            # Отправка запроса в Storage Element с Authorization header
            response = await client.post(
                "/api/v1/files/upload",
                headers={'Authorization': f'Bearer {access_token}'},
                files=files,
                data=data
            )

            # Sprint 17: Проверка на 507 Insufficient Storage
            if response.status_code == 507:
                # Sprint 21 Phase 2: Trigger lazy reload on 507
                await self.trigger_se_config_reload(reason="insufficient_storage")

                raise InsufficientStorageException(
                    message=f"Storage Element {storage_element_id} has insufficient storage",
                    storage_element_id=storage_element_id,
                    required_bytes=file_size,
                )

            response.raise_for_status()
            result = response.json()

            # Добавляем информацию о SE в результат
            result["storage_element_url"] = storage_element_url
            result["storage_element_id"] = storage_element_id

            return result

        except httpx.HTTPStatusError as e:
            # Sprint 17: Проверка на 507 через HTTPStatusError
            if e.response.status_code == 507:
                # Sprint 21 Phase 2: Trigger lazy reload on 507
                await self.trigger_se_config_reload(reason="insufficient_storage")

                raise InsufficientStorageException(
                    message=f"Storage Element {storage_element_id} has insufficient storage",
                    storage_element_id=storage_element_id,
                    required_bytes=file_size,
                )

            # Sprint 21 Phase 2: Trigger lazy reload on 404 Not Found
            if e.response.status_code == 404:
                await self.trigger_se_config_reload(reason="not_found")

            logger.error(
                "Storage Element HTTP error",
                extra={
                    "status_code": e.response.status_code,
                    "error": str(e),
                    "storage_element_url": storage_element_url,
                    "storage_element_id": storage_element_id,
                }
            )
            raise StorageElementUnavailableException(
                f"Storage Element returned error: {e.response.status_code}"
            )

        except httpx.RequestError as e:
            # Sprint 21 Phase 2: Trigger lazy reload on connection error
            await self.trigger_se_config_reload(reason="connection_error")

            logger.error(
                "Storage Element connection error",
                extra={
                    "error": str(e),
                    "storage_element_url": storage_element_url,
                    "storage_element_id": storage_element_id,
                }
            )
            raise StorageElementUnavailableException(
                f"Cannot connect to Storage Element: {str(e)}"
            )

    async def _select_storage_element_with_id(
        self,
        file_size: int,
        retention_policy: RetentionPolicy,
        excluded_se_ids: Optional[set[str]] = None,
    ) -> tuple[str, str]:
        """
        Выбор Storage Element для загрузки файла (Sprint 15).

        Sprint 15: Возвращает tuple (url, id) для использования в UploadResponse.

        Sprint 17: Добавлен excluded_se_ids для поддержки retry logic.
        SE из этого множества исключаются из выбора.

        Args:
            file_size: Размер файла в байтах
            retention_policy: Политика хранения (temporary/permanent)
            excluded_se_ids: Множество ID SE для исключения из выбора (Sprint 17)

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
                "retention_policy": retention_policy.value,
                "excluded_se_ids": list(excluded_se_ids) if excluded_se_ids else [],
            }
        )

        # Sprint 17: Выбор SE через StorageSelector с исключением failed SE
        se_info = await self._storage_selector.select_storage_element(
            file_size=file_size,
            retention_policy=selector_policy,
            excluded_se_ids=excluded_se_ids,  # Sprint 17
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

    async def trigger_se_config_reload(self, reason: str = "manual") -> None:
        """
        Принудительное обновление SE конфигурации.

        Sprint 21 Phase 2: Lazy Reload для немедленного обновления при ошибках.

        Вызывается при обнаружении проблем:
        - 507 Insufficient Storage (capacity cache stale)
        - 404 Not Found (SE удалён/переехал)
        - Connection errors (SE недоступен)

        Процесс:
        1. Fetch fresh SE endpoints from Redis (primary)
        2. Fallback to Admin Module API if Redis unavailable
        3. Call capacity_monitor.reload_storage_endpoints()
        4. Record metrics for monitoring

        Args:
            reason: Причина reload (insufficient_storage, not_found, connection_error, manual)
        """
        if not self._capacity_monitor:
            logger.warning(
                "Cannot trigger SE config reload: CapacityMonitor not configured",
                extra={"reason": reason}
            )
            record_lazy_se_config_reload(reason=reason, status="skipped_no_monitor")
            return

        logger.info(
            "Triggering lazy SE config reload",
            extra={"reason": reason}
        )

        import time
        start_time = time.time()

        try:
            # Попытка 1: Redis (primary source)
            endpoints, priorities = await self._fetch_from_redis()

            if endpoints:
                logger.info(
                    "SE config fetched from Redis",
                    extra={
                        "reason": reason,
                        "se_count": len(endpoints),
                        "source": "redis"
                    }
                )

                # Применяем обновления через CapacityMonitor
                await self._capacity_monitor.reload_storage_endpoints(
                    new_endpoints=endpoints,
                    new_priorities=priorities
                )

                duration = time.time() - start_time
                record_lazy_se_config_reload(reason=reason, status="success_redis")

                logger.info(
                    "Lazy SE config reload completed",
                    extra={
                        "reason": reason,
                        "source": "redis",
                        "se_count": len(endpoints),
                        "duration_seconds": round(duration, 3)
                    }
                )
                return

            # Попытка 2: Admin Module API (fallback)
            logger.warning(
                "Redis unavailable for SE config, trying Admin Module fallback",
                extra={"reason": reason}
            )

            endpoints, priorities = await self._fetch_from_admin_module()

            if endpoints:
                logger.info(
                    "SE config fetched from Admin Module",
                    extra={
                        "reason": reason,
                        "se_count": len(endpoints),
                        "source": "admin_module"
                    }
                )

                # Применяем обновления через CapacityMonitor
                await self._capacity_monitor.reload_storage_endpoints(
                    new_endpoints=endpoints,
                    new_priorities=priorities
                )

                duration = time.time() - start_time
                record_lazy_se_config_reload(reason=reason, status="success_admin")

                logger.info(
                    "Lazy SE config reload completed",
                    extra={
                        "reason": reason,
                        "source": "admin_module",
                        "se_count": len(endpoints),
                        "duration_seconds": round(duration, 3)
                    }
                )
                return

            # Оба источника недоступны
            logger.error(
                "Failed to fetch SE config from all sources",
                extra={"reason": reason}
            )
            record_lazy_se_config_reload(reason=reason, status="failed_all_sources")

        except Exception as e:
            duration = time.time() - start_time
            logger.error(
                "Lazy SE config reload failed with exception",
                extra={
                    "reason": reason,
                    "error": str(e),
                    "duration_seconds": round(duration, 3)
                },
                exc_info=True
            )
            record_lazy_se_config_reload(reason=reason, status="error")

    async def _fetch_from_redis(self) -> tuple[dict[str, str], dict[str, int]]:
        """
        Получение SE configuration из Redis.

        Sprint 21 Phase 2: Helper для trigger_se_config_reload().

        Returns:
            tuple: (endpoints dict, priorities dict) или ({}, {}) при ошибке
        """
        try:
            # Получаем Redis client из StorageSelector
            if not self._storage_selector:
                logger.warning("StorageSelector not configured for Redis fetch")
                return {}, {}

            # StorageSelector имеет доступ к Redis через ServiceDiscovery
            # Используем его метод для получения свежих данных
            redis_client = getattr(self._storage_selector, '_redis_client', None)

            if not redis_client:
                logger.warning("Redis client not available in StorageSelector")
                return {}, {}

            # Читаем SE configuration из Redis
            # Format: storage:elements:registry - Hash {se_id → endpoint}
            #         storage:elements:priorities - Hash {se_id → priority}
            endpoints_raw = await redis_client.hgetall("storage:elements:registry")
            priorities_raw = await redis_client.hgetall("storage:elements:priorities")

            if not endpoints_raw:
                logger.warning("No SE endpoints found in Redis")
                return {}, {}

            # Конвертация Redis strings to dict
            endpoints = {k: v for k, v in endpoints_raw.items()}
            priorities = {k: int(v) for k, v in priorities_raw.items()}

            logger.debug(
                "SE config fetched from Redis",
                extra={
                    "se_count": len(endpoints),
                    "se_ids": list(endpoints.keys())
                }
            )

            return endpoints, priorities

        except Exception as e:
            logger.warning(
                "Failed to fetch SE config from Redis",
                extra={"error": str(e)}
            )
            return {}, {}

    async def _fetch_from_admin_module(self) -> tuple[dict[str, str], dict[str, int]]:
        """
        Получение SE configuration из Admin Module API.

        Sprint 21 Phase 2: Fallback для trigger_se_config_reload().

        Returns:
            tuple: (endpoints dict, priorities dict) или ({}, {}) при ошибке
        """
        try:
            # Admin Module URL из конфигурации
            admin_url = settings.auth.admin_module_url

            # Получаем JWT токен для аутентификации
            access_token = await self.auth_service.get_access_token()

            # Запрос к Admin Module API
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{admin_url}/api/v1/storage-elements",
                    headers={'Authorization': f'Bearer {access_token}'},
                    timeout=10.0
                )

                response.raise_for_status()
                data = response.json()

            # Парсинг ответа
            # Expected format: {"storage_elements": [{"id": "...", "endpoint": "...", "priority": 1}, ...]}
            storage_elements = data.get("storage_elements", [])

            if not storage_elements:
                logger.warning("No SE found in Admin Module response")
                return {}, {}

            endpoints = {se["id"]: se["endpoint"] for se in storage_elements}
            priorities = {se["id"]: se.get("priority", 1) for se in storage_elements}

            logger.debug(
                "SE config fetched from Admin Module",
                extra={
                    "se_count": len(endpoints),
                    "se_ids": list(endpoints.keys())
                }
            )

            return endpoints, priorities

        except Exception as e:
            logger.warning(
                "Failed to fetch SE config from Admin Module",
                extra={
                    "admin_url": settings.auth.admin_module_url,
                    "error": str(e)
                }
            )
            return {}, {}
