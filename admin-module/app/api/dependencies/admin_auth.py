"""
Admin Authentication Dependencies для защиты Admin UI endpoints.

Предоставляет dependencies для:
- JWT token validation (RS256)
- Current admin user extraction
- Role-based access control
"""

from typing import Annotated, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.token_service import TokenService
from app.models.admin_user import AdminUser, AdminRole

# HTTP Bearer token scheme для Swagger UI
security = HTTPBearer(
    scheme_name="Admin JWT",
    description="JWT token для аутентификации администраторов Admin UI (type=admin_user)"
)


async def get_current_admin_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: AsyncSession = Depends(get_db)
) -> AdminUser:
    """
    Dependency для получения текущего аутентифицированного администратора.

    Процесс:
    1. Извлечение JWT token из Authorization header
    2. Декодирование и валидация токена (RS256)
    3. Проверка типа токена (должен быть admin_user)
    4. Получение администратора из БД по username
    5. Проверка что аккаунт активен и не заблокирован

    Args:
        credentials: HTTP Bearer credentials с JWT token
        db: Database session

    Returns:
        AdminUser: Текущий аутентифицированный администратор

    Raises:
        HTTPException: 401 если токен невалиден или администратор не найден
        HTTPException: 403 если аккаунт заблокирован или отключен

    Example:
        @router.get("/protected")
        async def protected_endpoint(
            admin: AdminUser = Depends(get_current_admin_user)
        ):
            return {"username": admin.username}
    """
    token = credentials.credentials
    token_service = TokenService()

    try:
        # Декодирование и валидация JWT token
        payload = token_service.decode_token(token)

        # Проверка типа токена
        token_type = payload.get("type")
        if token_type != "admin_user":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Invalid token type: expected admin_user, got {token_type}",
                headers={"WWW-Authenticate": "Bearer"}
            )

        # Извлечение username из токена
        username = payload.get("sub")
        if not username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload: missing subject",
                headers={"WWW-Authenticate": "Bearer"}
            )

        # Получение администратора из БД
        result = await db.execute(
            select(AdminUser).where(AdminUser.username == username)
        )
        admin_user = result.scalar_one_or_none()

        if not admin_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Admin user not found",
                headers={"WWW-Authenticate": "Bearer"}
            )

        # Проверка что аккаунт активен
        if not admin_user.enabled:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is disabled",
                headers={"WWW-Authenticate": "Bearer"}
            )

        # Проверка что аккаунт не заблокирован
        if admin_user.is_locked():
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=f"Account is locked until {admin_user.locked_until.isoformat()}",
                headers={"WWW-Authenticate": "Bearer"}
            )

        return admin_user

    except HTTPException:
        # Re-raise HTTP exceptions как есть
        raise

    except Exception as e:
        # Все остальные ошибки (декодирование токена, signature validation, etc.)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"}
        )


async def get_current_active_admin(
    current_admin: Annotated[AdminUser, Depends(get_current_admin_user)]
) -> AdminUser:
    """
    Dependency для получения текущего активного администратора.

    Дополнительно проверяет что аккаунт enabled (уже проверяется в get_current_admin_user).
    Полезно для явного указания требования активного аккаунта.

    Args:
        current_admin: Текущий администратор из get_current_admin_user

    Returns:
        AdminUser: Активный администратор

    Raises:
        HTTPException: 403 если аккаунт неактивен
    """
    if not current_admin.enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive admin account"
        )
    return current_admin


class RoleChecker:
    """
    Role-based access control dependency.

    Проверяет что текущий администратор имеет требуемую роль.

    Example:
        @router.delete("/admin-users/{user_id}")
        async def delete_admin_user(
            admin: AdminUser = Depends(RoleChecker([AdminRole.SUPER_ADMIN]))
        ):
            # Только SUPER_ADMIN может удалять администраторов
            ...
    """

    def __init__(self, required_roles: list[AdminRole]):
        """
        Инициализация RoleChecker.

        Args:
            required_roles: Список допустимых ролей
        """
        self.required_roles = required_roles

    async def __call__(
        self,
        current_admin: Annotated[AdminUser, Depends(get_current_admin_user)]
    ) -> AdminUser:
        """
        Проверка роли текущего администратора.

        Args:
            current_admin: Текущий администратор

        Returns:
            AdminUser: Администратор с требуемой ролью

        Raises:
            HTTPException: 403 если роль не соответствует требованиям
        """
        if current_admin.role not in self.required_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required roles: {[r.value for r in self.required_roles]}"
            )
        return current_admin


# Готовые dependencies для распространенных сценариев
require_super_admin = RoleChecker([AdminRole.SUPER_ADMIN])
require_admin = RoleChecker([AdminRole.SUPER_ADMIN, AdminRole.ADMIN])
require_any_admin = RoleChecker([AdminRole.SUPER_ADMIN, AdminRole.ADMIN, AdminRole.READONLY])


def require_role(role: AdminRole):
    """
    Фабричная функция для создания dependency для проверки конкретной роли.

    Args:
        role: Требуемая роль администратора

    Returns:
        RoleChecker: Dependency для FastAPI

    Example:
        @router.post("/admin-users")
        async def create_admin(
            admin: AdminUser = Depends(require_role(AdminRole.SUPER_ADMIN))
        ):
            # Только SUPER_ADMIN может создавать администраторов
            ...
    """
    return RoleChecker([role])
