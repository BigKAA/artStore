from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app import services
from app.core.config import settings
from app.core import security
from app.db import session
from app.models.token import Token

router = APIRouter()

from app.services.auth_strategy import get_auth_strategy

@router.post("/login", response_model=Token)
async def login_for_access_token(
    db: AsyncSession = Depends(session.get_db), form_data: OAuth2PasswordRequestForm = Depends()
) -> Any:
    """
    OAuth2-совместимый эндпоинт для получения access token.
    Использует композитную стратегию аутентификации, указанную в конфигурации.
    """
    auth_strategy = get_auth_strategy(settings.AUTH_PROVIDERS)
    user = await auth_strategy.authenticate(
        db, username=form_data.username, password=form_data.password
    )
    if not user:
        raise HTTPException(
            status_code=400,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        user.id, expires_delta=access_token_expires
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
    }