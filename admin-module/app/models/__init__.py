"""
Models для Admin Module.

Sprint 15: Добавлены модели для retention policy и lifecycle management:
- File: Центральный реестр файлов с retention_policy
- FileFinalizeTransaction: Лог Two-Phase Commit транзакций
- FileCleanupQueue: Очередь для Garbage Collection
"""

from .base import Base, TimestampMixin
from .admin_user import AdminUser, AdminRole
from .storage_element import StorageElement, StorageMode, StorageType, StorageStatus
from .service_account import ServiceAccount, ServiceAccountRole, ServiceAccountStatus
from .jwt_key import JWTKey
from .audit_log import AuditLog
# Sprint 15: Retention Policy & Lifecycle
from .file import File, RetentionPolicy
from .finalize_transaction import FileFinalizeTransaction, FinalizeTransactionStatus
from .cleanup_queue import FileCleanupQueue, CleanupReason, CleanupPriority

__all__ = [
    # Base
    "Base",
    "TimestampMixin",
    # Admin User (Admin UI authentication)
    "AdminUser",
    "AdminRole",
    # Storage Element
    "StorageElement",
    "StorageMode",
    "StorageType",
    "StorageStatus",
    # Service Account
    "ServiceAccount",
    "ServiceAccountRole",
    "ServiceAccountStatus",
    # JWT Key Rotation
    "JWTKey",
    # Audit Logging
    "AuditLog",
    # Sprint 15: File Registry & Lifecycle
    "File",
    "RetentionPolicy",
    "FileFinalizeTransaction",
    "FinalizeTransactionStatus",
    "FileCleanupQueue",
    "CleanupReason",
    "CleanupPriority",
]
