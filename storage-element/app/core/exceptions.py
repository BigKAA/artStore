"""
Кастомные исключения для Storage Element.

Иерархия исключений:
- StorageElementException (базовое)
  - StorageException (хранилище)
  - DatabaseException (БД)
  - AuthenticationException (аутентификация)
  - ValidationException (валидация)
"""

from typing import Optional


class StorageElementException(Exception):
    """Базовое исключение для всех ошибок Storage Element"""

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[dict] = None
    ):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)


class StorageException(StorageElementException):
    """Исключения связанные с файловым хранилищем"""
    pass


class InsufficientStorageException(StorageException):
    """Недостаточно места в хранилище"""

    def __init__(
        self,
        required_bytes: int,
        available_bytes: int
    ):
        message = (
            f"Недостаточно места в хранилище. "
            f"Требуется: {required_bytes / (1024**3):.2f} GB, "
            f"Доступно: {available_bytes / (1024**3):.2f} GB"
        )
        super().__init__(
            message=message,
            error_code="INSUFFICIENT_STORAGE",
            details={
                "required_bytes": required_bytes,
                "available_bytes": available_bytes
            }
        )


class FileNotFoundException(StorageException):
    """Файл не найден в хранилище"""

    def __init__(self, file_id: str):
        super().__init__(
            message=f"Файл с ID '{file_id}' не найден",
            error_code="FILE_NOT_FOUND",
            details={"file_id": file_id}
        )


class FileAlreadyExistsException(StorageException):
    """Файл уже существует"""

    def __init__(self, file_path: str):
        super().__init__(
            message=f"Файл уже существует: {file_path}",
            error_code="FILE_ALREADY_EXISTS",
            details={"file_path": file_path}
        )


class ArchivedFileAccessException(StorageException):
    """Попытка скачать файл из архивного хранилища"""

    def __init__(self, file_id: str):
        super().__init__(
            message=(
                f"Файл '{file_id}' перенесен в долговременное хранилище. "
                "Обратитесь к администратору для восстановления."
            ),
            error_code="ARCHIVED_FILE_ACCESS",
            details={"file_id": file_id}
        )


class InvalidStorageModeException(StorageException):
    """Операция недоступна в текущем режиме хранилища"""

    def __init__(self, operation: str, current_mode: str):
        super().__init__(
            message=f"Операция '{operation}' недоступна в режиме '{current_mode}'",
            error_code="INVALID_STORAGE_MODE",
            details={
                "operation": operation,
                "current_mode": current_mode
            }
        )


class DatabaseException(StorageElementException):
    """Исключения связанные с базой данных"""
    pass


class CacheInconsistencyException(DatabaseException):
    """Несоответствие между attr.json и кешем БД"""

    def __init__(self, file_id: str, details: str):
        super().__init__(
            message=f"Обнаружено несоответствие для файла '{file_id}': {details}",
            error_code="CACHE_INCONSISTENCY",
            details={
                "file_id": file_id,
                "inconsistency_details": details
            }
        )


class AuthenticationException(StorageElementException):
    """Исключения аутентификации"""
    pass


class InvalidTokenException(AuthenticationException):
    """Невалидный JWT токен"""

    def __init__(self, reason: str):
        super().__init__(
            message=f"Невалидный токен: {reason}",
            error_code="INVALID_TOKEN",
            details={"reason": reason}
        )


class TokenExpiredException(AuthenticationException):
    """JWT токен истек"""

    def __init__(self):
        super().__init__(
            message="Токен истек. Пожалуйста, обновите токен.",
            error_code="TOKEN_EXPIRED"
        )


class InsufficientPermissionsException(AuthenticationException):
    """Недостаточно прав для операции"""

    def __init__(self, required_role: str, user_role: str):
        super().__init__(
            message=f"Недостаточно прав. Требуется: {required_role}, текущая роль: {user_role}",
            error_code="INSUFFICIENT_PERMISSIONS",
            details={
                "required_role": required_role,
                "user_role": user_role
            }
        )


class ValidationException(StorageElementException):
    """Исключения валидации данных"""
    pass


class InvalidAttributeFileException(ValidationException):
    """Невалидный файл атрибутов"""

    def __init__(self, file_path: str, reason: str):
        super().__init__(
            message=f"Невалидный файл атрибутов '{file_path}': {reason}",
            error_code="INVALID_ATTRIBUTE_FILE",
            details={
                "file_path": file_path,
                "reason": reason
            }
        )


class WALException(StorageElementException):
    """Исключения Write-Ahead Log"""
    pass


class WALTransactionException(WALException):
    """Ошибка транзакции WAL"""

    def __init__(self, transaction_id: str, reason: str):
        super().__init__(
            message=f"Ошибка транзакции WAL '{transaction_id}': {reason}",
            error_code="WAL_TRANSACTION_ERROR",
            details={
                "transaction_id": transaction_id,
                "reason": reason
            }
        )
