"""
API v1 Router - объединение всех endpoints.

Структура:
- /info - информация о storage element для auto-discovery
- /files - файловые операции (upload, download, search, delete)
- /gc - системные операции для Garbage Collector (только service accounts)
- /admin - административные операции (в будущем)
- /health - health checks (в main.py)
"""

from fastapi import APIRouter

from app.api.v1.endpoints import files, info, gc, capacity

# Создание главного router для API v1
router = APIRouter()

# Подключение info endpoint для auto-discovery
router.include_router(
    info.router,
    prefix="/info",
    tags=["info"]
)

# Подключение files endpoints
router.include_router(
    files.router,
    prefix="/files",
    tags=["files"]
)

# Подключение GC endpoints для Garbage Collector (Sprint 16)
# Доступны только для Service Accounts
router.include_router(
    gc.router,
    prefix="/gc",
    tags=["gc"]
)

# Подключение capacity endpoint для мониторинга (Sprint N+1)
# Доступен без аутентификации для adaptive polling
router.include_router(
    capacity.router,
    tags=["capacity"]
)

# TODO: Подключить admin endpoints когда будут созданы
# from app.api.v1.endpoints import admin
# router.include_router(
#     admin.router,
#     prefix="/admin",
#     tags=["admin"]
# )
