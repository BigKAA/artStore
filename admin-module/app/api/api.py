"""
Главный API роутер, объединяющий все endpoints.
"""
from fastapi import APIRouter

from app.api.endpoints import auth, health, storage_elements, users

# Создаем главный роутер
api_router = APIRouter()

# Включаем роутеры для разных групп endpoints

# Health checks и metrics (без префикса /api)
api_router.include_router(
    health.router,
    prefix="/health",
    tags=["health"],
)

# Authentication endpoints
api_router.include_router(
    auth.router,
    prefix="/auth",
    tags=["authentication"],
)

# User management endpoints
api_router.include_router(
    users.router,
    prefix="/users",
    tags=["users"],
)

# Storage elements management endpoints
api_router.include_router(
    storage_elements.router,
    prefix="/storage-elements",
    tags=["storage-elements"],
)
