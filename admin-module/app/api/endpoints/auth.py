"""
API endpoints для аутентификации.
"""
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.config import settings
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.db.models.user import User
from app.schemas.auth import (
    AccessTokenResponse,
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    RefreshTokenRequest,
    UserInfo,
)
from app.services.auth_service import auth_service
from app.services.audit_service import audit_service
from app.services.user_service import user_service
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.post("/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def login(
    credentials: LoginRequest, db: AsyncSession = Depends(deps.get_db)
) -> Dict[str, Any]:
    """
    Аутентификация пользователя (локальная или LDAP/OAuth2).

    **Процесс**:
    1. Проверяет username/password через cascade authentication (local → LDAP)
    2. Генерирует access и refresh токены
    3. Логирует событие в audit log

    **Args**:
    - **username**: Имя пользователя
    - **password**: Пароль

    **Returns**:
    - **access_token**: JWT токен для доступа (30 минут)
    - **refresh_token**: JWT токен для обновления (7 дней)
    - **token_type**: Тип токена (bearer)
    - **expires_in**: Время жизни access токена в секундах
    - **user**: Информация о пользователе

    **Errors**:
    - **401**: Неверные credentials
    """
    # Аутентификация через auth service
    user, auth_method = await auth_service.authenticate(
        db, credentials.username, credentials.password
    )

    if user is None:
        # Логируем неудачную попытку входа
        await audit_service.log_action(
            db=db,
            user_id=None,
            username=credentials.username,
            action="login_failed",
            resource_type="auth",
            resource_id=None,
            details={"username": credentials.username, "method": auth_method},
            success=False,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверное имя пользователя или пароль",
        )

    # Генерируем токены
    access_token = create_access_token(
        data={"sub": str(user.id), "username": user.username, "is_admin": user.is_admin},
        access_token_expire_minutes=settings.auth.jwt.access_token_expire_minutes,
        algorithm=settings.auth.jwt.algorithm,
        issuer=settings.auth.jwt.issuer,
    )

    refresh_token = create_refresh_token(
        data={"sub": str(user.id)},
        refresh_token_expire_days=settings.auth.jwt.refresh_token_expire_days,
        algorithm=settings.auth.jwt.algorithm,
        issuer=settings.auth.jwt.issuer,
    )

    # Логируем успешный вход
    await audit_service.log_action(
        db=db,
        user_id=user.id,
        username=user.username,
        action="login",
        resource_type="auth",
        resource_id=None,
        details={"method": auth_method},
        success=True,
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.auth.jwt.access_token_expire_minutes * 60,
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "last_name": user.last_name,
            "first_name": user.first_name,
            "middle_name": user.middle_name,
            "is_admin": user.is_admin,
            "is_active": user.is_active,
            "auth_provider": user.auth_provider,
        },
    }


@router.post(
    "/refresh", response_model=AccessTokenResponse, status_code=status.HTTP_200_OK
)
async def refresh_token(
    request: RefreshTokenRequest, db: AsyncSession = Depends(deps.get_db)
) -> Dict[str, Any]:
    """
    Обновление access токена используя refresh токен.

    **Args**:
    - **refresh_token**: Refresh токен

    **Returns**:
    - **access_token**: Новый JWT access токен
    - **token_type**: bearer

    **Errors**:
    - **401**: Невалидный refresh токен
    """
    try:
        payload = decode_token(
            request.refresh_token,
            algorithm=settings.auth.jwt.algorithm,
            issuer=settings.auth.jwt.issuer,
        )
        user_id: str = payload.get("sub")

        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Невалидный refresh токен",
            )

        # Проверяем, что пользователь существует и активен
        user = await user_service.get_user_by_id(db, user_id)
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Пользователь не найден или неактивен",
            )

        # Генерируем новый access token
        access_token = create_access_token(
            data={"sub": str(user.id), "username": user.username, "is_admin": user.is_admin},
            access_token_expire_minutes=settings.auth.jwt.access_token_expire_minutes,
            algorithm=settings.auth.jwt.algorithm,
            issuer=settings.auth.jwt.issuer,
        )

        return {"access_token": access_token, "token_type": "bearer"}

    except Exception as e:
        logger.error(f"Ошибка обновления токена: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Невалидный refresh токен"
        )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db),
):
    """
    Выход пользователя из системы.

    **Note**: В JWT архитектуре logout - это client-side операция.
    Сервер только логирует событие для audit trail.

    **Errors**:
    - **401**: Не аутентифицирован
    """
    await audit_service.log_action(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        action="logout",
        resource_type="auth",
        resource_id=None,
        details={},
        success=True,
    )
    return None


@router.get("/me", response_model=UserInfo, status_code=status.HTTP_200_OK)
async def get_current_user_info(
    current_user: User = Depends(deps.get_current_user),
) -> Dict[str, Any]:
    """
    Получение информации о текущем аутентифицированном пользователе.

    **Returns**:
    - Информация о пользователе

    **Errors**:
    - **401**: Не аутентифицирован
    """
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "last_name": current_user.last_name,
        "first_name": current_user.first_name,
        "middle_name": current_user.middle_name,
        "is_admin": current_user.is_admin,
        "is_active": current_user.is_active,
        "auth_provider": current_user.auth_provider,
    }


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db),
):
    """
    Изменение пароля текущего пользователя.

    **Args**:
    - **current_password**: Текущий пароль
    - **new_password**: Новый пароль

    **Errors**:
    - **400**: Неверный старый пароль или слабый новый пароль
    - **401**: Не аутентифицирован
    - **403**: Нельзя изменить пароль для external auth провайдеров
    """
    # Проверяем, что это локальный пользователь
    if current_user.auth_provider != "local":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Невозможно изменить пароль для внешней аутентификации",
        )

    # Меняем пароль через сервис
    success = await user_service.change_password(
        db, current_user.id, request.current_password, request.new_password
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Неверный текущий пароль"
        )

    # Логируем изменение пароля
    await audit_service.log_action(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        action="password_changed",
        resource_type="user",
        resource_id=current_user.id,
        details={},
        success=True,
    )

    return None
