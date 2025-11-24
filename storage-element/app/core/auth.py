"""
JWT Authentication и Authorization для Storage Element.

Реализует:
- JWT token validation с RS256
- RBAC (Role-Based Access Control)
- Permission checking для файловых операций
"""

from typing import Optional, List, Set
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

import jwt
from jwt import PyJWTError
from pydantic import BaseModel, Field

from app.core.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)
config = get_config()


class UserRole(str, Enum):
    """Роли пользователей в системе."""

    ADMIN = "admin"  # Полный доступ к системе
    USER = "user"  # Стандартный пользователь
    READONLY = "readonly"  # Только чтение
    OPERATOR = "operator"  # Оператор хранилища (управление режимами)


class Permission(str, Enum):
    """Разрешения для файловых операций."""

    # File operations
    FILE_CREATE = "file:create"
    FILE_READ = "file:read"
    FILE_UPDATE = "file:update"
    FILE_DELETE = "file:delete"
    FILE_SEARCH = "file:search"

    # Metadata operations
    METADATA_READ = "metadata:read"
    METADATA_UPDATE = "metadata:update"

    # Storage mode operations
    MODE_READ = "mode:read"
    MODE_TRANSITION = "mode:transition"

    # Administrative operations
    ADMIN_USERS = "admin:users"
    ADMIN_STORAGE = "admin:storage"
    ADMIN_SYSTEM = "admin:system"


# Матрица разрешений для ролей
ROLE_PERMISSIONS: dict[UserRole, Set[Permission]] = {
    UserRole.ADMIN: {
        # Полный доступ ко всем операциям
        Permission.FILE_CREATE,
        Permission.FILE_READ,
        Permission.FILE_UPDATE,
        Permission.FILE_DELETE,
        Permission.FILE_SEARCH,
        Permission.METADATA_READ,
        Permission.METADATA_UPDATE,
        Permission.MODE_READ,
        Permission.MODE_TRANSITION,
        Permission.ADMIN_USERS,
        Permission.ADMIN_STORAGE,
        Permission.ADMIN_SYSTEM,
    },
    UserRole.OPERATOR: {
        # Управление режимами и чтение файлов
        Permission.FILE_READ,
        Permission.FILE_SEARCH,
        Permission.METADATA_READ,
        Permission.MODE_READ,
        Permission.MODE_TRANSITION,
        Permission.ADMIN_STORAGE,
    },
    UserRole.USER: {
        # Основные файловые операции
        Permission.FILE_CREATE,
        Permission.FILE_READ,
        Permission.FILE_UPDATE,
        Permission.FILE_DELETE,
        Permission.FILE_SEARCH,
        Permission.METADATA_READ,
        Permission.METADATA_UPDATE,
        Permission.MODE_READ,
    },
    UserRole.READONLY: {
        # Только чтение
        Permission.FILE_READ,
        Permission.FILE_SEARCH,
        Permission.METADATA_READ,
        Permission.MODE_READ,
    },
}


class TokenPayload(BaseModel):
    """JWT token payload модель."""

    sub: str = Field(..., description="User ID (subject)")
    username: str = Field(..., description="Username")
    roles: List[str] = Field(default_factory=list, description="User roles")
    exp: int = Field(..., description="Expiration timestamp")
    iat: int = Field(..., description="Issued at timestamp")

    # Optional fields
    email: Optional[str] = Field(None, description="User email")
    full_name: Optional[str] = Field(None, description="User full name")


class User(BaseModel):
    """Authenticated user модель."""

    user_id: str = Field(..., description="Unique user ID")
    username: str
    roles: List[UserRole]
    email: Optional[str] = None
    full_name: Optional[str] = None

    def has_role(self, role: UserRole) -> bool:
        """
        Проверка наличия роли у пользователя.

        Args:
            role: Роль для проверки

        Returns:
            bool: True если роль есть
        """
        return role in self.roles

    def has_any_role(self, roles: List[UserRole]) -> bool:
        """
        Проверка наличия хотя бы одной роли из списка.

        Args:
            roles: Список ролей для проверки

        Returns:
            bool: True если есть хотя бы одна роль
        """
        return any(role in self.roles for role in roles)

    def has_permission(self, permission: Permission) -> bool:
        """
        Проверка наличия разрешения у пользователя.

        Проверяет все роли пользователя и возвращает True,
        если хотя бы одна роль имеет требуемое разрешение.

        Args:
            permission: Разрешение для проверки

        Returns:
            bool: True если разрешение есть
        """
        for role in self.roles:
            if permission in ROLE_PERMISSIONS.get(role, set()):
                return True
        return False

    def has_any_permission(self, permissions: List[Permission]) -> bool:
        """
        Проверка наличия хотя бы одного разрешения из списка.

        Args:
            permissions: Список разрешений для проверки

        Returns:
            bool: True если есть хотя бы одно разрешение
        """
        return any(self.has_permission(perm) for perm in permissions)

    def has_all_permissions(self, permissions: List[Permission]) -> bool:
        """
        Проверка наличия всех разрешений из списка.

        Args:
            permissions: Список разрешений для проверки

        Returns:
            bool: True если есть все разрешения
        """
        return all(self.has_permission(perm) for perm in permissions)

    @property
    def is_admin(self) -> bool:
        """Проверка является ли пользователь администратором."""
        return self.has_role(UserRole.ADMIN)

    @property
    def all_permissions(self) -> Set[Permission]:
        """Получение всех разрешений пользователя."""
        permissions: Set[Permission] = set()
        for role in self.roles:
            permissions.update(ROLE_PERMISSIONS.get(role, set()))
        return permissions


class AuthenticationError(Exception):
    """Ошибка аутентификации."""
    pass


class AuthorizationError(Exception):
    """Ошибка авторизации (недостаточно прав)."""
    pass


class JWTValidator:
    """
    JWT token validator с RS256.

    Validates JWT tokens using public key from Admin Module.
    """

    def __init__(self):
        """Initialize validator с загрузкой публичного ключа."""
        self.config = config
        self.logger = logger
        self.algorithm = config.auth.jwt_algorithm
        self._public_key: Optional[str] = None

    def _load_public_key(self) -> str:
        """
        Загрузка публичного RSA ключа из файла.

        Returns:
            str: Public key PEM content

        Raises:
            FileNotFoundError: Если ключ не найден
        """
        if self._public_key is not None:
            return self._public_key

        key_path = Path(self.config.auth.jwt_public_key_path)

        if not key_path.exists():
            error_msg = f"JWT public key not found: {key_path}"
            self.logger.error("JWT public key missing", path=str(key_path))
            raise FileNotFoundError(error_msg)

        with open(key_path, 'r') as f:
            self._public_key = f.read()

        self.logger.info("JWT public key loaded", path=str(key_path))
        return self._public_key

    def validate_token(self, token: str) -> TokenPayload:
        """
        Валидация JWT token и извлечение payload.

        Args:
            token: JWT token string (без "Bearer " prefix)

        Returns:
            TokenPayload: Decoded и validated token payload

        Raises:
            AuthenticationError: Invalid token, expired, или другие ошибки
        """
        try:
            # Загрузка публичного ключа
            public_key = self._load_public_key()

            # Декодирование и валидация токена
            payload = jwt.decode(
                token,
                public_key,
                algorithms=[self.algorithm],
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_iat": True,
                }
            )

            # Валидация структуры payload
            token_payload = TokenPayload(**payload)

            # Проверка что токен не истек (дополнительная проверка)
            exp_timestamp = token_payload.exp
            now_timestamp = int(datetime.now(timezone.utc).timestamp())

            if exp_timestamp < now_timestamp:
                raise AuthenticationError("Token has expired")

            self.logger.debug(
                "JWT token validated",
                user_id=token_payload.sub,
                username=token_payload.username
            )

            return token_payload

        except jwt.ExpiredSignatureError:
            self.logger.warning("Expired JWT token")
            raise AuthenticationError("Token has expired")

        except jwt.InvalidTokenError as e:
            self.logger.warning("Invalid JWT token", error=str(e))
            raise AuthenticationError(f"Invalid token: {str(e)}")

        except FileNotFoundError:
            # Re-raise file not found
            raise

        except Exception as e:
            self.logger.error("JWT validation error", error=str(e))
            raise AuthenticationError(f"Token validation failed: {str(e)}")

    def create_user_from_token(self, token_payload: TokenPayload) -> User:
        """
        Создание User объекта из validated token payload.

        Args:
            token_payload: Validated JWT payload

        Returns:
            User: User object с ролями и разрешениями
        """
        # Конвертация строковых ролей в enum
        roles: List[UserRole] = []
        for role_str in token_payload.roles:
            try:
                role = UserRole(role_str.lower())
                roles.append(role)
            except ValueError:
                self.logger.warning(
                    "Unknown role in token",
                    role=role_str,
                    user=token_payload.username
                )

        # Если нет ролей, назначаем USER по умолчанию
        if not roles:
            roles = [UserRole.USER]
            self.logger.info(
                "No roles in token, assigned USER role",
                user=token_payload.username
            )

        return User(
            user_id=token_payload.sub,
            username=token_payload.username,
            roles=roles,
            email=token_payload.email,
            full_name=token_payload.full_name
        )


# Global validator instance
_validator: Optional[JWTValidator] = None


def get_jwt_validator() -> JWTValidator:
    """
    Получение глобального JWT validator instance (singleton).

    Returns:
        JWTValidator: Global validator
    """
    global _validator
    if _validator is None:
        _validator = JWTValidator()
    return _validator


def validate_token_and_get_user(token: str) -> User:
    """
    Convenience функция для валидации токена и получения пользователя.

    Args:
        token: JWT token string

    Returns:
        User: Authenticated user

    Raises:
        AuthenticationError: Invalid или expired token
    """
    validator = get_jwt_validator()
    token_payload = validator.validate_token(token)
    return validator.create_user_from_token(token_payload)


def check_permission(user: User, permission: Permission) -> None:
    """
    Проверка разрешения у пользователя с выбросом exception.

    Args:
        user: Authenticated user
        permission: Требуемое разрешение

    Raises:
        AuthorizationError: Если разрешения нет
    """
    if not user.has_permission(permission):
        logger.warning(
            "Permission denied",
            user=user.username,
            user_id=user.user_id,
            permission=permission.value,
            user_permissions=[p.value for p in user.all_permissions]
        )
        raise AuthorizationError(
            f"User {user.username} does not have permission: {permission.value}"
        )


def check_any_permission(user: User, permissions: List[Permission]) -> None:
    """
    Проверка наличия хотя бы одного разрешения с выбросом exception.

    Args:
        user: Authenticated user
        permissions: Список требуемых разрешений (хотя бы одно)

    Raises:
        AuthorizationError: Если нет ни одного разрешения
    """
    if not user.has_any_permission(permissions):
        logger.warning(
            "Permission denied (none of required)",
            user=user.username,
            user_id=user.user_id,
            required_permissions=[p.value for p in permissions],
            user_permissions=[p.value for p in user.all_permissions]
        )
        raise AuthorizationError(
            f"User {user.username} does not have any of required permissions"
        )


def check_role(user: User, role: UserRole) -> None:
    """
    Проверка роли у пользователя с выбросом exception.

    Args:
        user: Authenticated user
        role: Требуемая роль

    Raises:
        AuthorizationError: Если роли нет
    """
    if not user.has_role(role):
        logger.warning(
            "Role check failed",
            user=user.username,
            user_id=user.user_id,
            required_role=role.value,
            user_roles=[r.value for r in user.roles]
        )
        raise AuthorizationError(
            f"User {user.username} does not have required role: {role.value}"
        )
