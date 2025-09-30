"""
Импорт всех моделей для Alembic миграций.

Этот файл необходим для автоматического обнаружения моделей Alembic'ом.
Все модели должны быть импортированы здесь.
"""

# Импорт Base из session (необходимо для миграций)
from app.db.session import Base  # noqa: F401

# Импорт всех моделей
from app.db.models.audit_log import AuditLog  # noqa: F401
from app.db.models.storage_element import StorageElement, StorageMode  # noqa: F401
from app.db.models.user import User  # noqa: F401

# Экспорт для удобства
__all__ = [
    "Base",
    "User",
    "StorageElement",
    "StorageMode",
    "AuditLog",
]
