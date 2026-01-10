"""
Storage Backends для Cache Rebuild Service.
"""

from app.services.storage_backends.base import StorageBackend, AttrFileInfo
from app.services.storage_backends.s3_backend import S3Backend
from app.services.storage_backends.local_backend import LocalBackend
from app.core.config import settings, StorageType


def get_storage_backend() -> StorageBackend:
    """
    Factory function для получения storage backend по конфигурации.

    Returns:
        StorageBackend: S3Backend или LocalBackend в зависимости от настроек
    """
    if settings.storage.type == StorageType.S3:
        return S3Backend()
    else:
        return LocalBackend()


__all__ = [
    'StorageBackend',
    'AttrFileInfo',
    'S3Backend',
    'LocalBackend',
    'get_storage_backend'
]
