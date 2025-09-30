"""
Кастомные исключения для приложения.
Позволяют более точно обрабатывать ошибки и возвращать правильные HTTP статусы.
"""
from typing import Any, Dict, Optional


class AppException(Exception):
    """
    Базовое исключение приложения.
    Все кастомные исключения должны наследоваться от него.
    """

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


# Исключения аутентификации (401)
class AuthenticationException(AppException):
    """Базовое исключение для ошибок аутентификации"""

    def __init__(self, message: str = "Ошибка аутентификации", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=401, details=details)


class InvalidCredentialsException(AuthenticationException):
    """Неверные учетные данные"""

    def __init__(self, message: str = "Неверное имя пользователя или пароль"):
        super().__init__(message=message)


class InvalidTokenException(AuthenticationException):
    """Невалидный или истекший токен"""

    def __init__(self, message: str = "Токен невалиден или истек"):
        super().__init__(message=message)


class ExpiredTokenException(AuthenticationException):
    """Токен истек"""

    def __init__(self, message: str = "Срок действия токена истек"):
        super().__init__(message=message)


# Исключения авторизации (403)
class AuthorizationException(AppException):
    """Базовое исключение для ошибок авторизации"""

    def __init__(self, message: str = "Недостаточно прав", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=403, details=details)


class InsufficientPermissionsException(AuthorizationException):
    """Недостаточно прав для выполнения операции"""

    def __init__(self, message: str = "Недостаточно прав для выполнения этой операции"):
        super().__init__(message=message)


class ProtectedResourceException(AuthorizationException):
    """Попытка изменить защищенный ресурс"""

    def __init__(self, message: str = "Этот ресурс защищен и не может быть изменен"):
        super().__init__(message=message)


# Исключения не найдено (404)
class NotFoundException(AppException):
    """Базовое исключение для ненайденных ресурсов"""

    def __init__(self, message: str = "Ресурс не найден", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=404, details=details)


class UserNotFoundException(NotFoundException):
    """Пользователь не найден"""

    def __init__(self, username: Optional[str] = None, user_id: Optional[int] = None):
        if username:
            message = f"Пользователь '{username}' не найден"
        elif user_id:
            message = f"Пользователь с ID {user_id} не найден"
        else:
            message = "Пользователь не найден"
        super().__init__(message=message)


class StorageElementNotFoundException(NotFoundException):
    """Элемент хранилища не найден"""

    def __init__(self, element_id: Optional[int] = None):
        if element_id:
            message = f"Элемент хранилища с ID {element_id} не найден"
        else:
            message = "Элемент хранилища не найден"
        super().__init__(message=message)


# Исключения конфликта (409)
class ConflictException(AppException):
    """Базовое исключение для конфликтов"""

    def __init__(self, message: str = "Конфликт данных", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=409, details=details)


class UserAlreadyExistsException(ConflictException):
    """Пользователь уже существует"""

    def __init__(self, username: str):
        super().__init__(message=f"Пользователь '{username}' уже существует")


class StorageElementAlreadyExistsException(ConflictException):
    """Элемент хранилища уже существует"""

    def __init__(self, name: str):
        super().__init__(message=f"Элемент хранилища '{name}' уже существует")


# Исключения валидации (422)
class ValidationException(AppException):
    """Базовое исключение для ошибок валидации"""

    def __init__(self, message: str = "Ошибка валидации", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=422, details=details)


class WeakPasswordException(ValidationException):
    """Слабый пароль"""

    def __init__(self, message: str):
        super().__init__(message=message)


class InvalidEmailException(ValidationException):
    """Невалидный email"""

    def __init__(self, email: str):
        super().__init__(message=f"Невалидный email адрес: {email}")


class InvalidModeTransitionException(ValidationException):
    """Невалидный переход режима элемента хранилища"""

    def __init__(self, current_mode: str, target_mode: str):
        super().__init__(
            message=f"Невозможно перевести элемент хранилища из режима '{current_mode}' в '{target_mode}'"
        )


# Исключения сервера (500)
class ServerException(AppException):
    """Базовое исключение для серверных ошибок"""

    def __init__(self, message: str = "Внутренняя ошибка сервера", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=500, details=details)


class DatabaseException(ServerException):
    """Ошибка базы данных"""

    def __init__(self, message: str = "Ошибка базы данных", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, details=details)


class RedisException(ServerException):
    """Ошибка Redis"""

    def __init__(self, message: str = "Ошибка подключения к Redis", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, details=details)


class ExternalServiceException(ServerException):
    """Ошибка внешнего сервиса"""

    def __init__(self, service_name: str, message: str = "Ошибка внешнего сервиса"):
        super().__init__(message=f"{message}: {service_name}")


# Исключения rate limiting (429)
class RateLimitException(AppException):
    """Превышен лимит запросов"""

    def __init__(self, message: str = "Превышен лимит запросов. Попробуйте позже"):
        super().__init__(message=message, status_code=429)


# Исключения сервиса (503)
class ServiceUnavailableException(AppException):
    """Сервис временно недоступен"""

    def __init__(self, message: str = "Сервис временно недоступен"):
        super().__init__(message=message, status_code=503)


# Исключения LDAP
class LDAPException(AppException):
    """Ошибка LDAP аутентификации"""

    def __init__(self, message: str = "Ошибка LDAP аутентификации", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=500, details=details)


class LDAPConnectionException(LDAPException):
    """Ошибка подключения к LDAP серверу"""

    def __init__(self, message: str = "Не удалось подключиться к LDAP серверу"):
        super().__init__(message=message)


class LDAPBindException(LDAPException):
    """Ошибка bind к LDAP"""

    def __init__(self, message: str = "Ошибка аутентификации LDAP"):
        super().__init__(message=message)


# Исключения OAuth2
class OAuth2Exception(AppException):
    """Ошибка OAuth2 аутентификации"""

    def __init__(self, message: str = "Ошибка OAuth2 аутентификации", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=500, details=details)


class OAuth2ProviderException(OAuth2Exception):
    """Ошибка OAuth2 провайдера"""

    def __init__(self, provider: str, message: str = "Ошибка провайдера"):
        super().__init__(message=f"{message}: {provider}")


# Исключения Saga
class SagaException(AppException):
    """Ошибка выполнения Saga транзакции"""

    def __init__(self, message: str = "Ошибка выполнения транзакции", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=500, details=details)


class SagaTimeoutException(SagaException):
    """Превышено время ожидания Saga транзакции"""

    def __init__(self, saga_id: str):
        super().__init__(message=f"Превышено время ожидания транзакции {saga_id}")


class SagaCompensationException(SagaException):
    """Ошибка компенсации Saga транзакции"""

    def __init__(self, saga_id: str, step: str):
        super().__init__(message=f"Ошибка компенсации транзакции {saga_id} на шаге {step}")
