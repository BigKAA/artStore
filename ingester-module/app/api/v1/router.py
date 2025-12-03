"""
Ingester Module - API v1 Router.

Главный router для API версии 1.

Sprint 15: Добавлен finalize router для Two-Phase Commit финализации файлов.
Sprint 16: Health router перенесён на /health (без /api/v1 prefix) для консистентности.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import upload, finalize

# Создание главного router для API v1
api_router = APIRouter()

# Sprint 16: Health router подключается в main.py на /health (стандарт системы)
# НЕ включаем здесь чтобы избежать дублирования путей

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
