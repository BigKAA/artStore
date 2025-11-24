"""
FastAPI dependencies для authentication и authorization.

Предоставляет зависимости для:
- Извлечения JWT токена из headers
- Валидации токена и получения User
- Проверки разрешений и ролей
"""

from typing import Optional, List
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.auth import (
    User,
    UserRole,
    Permission,
    validate_token_and_get_user,
    check_permission,
    check_any_permission,
    check_role,
    AuthenticationError,
    AuthorizationError,
)
from app.core.logging import get_logger

logger = get_logger(__name__)

# HTTP Bearer token security scheme
# Два разных объекта для обязательной и опциональной аутентификации
# auto_error=True генерирует 403, но глобальный exception handler в main.py заменит на 401
security_required = HTTPBearer(auto_error=True)
security_optional = HTTPBearer(auto_error=False)


async def get_token_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional)
) -> Optional[str]:
    """
    Извлечение JWT токена из Authorization header (optional).

    Args:
        credentials: HTTP Bearer credentials

    Returns:
        Optional[str]: JWT token или None если не предоставлен
    """
    if credentials is None:
        return None

    return credentials.credentials


async def get_token(
    credentials: HTTPAuthorizationCredentials = Depends(security_required)
) -> str:
    """
    Извлечение JWT токена из Authorization header (required).

    Args:
        credentials: HTTP Bearer credentials

    Returns:
        str: JWT token

    Raises:
        HTTPException 401: Если токен не предоставлен
        (автоматически через HTTPBearer + exception handler в main.py)
    """
    # С auto_error=True, credentials никогда не будет None
    # HTTPBearer сгенерирует 403, но exception handler заменит на 401
    return credentials.credentials


async def get_current_user(token: str = Depends(get_token)) -> User:
    """
    Получение текущего authenticated пользователя из JWT токена.

    Args:
        token: JWT token

    Returns:
        User: Authenticated user

    Raises:
        HTTPException 401: Invalid или expired token
    """
    try:
        user = validate_token_and_get_user(token)

        logger.debug(
            "User authenticated",
            user_id=user.user_id,
            username=user.username,
            roles=[r.value for r in user.roles]
        )

        return user

    except AuthenticationError as e:
        logger.warning("Authentication failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.error("Unexpected authentication error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_optional(
    token: Optional[str] = Depends(get_token_optional)
) -> Optional[User]:
    """
    Получение текущего пользователя (optional).

    Используется для endpoints, где аутентификация необязательна.

    Args:
        token: Optional JWT token

    Returns:
        Optional[User]: User или None если не authenticated
    """
    if token is None:
        return None

    try:
        return validate_token_and_get_user(token)
    except AuthenticationError:
        # Token invalid, но endpoint позволяет anonymous access
        return None


def require_permission(permission: Permission):
    """
    Dependency factory для проверки конкретного разрешения.

    Args:
        permission: Требуемое разрешение

    Returns:
        Dependency function

    Example:
        @app.get("/files", dependencies=[Depends(require_permission(Permission.FILE_READ))])
        async def list_files():
            ...
    """

    async def check(user: User = Depends(get_current_user)) -> User:
        try:
            check_permission(user, permission)
            return user
        except AuthorizationError as e:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(e)
            )

    return check


def require_any_permission(permissions: List[Permission]):
    """
    Dependency factory для проверки хотя бы одного разрешения из списка.

    Args:
        permissions: Список разрешений (хотя бы одно требуется)

    Returns:
        Dependency function

    Example:
        @app.post("/files", dependencies=[Depends(require_any_permission([
            Permission.FILE_CREATE,
            Permission.ADMIN_STORAGE
        ]))])
        async def create_file():
            ...
    """

    async def check(user: User = Depends(get_current_user)) -> User:
        try:
            check_any_permission(user, permissions)
            return user
        except AuthorizationError as e:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(e)
            )

    return check


def require_role(role: UserRole):
    """
    Dependency factory для проверки конкретной роли.

    Args:
        role: Требуемая роль

    Returns:
        Dependency function

    Example:
        @app.post("/admin/system", dependencies=[Depends(require_role(UserRole.ADMIN))])
        async def system_operation():
            ...
    """

    async def check(user: User = Depends(get_current_user)) -> User:
        try:
            check_role(user, role)
            return user
        except AuthorizationError as e:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(e)
            )

    return check


def require_any_role(roles: List[UserRole]):
    """
    Dependency factory для проверки хотя бы одной роли из списка.

    Args:
        roles: Список ролей (хотя бы одна требуется)

    Returns:
        Dependency function

    Example:
        @app.get("/storage/manage", dependencies=[Depends(require_any_role([
            UserRole.ADMIN,
            UserRole.OPERATOR
        ]))])
        async def manage_storage():
            ...
    """

    async def check(user: User = Depends(get_current_user)) -> User:
        if not user.has_any_role(roles):
            logger.warning(
                "Role check failed (none of required)",
                user=user.username,
                required_roles=[r.value for r in roles],
                user_roles=[r.value for r in user.roles]
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User does not have any of required roles"
            )
        return user

    return check


# Convenience dependencies для часто используемых проверок
async def require_admin(user: User = Depends(get_current_user)) -> User:
    """
    Требует роль ADMIN.

    Convenience dependency для проверки администратора.
    """
    try:
        check_role(user, UserRole.ADMIN)
        return user
    except AuthorizationError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )


async def require_operator_or_admin(user: User = Depends(get_current_user)) -> User:
    """
    Требует роль OPERATOR или ADMIN.

    Convenience dependency для операций управления storage.
    """
    if not user.has_any_role([UserRole.ADMIN, UserRole.OPERATOR]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator or operator role required"
        )
    return user
