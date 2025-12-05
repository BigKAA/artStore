"""
Capacity Service - получение информации о capacity Storage Element.

Поддержка:
- Local filesystem (os.statvfs)
- S3-совместимые хранилища (soft limit из конфигурации)
"""

import logging
import os
from typing import Dict

import aioboto3
from botocore.exceptions import ClientError

from app.core.config import settings, StorageType
from app.core.exceptions import StorageException

logger = logging.getLogger(__name__)


class CapacityService:
    """
    Service для получения capacity информации Storage Element.

    Поддерживает различные типы storage backends:
    - Local filesystem: os.statvfs() для реального disk usage
    - S3/MinIO: вычисление размера bucket + soft limit
    """

    async def get_capacity_info(self) -> Dict[str, int | float]:
        """
        Получить capacity информацию в зависимости от storage backend.

        Returns:
            dict: {
                "total": int,         # Общий размер в байтах
                "used": int,          # Использованный размер
                "available": int,     # Доступный размер
                "percent_used": float # Процент использования
            }

        Raises:
            StorageException: Ошибка получения capacity информации
        """
        if settings.storage.type == StorageType.LOCAL:
            return await self._get_local_fs_capacity()
        elif settings.storage.type == StorageType.S3:
            return await self._get_s3_capacity()
        else:
            raise StorageException(
                message=f"Unsupported storage backend: {settings.storage.type}",
                error_code="UNSUPPORTED_BACKEND",
            )

    async def _get_local_fs_capacity(self) -> Dict[str, int | float]:
        """
        Получить capacity для local filesystem.

        Использует os.statvfs() для получения реального disk usage.

        Returns:
            dict: Capacity информация
        """
        try:
            storage_path = settings.storage.local.base_path
            stat = os.statvfs(storage_path)

            # Вычисляем размеры
            total = stat.f_blocks * stat.f_frsize
            available = stat.f_bavail * stat.f_frsize
            used = total - available

            percent_used = round((used / total) * 100, 2) if total > 0 else 0.0

            logger.debug(
                "Local filesystem capacity calculated",
                extra={
                    "storage_path": str(storage_path),
                    "total_bytes": total,
                    "used_bytes": used,
                    "available_bytes": available,
                    "percent_used": percent_used,
                },
            )

            return {
                "total": total,
                "used": used,
                "available": available,
                "percent_used": percent_used,
            }

        except OSError as e:
            logger.error(
                "Failed to get local filesystem capacity",
                extra={"storage_path": str(storage_path), "error": str(e)},
            )
            raise StorageException(
                message=f"Failed to get filesystem capacity: {e}",
                error_code="CAPACITY_CHECK_FAILED",
            )

    async def _get_s3_capacity(self) -> Dict[str, int | float]:
        """
        Получить capacity для S3/MinIO хранилища.

        S3 не имеет традиционного "capacity" (практически unlimited).
        Используем:
        - Вычисление текущего размера bucket через list_objects_v2
        - max_size из конфигурации как "total capacity" (унифицированный параметр)

        Returns:
            dict: Capacity информация
        """
        try:
            # Унифицированный max_size из конфигурации (в байтах)
            # Заменяет deprecated soft_capacity_limit
            max_capacity = settings.storage.max_size

            # Вычисляем текущий размер bucket
            total_size = await self._calculate_s3_bucket_size()

            available = max(max_capacity - total_size, 0)
            percent_used = round((total_size / max_capacity) * 100, 2) if max_capacity > 0 else 0.0

            logger.debug(
                "S3 capacity calculated",
                extra={
                    "bucket": settings.storage.s3.bucket_name,
                    "max_capacity_bytes": max_capacity,
                    "used_bytes": total_size,
                    "available_bytes": available,
                    "percent_used": percent_used,
                },
            )

            return {
                "total": max_capacity,
                "used": total_size,
                "available": available,
                "percent_used": percent_used,
            }

        except Exception as e:
            logger.error(
                "Failed to get S3 capacity",
                extra={
                    "bucket": settings.storage.s3.bucket_name,
                    "error": str(e),
                },
            )
            raise StorageException(
                message=f"Failed to get S3 capacity: {e}",
                error_code="CAPACITY_CHECK_FAILED",
            )

    async def _calculate_s3_bucket_size(self) -> int:
        """
        Вычислить текущий размер S3 bucket.

        Использует list_objects_v2 для суммирования размеров всех объектов.

        Returns:
            int: Общий размер всех объектов в bucket (байты)

        Note:
            Для больших buckets (> 100K объектов) может быть медленным.
            Рекомендуется кеширование результата или использование CloudWatch metrics.
        """
        session = aioboto3.Session()
        total_size = 0

        async with session.client(
            "s3",
            endpoint_url=settings.storage.s3.endpoint_url,
            aws_access_key_id=settings.storage.s3.access_key_id,
            aws_secret_access_key=settings.storage.s3.secret_access_key,
        ) as s3_client:
            # Pagination для больших buckets
            paginator = s3_client.get_paginator("list_objects_v2")

            # Учитываем prefix из конфигурации (например, "app/")
            prefix = settings.storage.s3.app_folder or ""

            async for page in paginator.paginate(
                Bucket=settings.storage.s3.bucket_name,
                Prefix=prefix,
            ):
                if "Contents" in page:
                    for obj in page["Contents"]:
                        total_size += obj.get("Size", 0)

        logger.debug(
            "S3 bucket size calculated",
            extra={
                "bucket": settings.storage.s3.bucket_name,
                "prefix": prefix,
                "total_size_bytes": total_size,
            },
        )

        return total_size


# FastAPI dependency для injection
async def get_capacity_service() -> CapacityService:
    """
    FastAPI dependency для получения CapacityService.

    Returns:
        CapacityService: Instance capacity service
    """
    return CapacityService()
