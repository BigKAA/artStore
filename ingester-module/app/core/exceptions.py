"""
Ingester Module - Custom Exceptions.

Определяет специфичные исключения для модуля.
"""

from typing import Optional


class IngesterException(Exception):
    """Базовое исключение для Ingester Module."""

    def __init__(self, message: str, details: Optional[dict] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


# Authentication Exceptions
class AuthenticationException(IngesterException):
    """Базовое исключение аутентификации."""
    pass


class InvalidTokenException(AuthenticationException):
    """Невалидный JWT токен."""
    pass


class TokenExpiredException(AuthenticationException):
    """Истекший JWT токен."""
    pass


class InsufficientPermissionsException(AuthenticationException):
    """Недостаточно прав для операции."""
    pass


# Upload Exceptions
class UploadException(IngesterException):
    """Базовое исключение загрузки файлов."""
    pass


class FileSizeLimitExceededException(UploadException):
    """Превышен лимит размера файла."""
    pass


class StorageElementUnavailableException(UploadException):
    """Storage Element недоступен."""
    pass


class NoAvailableStorageException(UploadException):
    """
    Нет доступного Storage Element для загрузки.

    Sprint 14: Возникает когда StorageSelector не может найти подходящий SE
    (все SE недоступны, переполнены или не соответствуют требуемому режиму).
    """
    pass


class InsufficientStorageException(UploadException):
    """
    Storage Element не имеет достаточно места (HTTP 507).

    Sprint 17: Триггерит lazy update в CapacityMonitor и retry на другой SE.

    Attributes:
        storage_element_id: ID SE который вернул 507
        required_bytes: Запрошенный размер файла
        available_bytes: Доступное место (если известно)
    """

    def __init__(
        self,
        message: str,
        storage_element_id: str,
        required_bytes: int = 0,
        available_bytes: int = 0,
        details: dict = None
    ):
        super().__init__(message, details)
        self.storage_element_id = storage_element_id
        self.required_bytes = required_bytes
        self.available_bytes = available_bytes


class InvalidFileTypeException(UploadException):
    """Недопустимый тип файла."""
    pass


# Service Discovery Exceptions
class ServiceDiscoveryException(IngesterException):
    """Ошибка Service Discovery."""
    pass


class StorageElementNotFoundException(ServiceDiscoveryException):
    """Storage Element не найден в Service Discovery."""
    pass


# Circuit Breaker Exceptions
class CircuitBreakerOpenException(IngesterException):
    """Circuit Breaker открыт, сервис недоступен."""
    pass
