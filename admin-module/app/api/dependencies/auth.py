"""
FastAPI Dependencies для аутентификации и авторизации.
Используются в эндпоинтах для проверки JWT токенов и прав доступа.

Sprint 15: Исправлен импорт моделей - используем ServiceAccount вместо несуществующего User.
"""

from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.service_account import ServiceAccount, ServiceAccountRole, ServiceAccountStatus
from app.services.token_service import token_service

# HTTP Bearer схема для JWT токенов
security = HTTPBearer()


async def get_current_service_account(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> ServiceAccount:
    """
    Dependency для получения текущего Service Account из JWT токена.

    Args:
        credentials: HTTP Authorization credentials (Bearer token)
        db: Database session

    Returns:
        ServiceAccount: Текущий аутентифицированный Service Account

    Raises:
        HTTPException: 401 если токен невалиден или Service Account не найден
    """
    # Извлекаем токен
    token = credentials.credentials

    # Валидируем токен и получаем payload
    # Sprint 21: Поддержка типа токена "service_account" (унифицированный JWT из Sprint 20)
    try:
        # Сначала пробуем как service_account токен (OAuth 2.0 Client Credentials)
        payload = token_service.validate_token(token, token_type="service_account")
        if not payload:
            # Если не service_account, пробуем как access токен (Admin User)
            payload = token_service.validate_token(token, token_type="access")

        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token validation failed: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Получаем client_id из токена
    client_id = payload.get("client_id")
    if not client_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token does not contain client_id",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Получаем Service Account из базы
    stmt = select(ServiceAccount).where(ServiceAccount.client_id == client_id)
    result = await db.execute(stmt)
    service_account = result.scalar_one_or_none()

    if not service_account:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Service Account not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Проверяем что Service Account активен
    if service_account.status != ServiceAccountStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Service Account is {service_account.status.value}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return service_account


async def get_current_active_service_account(
    current_service_account: ServiceAccount = Depends(get_current_service_account)
) -> ServiceAccount:
    """
    Dependency для получения активного Service Account.

    Args:
        current_service_account: Текущий Service Account из токена

    Returns:
        ServiceAccount: Активный Service Account

    Raises:
        HTTPException: 403 если Service Account неактивен
    """
    if current_service_account.status != ServiceAccountStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Service Account is not active"
        )

    return current_service_account


def require_role(required_role: ServiceAccountRole):
    """
    Factory для создания dependency с проверкой роли.

    Args:
        required_role: Требуемая минимальная роль

    Returns:
        Dependency function для проверки роли
    """
    async def check_role(
        current_service_account: ServiceAccount = Depends(get_current_active_service_account)
    ) -> ServiceAccount:
        """
        Проверка что Service Account имеет требуемую роль.

        Args:
            current_service_account: Текущий Service Account

        Returns:
            ServiceAccount: Service Account с требуемой ролью

        Raises:
            HTTPException: 403 если роль недостаточна
        """
        # Иерархия ролей: ADMIN > AUDITOR > USER > READONLY
        role_hierarchy = {
            ServiceAccountRole.ADMIN: 4,
            ServiceAccountRole.AUDITOR: 3,
            ServiceAccountRole.USER: 2,
            ServiceAccountRole.READONLY: 1
        }

        account_level = role_hierarchy.get(current_service_account.role, 0)
        required_level = role_hierarchy.get(required_role, 0)

        if account_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required role: {required_role.value}"
            )

        return current_service_account

    return check_role


# Pre-configured dependencies для разных ролей
require_admin = require_role(ServiceAccountRole.ADMIN)
require_auditor = require_role(ServiceAccountRole.AUDITOR)
require_user = require_role(ServiceAccountRole.USER)
require_readonly = require_role(ServiceAccountRole.READONLY)


async def get_optional_current_service_account(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
    db: AsyncSession = Depends(get_db)
) -> Optional[ServiceAccount]:
    """
    Dependency для опционального получения Service Account.
    Не выбрасывает исключение если токен отсутствует.

    Args:
        credentials: HTTP Authorization credentials (опционально)
        db: Database session

    Returns:
        Optional[ServiceAccount]: Service Account если токен валиден, None иначе
    """
    if not credentials:
        return None

    try:
        # Пытаемся получить Service Account
        # Sprint 21: Поддержка типа токена "service_account" (унифицированный JWT из Sprint 20)
        payload = token_service.validate_token(credentials.credentials, token_type="service_account")
        if not payload:
            # Fallback на access токен для совместимости
            payload = token_service.validate_token(credentials.credentials, token_type="access")
        if not payload:
            return None

        client_id = payload.get("client_id")
        if not client_id:
            return None

        stmt = select(ServiceAccount).where(ServiceAccount.client_id == client_id)
        result = await db.execute(stmt)
        service_account = result.scalar_one_or_none()

        if not service_account or service_account.status != ServiceAccountStatus.ACTIVE:
            return None

        return service_account

    except Exception:
        # Игнорируем ошибки валидации токена
        return None
