"""
Ingester Module - API v1 Router.

Главный router для API версии 1.

Sprint 15: Добавлен finalize router для Two-Phase Commit финализации файлов.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import health, upload, finalize

# Создание главного router для API v1
api_router = APIRouter()

# Подключение endpoints
api_router.include_router(
    health.router,
    prefix="/health",
    tags=["health"]
)

api_router.include_router(
    upload.router,
    prefix="/files",
    tags=["upload"]
)

# Sprint 15: Finalize endpoint для Two-Phase Commit
api_router.include_router(
    finalize.router,
    prefix="/finalize",
    tags=["finalize"]
)
