"""
Query Module - API Dependencies.

FastAPI dependencies для:
- JWT authentication
- Database session management
- User context extraction
"""

import logging
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import jwt_validator, UserContext
from app.core.exceptions import InvalidTokenException, TokenExpiredException
from app.db.database import get_db_session

logger = logging.getLogger(__name__)


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None
) -> UserContext:
    """
    Извлечение текущего пользователя из JWT токена.

    Args:
        authorization: Authorization header (Bearer {token})

    Returns:
        UserContext: Контекст пользователя

    Raises:
        HTTPException: 401 если токен невалиден или отсутствует
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        # Извлечение токена из "Bearer {token}"
        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authorization header format",
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = parts[1]

        # Валидация JWT токена
        user_context = jwt_validator.validate_token(token)

        logger.debug(
            "User authenticated",
            extra={
                "user_id": user_context.user_id,
                "username": user_context.username,
                "role": user_context.role.value
            }
        )

        return user_context

    except InvalidTokenException as e:
        logger.warning(
            "Invalid token",
            extra={"error": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    except TokenExpiredException as e:
        logger.warning(
            "Token expired",
            extra={"error": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_optional_user(
    authorization: Annotated[str | None, Header()] = None
) -> UserContext | None:
    """
    Извлечение пользователя из токена (optional).

    Используется для endpoints доступных и для anonymous users.

    Args:
        authorization: Authorization header (Bearer {token})

    Returns:
        UserContext | None: Контекст пользователя или None
    """
    if not authorization:
        return None

    try:
        return await get_current_user(authorization)
    except HTTPException:
        return None


# Type aliases для FastAPI Depends
CurrentUser = Annotated[UserContext, Depends(get_current_user)]
OptionalUser = Annotated[UserContext | None, Depends(get_optional_user)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
