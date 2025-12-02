"""
API Dependencies.

-:A?>@B 2A5E FastAPI dependencies 4;O C4>1=>3> 8<?>@B0.
"""

from app.api.deps.auth import (
    AdminUser,
    CurrentUser,
    OperatorUser,
    ServiceAccount,
    get_current_user,
    require_admin,
    require_operator_or_admin,
    require_service_account,
)
from app.api.deps.database import get_db

__all__ = [
    "get_current_user",
    "require_admin",
    "require_operator_or_admin",
    "require_service_account",
    "get_db",
    "CurrentUser",
    "AdminUser",
    "OperatorUser",
    "ServiceAccount",
]
