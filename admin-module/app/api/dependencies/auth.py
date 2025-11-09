"""
FastAPI Dependencies для аутентификации и авторизации.
Используются в эндпоинтах для проверки JWT токенов и прав доступа.
"""

from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User, UserRole, UserStatus
from app.services.token_service import token_service
from app.services.auth_service import auth_service

# HTTP Bearer схема для JWT токенов
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Dependency для получения текущего пользователя из JWT токена.

    Args:
        credentials: HTTP Authorization credentials (Bearer token)
        db: Database session

    Returns:
        User: Текущий аутентифицированный пользователь

    Raises:
        HTTPException: 401 если токен невалиден или пользователь не найден
    """
    # Извлекаем токен
    token = credentials.credentials

    # Валидируем токен и получаем user_id
    user_id = token_service.get_user_id_from_token(token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Получаем пользователя из базы
    user = await auth_service.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Проверяем что пользователь активен
    if user.status != UserStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"User is {user.status.value}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Dependency для получения активного пользователя.

    Args:
        current_user: Текущий пользователь из токена

    Returns:
        User: Активный пользователь

    Raises:
        HTTPException: 403 если пользователь неактивен
    """
    if not current_user.can_login():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is not active"
        )

    return current_user


def require_role(required_role: UserRole):
    """
    Factory для создания dependency с проверкой роли.

    Args:
        required_role: Требуемая минимальная роль

    Returns:
        Dependency function для проверки роли
    """
    async def check_role(current_user: User = Depends(get_current_active_user)) -> User:
        """
        Проверка что пользователь имеет требуемую роль.

        Args:
            current_user: Текущий пользователь

        Returns:
            User: Пользователь с требуемой ролью

        Raises:
            HTTPException: 403 если роль недостаточна
        """
        # Иерархия ролей: ADMIN > OPERATOR > USER
        role_hierarchy = {
            UserRole.ADMIN: 3,
            UserRole.OPERATOR: 2,
            UserRole.USER: 1
        }

        user_level = role_hierarchy.get(current_user.role, 0)
        required_level = role_hierarchy.get(required_role, 0)

        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required role: {required_role.value}"
            )

        return current_user

    return check_role


# Pre-configured dependencies для разных ролей
require_admin = require_role(UserRole.ADMIN)
require_operator = require_role(UserRole.OPERATOR)
require_user = require_role(UserRole.USER)


async def get_optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """
    Dependency для опционального получения пользователя.
    Не выбрасывает исключение если токен отсутствует.

    Args:
        credentials: HTTP Authorization credentials (опционально)
        db: Database session

    Returns:
        Optional[User]: Пользователь если токен валиден, None иначе
    """
    if not credentials:
        return None

    try:
        # Пытаемся получить пользователя
        user_id = token_service.get_user_id_from_token(credentials.credentials)
        if not user_id:
            return None

        user = await auth_service.get_user_by_id(db, user_id)
        if not user or user.status != UserStatus.ACTIVE:
            return None

        return user

    except Exception:
        # Игнорируем ошибки валидации токена
        return None
