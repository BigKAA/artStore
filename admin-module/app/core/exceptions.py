"""
Custom Exceptions для Admin Module.

Иерархия исключений для обработки ошибок в различных компонентах системы.
"""


class AdminModuleException(Exception):
    """Базовое исключение для Admin Module."""
    pass


# =============================================================================
# Storage Element Discovery Exceptions
# =============================================================================

class StorageElementDiscoveryError(AdminModuleException):
    """
    Базовое исключение для ошибок auto-discovery storage element.

    Возникает при проблемах с автоматическим обнаружением
    и получением информации от storage element.
    """
    def __init__(self, message: str, api_url: str | None = None):
        self.api_url = api_url
        super().__init__(message)


class StorageElementUnreachableError(StorageElementDiscoveryError):
    """
    Storage element недоступен по указанному URL.

    Возникает когда:
    - URL некорректен
    - Сервис не отвечает
    - Превышен timeout подключения
    - Сетевые проблемы
    """
    def __init__(self, api_url: str, reason: str | None = None):
        message = f"Storage element недоступен по URL: {api_url}"
        if reason:
            message += f". Причина: {reason}"
        super().__init__(message, api_url)
        self.reason = reason


class StorageElementInvalidResponseError(StorageElementDiscoveryError):
    """
    Невалидный ответ от storage element.

    Возникает когда:
    - Ответ не является валидным JSON
    - Отсутствуют обязательные поля
    - Неверные типы данных в ответе
    - Endpoint существует, но возвращает неожиданную структуру
    """
    def __init__(self, api_url: str, reason: str):
        message = f"Невалидный ответ от storage element ({api_url}): {reason}"
        super().__init__(message, api_url)
        self.reason = reason


class StorageElementTimeoutError(StorageElementDiscoveryError):
    """
    Превышен timeout при запросе к storage element.

    Возникает когда storage element не отвечает в течение
    заданного времени ожидания.
    """
    def __init__(self, api_url: str, timeout_seconds: int):
        message = f"Timeout ({timeout_seconds}s) при запросе к storage element: {api_url}"
        super().__init__(message, api_url)
        self.timeout_seconds = timeout_seconds


class StorageElementAlreadyExistsError(StorageElementDiscoveryError):
    """
    Storage element с таким URL уже существует в системе.

    Возникает при попытке добавить storage element
    с URL, который уже зарегистрирован.
    """
    def __init__(self, api_url: str):
        message = f"Storage element с URL {api_url} уже зарегистрирован"
        super().__init__(message, api_url)


# =============================================================================
# Storage Element Sync Exceptions
# =============================================================================

class StorageElementSyncError(AdminModuleException):
    """
    Базовое исключение для ошибок синхронизации storage element.
    """
    def __init__(self, message: str, storage_element_id: int | None = None):
        self.storage_element_id = storage_element_id
        super().__init__(message)


class StorageElementNotFoundError(StorageElementSyncError):
    """
    Storage element не найден в базе данных.
    """
    def __init__(self, storage_element_id: int):
        message = f"Storage element с ID {storage_element_id} не найден"
        super().__init__(message, storage_element_id)
