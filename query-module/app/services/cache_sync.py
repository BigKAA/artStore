"""
Cache Sync Service для Query Module.

PHASE 2/3: Sprint 16 - Query Module Sync Repair.

CacheSyncService отвечает за обновление file_metadata_cache таблицы
при получении events от Admin Module через Redis Pub/Sub.

Архитектура:
- EventSubscriber получает events → CacheSyncService обрабатывает → PostgreSQL cache
- Операции: INSERT (file:created), UPDATE (file:updated), DELETE (file:deleted)
- Idempotent operations с ON CONFLICT DO UPDATE
"""

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select, delete, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db_session
from app.db.models import FileMetadata
from app.schemas.events import FileMetadataEvent, FileCreatedEvent, FileUpdatedEvent, FileDeletedEvent

logger = logging.getLogger(__name__)


class CacheSyncService:
    """
    Сервис синхронизации cache при получении events.

    Обрабатывает:
    - file:created → INSERT или UPDATE метаданных
    - file:updated → UPDATE метаданных
    - file:deleted → DELETE (soft или hard) метаданных

    Usage:
        service = CacheSyncService()
        await service.handle_file_created(event)
    """

    async def handle_file_created(
        self,
        event: FileCreatedEvent,
    ) -> bool:
        """
        Обработка file:created event.

        Вставка новых метаданных в cache или обновление существующих (idempotent).

        Args:
            event: Event с метаданными созданного файла

        Returns:
            bool: True если успешно обработано, False при ошибке

        Example:
            success = await service.handle_file_created(event)
        """
        try:
            async for session in get_db_session():
                metadata = event.metadata

                # Получаем storage_element_url (будет добавлено в следующем спринте)
                # TODO: Service Discovery для получения URL Storage Element
                storage_element_url = f"http://storage-element-{event.storage_element_id}:8010"

                # Используем PostgreSQL INSERT ... ON CONFLICT DO UPDATE (upsert)
                stmt = insert(FileMetadata).values(
                    id=str(event.file_id),
                    filename=metadata.original_filename,
                    storage_filename=metadata.storage_filename,
                    file_size=metadata.file_size,
                    mime_type=metadata.content_type,
                    sha256_hash=metadata.checksum_sha256,
                    username=metadata.uploaded_by,
                    tags=metadata.tags,
                    description=metadata.description,
                    storage_element_id=str(event.storage_element_id),
                    storage_element_url=storage_element_url,
                    created_at=metadata.created_at,
                    updated_at=metadata.updated_at or datetime.utcnow(),
                    cache_updated_at=datetime.utcnow(),
                ).on_conflict_do_update(
                    index_elements=['id'],  # Primary key
                    set_={
                        'filename': metadata.original_filename,
                        'storage_filename': metadata.storage_filename,
                        'file_size': metadata.file_size,
                        'mime_type': metadata.content_type,
                        'sha256_hash': metadata.checksum_sha256,
                        'username': metadata.uploaded_by,
                        'tags': metadata.tags,
                        'description': metadata.description,
                        'storage_element_id': str(event.storage_element_id),
                        'storage_element_url': storage_element_url,
                        'updated_at': metadata.updated_at or datetime.utcnow(),
                        'cache_updated_at': datetime.utcnow(),
                    }
                )

                await session.execute(stmt)
                await session.commit()

                logger.info(
                    "Cache synced for file:created event",
                    extra={
                        "file_id": str(event.file_id),
                        "original_filename": metadata.original_filename,
                        "storage_element_id": event.storage_element_id,
                    }
                )

                return True

        except Exception as e:
            logger.error(
                "Failed to sync cache for file:created event",
                extra={
                    "file_id": str(event.file_id),
                    "error": str(e),
                },
                exc_info=True
            )
            return False

    async def handle_file_updated(
        self,
        event: FileUpdatedEvent,
    ) -> bool:
        """
        Обработка file:updated event.

        Обновление существующих метаданных в cache.

        Args:
            event: Event с обновленными метаданными файла

        Returns:
            bool: True если успешно обработано, False при ошибке
        """
        try:
            async for session in get_db_session():
                metadata = event.metadata

                # Получаем storage_element_url
                storage_element_url = f"http://storage-element-{event.storage_element_id}:8010"

                # UPDATE метаданных
                stmt = update(FileMetadata).where(
                    FileMetadata.id == str(event.file_id)
                ).values(
                    filename=metadata.original_filename,
                    storage_filename=metadata.storage_filename,
                    file_size=metadata.file_size,
                    mime_type=metadata.content_type,
                    sha256_hash=metadata.checksum_sha256,
                    username=metadata.uploaded_by,
                    tags=metadata.tags,
                    description=metadata.description,
                    storage_element_id=str(event.storage_element_id),
                    storage_element_url=storage_element_url,
                    updated_at=metadata.updated_at or datetime.utcnow(),
                    cache_updated_at=datetime.utcnow(),
                )

                result = await session.execute(stmt)
                await session.commit()

                if result.rowcount == 0:
                    logger.warning(
                        "File not found in cache for file:updated event",
                        extra={
                            "file_id": str(event.file_id),
                            "storage_element_id": event.storage_element_id,
                        }
                    )
                    # Если файл не найден, вставляем его (recovery scenario)
                    return await self.handle_file_created(
                        FileCreatedEvent(
                            file_id=event.file_id,
                            storage_element_id=event.storage_element_id,
                            metadata=metadata,
                        )
                    )

                logger.info(
                    "Cache synced for file:updated event",
                    extra={
                        "file_id": str(event.file_id),
                        "original_filename": metadata.original_filename,
                        "storage_element_id": event.storage_element_id,
                    }
                )

                return True

        except Exception as e:
            logger.error(
                "Failed to sync cache for file:updated event",
                extra={
                    "file_id": str(event.file_id),
                    "error": str(e),
                },
                exc_info=True
            )
            return False

    async def handle_file_deleted(
        self,
        event: FileDeletedEvent,
    ) -> bool:
        """
        Обработка file:deleted event.

        Hard delete метаданных из cache (Query Module не нуждается в soft delete).

        Args:
            event: Event с информацией об удаленном файле

        Returns:
            bool: True если успешно обработано, False при ошибке
        """
        try:
            async for session in get_db_session():
                # Hard DELETE из cache
                stmt = delete(FileMetadata).where(
                    FileMetadata.id == str(event.file_id)
                )

                result = await session.execute(stmt)
                await session.commit()

                if result.rowcount == 0:
                    logger.warning(
                        "File not found in cache for file:deleted event",
                        extra={
                            "file_id": str(event.file_id),
                            "storage_element_id": event.storage_element_id,
                        }
                    )
                else:
                    logger.info(
                        "Cache synced for file:deleted event",
                        extra={
                            "file_id": str(event.file_id),
                            "storage_element_id": event.storage_element_id,
                        }
                    )

                return True

        except Exception as e:
            logger.error(
                "Failed to sync cache for file:deleted event",
                extra={
                    "file_id": str(event.file_id),
                    "error": str(e),
                },
                exc_info=True
            )
            return False


# Глобальный экземпляр CacheSyncService
cache_sync_service = CacheSyncService()
