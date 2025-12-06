"""
Storage Discovery Service для автоматического обнаружения storage elements.

Сервис для получения информации о storage element по его URL
и автоматического заполнения данных при регистрации.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import httpx

from app.core.config import settings
from app.core.exceptions import (
    StorageElementDiscoveryError,
    StorageElementUnreachableError,
    StorageElementInvalidResponseError,
    StorageElementTimeoutError,
)

logger = logging.getLogger(__name__)


@dataclass
class StorageElementDiscoveryResult:
    """
    Результат auto-discovery storage element.

    Содержит все данные, полученные от storage element
    через его /api/v1/info endpoint.
    """
    # Идентификация
    name: str
    display_name: str
    version: str

    # Режим и тип
    mode: str
    storage_type: str
    base_path: str

    # Емкость
    capacity_bytes: int
    used_bytes: int
    file_count: int

    # Статус
    status: str

    # Service Discovery (Sequential Fill)
    priority: int
    element_id: str

    # URL источника
    api_url: str


class StorageDiscoveryService:
    """
    Сервис для auto-discovery storage elements.

    Функции:
    - Получение информации о storage element по URL
    - Валидация доступности storage element
    - Парсинг и валидация ответа от /api/v1/info endpoint
    """

    # Настройки по умолчанию
    DEFAULT_TIMEOUT_SECONDS = 10
    INFO_ENDPOINT_PATH = "/api/v1/info"

    # Обязательные поля в ответе
    REQUIRED_FIELDS = {
        "name", "display_name", "version", "mode",
        "storage_type", "base_path", "capacity_bytes",
        "used_bytes", "file_count", "status",
        "priority", "element_id"  # Service Discovery (Sequential Fill)
    }

    def __init__(self, timeout_seconds: Optional[int] = None):
        """
        Инициализация сервиса.

        Args:
            timeout_seconds: Таймаут для HTTP запросов (секунды)
        """
        self.timeout_seconds = timeout_seconds or self.DEFAULT_TIMEOUT_SECONDS

    def _normalize_url(self, api_url: str) -> str:
        """
        Нормализация URL storage element.

        Удаляет trailing slash и добавляет схему если отсутствует.

        Args:
            api_url: Исходный URL

        Returns:
            str: Нормализованный URL
        """
        url = api_url.strip()

        # Удаляем trailing slash
        url = url.rstrip("/")

        # Добавляем схему если отсутствует
        if not url.startswith(("http://", "https://")):
            url = f"http://{url}"

        return url

    def _build_info_url(self, api_url: str) -> str:
        """
        Построение полного URL для /api/v1/info endpoint.

        Args:
            api_url: Базовый URL storage element

        Returns:
            str: Полный URL до info endpoint
        """
        base_url = self._normalize_url(api_url)
        return f"{base_url}{self.INFO_ENDPOINT_PATH}"

    def _validate_response(self, data: dict, api_url: str) -> None:
        """
        Валидация ответа от storage element.

        Проверяет наличие всех обязательных полей.

        Args:
            data: JSON ответ от storage element
            api_url: URL для включения в ошибку

        Raises:
            StorageElementInvalidResponseError: Если ответ невалидный
        """
        missing_fields = self.REQUIRED_FIELDS - set(data.keys())
        if missing_fields:
            raise StorageElementInvalidResponseError(
                api_url=api_url,
                reason=f"Отсутствуют обязательные поля: {', '.join(missing_fields)}"
            )

        # Валидация типов данных
        try:
            # Проверяем числовые поля
            int(data["capacity_bytes"])
            int(data["used_bytes"])
            int(data["file_count"])
            int(data["priority"])
        except (ValueError, TypeError) as e:
            raise StorageElementInvalidResponseError(
                api_url=api_url,
                reason=f"Неверный тип данных в числовых полях: {e}"
            )

        # Валидация mode
        valid_modes = {"edit", "rw", "ro", "ar"}
        if data["mode"] not in valid_modes:
            raise StorageElementInvalidResponseError(
                api_url=api_url,
                reason=f"Неверный mode: {data['mode']}. Допустимые: {valid_modes}"
            )

        # Валидация storage_type
        valid_types = {"local", "s3"}
        if data["storage_type"] not in valid_types:
            raise StorageElementInvalidResponseError(
                api_url=api_url,
                reason=f"Неверный storage_type: {data['storage_type']}. Допустимые: {valid_types}"
            )

    async def discover_storage_element(
        self,
        api_url: str
    ) -> StorageElementDiscoveryResult:
        """
        Получить информацию о storage element по URL.

        Выполняет HTTP GET запрос к /api/v1/info endpoint
        и возвращает структурированный результат.

        Args:
            api_url: URL API storage element

        Returns:
            StorageElementDiscoveryResult: Информация о storage element

        Raises:
            StorageElementUnreachableError: Storage element недоступен
            StorageElementInvalidResponseError: Невалидный ответ
            StorageElementTimeoutError: Превышен timeout
        """
        info_url = self._build_info_url(api_url)
        normalized_url = self._normalize_url(api_url)

        logger.info(f"Выполняю discovery storage element: {info_url}")

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(info_url)

                if response.status_code != 200:
                    raise StorageElementUnreachableError(
                        api_url=normalized_url,
                        reason=f"HTTP {response.status_code}: {response.text[:200]}"
                    )

                try:
                    data = response.json()
                except Exception as e:
                    raise StorageElementInvalidResponseError(
                        api_url=normalized_url,
                        reason=f"Ответ не является валидным JSON: {e}"
                    )

                # Валидируем структуру ответа
                self._validate_response(data, normalized_url)

                # Формируем результат
                result = StorageElementDiscoveryResult(
                    name=str(data["name"]),
                    display_name=str(data["display_name"]),
                    version=str(data["version"]),
                    mode=str(data["mode"]),
                    storage_type=str(data["storage_type"]),
                    base_path=str(data["base_path"]),
                    capacity_bytes=int(data["capacity_bytes"]),
                    used_bytes=int(data["used_bytes"]),
                    file_count=int(data["file_count"]),
                    status=str(data["status"]),
                    priority=int(data["priority"]),
                    element_id=str(data["element_id"]),
                    api_url=normalized_url
                )

                logger.info(
                    f"Discovery успешен для {normalized_url}: "
                    f"name={result.display_name}, mode={result.mode}, "
                    f"type={result.storage_type}"
                )

                return result

        except httpx.TimeoutException:
            logger.warning(f"Timeout при запросе к {info_url}")
            raise StorageElementTimeoutError(
                api_url=normalized_url,
                timeout_seconds=self.timeout_seconds
            )

        except httpx.ConnectError as e:
            logger.warning(f"Ошибка подключения к {info_url}: {e}")
            raise StorageElementUnreachableError(
                api_url=normalized_url,
                reason=f"Ошибка подключения: {e}"
            )

        except httpx.HTTPError as e:
            logger.warning(f"HTTP ошибка при запросе к {info_url}: {e}")
            raise StorageElementUnreachableError(
                api_url=normalized_url,
                reason=f"HTTP ошибка: {e}"
            )

        except (StorageElementDiscoveryError,):
            # Пробрасываем наши исключения дальше
            raise

        except Exception as e:
            logger.error(f"Неожиданная ошибка при discovery {info_url}: {e}")
            raise StorageElementDiscoveryError(
                message=f"Неожиданная ошибка: {e}",
                api_url=normalized_url
            )

    async def validate_storage_element_url(self, api_url: str) -> bool:
        """
        Проверить доступность storage element по URL.

        Выполняет легкий health check без полного discovery.

        Args:
            api_url: URL API storage element

        Returns:
            bool: True если storage element доступен
        """
        try:
            await self.discover_storage_element(api_url)
            return True
        except StorageElementDiscoveryError:
            return False


# Глобальный экземпляр сервиса
storage_discovery_service = StorageDiscoveryService()
