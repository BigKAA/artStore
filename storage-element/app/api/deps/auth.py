"""
FastAPI Dependencies для аутентификации и авторизации.

JWT Bearer Token валидация через публичный ключ RS256.
RBAC проверки для различных операций.
"""

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import UserContext, UserRole, jwt_validator

logger = logging.getLogger(__name__)

# Security scheme для Swagger UI
security = HTTPBearer(
    scheme_name="Bearer Token",
    description="JWT токен из Admin Module (Bearer <token>)"
)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]
) -> UserContext:
    """
    Получить текущего пользователя из JWT токена.

    Dependency для всех защищенных endpoints.
    Валидирует JWT токен через публичный ключ RS256.

    Args:
        credentials: Bearer token из Authorization header

    Returns:
        UserContext: Контекст текущего пользователя

    Raises:
        HTTPException: 401 если токен невалиден или истёк

    Примеры:
        >>> @app.get("/files")
        >>> async def list_files(user: Annotated[UserContext, Depends(get_current_user)]):
        ...     # user содержит sub, username, role
        ...     return {"user_id": user.sub}
    """
    token = credentials.credentials

    try:
        user_context = jwt_validator.validate_token(token)

        logger.debug(
            "User authenticated successfully",
            extra={
                "user_id": user_context.sub,
                "username": user_context.username,
                "role": user_context.role.value
            }
        )

        return user_context

    except Exception as e:
        logger.warning(
            f"Authentication failed: {e}",
            extra={"error": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"}
        )


async def require_admin(
    user: Annotated[UserContext, Depends(get_current_user)]
) -> UserContext:
    """
    Требовать роль ADMIN.

    Dependency для административных endpoints (смена режима, управление).

    Args:
        user: Текущий пользователь из get_current_user

    Returns:
        UserContext: Контекст администратора

    Raises:
        HTTPException: 403 если роль не ADMIN

    Примеры:
        >>> @app.post("/admin/mode")
        >>> async def change_mode(admin: Annotated[UserContext, Depends(require_admin)]):
        ...     # Только администраторы могут вызвать этот endpoint
        ...     return {"status": "mode_changed"}
    """
    if not user.is_admin:
        logger.warning(
            "Admin access denied",
            extra={
                "user_id": user.sub,
                "username": user.username,
                "role": user.role.value
            }
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    return user


async def require_operator_or_admin(
    user: Annotated[UserContext, Depends(get_current_user)]
) -> UserContext:
    """
    Требовать роль OPERATOR или ADMIN.

    Dependency для операционных endpoints (загрузка, удаление файлов в edit mode).

    Args:
        user: Текущий пользователь из get_current_user

    Returns:
        UserContext: Контекст оператора или администратора

    Raises:
        HTTPException: 403 если роль не OPERATOR или ADMIN

    Примеры:
        >>> @app.delete("/files/{file_id}")
        >>> async def delete_file(
        ...     file_id: UUID,
        ...     operator: Annotated[UserContext, Depends(require_operator_or_admin)]
        ... ):
        ...     # Только операторы и администраторы могут удалять файлы
        ...     return {"status": "deleted"}
    """
    if user.role not in [UserRole.OPERATOR, UserRole.ADMIN]:
        logger.warning(
            "Operator access denied",
            extra={
                "user_id": user.sub,
                "username": user.username,
                "role": user.role.value
            }
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator or admin access required"
        )

    return user


async def require_service_account(
    user: Annotated[UserContext, Depends(get_current_user)]
) -> UserContext:
    """
    Требовать тип Service Account.

    Dependency для системных endpoints (GC cleanup, inter-service communication).
    Service Accounts имеют token_type="service_account".

    Args:
        user: Текущий пользователь из get_current_user

    Returns:
        UserContext: Контекст Service Account

    Raises:
        HTTPException: 403 если не Service Account

    Примеры:
        >>> @app.delete("/gc/files/{file_id}")
        >>> async def gc_delete_file(
        ...     file_id: UUID,
        ...     service: Annotated[UserContext, Depends(require_service_account)]
        ... ):
        ...     # Только Service Accounts могут вызвать этот endpoint
        ...     return {"status": "deleted"}
    """
    if not user.is_service_account:
        logger.warning(
            "Service account access denied",
            extra={
                "user_id": user.sub,
                "username": user.username,
                "token_type": user.token_type,
                "role": user.role.value
            }
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Service account access required. Only service accounts can perform GC operations."
        )

    return user


# Type aliases для удобства использования
CurrentUser = Annotated[UserContext, Depends(get_current_user)]
AdminUser = Annotated[UserContext, Depends(require_admin)]
OperatorUser = Annotated[UserContext, Depends(require_operator_or_admin)]
ServiceAccount = Annotated[UserContext, Depends(require_service_account)]
