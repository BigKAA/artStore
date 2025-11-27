"""
API v1 Router - объединение всех endpoints.

Структура:
- /info - информация о storage element для auto-discovery
- /files - файловые операции (upload, download, search, delete)
- /admin - административные операции (в будущем)
- /health - health checks (в main.py)
"""

from fastapi import APIRouter

from app.api.v1.endpoints import files, info

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

# TODO: Подключить admin endpoints когда будут созданы
# from app.api.v1.endpoints import admin
# router.include_router(
#     admin.router,
#     prefix="/admin",
#     tags=["admin"]
# )
