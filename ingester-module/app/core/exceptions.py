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
