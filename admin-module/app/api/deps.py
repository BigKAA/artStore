"""
Общие зависимости для API endpoints.
Используются для внедрения зависимостей (Dependency Injection) в FastAPI endpoints.
"""
from typing import AsyncGenerator, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.models.user import User
from app.db.session import get_db


# OAuth2 bearer token scheme для Swagger UI
security = HTTPBearer(auto_error=False)


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """
    Dependency для получения текущего пользователя (опционально).
    Возвращает None если токен отсутствует или невалиден.

    Args:
        credentials: Bearer token из Authorization header
        db: Database сессия

    Returns:
        Optional[User]: Пользователь или None

    Usage:
        @router.get("/some-endpoint")
        async def endpoint(user: Optional[User] = Depends(get_current_user_optional)):
            if user:
                # Пользователь авторизован
            else:
                # Анонимный доступ
    """
    if credentials is None:
        return None

    try:
        token = credentials.credentials
        payload = decode_token(token)
        user_id: str = payload.get("sub")

        if user_id is None:
            return None

        # Загружаем пользователя из БД
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if user is None or not user.is_active:
            return None

        return user

    except (JWTError, ValueError, KeyError):
        return None


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Dependency для получения текущего аутентифицированного пользователя.
    Возвращает 401 если токен отсутствует или невалиден.

    Args:
        credentials: Bearer token из Authorization header
        db: Database сессия

    Returns:
        User: Текущий пользователь

    Raises:
        HTTPException: 401 если токен невалиден или пользователь не найден

    Usage:
        @router.get("/protected-endpoint")
        async def endpoint(current_user: User = Depends(get_current_user)):
            # Пользователь обязательно авторизован
            return {"user": current_user.username}
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется аутентификация",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        token = credentials.credentials
        payload = decode_token(token)
        user_id: str = payload.get("sub")

        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Невалидный токен: отсутствует ID пользователя",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Загружаем пользователя из БД
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Пользователь не найден",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Учетная запись пользователя деактивирована",
            )

        return user

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный токен",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный формат токена",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Dependency для проверки, что текущий пользователь - администратор.

    Args:
        current_user: Текущий пользователь

    Returns:
        User: Пользователь с правами администратора

    Raises:
        HTTPException: 403 если пользователь не администратор

    Usage:
        @router.post("/admin-only-endpoint")
        async def endpoint(admin: User = Depends(get_current_admin_user)):
            # Только администраторы могут вызвать этот endpoint
            return {"message": "Admin operation"}
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Требуются права администратора",
        )
    return current_user


async def get_current_system_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Dependency для проверки, что текущий пользователь - системный администратор.
    Системные пользователи имеют полные права и защищены от удаления.

    Args:
        current_user: Текущий пользователь

    Returns:
        User: Пользователь с системными правами

    Raises:
        HTTPException: 403 если пользователь не системный администратор

    Usage:
        @router.delete("/critical-operation")
        async def endpoint(sysadmin: User = Depends(get_current_system_user)):
            # Только системные администраторы
            return {"message": "Critical operation"}
    """
    if not current_user.is_system:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Требуются системные права администратора",
        )
    return current_user
