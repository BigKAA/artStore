"""
Admin Module HTTP Client для Ingester.

Sprint 14: Redis Storage Registry & Adaptive Capacity.

Используется как fallback когда Redis недоступен.
Получает информацию о Storage Elements напрямую из Admin Module API.

ВАЖНО: Использует httpx с async для неблокирующих HTTP запросов.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional
import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.services.storage_selector import StorageElementInfo, CapacityStatus

logger = get_logger(__name__)


class AdminClientError(Exception):
    """Базовое исключение для ошибок Admin Client."""
    pass


class AdminClientConnectionError(AdminClientError):
    """Ошибка подключения к Admin Module."""
    pass


class AdminClientAuthError(AdminClientError):
    """Ошибка аутентификации в Admin Module."""
    pass


class AdminModuleClient:
    """
    HTTP клиент для взаимодействия с Admin Module.

    Предоставляет методы для:
    - Получения списка доступных Storage Elements (fallback)
    - Аутентификации через OAuth 2.0 Client Credentials

    Usage:
        client = AdminModuleClient()
        await client.initialize()

        se_list = await client.get_available_storage_elements(mode="edit")

        await client.close()
    """

    def __init__(self):
        """Инициализация клиента."""
        self._http_client: Optional[httpx.AsyncClient] = None
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
        self._initialized = False

        # Конфигурация
        self._admin_url = settings.service_account.admin_module_url
        self._client_id = settings.service_account.client_id
        self._client_secret = settings.service_account.client_secret
        self._timeout = settings.service_account.timeout

    async def initialize(self) -> None:
        """
        Инициализация HTTP клиента.

        Создаёт httpx.AsyncClient с connection pooling.
        """
        self._http_client = httpx.AsyncClient(
            base_url=self._admin_url,
            timeout=httpx.Timeout(self._timeout),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
        )
        self._initialized = True

        logger.info(
            "Admin Module client initialized",
            extra={"admin_url": self._admin_url}
        )

    async def close(self) -> None:
        """Закрытие HTTP клиента."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        self._initialized = False
        logger.info("Admin Module client closed")

    async def _ensure_authenticated(self) -> str:
        """
        Получение или обновление access token.

        Использует OAuth 2.0 Client Credentials flow.

        Returns:
            str: Валидный access token

        Raises:
            AdminClientAuthError: При ошибке аутентификации
        """
        # Проверяем есть ли валидный токен
        if self._access_token and self._token_expires_at:
            # Обновляем за 60 секунд до истечения
            if datetime.now(timezone.utc) < self._token_expires_at:
                return self._access_token

        # Получаем новый токен
        try:
            response = await self._http_client.post(
                "/api/v1/auth/token",
                json={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret
                }
            )

            if response.status_code == 200:
                data = response.json()
                self._access_token = data["access_token"]

                # Рассчитываем время истечения (с буфером в 60 секунд)
                expires_in = data.get("expires_in", 1800)  # default 30 min
                self._token_expires_at = datetime.now(timezone.utc) + \
                    timedelta(seconds=expires_in - 60)

                logger.debug("Admin Module access token obtained")
                return self._access_token

            elif response.status_code == 401:
                raise AdminClientAuthError(
                    f"Invalid credentials: {response.text}"
                )
            else:
                raise AdminClientAuthError(
                    f"Auth failed with status {response.status_code}: {response.text}"
                )

        except httpx.RequestError as e:
            raise AdminClientConnectionError(
                f"Failed to connect to Admin Module for auth: {e}"
            )

    async def get_available_storage_elements(
        self,
        mode: Optional[str] = None,
        min_free_bytes: Optional[int] = None
    ) -> list[StorageElementInfo]:
        """
        Получение списка доступных Storage Elements.

        Запрашивает данные из Admin Module Fallback API.

        Args:
            mode: Фильтр по режиму (edit, rw)
            min_free_bytes: Минимальное свободное место в байтах

        Returns:
            list[StorageElementInfo]: Список SE отсортированный по priority

        Raises:
            AdminClientError: При ошибке запроса
        """
        if not self._initialized:
            raise AdminClientError("Client not initialized. Call initialize() first.")

        try:
            token = await self._ensure_authenticated()

            # Формируем параметры запроса
            params = {}
            if mode:
                params["mode"] = mode
            if min_free_bytes:
                params["min_free_bytes"] = min_free_bytes

            # Запрос к Fallback API
            response = await self._http_client.get(
                "/api/v1/internal/storage-elements/available",
                params=params,
                headers={"Authorization": f"Bearer {token}"}
            )

            if response.status_code == 200:
                data = response.json()
                return self._parse_storage_elements(data.get("storage_elements", []))

            elif response.status_code == 401:
                # Токен истёк, пробуем обновить
                self._access_token = None
                token = await self._ensure_authenticated()

                response = await self._http_client.get(
                    "/api/v1/internal/storage-elements/available",
                    params=params,
                    headers={"Authorization": f"Bearer {token}"}
                )

                if response.status_code == 200:
                    data = response.json()
                    return self._parse_storage_elements(data.get("storage_elements", []))

                raise AdminClientAuthError(f"Auth retry failed: {response.text}")

            elif response.status_code == 503:
                # Admin Module не может предоставить данные
                logger.warning(
                    "Admin Module storage elements unavailable",
                    extra={"status": response.status_code}
                )
                return []

            else:
                raise AdminClientError(
                    f"Failed to get storage elements: {response.status_code}"
                )

        except httpx.RequestError as e:
            raise AdminClientConnectionError(
                f"Failed to connect to Admin Module: {e}"
            )

    def _parse_storage_elements(self, data: list[dict]) -> list[StorageElementInfo]:
        """
        Парсинг ответа API в список StorageElementInfo.

        Args:
            data: Список SE из API response

        Returns:
            list[StorageElementInfo]: Распарсенные объекты
        """
        result = []

        for item in data:
            try:
                # element_id может быть null в JSON - используем id как fallback
                element_id = item.get("element_id") or str(item.get("id", ""))
                se_info = StorageElementInfo(
                    element_id=element_id,
                    mode=item.get("mode", "unknown"),
                    endpoint=item.get("api_url", ""),
                    priority=item.get("priority", 100),
                    capacity_total=item.get("capacity_bytes", 0),
                    capacity_used=item.get("used_bytes", 0),
                    capacity_free=item.get("capacity_bytes", 0) - item.get("used_bytes", 0),
                    capacity_percent=self._calculate_percent(
                        item.get("used_bytes", 0),
                        item.get("capacity_bytes", 0)
                    ),
                    capacity_status=CapacityStatus(
                        item.get("capacity_status", "ok")
                    ),
                    health_status=item.get("health_status", "healthy"),
                    last_updated=datetime.fromisoformat(
                        item.get("updated_at", datetime.now(timezone.utc).isoformat())
                    ) if item.get("updated_at") else datetime.now(timezone.utc)
                )
                result.append(se_info)

            except Exception as e:
                logger.warning(
                    f"Failed to parse SE data",
                    extra={"error": str(e), "data": item}
                )
                continue

        # Сортируем по priority
        result.sort(key=lambda x: x.priority)

        return result

    @staticmethod
    def _calculate_percent(used: int, total: int) -> float:
        """Расчёт процента использования."""
        if total <= 0:
            return 0.0
        return (used / total) * 100

    async def health_check(self) -> tuple[bool, str]:
        """
        Проверка доступности Admin Module.

        Returns:
            tuple[bool, str]: (is_healthy, status_message)
        """
        if not self._initialized:
            return False, "Client not initialized"

        try:
            response = await self._http_client.get("/health/live")
            if response.status_code == 200:
                return True, "Admin Module healthy"
            return False, f"Admin Module returned {response.status_code}"

        except httpx.RequestError as e:
            return False, f"Connection failed: {e}"

    # ==================== Sprint 15.2: File Registry Methods ====================

    async def register_file(self, file_data: dict) -> dict:
        """
        Регистрация нового файла в file registry.

        Sprint 15.2: POST /api/v1/files

        Args:
            file_data: Данные файла для регистрации (FileRegisterRequest schema)

        Returns:
            dict: Зарегистрированный файл (FileResponse)

        Raises:
            AdminClientAuthError: Authentication failed
            AdminClientError: Registration failed
            AdminClientConnectionError: Connection failed
        """
        if not self._initialized:
            raise AdminClientError("Client not initialized")

        logger.info(
            "Registering file in Admin Module",
            extra={
                "file_id": file_data.get("file_id"),
                "original_filename": file_data.get("original_filename")
            }
        )

        try:
            token = await self._ensure_authenticated()

            response = await self._http_client.post(
                "/api/v1/files",
                json=file_data,
                headers={"Authorization": f"Bearer {token}"}
            )

            if response.status_code == 201:
                result = response.json()
                logger.info(
                    "File registered successfully",
                    extra={"file_id": result.get("file_id")}
                )
                return result

            elif response.status_code == 401:
                # Token expired, retry with new token
                logger.warning("Token expired during file registration, refreshing")
                self._access_token = None
                token = await self._ensure_authenticated()

                response = await self._http_client.post(
                    "/api/v1/files",
                    json=file_data,
                    headers={"Authorization": f"Bearer {token}"}
                )

                if response.status_code == 201:
                    result = response.json()
                    return result

                raise AdminClientAuthError(f"Auth retry failed: {response.text}")

            elif response.status_code == 400:
                # Validation error или файл уже существует
                error_detail = response.json().get("detail", "Validation error")
                raise AdminClientError(f"File registration failed: {error_detail}")

            else:
                raise AdminClientError(
                    f"Failed to register file: {response.status_code} - {response.text}"
                )

        except httpx.RequestError as e:
            raise AdminClientConnectionError(
                f"Failed to connect to Admin Module: {e}"
            )

    async def update_file(self, file_id: str, file_data: dict) -> dict:
        """
        Обновление файла (финализация).

        Sprint 15.2: PUT /api/v1/files/{file_id}

        Args:
            file_id: UUID файла
            file_data: Данные для обновления (FileUpdateRequest schema)

        Returns:
            dict: Обновленный файл (FileResponse)

        Raises:
            AdminClientAuthError: Authentication failed
            AdminClientError: Update failed
            AdminClientConnectionError: Connection failed
        """
        if not self._initialized:
            raise AdminClientError("Client not initialized")

        logger.info(
            "Updating file in Admin Module",
            extra={
                "file_id": file_id,
                "retention_policy": file_data.get("retention_policy")
            }
        )

        try:
            token = await self._ensure_authenticated()

            response = await self._http_client.put(
                f"/api/v1/files/{file_id}",
                json=file_data,
                headers={"Authorization": f"Bearer {token}"}
            )

            if response.status_code == 200:
                result = response.json()
                logger.info(
                    "File updated successfully",
                    extra={"file_id": result.get("file_id")}
                )
                return result

            elif response.status_code == 401:
                # Token expired, retry with new token
                logger.warning("Token expired during file update, refreshing")
                self._access_token = None
                token = await self._ensure_authenticated()

                response = await self._http_client.put(
                    f"/api/v1/files/{file_id}",
                    json=file_data,
                    headers={"Authorization": f"Bearer {token}"}
                )

                if response.status_code == 200:
                    result = response.json()
                    return result

                raise AdminClientAuthError(f"Auth retry failed: {response.text}")

            elif response.status_code == 404:
                raise AdminClientError(f"File {file_id} not found")

            elif response.status_code == 400:
                error_detail = response.json().get("detail", "Validation error")
                raise AdminClientError(f"File update failed: {error_detail}")

            else:
                raise AdminClientError(
                    f"Failed to update file: {response.status_code} - {response.text}"
                )

        except httpx.RequestError as e:
            raise AdminClientConnectionError(
                f"Failed to connect to Admin Module: {e}"
            )

    async def get_file(self, file_id: str) -> Optional[dict]:
        """
        Получение метаданных файла по ID.

        Sprint 15.2: GET /api/v1/files/{file_id}

        Args:
            file_id: UUID файла

        Returns:
            dict или None: FileResponse или None если не найден

        Raises:
            AdminClientAuthError: Authentication failed
            AdminClientConnectionError: Connection failed
        """
        if not self._initialized:
            raise AdminClientError("Client not initialized")

        logger.debug(
            "Fetching file metadata from Admin Module",
            extra={"file_id": file_id}
        )

        try:
            token = await self._ensure_authenticated()

            response = await self._http_client.get(
                f"/api/v1/files/{file_id}",
                headers={"Authorization": f"Bearer {token}"}
            )

            if response.status_code == 200:
                return response.json()

            elif response.status_code == 404:
                logger.debug("File not found", extra={"file_id": file_id})
                return None

            elif response.status_code == 401:
                # Token expired, retry with new token
                logger.warning("Token expired during file fetch, refreshing")
                self._access_token = None
                token = await self._ensure_authenticated()

                response = await self._http_client.get(
                    f"/api/v1/files/{file_id}",
                    headers={"Authorization": f"Bearer {token}"}
                )

                if response.status_code == 200:
                    return response.json()

                if response.status_code == 404:
                    return None

                raise AdminClientAuthError(f"Auth retry failed: {response.text}")

            else:
                raise AdminClientError(
                    f"Failed to get file: {response.status_code} - {response.text}"
                )

        except httpx.RequestError as e:
            raise AdminClientConnectionError(
                f"Failed to connect to Admin Module: {e}"
            )


# Глобальный singleton экземпляр
_admin_client: Optional[AdminModuleClient] = None


async def get_admin_client() -> AdminModuleClient:
    """
    Получение singleton экземпляра AdminModuleClient.

    Returns:
        AdminModuleClient: Клиент
    """
    global _admin_client

    if _admin_client is None:
        _admin_client = AdminModuleClient()

    return _admin_client


async def init_admin_client() -> AdminModuleClient:
    """
    Инициализация глобального AdminModuleClient.

    Вызывается при startup приложения.

    Returns:
        AdminModuleClient: Инициализированный клиент
    """
    global _admin_client

    _admin_client = AdminModuleClient()
    await _admin_client.initialize()

    return _admin_client


async def close_admin_client() -> None:
    """
    Закрытие AdminModuleClient при shutdown.
    """
    global _admin_client

    if _admin_client:
        await _admin_client.close()
        _admin_client = None
